from django.contrib import admin
from .models import (
    Account, Transaction, Journal, JournalEntry, JournalEntryLine,
    ClientInvoice, SupplierInvoice, InvoiceLine,
    BankAccount, BankStatement, BankTransaction, Reconciliation,
    FinancialReport, ReportLine, MarketplaceFinanceSettings
)

# Register your models here.


class JournalEntryLineInline(admin.TabularInline):
    model = JournalEntryLine
    extra = 1
    fields = ('account', 'description', 'debit', 'credit')


class InvoiceLineInline(admin.TabularInline):
    model = InvoiceLine
    extra = 1
    fields = ('description', 'quantity', 'unit_price', 'account', 'line_total')
    readonly_fields = ('line_total',)


@admin.register(Account)
class AccountAdmin(admin.ModelAdmin):
    list_display = ('code', 'name', 'company', 'account_type', 'balance', 'created_at')
    search_fields = ('code', 'name')
    list_filter = ('company', 'account_type')


@admin.register(Transaction)
class TransactionAdmin(admin.ModelAdmin):
    list_display = ('account', 'transaction_type', 'amount', 'date', 'company')
    list_filter = ('transaction_type', 'date', 'company')
    search_fields = ('account__name', 'description')
    date_hierarchy = 'date'


@admin.register(Journal)
class JournalAdmin(admin.ModelAdmin):
    list_display = ('name', 'journal_type', 'company', 'code', 'created_at')
    list_filter = ('journal_type', 'company')
    search_fields = ('name', 'code', 'description')


@admin.register(JournalEntry)
class JournalEntryAdmin(admin.ModelAdmin):
    list_display = ('reference', 'journal', 'company', 'date', 'created_at')
    list_filter = ('journal__journal_type', 'journal', 'company', 'date')
    search_fields = ('reference', 'description', 'journal__name')
    inlines = [JournalEntryLineInline]


@admin.register(ClientInvoice)
class ClientInvoiceAdmin(admin.ModelAdmin):
    list_display = ('invoice_number', 'client_name', 'company', 'date', 'total', 'status', 'created_at')
    list_filter = ('status', 'company', 'date')
    search_fields = ('invoice_number', 'client_name', 'client_email')
    date_hierarchy = 'date'
    inlines = [InvoiceLineInline]


@admin.register(SupplierInvoice)
class SupplierInvoiceAdmin(admin.ModelAdmin):
    list_display = ('invoice_number', 'supplier_name', 'company', 'date', 'total', 'status', 'created_at')
    list_filter = ('status', 'company', 'date')
    search_fields = ('invoice_number', 'supplier_name')
    date_hierarchy = 'date'
    inlines = [InvoiceLineInline]


@admin.register(InvoiceLine)
class InvoiceLineAdmin(admin.ModelAdmin):
    list_display = ('description', 'quantity', 'unit_price', 'line_total', 'account', 'get_invoice_type')
    list_filter = ('account__account_type',)
    search_fields = ('description', 'account__name')

    def get_invoice_type(self, obj):
        if obj.client_invoice:
            return f"Client: {obj.client_invoice.invoice_number}"
        elif obj.supplier_invoice:
            return f"Supplier: {obj.supplier_invoice.invoice_number}"
        return "—"
    get_invoice_type.short_description = 'Invoice'


# Phase 3: Bank Reconciliation Admin
# ---------------------------------------------------------------------------

class BankTransactionInline(admin.TabularInline):
    model = BankTransaction
    extra = 0
    fields = ('date', 'description', 'amount', 'reconciled')
    readonly_fields = ('date', 'description', 'amount')


@admin.register(BankAccount)
class BankAccountAdmin(admin.ModelAdmin):
    list_display = ('name', 'account_number', 'bank_name', 'company', 'account', 'opening_balance')
    list_filter = ('company', 'bank_name')
    search_fields = ('name', 'account_number', 'bank_name')
    readonly_fields = ('created_at',)


@admin.register(BankStatement)
class BankStatementAdmin(admin.ModelAdmin):
    list_display = ('bank_account', 'statement_date', 'opening_balance', 'closing_balance', 'imported_at')
    list_filter = ('statement_date', 'bank_account__company')
    search_fields = ('bank_account__name',)
    inlines = [BankTransactionInline]
    readonly_fields = ('imported_at',)


@admin.register(BankTransaction)
class BankTransactionAdmin(admin.ModelAdmin):
    list_display = ('statement', 'date', 'description', 'amount', 'reconciled', 'reconciled_transaction')
    list_filter = ('reconciled', 'date', 'statement__bank_account__company')
    search_fields = ('description', 'statement__bank_account__name')
    readonly_fields = ('created_at',)


@admin.register(Reconciliation)
class ReconciliationAdmin(admin.ModelAdmin):
    list_display = ('bank_account', 'statement', 'reconciled_date', 'bank_balance', 'book_balance', 'difference')
    list_filter = ('reconciled_date', 'bank_account__company')
    search_fields = ('bank_account__name',)
    readonly_fields = ('created_at',)

    def difference(self, obj):
        return obj.bank_balance - obj.book_balance
    difference.short_description = 'Difference'


# Phase 3: Financial Reports Admin
# ---------------------------------------------------------------------------

class ReportLineInline(admin.TabularInline):
    model = ReportLine
    extra = 0
    fields = ('order', 'description', 'amount', 'line_type')
    readonly_fields = ('order', 'description', 'amount', 'line_type')


@admin.register(FinancialReport)
class FinancialReportAdmin(admin.ModelAdmin):
    list_display = ('report_type', 'report_date', 'start_date', 'end_date', 'company', 'generated_at')
    list_filter = ('report_type', 'report_date', 'company')
    search_fields = ('company__name',)
    inlines = [ReportLineInline]
    readonly_fields = ('generated_at',)


@admin.register(ReportLine)
class ReportLineAdmin(admin.ModelAdmin):
    list_display = ('report', 'order', 'description', 'amount', 'line_type')
    list_filter = ('line_type', 'report__report_type')
    search_fields = ('description', 'report__company__name')
    readonly_fields = ('order', 'description', 'amount', 'line_type')


@admin.register(MarketplaceFinanceSettings)
class MarketplaceFinanceSettingsAdmin(admin.ModelAdmin):
    list_display = (
        'company',
        'sales_journal',
        'receivable_account',
        'revenue_account',
        'tax_account',
        'is_enabled',
        'updated_at',
    )
    list_filter = ('is_enabled', 'company')
    search_fields = (
        'company__name',
        'sales_journal__name',
        'receivable_account__name',
        'revenue_account__name',
    )
    readonly_fields = ('created_at', 'updated_at')
