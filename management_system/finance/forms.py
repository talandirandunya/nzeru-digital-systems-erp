from decimal import Decimal

from django import forms
from django.core.exceptions import ValidationError
from django.forms import BaseInlineFormSet, inlineformset_factory

from .models import Account, JournalEntry, JournalEntryLine, Journal, Transaction, ClientInvoice, SupplierInvoice, InvoiceLine, BankAccount, BankStatement, BankTransaction, Reconciliation, FinancialReport, ReportLine, MarketplaceFinanceSettings


class AccountForm(forms.ModelForm):
    class Meta:
        model = Account
        fields = ['code', 'parent', 'name', 'account_type', 'balance']
        widgets = {
            'code': forms.TextInput(attrs={'class': 'form-control', 'placeholder': 'e.g. 1010'}),
            'parent': forms.Select(attrs={'class': 'form-select'}),
            'name': forms.TextInput(attrs={'class': 'form-control', 'placeholder': 'e.g. Cash, Bank — BGFI, Receivables'}),
            'account_type': forms.Select(attrs={'class': 'form-select'}),
            'balance': forms.NumberInput(attrs={'class': 'form-control', 'step': '0.01'}),
        }
        help_texts = {
            'balance': 'Opening balance. Will be adjusted automatically as transactions are recorded.',
        }

    def __init__(self, *args, **kwargs):
        self.company = kwargs.pop('company', None)
        super().__init__(*args, **kwargs)

        if self.company:
            self.fields['parent'].queryset = Account.objects.filter(company=self.company).order_by('code', 'name')
            self.fields['parent'].required = False

    def clean_name(self):
        name = self.cleaned_data['name'].strip()
        if self.company:
            qs = Account.objects.filter(company=self.company, name__iexact=name)
            if self.instance.pk:
                qs = qs.exclude(pk=self.instance.pk)
            if qs.exists():
                raise forms.ValidationError(f'An account named "{name}" already exists.')
        return name


class TransactionForm(forms.ModelForm):
    class Meta:
        model = Transaction
        fields = ['account', 'transaction_type', 'amount', 'description', 'date']
        widgets = {
            'account': forms.Select(attrs={'class': 'form-select'}),
            'transaction_type': forms.Select(attrs={'class': 'form-select'}),
            'amount': forms.NumberInput(attrs={'class': 'form-control', 'min': '0.01', 'step': '0.01'}),
            'description': forms.Textarea(attrs={'class': 'form-control', 'rows': 3}),
            'date': forms.DateInput(attrs={'class': 'form-control', 'type': 'date'}),
        }

    def __init__(self, *args, **kwargs):
        company = kwargs.pop('company', None)
        super().__init__(*args, **kwargs)
        if company:
            self.fields['account'].queryset = Account.objects.filter(
                company=company
            ).order_by('code', 'name')
        self.fields['description'].required = False


class JournalForm(forms.ModelForm):
    """Form to create or edit a journal."""

    class Meta:
        model = Journal
        fields = ['code', 'name', 'journal_type', 'description']
        widgets = {
            'code': forms.TextInput(attrs={'class': 'form-control', 'placeholder': 'e.g. VTE'}),
            'name': forms.TextInput(attrs={'class': 'form-control', 'placeholder': 'e.g. Sales'}),
            'journal_type': forms.Select(attrs={'class': 'form-select'}),
            'description': forms.Textarea(attrs={'class': 'form-control', 'rows': 3}),
        }

    def __init__(self, *args, **kwargs):
        self.company = kwargs.pop('company', None)
        super().__init__(*args, **kwargs)
        self.fields['description'].required = False
        self.fields['code'].required = False

    def clean_name(self):
        name = self.cleaned_data['name'].strip()
        if self.company:
            qs = Journal.objects.filter(company=self.company, name__iexact=name)
            if self.instance.pk:
                qs = qs.exclude(pk=self.instance.pk)
            if qs.exists():
                raise forms.ValidationError(f'A journal named "{name}" already exists.')
        return name


class JournalEntryForm(forms.ModelForm):
    """Form to create or edit a journal entry header."""

    class Meta:
        model = JournalEntry
        fields = ['journal', 'reference', 'description', 'date']
        widgets = {
            'journal': forms.Select(attrs={'class': 'form-select'}),
            'reference': forms.TextInput(attrs={'class': 'form-control', 'placeholder': 'e.g. INV-001'}),
            'description': forms.Textarea(attrs={'class': 'form-control', 'rows': 3}),
            'date': forms.DateInput(attrs={'class': 'form-control', 'type': 'date'}),
        }

    def __init__(self, *args, **kwargs):
        self.company = kwargs.pop('company', None)
        super().__init__(*args, **kwargs)

        if self.company:
            self.fields['journal'].queryset = Journal.objects.filter(
                company=self.company
            ).order_by('journal_type', 'name')

        self.fields['reference'].required = False
        self.fields['description'].required = False


class JournalEntryLineForm(forms.ModelForm):
    """Form for individual lines within a journal entry."""

    class Meta:
        model = JournalEntryLine
        fields = ['account', 'description', 'debit', 'credit']
        widgets = {
            'account': forms.Select(attrs={'class': 'form-select'}),
            'description': forms.TextInput(attrs={'class': 'form-control', 'placeholder': 'Description (optional)'}),
            'debit': forms.NumberInput(attrs={'class': 'form-control text-end', 'min': '0', 'step': '0.01'}),
            'credit': forms.NumberInput(attrs={'class': 'form-control text-end', 'min': '0', 'step': '0.01'}),
        }

    def __init__(self, *args, **kwargs):
        self.company = kwargs.pop('company', None)
        super().__init__(*args, **kwargs)

        if self.company:
            self.fields['account'].queryset = Account.objects.filter(
                company=self.company
            ).order_by('code', 'name')

        self.fields['description'].required = False
        # Set debit/credit to 0 if empty
        for field in ['debit', 'credit']:
            if not self.data and not self.instance.pk:
                self.initial[field] = 0

    def clean(self):
        cleaned_data = super().clean()
        debit = cleaned_data.get('debit') or Decimal('0')
        credit = cleaned_data.get('credit') or Decimal('0')

        if debit <= 0 and credit <= 0:
            raise ValidationError('Each line must have either a debit or a credit amount.')
        if debit > 0 and credit > 0:
            raise ValidationError('A line cannot have both debit and credit.')

        return cleaned_data


class BaseJournalEntryLineFormSet(BaseInlineFormSet):
    """Custom formset to validate that debits equal credits across all lines."""

    def __init__(self, *args, **kwargs):
        self.company = kwargs.pop('company', None)
        super().__init__(*args, **kwargs)

    def _construct_form(self, i, **kwargs):
        """Override to pass company to each form instance."""
        if self.company:
            kwargs['company'] = self.company
        return super()._construct_form(i, **kwargs)

    def clean(self):
        super().clean()

        if any(self.errors):
            return

        total_debits = Decimal('0')
        total_credits = Decimal('0')

        for form in self.forms:
            if self.instance.pk is None and not form.cleaned_data:
                continue

            if form.cleaned_data.get('DELETE'):
                continue

            debit = form.cleaned_data.get('debit') or Decimal('0')
            credit = form.cleaned_data.get('credit') or Decimal('0')
            total_debits += debit
            total_credits += credit

        if not self.forms or (total_debits == 0 and total_credits == 0):
            raise ValidationError('Journal entry must contain at least 1 line with amounts.')

        if total_debits != total_credits:
            raise ValidationError(
                f'Journal entry does not balance. Total debits: {total_debits}, Total credits: {total_credits}'
            )


JournalEntryLineFormSet = inlineformset_factory(
    JournalEntry,
    JournalEntryLine,
    form=JournalEntryLineForm,
    formset=BaseJournalEntryLineFormSet,
    extra=3,
    min_num=2,
    can_delete=True,
)


# ---------------------------------------------------------------------------
# Invoicing Forms (Phase 2)
# ---------------------------------------------------------------------------

class ClientInvoiceForm(forms.ModelForm):
    """Form for creating/editing client invoices."""

    class Meta:
        model = ClientInvoice
        fields = [
            'invoice_number', 'client_name', 'client_address', 'client_email',
            'date', 'due_date', 'tax_rate', 'notes'
        ]
        widgets = {
            'invoice_number': forms.TextInput(attrs={'class': 'form-control', 'placeholder': 'e.g. INV-001'}),
            'client_name': forms.TextInput(attrs={'class': 'form-control'}),
            'client_address': forms.Textarea(attrs={'class': 'form-control', 'rows': 3}),
            'client_email': forms.EmailInput(attrs={'class': 'form-control'}),
            'date': forms.DateInput(attrs={'class': 'form-control', 'type': 'date'}),
            'due_date': forms.DateInput(attrs={'class': 'form-control', 'type': 'date'}),
            'tax_rate': forms.NumberInput(attrs={'class': 'form-control', 'min': '0', 'step': '0.01'}),
            'notes': forms.Textarea(attrs={'class': 'form-control', 'rows': 3}),
        }

    def __init__(self, *args, **kwargs):
        self.company = kwargs.pop('company', None)
        super().__init__(*args, **kwargs)
        self.fields['client_address'].required = False
        self.fields['client_email'].required = False
        self.fields['notes'].required = False


class SupplierInvoiceForm(forms.ModelForm):
    """Form for creating/editing supplier invoices."""

    class Meta:
        model = SupplierInvoice
        fields = [
            'invoice_number', 'supplier_name', 'supplier_address',
            'date', 'due_date', 'tax_rate', 'notes'
        ]
        widgets = {
            'invoice_number': forms.TextInput(attrs={'class': 'form-control', 'placeholder': 'e.g. SUP-001'}),
            'supplier_name': forms.TextInput(attrs={'class': 'form-control'}),
            'supplier_address': forms.Textarea(attrs={'class': 'form-control', 'rows': 3}),
            'date': forms.DateInput(attrs={'class': 'form-control', 'type': 'date'}),
            'due_date': forms.DateInput(attrs={'class': 'form-control', 'type': 'date'}),
            'tax_rate': forms.NumberInput(attrs={'class': 'form-control', 'min': '0', 'step': '0.01'}),
            'notes': forms.Textarea(attrs={'class': 'form-control', 'rows': 3}),
        }

    def __init__(self, *args, **kwargs):
        self.company = kwargs.pop('company', None)
        super().__init__(*args, **kwargs)
        self.fields['supplier_address'].required = False
        self.fields['notes'].required = False


class InvoiceLineForm(forms.ModelForm):
    """Form for invoice line items."""

    class Meta:
        model = InvoiceLine
        fields = ['description', 'quantity', 'unit_price', 'account']
        widgets = {
            'description': forms.TextInput(attrs={'class': 'form-control'}),
            'quantity': forms.NumberInput(attrs={'class': 'form-control text-end', 'min': '0.01', 'step': '0.01'}),
            'unit_price': forms.NumberInput(attrs={'class': 'form-control text-end', 'min': '0', 'step': '0.01'}),
            'account': forms.Select(attrs={'class': 'form-select'}),
        }

    def __init__(self, *args, **kwargs):
        self.company = kwargs.pop('company', None)
        super().__init__(*args, **kwargs)

        if self.company:
            self.fields['account'].queryset = Account.objects.filter(
                company=self.company
            ).order_by('code', 'name')


class BaseInvoiceLineFormSet(BaseInlineFormSet):
    """Custom formset for invoice lines."""

    def __init__(self, *args, **kwargs):
        self.company = kwargs.pop('company', None)
        super().__init__(*args, **kwargs)

    def _construct_form(self, i, **kwargs):
        """Override to pass company to each form instance."""
        if self.company:
            kwargs['company'] = self.company
        return super()._construct_form(i, **kwargs)


ClientInvoiceLineFormSet = inlineformset_factory(
    ClientInvoice,
    InvoiceLine,
    form=InvoiceLineForm,
    formset=BaseInvoiceLineFormSet,
    fk_name='client_invoice',
    extra=2,
    min_num=1,
    can_delete=True,
)

SupplierInvoiceLineFormSet = inlineformset_factory(
    SupplierInvoice,
    InvoiceLine,
    form=InvoiceLineForm,
    formset=BaseInvoiceLineFormSet,
    fk_name='supplier_invoice',
    extra=2,
    min_num=1,
    can_delete=True,
)


# ---------------------------------------------------------------------------
# Bank Reconciliation Forms (Phase 3)
# ---------------------------------------------------------------------------

class BankAccountForm(forms.ModelForm):
    """Form for creating/editing bank accounts."""

    class Meta:
        model = BankAccount
        fields = ['name', 'account_number', 'bank_name', 'account', 'opening_balance']
        widgets = {
            'name': forms.TextInput(attrs={'class': 'form-control'}),
            'account_number': forms.TextInput(attrs={'class': 'form-control'}),
            'bank_name': forms.TextInput(attrs={'class': 'form-control'}),
            'account': forms.Select(attrs={'class': 'form-select'}),
            'opening_balance': forms.NumberInput(attrs={'class': 'form-control', 'step': '0.01'}),
        }

    def __init__(self, *args, **kwargs):
        self.company = kwargs.pop('company', None)
        super().__init__(*args, **kwargs)

        if self.company:
            # Only show asset accounts that are not already linked to bank accounts
            used_accounts = BankAccount.objects.filter(company=self.company).values_list('account_id', flat=True)
            self.fields['account'].queryset = Account.objects.filter(
                company=self.company,
                account_type='asset'
            ).exclude(id__in=used_accounts).order_by('code', 'name')


class BankStatementUploadForm(forms.Form):
    """Form for uploading bank statements."""

    bank_account = forms.ModelChoiceField(
        queryset=BankAccount.objects.none(),
        widget=forms.Select(attrs={'class': 'form-select'}),
        label="Bank Account"
    )
    statement_file = forms.FileField(
        widget=forms.FileInput(attrs={'class': 'form-control'}),
        label="Statement File (CSV or MT940)"
    )
    statement_date = forms.DateField(
        widget=forms.DateInput(attrs={'class': 'form-control', 'type': 'date'}),
        label="Statement Date"
    )

    def __init__(self, *args, **kwargs):
        self.company = kwargs.pop('company', None)
        super().__init__(*args, **kwargs)

        if self.company:
            self.fields['bank_account'].queryset = BankAccount.objects.filter(company=self.company)


class ReconciliationForm(forms.ModelForm):
    """Form for bank reconciliation."""

    class Meta:
        model = Reconciliation
        fields = ['bank_account', 'statement', 'reconciled_date', 'bank_balance', 'book_balance']
        widgets = {
            'bank_account': forms.Select(attrs={'class': 'form-select'}),
            'statement': forms.Select(attrs={'class': 'form-select'}),
            'reconciled_date': forms.DateInput(attrs={'class': 'form-control', 'type': 'date'}),
            'bank_balance': forms.NumberInput(attrs={'class': 'form-control', 'step': '0.01'}),
            'book_balance': forms.NumberInput(attrs={'class': 'form-control', 'step': '0.01'}),
        }

    def __init__(self, *args, **kwargs):
        self.company = kwargs.pop('company', None)
        super().__init__(*args, **kwargs)

        if self.company:
            self.fields['bank_account'].queryset = BankAccount.objects.filter(company=self.company)
            self.fields['statement'].queryset = BankStatement.objects.filter(
                bank_account__company=self.company
            ).order_by('-statement_date')


class TransactionMatchingForm(forms.Form):
    """Form for matching bank transactions to accounting transactions."""

    bank_transaction = forms.ModelChoiceField(
        queryset=BankTransaction.objects.none(),
        widget=forms.HiddenInput()
    )
    accounting_transaction = forms.ModelChoiceField(
        queryset=Transaction.objects.none(),
        widget=forms.Select(attrs={'class': 'form-select'}),
        required=False,
        label="Match to Transaction"
    )

    def __init__(self, *args, **kwargs):
        self.company = kwargs.pop('company', None)
        self.bank_transaction = kwargs.pop('bank_transaction', None)
        super().__init__(*args, **kwargs)

        if self.company and self.bank_transaction:
            self.fields['bank_transaction'].queryset = BankTransaction.objects.filter(
                statement__bank_account__company=self.company
            )
            self.fields['accounting_transaction'].queryset = Transaction.objects.filter(
                company=self.company,
                date__range=[
                    self.bank_transaction.date - timedelta(days=7),
                    self.bank_transaction.date + timedelta(days=7)
                ]
            ).order_by('-date')


# ---------------------------------------------------------------------------
# Financial Reports Forms (Phase 3)
# ---------------------------------------------------------------------------

class FinancialReportForm(forms.Form):
    """Form for generating financial reports."""

    report_type = forms.ChoiceField(
        choices=[
            ('balance_sheet', 'Balance Sheet'),
            ('income_statement', 'Income Statement'),
            ('cash_flow', 'Cash Flow Statement'),
        ],
        widget=forms.Select(attrs={'class': 'form-select'}),
        label="Report Type"
    )
    report_date = forms.DateField(
        widget=forms.DateInput(attrs={'class': 'form-control', 'type': 'date'}),
        label="Report Date"
    )
    start_date = forms.DateField(
        widget=forms.DateInput(attrs={'class': 'form-control', 'type': 'date'}),
        required=False,
        label="Start Date (optional)"
    )
    end_date = forms.DateField(
        widget=forms.DateInput(attrs={'class': 'form-control', 'type': 'date'}),
        required=False,
        label="End Date (optional)"
    )


class MarketplaceFinanceSettingsForm(forms.ModelForm):
    """Configure how marketplace orders map into finance."""

    class Meta:
        model = MarketplaceFinanceSettings
        fields = [
            'sales_journal',
            'receivable_account',
            'revenue_account',
            'tax_account',
            'is_enabled',
        ]
        widgets = {
            'sales_journal': forms.Select(attrs={'class': 'form-select'}),
            'receivable_account': forms.Select(attrs={'class': 'form-select'}),
            'revenue_account': forms.Select(attrs={'class': 'form-select'}),
            'tax_account': forms.Select(attrs={'class': 'form-select'}),
            'is_enabled': forms.CheckboxInput(attrs={'class': 'form-check-input'}),
        }

    def __init__(self, *args, **kwargs):
        self.company = kwargs.pop('company', None)
        super().__init__(*args, **kwargs)

        self.fields['tax_account'].required = False

        if self.company:
            self.instance.company = self.company
            self.fields['sales_journal'].queryset = Journal.objects.filter(
                company=self.company,
                journal_type__in=('sales', 'general'),
            ).order_by('journal_type', 'name')
            self.fields['receivable_account'].queryset = Account.objects.filter(
                company=self.company,
                account_type='asset',
            ).order_by('code', 'name')
            self.fields['revenue_account'].queryset = Account.objects.filter(
                company=self.company,
                account_type='revenue',
            ).order_by('code', 'name')
            self.fields['tax_account'].queryset = Account.objects.filter(
                company=self.company,
                account_type='liability',
            ).order_by('code', 'name')

    def save(self, commit=True):
        instance = super().save(commit=False)
        if self.company:
            instance.company = self.company
        if commit:
            instance.save()
        return instance
