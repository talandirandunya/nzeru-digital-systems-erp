from django.db import transaction as db_transaction
from django.utils import timezone

from finance.models import JournalEntry, JournalEntryLine, MarketplaceFinanceSettings, Transaction

from .models import Order


class MarketplaceFinancePostingError(Exception):
    """Raised when a marketplace order cannot be posted into finance."""


def _account_delta_from_journal_line(account, debit, credit):
    """Translate a journal line into a signed balance effect for this app's account balance model."""
    if account.account_type in ('asset', 'expense'):
        return debit - credit
    return credit - debit


def _create_balance_transaction(company, account, debit, credit, description, date, user):
    """Mirror a journal line into the simpler Transaction ledger used by dashboards and balances."""
    delta = _account_delta_from_journal_line(account, debit, credit)
    if delta == 0:
        return None

    return Transaction.objects.create(
        company=company,
        account=account,
        transaction_type='credit' if delta > 0 else 'debit',
        amount=abs(delta),
        description=description,
        date=date,
        entered_by=user,
    )


def reset_order_finance_sync(order):
    """Reset sync state when payment is no longer marked as paid."""
    Order.objects.filter(pk=order.pk).update(
        finance_sync_status='pending',
        finance_reversal_journal_entry=None,
        finance_sync_error='',
        finance_synced_at=None,
        finance_reversed_at=None,
    )


def mark_order_finance_sync_failed(order, message):
    """Persist a sync failure without creating accounting entries."""
    Order.objects.filter(pk=order.pk).update(
        finance_sync_status='failed',
        finance_sync_error=message[:1000],
        finance_synced_at=None,
        finance_reversed_at=None,
    )


def set_order_finance_sync_error(order, message):
    """Record a finance sync error without changing posted/reversed state."""
    Order.objects.filter(pk=order.pk).update(
        finance_sync_error=message[:1000],
    )


def post_order_payment_to_finance(order, user=None):
    """Create a balanced journal entry for a paid marketplace order."""
    with db_transaction.atomic():
        order = (
            Order.objects.select_for_update(of=('self',))
            .select_related(
                'company',
                'client',
                'finance_journal_entry',
            )
            .get(pk=order.pk)
        )

        if order.finance_journal_entry_id:
            return order.finance_journal_entry, False

        if order.payment_status != 'paid':
            raise MarketplaceFinancePostingError('Only paid orders can be posted to finance.')

        try:
            finance_settings = MarketplaceFinanceSettings.objects.select_related(
                'sales_journal',
                'receivable_account',
                'revenue_account',
                'tax_account',
            ).get(company=order.company)
        except MarketplaceFinanceSettings.DoesNotExist as exc:
            raise MarketplaceFinancePostingError(
                f'Marketplace finance settings are not configured for {order.company.name}.'
            ) from exc

        if not finance_settings.is_enabled:
            raise MarketplaceFinancePostingError(
                f'Marketplace finance posting is disabled for {order.company.name}.'
            )

        tax_amount = order.tax
        revenue_amount = order.subtotal + order.shipping
        if tax_amount and not finance_settings.tax_account_id:
            revenue_amount += tax_amount

        entry = JournalEntry.objects.create(
            company=order.company,
            journal=finance_settings.sales_journal,
            reference=order.order_number,
            description=f'Marketplace order {order.order_number} for {order.client.get_full_name()}',
            date=timezone.localdate(),
            entered_by=user,
        )

        JournalEntryLine.objects.create(
            entry=entry,
            account=finance_settings.receivable_account,
            description=f'Receivable for marketplace order {order.order_number}',
            debit=order.total,
            credit=0,
        )
        _create_balance_transaction(
            company=order.company,
            account=finance_settings.receivable_account,
            debit=order.total,
            credit=0,
            description=f'Marketplace receivable for order {order.order_number}',
            date=entry.date,
            user=user,
        )

        if revenue_amount > 0:
            JournalEntryLine.objects.create(
                entry=entry,
                account=finance_settings.revenue_account,
                description=f'Revenue for marketplace order {order.order_number}',
                debit=0,
                credit=revenue_amount,
            )
            _create_balance_transaction(
                company=order.company,
                account=finance_settings.revenue_account,
                debit=0,
                credit=revenue_amount,
                description=f'Marketplace revenue for order {order.order_number}',
                date=entry.date,
                user=user,
            )

        if tax_amount and finance_settings.tax_account_id:
            JournalEntryLine.objects.create(
                entry=entry,
                account=finance_settings.tax_account,
                description=f'Tax for marketplace order {order.order_number}',
                debit=0,
                credit=tax_amount,
            )
            _create_balance_transaction(
                company=order.company,
                account=finance_settings.tax_account,
                debit=0,
                credit=tax_amount,
                description=f'Marketplace tax for order {order.order_number}',
                date=entry.date,
                user=user,
            )

        order.finance_journal_entry = entry
        order.finance_sync_status = 'posted'
        order.finance_reversal_journal_entry = None
        order.finance_sync_error = ''
        order.finance_synced_at = timezone.now()
        order.finance_reversed_at = None
        order.save(update_fields=[
            'finance_journal_entry',
            'finance_reversal_journal_entry',
            'finance_sync_status',
            'finance_sync_error',
            'finance_synced_at',
            'finance_reversed_at',
            'updated_at',
        ])

        return entry, True


def reverse_order_payment_in_finance(order, user=None, reason=''):
    """Create a reversing journal entry for an already-posted marketplace order."""
    with db_transaction.atomic():
        order = (
            Order.objects.select_for_update(of=('self',))
            .select_related(
                'company',
                'client',
                'finance_journal_entry',
                'finance_reversal_journal_entry',
            )
            .get(pk=order.pk)
        )

        if order.finance_reversal_journal_entry_id:
            return order.finance_reversal_journal_entry, False

        if not order.finance_journal_entry_id:
            raise MarketplaceFinancePostingError('This order has no posted finance entry to reverse.')

        original_entry = (
            JournalEntry.objects.select_related('journal')
            .prefetch_related('lines__account')
            .get(pk=order.finance_journal_entry_id)
        )

        reversal_entry = JournalEntry.objects.create(
            company=order.company,
            journal=original_entry.journal,
            reference=f'REV-{order.order_number}',
            description=(
                f'Reversal of marketplace order {order.order_number}'
                + (f' ({reason})' if reason else '')
            ),
            date=timezone.localdate(),
            entered_by=user,
        )

        for line in original_entry.lines.all():
            JournalEntryLine.objects.create(
                entry=reversal_entry,
                account=line.account,
                description=f'Reversal for {order.order_number}',
                debit=line.credit,
                credit=line.debit,
            )
            _create_balance_transaction(
                company=order.company,
                account=line.account,
                debit=line.credit,
                credit=line.debit,
                description=f'Reversal for marketplace order {order.order_number}',
                date=reversal_entry.date,
                user=user,
            )

        order.finance_reversal_journal_entry = reversal_entry
        order.finance_sync_status = 'reversed'
        order.finance_sync_error = ''
        order.finance_reversed_at = timezone.now()
        order.save(update_fields=[
            'finance_reversal_journal_entry',
            'finance_sync_status',
            'finance_sync_error',
            'finance_reversed_at',
            'updated_at',
        ])

        return reversal_entry, True
