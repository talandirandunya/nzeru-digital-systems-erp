from django.conf import settings
from django.core.exceptions import ValidationError
from django.core.validators import MinValueValidator
from django.db import models
from django.db import transaction as db_transaction

# Create your models here.


class Account(models.Model):
    """Financial account scoped to a company, with number, type and hierarchy."""

    ACCOUNT_TYPES = [
        ('asset', 'Asset'),
        ('liability', 'Liability'),
        ('equity', 'Equity'),
        ('revenue', 'Revenue'),
        ('expense', 'Expense'),
    ]

    company = models.ForeignKey('accounts.Company', on_delete=models.CASCADE, related_name='accounts')
    code = models.CharField(max_length=20, blank=True, help_text='Account number or code')
    parent = models.ForeignKey('self', null=True, blank=True, on_delete=models.CASCADE, related_name='children')
    name = models.CharField(max_length=100)
    account_type = models.CharField(max_length=20, choices=ACCOUNT_TYPES, default='asset')
    balance = models.DecimalField(max_digits=12, decimal_places=2, default=0)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        unique_together = ['company', 'name']
        ordering = ['company', 'code', 'name']

    def __str__(self):
        return f"{self.code + ' ' if self.code else ''}{self.name}"

    def full_name(self):
        labels = [self.name]
        parent = self.parent
        while parent:
            labels.insert(0, parent.name)
            parent = parent.parent
        return ' > '.join(labels)


class Transaction(models.Model):
    TYPE_CHOICES = [
        ('credit', 'Credit'),
        ('debit', 'Debit'),
    ]

    company = models.ForeignKey('accounts.Company', on_delete=models.CASCADE, related_name='transactions')
    account = models.ForeignKey(Account, on_delete=models.CASCADE, related_name='transactions')
    transaction_type = models.CharField(max_length=10, choices=TYPE_CHOICES)
    amount = models.DecimalField(max_digits=12, decimal_places=2, validators=[MinValueValidator(0.01)])
    description = models.TextField(blank=True)
    date = models.DateField()
    entered_by = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.SET_NULL, null=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ['-date']

    def __str__(self):
        return f"{self.transaction_type} {self.amount} on {self.account.name}"


    def save(self, *args, **kwargs):
        # adjust account balance when transactions are created or updated
        with db_transaction.atomic():
            is_new = self.pk is None
            previous_amount = None
            previous_type = None
            if not is_new:
                old = Transaction.objects.select_for_update().get(pk=self.pk)
                previous_amount = old.amount
                previous_type = old.transaction_type
            super().save(*args, **kwargs)
            # compute balance delta
            if is_new:
                delta = self.amount if self.transaction_type == 'credit' else -self.amount
            else:
                prev_delta = previous_amount if previous_type == 'credit' else -previous_amount
                curr_delta = self.amount if self.transaction_type == 'credit' else -self.amount
                delta = curr_delta - prev_delta
            # use select_for_update on account as well
            acct = self.account
            acct.balance = models.F('balance') + delta
            acct.save(update_fields=['balance'])

    def delete(self, *args, **kwargs):
        with db_transaction.atomic():
            delta = -self.amount if self.transaction_type == 'credit' else self.amount
            acct = self.account
            acct.balance = models.F('balance') + delta
            acct.save(update_fields=['balance'])
            super().delete(*args, **kwargs)


class Journal(models.Model):
    """Accounting journal, e.g. sales, purchases, bank."""

    JOURNAL_TYPES = [
        ('sales', 'Sales'),
        ('purchases', 'Purchases'),
        ('bank', 'Bank'),
        ('cash', 'Cash'),
        ('general', 'General'),
    ]

    company = models.ForeignKey('accounts.Company', on_delete=models.CASCADE, related_name='journals')
    code = models.CharField(max_length=20, blank=True, help_text='Optional journal code')
    name = models.CharField(max_length=100)
    journal_type = models.CharField(max_length=20, choices=JOURNAL_TYPES, default='general')
    description = models.TextField(blank=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        unique_together = ['company', 'name']
        ordering = ['company', 'journal_type', 'name']

    def __str__(self):
        return f"{self.name} ({self.get_journal_type_display()})"


class JournalEntry(models.Model):
    """A journal entry grouping balanced debit and credit lines."""

    company = models.ForeignKey('accounts.Company', on_delete=models.CASCADE, related_name='journal_entries')
    journal = models.ForeignKey(Journal, on_delete=models.PROTECT, related_name='entries')
    reference = models.CharField(max_length=50, blank=True)
    description = models.TextField(blank=True)
    date = models.DateField()
    entered_by = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.SET_NULL, null=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ['-date', '-created_at']

    def __str__(self):
        return f"{self.date} {self.reference or self.journal.name}"

    def total_debits(self):
        return self.lines.aggregate(total=models.Sum('debit'))['total'] or 0

    def total_credits(self):
        return self.lines.aggregate(total=models.Sum('credit'))['total'] or 0

    def is_balanced(self):
        return self.total_debits() == self.total_credits()

    def clean(self):
        if not self.is_balanced():
            raise ValidationError('Journal entry must be balanced before saving.')


class JournalEntryLine(models.Model):
    """Single debit or credit line within a journal entry."""

    entry = models.ForeignKey(JournalEntry, on_delete=models.CASCADE, related_name='lines')
    account = models.ForeignKey(Account, on_delete=models.PROTECT, related_name='entry_lines')
    description = models.CharField(max_length=200, blank=True)
    debit = models.DecimalField(max_digits=12, decimal_places=2, default=0)
    credit = models.DecimalField(max_digits=12, decimal_places=2, default=0)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ['entry', 'account']

    def __str__(self):
        amount = self.debit if self.debit else self.credit
        side = 'Dr' if self.debit else 'Cr'
        return f"{self.account} {side} {amount}"

    def clean(self):
        if self.debit <= 0 and self.credit <= 0:
            raise ValidationError('Each line must have either a debit or a credit amount.')
        if self.debit > 0 and self.credit > 0:
            raise ValidationError('A line cannot have both debit and credit.')

    def save(self, *args, **kwargs):
        self.full_clean()
        super().save(*args, **kwargs)


# ---------------------------------------------------------------------------
# Invoicing System (Phase 2)
# ---------------------------------------------------------------------------

class ClientInvoice(models.Model):
    """Client invoice with line items and workflow."""

    STATUS_CHOICES = [
        ('draft', 'Draft'),
        ('validated', 'Validated'),
        ('sent', 'Sent'),
        ('paid', 'Paid'),
        ('cancelled', 'Cancelled'),
    ]

    company = models.ForeignKey('accounts.Company', on_delete=models.CASCADE, related_name='client_invoices')
    invoice_number = models.CharField(max_length=50, unique=True)
    client_name = models.CharField(max_length=100)
    client_address = models.TextField(blank=True)
    client_email = models.EmailField(blank=True)
    date = models.DateField()
    due_date = models.DateField()
    status = models.CharField(max_length=20, choices=STATUS_CHOICES, default='draft')
    subtotal = models.DecimalField(max_digits=12, decimal_places=2, default=0)
    tax_rate = models.DecimalField(max_digits=5, decimal_places=2, default=0)
    tax_amount = models.DecimalField(max_digits=12, decimal_places=2, default=0)
    total = models.DecimalField(max_digits=12, decimal_places=2, default=0)
    notes = models.TextField(blank=True)
    created_by = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.SET_NULL, null=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ['-date', '-created_at']

    def __str__(self):
        return f"INV-{self.invoice_number} - {self.client_name}"

    def calculate_totals(self):
        """Calculate subtotal, tax, and total from lines."""
        self.subtotal = self.lines.aggregate(total=models.Sum('line_total'))['total'] or 0
        self.tax_amount = self.subtotal * (self.tax_rate / 100)
        self.total = self.subtotal + self.tax_amount

    def can_validate(self):
        """Check if invoice can be validated."""
        return self.status == 'draft' and self.lines.exists()

    def can_send(self):
        """Check if invoice can be sent."""
        return self.status == 'validated'

    def can_pay(self):
        """Check if invoice can be marked as paid."""
        return self.status in ['validated', 'sent']


class SupplierInvoice(models.Model):
    """Supplier invoice with 2-step validation workflow."""

    STATUS_CHOICES = [
        ('draft', 'Draft'),
        ('validated_level1', 'Validated Level 1'),
        ('validated_level2', 'Validated Level 2'),
        ('paid', 'Paid'),
        ('cancelled', 'Cancelled'),
    ]

    company = models.ForeignKey('accounts.Company', on_delete=models.CASCADE, related_name='supplier_invoices')
    invoice_number = models.CharField(max_length=50)
    supplier_name = models.CharField(max_length=100)
    supplier_address = models.TextField(blank=True)
    date = models.DateField()
    due_date = models.DateField()
    status = models.CharField(max_length=20, choices=STATUS_CHOICES, default='draft')
    subtotal = models.DecimalField(max_digits=12, decimal_places=2, default=0)
    tax_rate = models.DecimalField(max_digits=5, decimal_places=2, default=0)
    tax_amount = models.DecimalField(max_digits=12, decimal_places=2, default=0)
    total = models.DecimalField(max_digits=12, decimal_places=2, default=0)
    notes = models.TextField(blank=True)
    validated_by_level1 = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='supplier_invoices_validated_level1'
    )
    validated_by_level2 = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='supplier_invoices_validated_level2'
    )
    created_by = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.SET_NULL, null=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ['-date', '-created_at']
        unique_together = ['company', 'invoice_number']

    def __str__(self):
        return f"SUP-{self.invoice_number} - {self.supplier_name}"

    def calculate_totals(self):
        """Calculate subtotal, tax, and total from lines."""
        self.subtotal = self.lines.aggregate(total=models.Sum('line_total'))['total'] or 0
        self.tax_amount = self.subtotal * (self.tax_rate / 100)
        self.total = self.subtotal + self.tax_amount

    def can_validate_level1(self):
        """Check if invoice can be validated to level 1."""
        return self.status == 'draft' and self.lines.exists()

    def can_validate_level2(self):
        """Check if invoice can be validated to level 2."""
        return self.status == 'validated_level1'

    def can_pay(self):
        """Check if invoice can be marked as paid."""
        return self.status == 'validated_level2'


class InvoiceLine(models.Model):
    """Line item for both client and supplier invoices."""

    client_invoice = models.ForeignKey(
        ClientInvoice,
        on_delete=models.CASCADE,
        null=True,
        blank=True,
        related_name='lines'
    )
    supplier_invoice = models.ForeignKey(
        SupplierInvoice,
        on_delete=models.CASCADE,
        null=True,
        blank=True,
        related_name='lines'
    )
    description = models.CharField(max_length=200)
    quantity = models.DecimalField(max_digits=10, decimal_places=2, default=1)
    unit_price = models.DecimalField(max_digits=12, decimal_places=2)
    line_total = models.DecimalField(max_digits=12, decimal_places=2)
    account = models.ForeignKey(Account, on_delete=models.PROTECT, related_name='invoice_lines')
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ['created_at']

    def __str__(self):
        return f"{self.description} - {self.line_total}"

    def save(self, *args, **kwargs):
        """Calculate line total before saving."""
        self.line_total = self.quantity * self.unit_price
        super().save(*args, **kwargs)

    def clean(self):
        """Ensure line belongs to exactly one invoice type."""
        if not self.client_invoice and not self.supplier_invoice:
            raise ValidationError('Line must belong to either a client or supplier invoice.')
        if self.client_invoice and self.supplier_invoice:
            raise ValidationError('Line cannot belong to both client and supplier invoices.')


# ---------------------------------------------------------------------------
# Bank Reconciliation System (Phase 3)
# ---------------------------------------------------------------------------

class BankAccount(models.Model):
    """Bank account linked to accounting accounts."""

    company = models.ForeignKey('accounts.Company', on_delete=models.CASCADE, related_name='bank_accounts')
    name = models.CharField(max_length=100)
    account_number = models.CharField(max_length=50)
    bank_name = models.CharField(max_length=100)
    account = models.OneToOneField(Account, on_delete=models.PROTECT, related_name='bank_account')
    opening_balance = models.DecimalField(max_digits=12, decimal_places=2, default=0)
    current_balance = models.DecimalField(max_digits=12, decimal_places=2, default=0)
    last_reconciled = models.DateField(null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        unique_together = ['company', 'account_number']

    def __str__(self):
        return f"{self.name} - {self.account_number}"


class BankStatement(models.Model):
    """Imported bank statement."""

    bank_account = models.ForeignKey(BankAccount, on_delete=models.CASCADE, related_name='statements')
    statement_date = models.DateField()
    opening_balance = models.DecimalField(max_digits=12, decimal_places=2)
    closing_balance = models.DecimalField(max_digits=12, decimal_places=2)
    imported_at = models.DateTimeField(auto_now_add=True)
    imported_by = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.SET_NULL, null=True)

    class Meta:
        ordering = ['-statement_date']

    def __str__(self):
        return f"{self.bank_account.name} - {self.statement_date}"


class BankTransaction(models.Model):
    """Individual transaction from bank statement."""

    statement = models.ForeignKey(BankStatement, on_delete=models.CASCADE, related_name='transactions')
    date = models.DateField()
    description = models.CharField(max_length=200)
    amount = models.DecimalField(max_digits=12, decimal_places=2)
    balance = models.DecimalField(max_digits=12, decimal_places=2)
    reference = models.CharField(max_length=100, blank=True)
    reconciled = models.BooleanField(default=False)
    reconciled_transaction = models.ForeignKey(
        Transaction,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='bank_transactions'
    )
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ['date', 'created_at']

    def __str__(self):
        return f"{self.date} {self.description} {self.amount}"

    @property
    def is_credit(self):
        return self.amount > 0

    @property
    def is_debit(self):
        return self.amount < 0


class Reconciliation(models.Model):
    """Bank reconciliation record."""

    bank_account = models.ForeignKey(BankAccount, on_delete=models.CASCADE, related_name='reconciliations')
    statement = models.ForeignKey(BankStatement, on_delete=models.CASCADE, related_name='reconciliations')
    reconciled_date = models.DateField()
    bank_balance = models.DecimalField(max_digits=12, decimal_places=2)
    book_balance = models.DecimalField(max_digits=12, decimal_places=2)
    difference = models.DecimalField(max_digits=12, decimal_places=2)
    reconciled_by = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.SET_NULL, null=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ['-reconciled_date']

    def __str__(self):
        return f"{self.bank_account.name} - {self.reconciled_date}"

    def save(self, *args, **kwargs):
        self.difference = self.bank_balance - self.book_balance
        super().save(*args, **kwargs)


# ---------------------------------------------------------------------------
# Financial Reports (Phase 3)
# ---------------------------------------------------------------------------

class FinancialReport(models.Model):
    """Base class for financial reports."""

    REPORT_TYPES = [
        ('balance_sheet', 'Balance Sheet'),
        ('income_statement', 'Income Statement'),
        ('cash_flow', 'Cash Flow Statement'),
    ]

    company = models.ForeignKey('accounts.Company', on_delete=models.CASCADE, related_name='financial_reports')
    report_type = models.CharField(max_length=20, choices=REPORT_TYPES)
    report_date = models.DateField()
    start_date = models.DateField(null=True, blank=True)
    end_date = models.DateField(null=True, blank=True)
    generated_by = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.SET_NULL, null=True)
    generated_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ['-report_date']

    def __str__(self):
        return f"{self.get_report_type_display()} - {self.report_date}"


class ReportLine(models.Model):
    """Individual line in a financial report."""

    report = models.ForeignKey(FinancialReport, on_delete=models.CASCADE, related_name='lines')
    account = models.ForeignKey(Account, on_delete=models.CASCADE, related_name='report_lines')
    description = models.CharField(max_length=200)
    amount = models.DecimalField(max_digits=12, decimal_places=2, default=0)
    line_type = models.CharField(max_length=20, choices=[
        ('asset', 'Asset'),
        ('liability', 'Liability'),
        ('equity', 'Equity'),
        ('revenue', 'Revenue'),
        ('expense', 'Expense'),
        ('header', 'Header'),
        ('subtotal', 'Subtotal'),
    ])
    order = models.PositiveIntegerField(default=0)

    class Meta:
        ordering = ['order', 'account__code']

    def __str__(self):
        return f"{self.description} - {self.amount}"


class MarketplaceFinanceSettings(models.Model):
    """Company-level mapping used for marketplace order accounting."""

    company = models.OneToOneField(
        'accounts.Company',
        on_delete=models.CASCADE,
        related_name='marketplace_finance_settings',
    )
    sales_journal = models.ForeignKey(
        Journal,
        on_delete=models.PROTECT,
        related_name='marketplace_settings',
    )
    receivable_account = models.ForeignKey(
        Account,
        on_delete=models.PROTECT,
        related_name='marketplace_receivable_settings',
        help_text='Asset account used until marketplace orders are settled.',
    )
    revenue_account = models.ForeignKey(
        Account,
        on_delete=models.PROTECT,
        related_name='marketplace_revenue_settings',
        help_text='Revenue account credited for marketplace sales.',
    )
    tax_account = models.ForeignKey(
        Account,
        on_delete=models.PROTECT,
        null=True,
        blank=True,
        related_name='marketplace_tax_settings',
        help_text='Optional liability account used when marketplace tax is posted separately.',
    )
    is_enabled = models.BooleanField(
        default=False,
        help_text='Enable this after all required finance mappings are ready.',
    )
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        verbose_name = 'Marketplace finance settings'
        verbose_name_plural = 'Marketplace finance settings'

    def __str__(self):
        return f"Marketplace finance settings for {self.company.name}"

    def clean(self):
        super().clean()

        if self.sales_journal_id and self.sales_journal.company_id != self.company_id:
            raise ValidationError({'sales_journal': 'Journal must belong to the same company.'})

        if self.receivable_account_id:
            if self.receivable_account.company_id != self.company_id:
                raise ValidationError({'receivable_account': 'Receivable account must belong to the same company.'})
            if self.receivable_account.account_type != 'asset':
                raise ValidationError({'receivable_account': 'Receivable account must be an asset account.'})

        if self.revenue_account_id:
            if self.revenue_account.company_id != self.company_id:
                raise ValidationError({'revenue_account': 'Revenue account must belong to the same company.'})
            if self.revenue_account.account_type != 'revenue':
                raise ValidationError({'revenue_account': 'Revenue account must be a revenue account.'})

        if self.tax_account_id:
            if self.tax_account.company_id != self.company_id:
                raise ValidationError({'tax_account': 'Tax account must belong to the same company.'})
            if self.tax_account.account_type != 'liability':
                raise ValidationError({'tax_account': 'Tax account must be a liability account.'})

    def save(self, *args, **kwargs):
        self.full_clean()
        return super().save(*args, **kwargs)
