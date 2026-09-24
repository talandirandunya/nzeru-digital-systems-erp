from decimal import Decimal

from django.core.exceptions import ValidationError
from django.db import transaction
from django.db.models import Sum
from django.utils import timezone

from finance.models import Account, Journal, JournalEntry, JournalEntryLine
from governance.models import AuditEvent
from inventory.models import InventoryBatch, Stock, StockTransaction

from .models import GoodsReceipt, GoodsReceiptLine, PurchaseOrder


@transaction.atomic
def receive_goods(*, order, received_by, receipt_number, quantities, notes=''):
    order = PurchaseOrder.objects.select_for_update().select_related('company').get(pk=order.pk)
    if order.status not in ('approved', 'partially_received'):
        raise ValidationError('Only approved purchase orders can receive goods.')
    receipt = GoodsReceipt.objects.create(order=order, received_by=received_by, receipt_number=receipt_number, notes=notes)
    total_ordered = 0
    total_received = 0
    receipt_cost_total = Decimal('0')

    company = order.company
    inventory_asset_account = company.accounts.filter(account_type='asset', name__icontains='inventory').first()
    if not inventory_asset_account:
        inventory_asset_account = company.accounts.create(name='Inventory Asset', code='INV-001', account_type='asset', balance=0)
    payable_account = company.accounts.filter(account_type='liability', name__icontains='payable').first()
    if not payable_account:
        payable_account = company.accounts.create(name='Accounts Payable', code='AP-001', account_type='liability', balance=0)
    purchase_journal = company.journals.filter(journal_type='purchases').first() or company.journals.filter(journal_type='general').first()
    if not purchase_journal:
        purchase_journal = company.journals.create(name='Purchases', code='PUR', journal_type='purchases')

    accrual_entry = JournalEntry.objects.create(
        company=company,
        journal=purchase_journal,
        reference=f'GR-{receipt.receipt_number}',
        description=f'Goods receipt {receipt.receipt_number}',
        date=timezone.localdate(),
        entered_by=received_by,
    )

    for line in order.lines.select_for_update().select_related('stock'):
        quantity = int(quantities.get(str(line.pk), 0) or 0)
        already_received = line.receipt_lines.aggregate(total=Sum('quantity'))['total'] or 0
        if quantity < 0 or already_received + quantity > line.ordered_quantity:
            raise ValidationError(f'Receipt exceeds ordered quantity for {line.stock.name}.')
        total_ordered += line.ordered_quantity
        total_received += already_received + quantity
        if quantity:
            stock = Stock.objects.select_for_update().get(pk=line.stock_id, company=order.company)
            purchase_cost = Decimal(str(line.unit_cost or 0))
            previous_qty = stock.quantity
            previous_cost = Decimal(str(stock.cost_price or 0))
            new_total_qty = previous_qty + quantity
            if new_total_qty:
                weighted_cost = ((Decimal(previous_qty) * previous_cost) + (Decimal(quantity) * purchase_cost)) / Decimal(new_total_qty)
            else:
                weighted_cost = purchase_cost
            stock.quantity = new_total_qty
            stock.cost_price = weighted_cost
            stock.last_restocked = timezone.localdate()
            stock.save(update_fields=['quantity', 'cost_price', 'last_restocked', 'updated_at'])

            batch_code = f"{receipt.receipt_number}-{line.pk}"
            InventoryBatch.objects.update_or_create(
                company=company,
                stock=stock,
                batch_code=batch_code,
                defaults={
                    'quantity': quantity,
                    'unit_cost': purchase_cost,
                    'supplier': order.supplier,
                },
            )

            GoodsReceiptLine.objects.create(receipt=receipt, order_line=line, quantity=quantity)
            StockTransaction.objects.create(
                company=order.company, stock=stock, transaction_type='in', quantity=quantity,
                remarks=f'Goods receipt {receipt.receipt_number}', user=received_by,
            )
            receipt_cost_total += Decimal(quantity) * purchase_cost

    if total_received == 0:
        raise ValidationError('At least one positive receipt quantity is required.')

    if receipt_cost_total > 0:
        JournalEntryLine.objects.create(
            entry=accrual_entry,
            account=inventory_asset_account,
            description=f'Inventory receipt {receipt.receipt_number}',
            debit=receipt_cost_total,
        )
        JournalEntryLine.objects.create(
            entry=accrual_entry,
            account=payable_account,
            description=f'AP accrual for {receipt.receipt_number}',
            credit=receipt_cost_total,
        )
        accrual_entry.post()

    order.status = 'received' if total_received >= total_ordered else 'partially_received'
    order.save(update_fields=['status'])
    AuditEvent.record(actor=received_by, company=order.company, module='procurement', action='goods_received', obj=receipt, after={'status': order.status, 'quantity': total_received})
    return receipt
