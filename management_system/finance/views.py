"""
finance/views.py — upgraded

Views:
  - index         : dashboard with stats, recent transactions, account balances
  - account_list  : searchable paginated list
  - account_detail: per-account transaction history + running balance
  - account_create / account_edit / account_delete
  - transaction_list  : filterable by account, type, date range + search
  - transaction_create / transaction_edit / transaction_delete
"""

from datetime import date, timedelta

from django.contrib import messages
from django.core.paginator import EmptyPage, PageNotAnInteger, Paginator
from django.db.models import Q, Sum
from django.shortcuts import get_object_or_404, redirect, render

from accounts.decorators import role_required
from governance.models import AuditEvent

from .forms import (
    AccountForm,
    TransactionForm,
    JournalEntryForm,
    JournalEntryLineFormSet,
    JournalForm,
    ClientInvoiceForm,
    SupplierInvoiceForm,
    ClientInvoiceLineFormSet,
    SupplierInvoiceLineFormSet,
    BankAccountForm,
    BankStatementUploadForm,
    ReconciliationForm,
    TransactionMatchingForm,
    FinancialReportForm,
    MarketplaceFinanceSettingsForm,
)
from .models import Account, Journal, JournalEntry, Transaction, ClientInvoice, SupplierInvoice, BankAccount, BankStatement, BankTransaction, Reconciliation, FinancialReport, ReportLine, MarketplaceFinanceSettings

FINANCE_ROLES = ('admin', 'accountant', 'manager')


# ---------------------------------------------------------------------------
# Dashboard
# ---------------------------------------------------------------------------

@role_required(*FINANCE_ROLES)
def index(request):
    company = request.user.company
    today = date.today()
    month_start = today.replace(day=1)

    accounts = Account.objects.filter(company=company)
    total_balance = accounts.aggregate(total=Sum('balance'))['total'] or 0

    txns = Transaction.objects.filter(company=company)
    total_credits = txns.filter(transaction_type='credit').aggregate(s=Sum('amount'))['s'] or 0
    total_debits  = txns.filter(transaction_type='debit').aggregate(s=Sum('amount'))['s'] or 0

    # This month
    month_txns = txns.filter(date__gte=month_start)
    month_credits = month_txns.filter(transaction_type='credit').aggregate(s=Sum('amount'))['s'] or 0
    month_debits  = month_txns.filter(transaction_type='debit').aggregate(s=Sum('amount'))['s'] or 0

    recent_txns = (
        txns
        .select_related('account', 'entered_by')
        .order_by('-date', '-created_at')[:10]
    )

    top_accounts = accounts.order_by('-balance')[:5]
    marketplace_finance_settings = MarketplaceFinanceSettings.objects.filter(company=company).first()

    context = {
        'total_balance': total_balance,
        'total_credits': total_credits,
        'total_debits': total_debits,
        'month_credits': month_credits,
        'month_debits': month_debits,
        'net_month': month_credits - month_debits,
        'account_count': accounts.count(),
        'recent_txns': recent_txns,
        'top_accounts': top_accounts,
        'today': today,
        'marketplace_finance_settings': marketplace_finance_settings,
    }
    return render(request, 'finance/index.html', context)


# ---------------------------------------------------------------------------
# Accounts
# ---------------------------------------------------------------------------

@role_required(*FINANCE_ROLES)
def account_list(request):
    company = request.user.company
    qs = Account.objects.filter(company=company)

    query = request.GET.get('q', '').strip()
    if query:
        qs = qs.filter(name__icontains=query)

    paginator = Paginator(qs.order_by('name'), 25)
    page = request.GET.get('page')
    try:
        accounts_page = paginator.page(page)
    except PageNotAnInteger:
        accounts_page = paginator.page(1)
    except EmptyPage:
        accounts_page = paginator.page(paginator.num_pages)

    total_balance = qs.aggregate(total=Sum('balance'))['total'] or 0

    return render(request, 'finance/account_list.html', {
        'accounts': accounts_page,
        'query': query,
        'total_balance': total_balance,
    })


@role_required(*FINANCE_ROLES)
def account_detail(request, pk):
    company = request.user.company
    acct = get_object_or_404(Account, pk=pk, company=company)

    txns = (
        Transaction.objects
        .filter(account=acct)
        .select_related('entered_by')
        .order_by('-date', '-created_at')
    )

    # Filters
    type_filter = request.GET.get('type', '').strip()
    if type_filter:
        txns = txns.filter(transaction_type=type_filter)

    date_from = request.GET.get('date_from', '').strip()
    date_to   = request.GET.get('date_to', '').strip()
    if date_from:
        txns = txns.filter(date__gte=date_from)
    if date_to:
        txns = txns.filter(date__lte=date_to)

    paginator = Paginator(txns, 25)
    page = request.GET.get('page')
    try:
        txns_page = paginator.page(page)
    except PageNotAnInteger:
        txns_page = paginator.page(1)
    except EmptyPage:
        txns_page = paginator.page(paginator.num_pages)

    credits = txns.filter(transaction_type='credit').aggregate(s=Sum('amount'))['s'] or 0
    debits  = txns.filter(transaction_type='debit').aggregate(s=Sum('amount'))['s'] or 0

    return render(request, 'finance/account_detail.html', {
        'account': acct,
        'transactions': txns_page,
        'credits': credits,
        'debits': debits,
        'type_filter': type_filter,
        'date_from': date_from,
        'date_to': date_to,
    })


@role_required(*FINANCE_ROLES)
def account_create(request):
    company = request.user.company
    if request.method == 'POST':
        form = AccountForm(request.POST, company=company)
        if form.is_valid():
            acct = form.save(commit=False)
            acct.company = company
            acct.save()
            messages.success(request, f'Account "{acct.name}" created.')
            return redirect('finance:account_list')
    else:
        form = AccountForm(company=company)
    return render(request, 'finance/account_form.html', {'form': form, 'title': 'New Account'})


@role_required(*FINANCE_ROLES)
def account_edit(request, pk):
    company = request.user.company
    acct = get_object_or_404(Account, pk=pk, company=company)
    if request.method == 'POST':
        form = AccountForm(request.POST, instance=acct, company=company)
        if form.is_valid():
            form.save()
            messages.success(request, f'Account "{acct.name}" updated.')
            return redirect('finance:account_list')
    else:
        form = AccountForm(instance=acct, company=company)
    return render(request, 'finance/account_form.html', {'form': form, 'title': 'Edit Account'})


@role_required(*FINANCE_ROLES)
def account_delete(request, pk):
    company = request.user.company
    acct = get_object_or_404(Account, pk=pk, company=company)
    if request.method == 'POST':
        name = acct.name
        acct.delete()
        messages.success(request, f'Account "{name}" deleted.')
        return redirect('finance:account_list')
    return render(request, 'finance/account_confirm_delete.html', {'account': acct})


# ---------------------------------------------------------------------------
# Transactions
# ---------------------------------------------------------------------------

@role_required(*FINANCE_ROLES)
def transaction_list(request):
    company = request.user.company
    qs = (
        Transaction.objects
        .filter(company=company)
        .select_related('account', 'entered_by')
        .order_by('-date', '-created_at')
    )

    # Filters
    account_filter = request.GET.get('account', '').strip()
    if account_filter:
        qs = qs.filter(account_id=account_filter)

    type_filter = request.GET.get('type', '').strip()
    if type_filter:
        qs = qs.filter(transaction_type=type_filter)

    date_from = request.GET.get('date_from', '').strip()
    date_to   = request.GET.get('date_to', '').strip()
    if date_from:
        qs = qs.filter(date__gte=date_from)
    if date_to:
        qs = qs.filter(date__lte=date_to)

    query = request.GET.get('q', '').strip()
    if query:
        qs = qs.filter(
            Q(description__icontains=query) |
            Q(account__name__icontains=query)
        )

    # Totals on filtered set
    credits = qs.filter(transaction_type='credit').aggregate(s=Sum('amount'))['s'] or 0
    debits  = qs.filter(transaction_type='debit').aggregate(s=Sum('amount'))['s'] or 0

    paginator = Paginator(qs, 25)
    page = request.GET.get('page')
    try:
        txns_page = paginator.page(page)
    except PageNotAnInteger:
        txns_page = paginator.page(1)
    except EmptyPage:
        txns_page = paginator.page(paginator.num_pages)

    accounts = Account.objects.filter(company=company).order_by('name')

    return render(request, 'finance/transaction_list.html', {
        'transactions': txns_page,
        'accounts': accounts,
        'account_filter': account_filter,
        'type_filter': type_filter,
        'date_from': date_from,
        'date_to': date_to,
        'query': query,
        'credits': credits,
        'debits': debits,
        'net': credits - debits,
    })


@role_required(*FINANCE_ROLES)
def transaction_create(request):
    company = request.user.company
    if request.method == 'POST':
        form = TransactionForm(request.POST, company=company)
        if form.is_valid():
            txn = form.save(commit=False)
            txn.company = company
            txn.entered_by = request.user
            txn.save()
            AuditEvent.record(actor=request.user, company=company, module='finance', action='transaction_created', obj=txn, after={'amount': str(txn.amount), 'type': txn.transaction_type}, request=request)
            messages.success(request, 'Transaction recorded.')
            return redirect('finance:transaction_list')
    else:
        form = TransactionForm(company=company)
    return render(request, 'finance/transaction_form.html', {
        'form': form, 'title': 'New Transaction'
    })


@role_required(*FINANCE_ROLES)
def transaction_edit(request, pk):
    company = request.user.company
    txn = get_object_or_404(Transaction, pk=pk, company=company)
    if request.method == 'POST':
        form = TransactionForm(request.POST, instance=txn, company=company)
        if form.is_valid():
            form.save()
            messages.success(request, 'Transaction updated.')
            return redirect('finance:transaction_list')
    else:
        form = TransactionForm(instance=txn, company=company)
    return render(request, 'finance/transaction_form.html', {
        'form': form, 'title': 'Edit Transaction'
    })


@role_required(*FINANCE_ROLES)
def transaction_delete(request, pk):
    company = request.user.company
    txn = get_object_or_404(Transaction, pk=pk, company=company)
    if request.method == 'POST':
        txn.delete()
        messages.success(request, 'Transaction deleted.')
        return redirect('finance:transaction_list')
    return render(request, 'finance/transaction_confirm_delete.html', {'transaction': txn})


@role_required(*FINANCE_ROLES)
def journal_list(request):
    company = request.user.company
    journals = Journal.objects.filter(company=company).order_by('journal_type', 'name')
    return render(request, 'finance/journal_list.html', {'journals': journals})


@role_required(*FINANCE_ROLES)
def journal_create(request):
    company = request.user.company
    if request.method == 'POST':
        form = JournalForm(request.POST, company=company)
        if form.is_valid():
            journal = form.save(commit=False)
            journal.company = company
            journal.save()
            messages.success(request, f'Journal "{journal.name}" created.')
            return redirect('finance:journal_list')
    else:
        form = JournalForm(company=company)
    return render(request, 'finance/journal_form.html', {'form': form, 'title': 'New Journal'})


@role_required(*FINANCE_ROLES)
def journal_entry_list(request):
    company = request.user.company
    entries = JournalEntry.objects.filter(company=company).select_related('journal').order_by('-date', '-created_at')
    return render(request, 'finance/journal_entry_list.html', {'entries': entries})


@role_required(*FINANCE_ROLES)
def journal_detail(request, pk):
    company = request.user.company
    journal = get_object_or_404(Journal, pk=pk, company=company)
    entries = journal.entries.all().select_related('entered_by').order_by('-date', '-created_at')
    return render(request, 'finance/journal_detail.html', {
        'journal': journal,
        'entries': entries,
    })


@role_required(*FINANCE_ROLES)
def journal_edit(request, pk):
    company = request.user.company
    journal = get_object_or_404(Journal, pk=pk, company=company)
    if request.method == 'POST':
        form = JournalForm(request.POST, instance=journal, company=company)
        if form.is_valid():
            form.save()
            messages.success(request, f'Journal "{journal.name}" updated.')
            return redirect('finance:journal_detail', pk=journal.pk)
    else:
        form = JournalForm(instance=journal, company=company)
    return render(request, 'finance/journal_form.html', {'form': form, 'title': 'Edit Journal'})


@role_required(*FINANCE_ROLES)
def journal_delete(request, pk):
    company = request.user.company
    journal = get_object_or_404(Journal, pk=pk, company=company)
    if request.method == 'POST':
        name = journal.name
        journal.delete()
        messages.success(request, f'Journal "{name}" deleted.')
        return redirect('finance:journal_list')
    return render(request, 'finance/journal_confirm_delete.html', {'journal': journal})


@role_required(*FINANCE_ROLES)
def journal_entry_create(request):
    company = request.user.company
    entry = JournalEntry(company=company)
    if request.method == 'POST':
        form = JournalEntryForm(request.POST, company=company, instance=entry)
        formset = JournalEntryLineFormSet(request.POST, instance=entry, company=company)
        if form.is_valid() and formset.is_valid():
            entry = form.save(commit=False)
            entry.company = company
            entry.entered_by = request.user
            entry.save()
            formset.instance = entry
            formset.save()
            messages.success(request, 'Journal entry recorded.')
            return redirect('finance:journal_entry_detail', pk=entry.pk)
    else:
        form = JournalEntryForm(company=company, instance=entry)
        formset = JournalEntryLineFormSet(instance=entry, company=company)
    return render(request, 'finance/journal_entry_form.html', {
        'form': form,
        'formset': formset,
        'title': 'New Journal Entry',
    })


@role_required(*FINANCE_ROLES)
def journal_entry_detail(request, pk):
    company = request.user.company
    entry = get_object_or_404(JournalEntry, pk=pk, company=company)
    lines = entry.lines.all().select_related('account').order_by('account')
    return render(request, 'finance/journal_entry_detail.html', {
        'entry': entry,
        'lines': lines,
    })


@role_required(*FINANCE_ROLES)
def journal_entry_edit(request, pk):
    company = request.user.company
    entry = get_object_or_404(JournalEntry, pk=pk, company=company)
    if request.method == 'POST':
        form = JournalEntryForm(request.POST, instance=entry, company=company)
        formset = JournalEntryLineFormSet(request.POST, instance=entry, company=company)
        if form.is_valid() and formset.is_valid():
            form.save()
            formset.save()
            messages.success(request, 'Journal entry updated.')
            return redirect('finance:journal_entry_detail', pk=entry.pk)
    else:
        form = JournalEntryForm(instance=entry, company=company)
        formset = JournalEntryLineFormSet(instance=entry, company=company)
    return render(request, 'finance/journal_entry_form.html', {
        'form': form,
        'formset': formset,
        'title': 'Edit Journal Entry',
    })


@role_required(*FINANCE_ROLES)
def journal_entry_delete(request, pk):
    company = request.user.company
    entry = get_object_or_404(JournalEntry, pk=pk, company=company)
    if request.method == 'POST':
        date_str = entry.date.strftime('%Y-%m-%d')
        entry.delete()
        messages.success(request, f'Journal entry from {date_str} deleted.')
        return redirect('finance:journal_entry_list')
    return render(request, 'finance/journal_entry_confirm_delete.html', {'entry': entry})


# ---------------------------------------------------------------------------
# Client Invoices (Phase 2)
# ---------------------------------------------------------------------------

@role_required(*FINANCE_ROLES)
def client_invoice_list(request):
    company = request.user.company
    invoices = ClientInvoice.objects.filter(company=company).select_related('created_by')
    return render(request, 'finance/client_invoice_list.html', {'invoices': invoices})


@role_required(*FINANCE_ROLES)
def client_invoice_create(request):
    company = request.user.company
    invoice = ClientInvoice(company=company)
    if request.method == 'POST':
        form = ClientInvoiceForm(request.POST, company=company, instance=invoice)
        formset = ClientInvoiceLineFormSet(request.POST, instance=invoice, company=company)
        if form.is_valid() and formset.is_valid():
            invoice = form.save(commit=False)
            invoice.company = company
            invoice.created_by = request.user
            invoice.save()
            formset.instance = invoice
            formset.save()
            invoice.calculate_totals()
            invoice.save()
            messages.success(request, f'Client invoice "{invoice.invoice_number}" created.')

            # Create notification for managers about new client invoice
            from notifications.utils import create_notification
            from django.contrib.auth import get_user_model
            User = get_user_model()

            # Notify managers and accountants about new invoice
            managers_and_accountants = User.objects.filter(
                company=company,
                role__in=['manager', 'accountant']
            ).exclude(pk=request.user.pk)  # Don't notify the creator

            for user in managers_and_accountants:
                create_notification(
                    user=user,
                    notification_type='client_invoice_created',
                    title=f'New Client Invoice: {invoice.invoice_number}',
                    message=f'Client invoice "{invoice.invoice_number}" for {invoice.client.name} has been created. Amount: ${invoice.total_amount}.',
                    related_object=invoice
                )

            return redirect('finance:client_invoice_detail', pk=invoice.pk)
    else:
        form = ClientInvoiceForm(company=company, instance=invoice)
        formset = ClientInvoiceLineFormSet(instance=invoice, company=company)
    return render(request, 'finance/client_invoice_form.html', {
        'form': form,
        'formset': formset,
        'title': 'New Client Invoice',
    })


@role_required(*FINANCE_ROLES)
def client_invoice_detail(request, pk):
    company = request.user.company
    invoice = get_object_or_404(ClientInvoice, pk=pk, company=company)
    lines = invoice.lines.all().select_related('account')
    return render(request, 'finance/client_invoice_detail.html', {
        'invoice': invoice,
        'lines': lines,
    })


@role_required(*FINANCE_ROLES)
def client_invoice_print(request, pk):
    company = request.user.company
    invoice = get_object_or_404(ClientInvoice, pk=pk, company=company)
    lines = invoice.lines.all().select_related('account')
    
    print_type = request.GET.get('type')
    if not print_type:
        print_type = 'proforma' if invoice.status == 'draft' else 'invoice'
        
    return render(request, 'finance/client_invoice_print.html', {
        'invoice': invoice,
        'lines': lines,
        'print_type': print_type,
    })


@role_required(*FINANCE_ROLES)
def client_invoice_edit(request, pk):
    company = request.user.company
    invoice = get_object_or_404(ClientInvoice, pk=pk, company=company)
    if request.method == 'POST':
        form = ClientInvoiceForm(request.POST, instance=invoice, company=company)
        formset = ClientInvoiceLineFormSet(request.POST, instance=invoice, company=company)
        if form.is_valid() and formset.is_valid():
            form.save()
            formset.save()
            invoice.calculate_totals()
            invoice.save()
            messages.success(request, f'Client invoice "{invoice.invoice_number}" updated.')
            return redirect('finance:client_invoice_detail', pk=invoice.pk)
    else:
        form = ClientInvoiceForm(instance=invoice, company=company)
        formset = ClientInvoiceLineFormSet(instance=invoice, company=company)
    return render(request, 'finance/client_invoice_form.html', {
        'form': form,
        'formset': formset,
        'title': 'Edit Client Invoice',
    })


@role_required(*FINANCE_ROLES)
def client_invoice_delete(request, pk):
    company = request.user.company
    invoice = get_object_or_404(ClientInvoice, pk=pk, company=company)
    if request.method == 'POST':
        number = invoice.invoice_number
        invoice.delete()
        messages.success(request, f'Client invoice "{number}" deleted.')
        return redirect('finance:client_invoice_list')
    return render(request, 'finance/client_invoice_confirm_delete.html', {'invoice': invoice})


# ---------------------------------------------------------------------------
# Supplier Invoices (Phase 2)
# ---------------------------------------------------------------------------

@role_required(*FINANCE_ROLES)
def supplier_invoice_list(request):
    company = request.user.company
    invoices = SupplierInvoice.objects.filter(company=company).select_related('created_by')
    return render(request, 'finance/supplier_invoice_list.html', {'invoices': invoices})


@role_required(*FINANCE_ROLES)
def supplier_invoice_create(request):
    company = request.user.company
    invoice = SupplierInvoice(company=company)
    if request.method == 'POST':
        form = SupplierInvoiceForm(request.POST, company=company, instance=invoice)
        formset = SupplierInvoiceLineFormSet(request.POST, instance=invoice, company=company)
        if form.is_valid() and formset.is_valid():
            invoice = form.save(commit=False)
            invoice.company = company
            invoice.created_by = request.user
            invoice.save()
            formset.instance = invoice
            formset.save()
            invoice.calculate_totals()
            invoice.save()
            messages.success(request, f'Supplier invoice "{invoice.invoice_number}" created.')

            # Create notification for accountants about new supplier invoice
            from notifications.utils import create_notification
            from django.contrib.auth import get_user_model
            User = get_user_model()

            # Notify accountants about new supplier invoice requiring payment
            accountants = User.objects.filter(
                company=company,
                role='accountant'
            ).exclude(pk=request.user.pk)  # Don't notify the creator

            for accountant in accountants:
                create_notification(
                    user=accountant,
                    notification_type='supplier_invoice_created',
                    title=f'New Supplier Invoice: {invoice.invoice_number}',
                    message=f'Supplier invoice "{invoice.invoice_number}" from {invoice.supplier.name} requires payment. Amount: ${invoice.total_amount}.',
                    related_object=invoice
                )

            return redirect('finance:supplier_invoice_detail', pk=invoice.pk)
    else:
        form = SupplierInvoiceForm(company=company, instance=invoice)
        formset = SupplierInvoiceLineFormSet(instance=invoice, company=company)
    return render(request, 'finance/supplier_invoice_form.html', {
        'form': form,
        'formset': formset,
        'title': 'New Supplier Invoice',
    })


@role_required(*FINANCE_ROLES)
def supplier_invoice_detail(request, pk):
    company = request.user.company
    invoice = get_object_or_404(SupplierInvoice, pk=pk, company=company)
    lines = invoice.lines.all().select_related('account')
    return render(request, 'finance/supplier_invoice_detail.html', {
        'invoice': invoice,
        'lines': lines,
    })


@role_required(*FINANCE_ROLES)
def supplier_invoice_edit(request, pk):
    company = request.user.company
    invoice = get_object_or_404(SupplierInvoice, pk=pk, company=company)
    if request.method == 'POST':
        form = SupplierInvoiceForm(request.POST, instance=invoice, company=company)
        formset = SupplierInvoiceLineFormSet(request.POST, instance=invoice, company=company)
        if form.is_valid() and formset.is_valid():
            form.save()
            formset.save()
            invoice.calculate_totals()
            invoice.save()
            messages.success(request, f'Supplier invoice "{invoice.invoice_number}" updated.')
            return redirect('finance:supplier_invoice_detail', pk=invoice.pk)
    else:
        form = SupplierInvoiceForm(instance=invoice, company=company)
        formset = SupplierInvoiceLineFormSet(instance=invoice, company=company)
    return render(request, 'finance/supplier_invoice_form.html', {
        'form': form,
        'formset': formset,
        'title': 'Edit Supplier Invoice',
    })


@role_required(*FINANCE_ROLES)
def supplier_invoice_delete(request, pk):
    company = request.user.company
    invoice = get_object_or_404(SupplierInvoice, pk=pk, company=company)
    if request.method == 'POST':
        number = invoice.invoice_number
        invoice.delete()
        messages.success(request, f'Supplier invoice "{number}" deleted.')
        return redirect('finance:supplier_invoice_list')
    return render(request, 'finance/supplier_invoice_confirm_delete.html', {'invoice': invoice})


# ---------------------------------------------------------------------------
# Bank Reconciliation Views (Phase 3)
# ---------------------------------------------------------------------------

@role_required(*FINANCE_ROLES)
def bank_account_list(request):
    """List all bank accounts for the company."""
    company = request.user.company
    bank_accounts = BankAccount.objects.filter(company=company).select_related('account')

    context = {
        'bank_accounts': bank_accounts,
        'title': 'Bank Accounts',
    }
    return render(request, 'finance/bank_account_list.html', context)


@role_required(*FINANCE_ROLES)
def bank_account_create(request):
    """Create a new bank account."""
    company = request.user.company

    if request.method == 'POST':
        form = BankAccountForm(request.POST, company=company)
        if form.is_valid():
            bank_account = form.save(commit=False)
            bank_account.company = company
            bank_account.save()
            messages.success(request, f'Bank account "{bank_account.name}" created successfully.')
            return redirect('finance:bank_account_list')
    else:
        form = BankAccountForm(company=company)

    context = {
        'form': form,
        'title': 'Create Bank Account',
    }
    return render(request, 'finance/bank_account_form.html', context)


@role_required(*FINANCE_ROLES)
def bank_account_edit(request, pk):
    """Edit an existing bank account."""
    company = request.user.company
    bank_account = get_object_or_404(BankAccount, pk=pk, company=company)

    if request.method == 'POST':
        form = BankAccountForm(request.POST, instance=bank_account, company=company)
        if form.is_valid():
            form.save()
            messages.success(request, f'Bank account "{bank_account.name}" updated successfully.')
            return redirect('finance:bank_account_list')
    else:
        form = BankAccountForm(instance=bank_account, company=company)

    context = {
        'form': form,
        'bank_account': bank_account,
        'title': 'Edit Bank Account',
    }
    return render(request, 'finance/bank_account_form.html', context)


@role_required(*FINANCE_ROLES)
def bank_account_delete(request, pk):
    """Delete a bank account."""
    company = request.user.company
    bank_account = get_object_or_404(BankAccount, pk=pk, company=company)

    if request.method == 'POST':
        bank_account.delete()
        messages.success(request, f'Bank account "{bank_account.name}" deleted successfully.')
        return redirect('finance:bank_account_list')

    context = {
        'bank_account': bank_account,
        'title': 'Delete Bank Account',
    }
    return render(request, 'finance/bank_account_confirm_delete.html', context)


@role_required(*FINANCE_ROLES)
def bank_statement_upload(request):
    """Upload and process bank statements."""
    company = request.user.company

    if request.method == 'POST':
        form = BankStatementUploadForm(request.POST, request.FILES, company=company)
        if form.is_valid():
            bank_account = form.cleaned_data['bank_account']
            statement_file = form.cleaned_data['statement_file']
            statement_date = form.cleaned_data['statement_date']

            # Create bank statement
            statement = BankStatement.objects.create(
                bank_account=bank_account,
                statement_date=statement_date,
                file_name=statement_file.name,
            )

            # Process the file (CSV or MT940)
            try:
                if statement_file.name.endswith('.csv'):
                    process_csv_statement(statement, statement_file)
                elif statement_file.name.endswith('.sta') or 'mt940' in statement_file.name.lower():
                    process_mt940_statement(statement, statement_file)
                else:
                    raise ValueError("Unsupported file format")

                messages.success(request, f'Statement for {bank_account.name} uploaded and processed successfully.')
                return redirect('finance:bank_reconciliation_list')

            except Exception as e:
                statement.delete()  # Clean up on error
                messages.error(request, f'Error processing statement: {str(e)}')
    else:
        form = BankStatementUploadForm(company=company)

    context = {
        'form': form,
        'title': 'Upload Bank Statement',
    }
    return render(request, 'finance/bank_statement_upload.html', context)


@role_required(*FINANCE_ROLES)
def bank_reconciliation_list(request):
    """List bank reconciliations."""
    company = request.user.company
    reconciliations = Reconciliation.objects.filter(
        bank_account__company=company
    ).select_related('bank_account', 'statement').order_by('-reconciled_date')

    context = {
        'reconciliations': reconciliations,
        'title': 'Bank Reconciliations',
    }
    return render(request, 'finance/bank_reconciliation_list.html', context)


@role_required(*FINANCE_ROLES)
def bank_reconciliation_create(request):
    """Create a new bank reconciliation."""
    company = request.user.company

    if request.method == 'POST':
        form = ReconciliationForm(request.POST, company=company)
        if form.is_valid():
            reconciliation = form.save(commit=False)
            reconciliation.company = company
            reconciliation.save()
            messages.success(request, 'Bank reconciliation created successfully.')
            return redirect('finance:bank_reconciliation_detail', pk=reconciliation.pk)
    else:
        form = ReconciliationForm(company=company)

    context = {
        'form': form,
        'title': 'Create Bank Reconciliation',
    }
    return render(request, 'finance/bank_reconciliation_form.html', context)


@role_required(*FINANCE_ROLES)
def bank_reconciliation_detail(request, pk):
    """View bank reconciliation details and manage transaction matching."""
    company = request.user.company
    reconciliation = get_object_or_404(
        Reconciliation,
        pk=pk,
        bank_account__company=company
    )

    # Get unreconciled bank transactions
    bank_transactions = BankTransaction.objects.filter(
        statement=reconciliation.statement,
        reconciled=False
    ).order_by('date')

    # Get potential matching accounting transactions
    accounting_transactions = Transaction.objects.filter(
        company=company,
        account=reconciliation.bank_account.account,
        date__range=[
            reconciliation.statement.statement_date - timedelta(days=30),
            reconciliation.statement.statement_date + timedelta(days=30)
        ]
    ).order_by('-date')

    if request.method == 'POST':
        transaction_id = request.POST.get('bank_transaction_id')
        accounting_transaction_id = request.POST.get('accounting_transaction_id')

        if transaction_id and accounting_transaction_id:
            bank_transaction = get_object_or_404(BankTransaction, pk=transaction_id, statement=reconciliation.statement)
            accounting_transaction = get_object_or_404(Transaction, pk=accounting_transaction_id, company=company)

            # Mark as reconciled
            bank_transaction.reconciled = True
            bank_transaction.matched_transaction = accounting_transaction
            bank_transaction.save()

            messages.success(request, 'Transaction matched successfully.')

    context = {
        'reconciliation': reconciliation,
        'bank_transactions': bank_transactions,
        'accounting_transactions': accounting_transactions,
        'title': 'Bank Reconciliation Details',
    }
    return render(request, 'finance/bank_reconciliation_detail.html', context)


# ---------------------------------------------------------------------------
# Financial Reports Views (Phase 3)
# ---------------------------------------------------------------------------

@role_required(*FINANCE_ROLES)
def financial_report_list(request):
    """List available financial reports."""
    company = request.user.company
    reports = FinancialReport.objects.filter(company=company).order_by('-generated_at')

    context = {
        'reports': reports,
        'title': 'Financial Reports',
    }
    return render(request, 'finance/financial_report_list.html', context)


@role_required(*FINANCE_ROLES)
def financial_report_generate(request):
    """Generate a new financial report."""
    company = request.user.company

    if request.method == 'POST':
        form = FinancialReportForm(request.POST)
        if form.is_valid():
            report_type = form.cleaned_data['report_type']
            report_date = form.cleaned_data['report_date']
            start_date = form.cleaned_data.get('start_date')
            end_date = form.cleaned_data.get('end_date')

            # Create the report
            report = FinancialReport.objects.create(
                company=company,
                report_type=report_type,
                report_date=report_date,
                start_date=start_date,
                end_date=end_date,
            )

            # Generate report lines based on type
            if report_type == 'balance_sheet':
                generate_balance_sheet(report)
            elif report_type == 'income_statement':
                generate_income_statement(report)
            elif report_type == 'cash_flow':
                generate_cash_flow_statement(report)

            messages.success(request, f'{report.get_report_type_display()} generated successfully.')
            return redirect('finance:financial_report_detail', pk=report.pk)
    else:
        form = FinancialReportForm()

    context = {
        'form': form,
        'title': 'Generate Financial Report',
    }
    return render(request, 'finance/financial_report_generate.html', context)


@role_required(*FINANCE_ROLES)
def financial_report_detail(request, pk):
    """View financial report details."""
    company = request.user.company
    report = get_object_or_404(FinancialReport, pk=pk, company=company)

    report_lines = ReportLine.objects.filter(report=report).order_by('line_number')

    context = {
        'report': report,
        'report_lines': report_lines,
        'title': f'{report.get_report_type_display()} - {report.report_date}',
    }
    return render(request, 'finance/financial_report_detail.html', context)


@role_required(*FINANCE_ROLES)
def marketplace_finance_settings_edit(request):
    """Create or update marketplace finance mappings for the current company."""
    company = request.user.company
    settings_obj = MarketplaceFinanceSettings.objects.filter(company=company).first()

    if request.method == 'POST':
        form = MarketplaceFinanceSettingsForm(
            request.POST,
            instance=settings_obj,
            company=company,
        )
        if form.is_valid():
            created = settings_obj is None
            settings_obj = form.save()
            messages.success(
                request,
                'Marketplace finance settings created.' if created else 'Marketplace finance settings updated.',
            )
            return redirect('finance:marketplace_finance_settings')
    else:
        form = MarketplaceFinanceSettingsForm(instance=settings_obj, company=company)

    return render(request, 'finance/marketplace_finance_settings_form.html', {
        'form': form,
        'settings_obj': settings_obj,
        'title': 'Marketplace Finance Settings',
    })


# ---------------------------------------------------------------------------
# Helper Functions for Phase 3
# ---------------------------------------------------------------------------

def process_csv_statement(statement, file):
    """Process CSV bank statement file."""
    import csv
    from io import TextIOWrapper

    file_wrapper = TextIOWrapper(file.file, encoding='utf-8')
    reader = csv.DictReader(file_wrapper)

    for row in reader:
        # Assuming CSV format: date,description,amount
        # Adjust field names based on actual CSV structure
        BankTransaction.objects.create(
            statement=statement,
            date=row.get('date'),
            description=row.get('description'),
            amount=row.get('amount'),
        )


def process_mt940_statement(statement, file):
    """Process MT940 bank statement file."""
    # MT940 processing would require a specialized library
    # For now, create a placeholder transaction
    BankTransaction.objects.create(
        statement=statement,
        date=statement.statement_date,
        description="MT940 import - placeholder",
        amount=0,
    )


def generate_balance_sheet(report):
    """Generate balance sheet report lines."""
    company = report.company

    # Assets
    assets_accounts = Account.objects.filter(
        company=company,
        account_type='asset'
    )

    line_number = 1
    total_assets = 0

    for account in assets_accounts:
        balance = account.get_balance_at_date(report.report_date)
        if balance != 0:
            ReportLine.objects.create(
                report=report,
                line_number=line_number,
                label=f"{account.code} - {account.name}",
                amount=balance,
                line_type='asset',
            )
            total_assets += balance
            line_number += 1

    # Total Assets
    ReportLine.objects.create(
        report=report,
        line_number=line_number,
        label="Total Assets",
        amount=total_assets,
        line_type='total',
        is_total=True,
    )
    line_number += 1

    # Liabilities
    liabilities_accounts = Account.objects.filter(
        company=company,
        account_type='liability'
    )

    total_liabilities = 0

    for account in liabilities_accounts:
        balance = account.get_balance_at_date(report.report_date)
        if balance != 0:
            ReportLine.objects.create(
                report=report,
                line_number=line_number,
                label=f"{account.code} - {account.name}",
                amount=balance,
                line_type='liability',
            )
            total_liabilities += balance
            line_number += 1

    # Equity
    equity_accounts = Account.objects.filter(
        company=company,
        account_type='equity'
    )

    total_equity = 0

    for account in equity_accounts:
        balance = account.get_balance_at_date(report.report_date)
        if balance != 0:
            ReportLine.objects.create(
                report=report,
                line_number=line_number,
                label=f"{account.code} - {account.name}",
                amount=balance,
                line_type='equity',
            )
            total_equity += balance
            line_number += 1

    # Total Liabilities & Equity
    ReportLine.objects.create(
        report=report,
        line_number=line_number,
        label="Total Liabilities & Equity",
        amount=total_liabilities + total_equity,
        line_type='total',
        is_total=True,
    )


def generate_income_statement(report):
    """Generate income statement report lines."""
    company = report.company
    start_date = report.start_date or report.report_date.replace(day=1)
    end_date = report.end_date or report.report_date

    # Revenue
    revenue_accounts = Account.objects.filter(
        company=company,
        account_type='revenue'
    )

    line_number = 1
    total_revenue = 0

    for account in revenue_accounts:
        balance = account.get_balance_between_dates(start_date, end_date)
        if balance != 0:
            ReportLine.objects.create(
                report=report,
                line_number=line_number,
                label=f"{account.code} - {account.name}",
                amount=balance,
                line_type='revenue',
            )
            total_revenue += balance
            line_number += 1

    # Total Revenue
    ReportLine.objects.create(
        report=report,
        line_number=line_number,
        label="Total Revenue",
        amount=total_revenue,
        line_type='total',
        is_total=True,
    )
    line_number += 1

    # Expenses
    expense_accounts = Account.objects.filter(
        company=company,
        account_type='expense'
    )

    total_expenses = 0

    for account in expense_accounts:
        balance = account.get_balance_between_dates(start_date, end_date)
        if balance != 0:
            ReportLine.objects.create(
                report=report,
                line_number=line_number,
                label=f"{account.code} - {account.name}",
                amount=balance,
                line_type='expense',
            )
            total_expenses += balance
            line_number += 1

    # Total Expenses
    ReportLine.objects.create(
        report=report,
        line_number=line_number,
        label="Total Expenses",
        amount=total_expenses,
        line_type='total',
        is_total=True,
    )
    line_number += 1

    # Net Income
    net_income = total_revenue - total_expenses
    ReportLine.objects.create(
        report=report,
        line_number=line_number,
        label="Net Income",
        amount=net_income,
        line_type='net_income',
        is_total=True,
    )


def generate_cash_flow_statement(report):
    """Generate cash flow statement report lines."""
    company = report.company
    start_date = report.start_date or report.report_date.replace(day=1)
    end_date = report.end_date or report.report_date

    # Operating Activities
    operating_accounts = Account.objects.filter(
        company=company,
        account_type__in=['revenue', 'expense']
    )

    line_number = 1
    cash_from_operations = 0

    for account in operating_accounts:
        balance = account.get_balance_between_dates(start_date, end_date)
        if balance != 0:
            ReportLine.objects.create(
                report=report,
                line_number=line_number,
                label=f"{account.code} - {account.name}",
                amount=balance,
                line_type='operating',
            )
            cash_from_operations += balance
            line_number += 1

    # Net Cash from Operating Activities
    ReportLine.objects.create(
        report=report,
        line_number=line_number,
        label="Net Cash from Operating Activities",
        amount=cash_from_operations,
        line_type='total',
        is_total=True,
    )
    line_number += 1

    # Investing Activities (placeholder)
    ReportLine.objects.create(
        report=report,
        line_number=line_number,
        label="Net Cash from Investing Activities",
        amount=0,
        line_type='total',
        is_total=True,
    )
    line_number += 1

    # Financing Activities (placeholder)
    ReportLine.objects.create(
        report=report,
        line_number=line_number,
        label="Net Cash from Financing Activities",
        amount=0,
        line_type='total',
        is_total=True,
    )
    line_number += 1

    # Net Change in Cash
    ReportLine.objects.create(
        report=report,
        line_number=line_number,
        label="Net Change in Cash",
        amount=cash_from_operations,
        line_type='net_change',
        is_total=True,
    )
