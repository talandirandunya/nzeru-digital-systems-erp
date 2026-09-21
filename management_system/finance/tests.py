from django.test import TestCase, override_settings
from django.contrib.auth import get_user_model
from django.urls import reverse
from decimal import Decimal
from django.core.exceptions import ValidationError
from accounts.models import Company
from .models import Account, Transaction, Journal, MarketplaceFinanceSettings, ClientInvoice, InvoiceLine
from .forms import MarketplaceFinanceSettingsForm

User = get_user_model()


class FinanceModelTests(TestCase):
    def setUp(self):
        self.company = Company.objects.create(name='TestCo', domain='testco')
        # create user with required fields using custom manager
        self.user = User.objects.create_user(
            email='user1@example.com',
            password='password',
            company=self.company,
            first_name='User',
            last_name='One'
        )
        self.account = Account.objects.create(company=self.company, name='Cash', balance=1000)

    def test_transaction_creation(self):
        txn = Transaction.objects.create(
            company=self.company,
            account=self.account,
            transaction_type='credit',
            amount=50,
            date='2026-01-01',
            entered_by=self.user,
        )
        self.assertEqual(str(txn), 'credit 50 on Cash')
        # balance should have been updated on save
        self.account.refresh_from_db()
        self.assertEqual(self.account.balance, 1050)
        # updating amount adjusts balance further
        txn.amount = 100
        txn.save()
        self.account.refresh_from_db()
        self.assertEqual(self.account.balance, 1100)

    def test_balance_adjust_on_delete(self):
        txn = Transaction.objects.create(
            company=self.company,
            account=self.account,
            transaction_type='debit',
            amount=100,
            date='2026-01-02',
            entered_by=self.user,
        )
        self.account.refresh_from_db()
        self.assertEqual(self.account.balance, 900)
        txn.delete()
        self.account.refresh_from_db()
        self.assertEqual(self.account.balance, 1000)


class MarketplaceFinanceSettingsModelTests(TestCase):
    def setUp(self):
        self.company = Company.objects.create(name='SettingsCo', domain='settingsco')
        self.other_company = Company.objects.create(name='OtherCo', domain='otherco')
        self.sales_journal = Journal.objects.create(company=self.company, name='Sales Journal', journal_type='sales')
        self.receivable_account = Account.objects.create(
            company=self.company,
            name='Marketplace Receivable',
            account_type='asset',
        )
        self.revenue_account = Account.objects.create(
            company=self.company,
            name='Marketplace Revenue',
            account_type='revenue',
        )
        self.other_company_account = Account.objects.create(
            company=self.other_company,
            name='Other Revenue',
            account_type='revenue',
        )

    def test_marketplace_settings_accept_valid_company_mapping(self):
        settings_obj = MarketplaceFinanceSettings.objects.create(
            company=self.company,
            sales_journal=self.sales_journal,
            receivable_account=self.receivable_account,
            revenue_account=self.revenue_account,
            is_enabled=True,
        )
        self.assertEqual(settings_obj.company, self.company)

    def test_marketplace_settings_reject_cross_company_account(self):
        settings_obj = MarketplaceFinanceSettings(
            company=self.company,
            sales_journal=self.sales_journal,
            receivable_account=self.receivable_account,
            revenue_account=self.other_company_account,
        )

        with self.assertRaises(ValidationError):
            settings_obj.full_clean()


class MarketplaceFinanceSettingsFormTests(TestCase):
    def setUp(self):
        self.company = Company.objects.create(name='FormCo', domain='formco')
        self.other_company = Company.objects.create(name='Elsewhere', domain='elsewhere')
        self.sales_journal = Journal.objects.create(company=self.company, name='Sales Journal', journal_type='sales')
        self.general_journal = Journal.objects.create(company=self.company, name='General Journal', journal_type='general')
        self.other_journal = Journal.objects.create(company=self.other_company, name='Other Journal', journal_type='sales')
        self.receivable_account = Account.objects.create(company=self.company, name='Receivable', account_type='asset')
        self.revenue_account = Account.objects.create(company=self.company, name='Revenue', account_type='revenue')
        self.tax_account = Account.objects.create(company=self.company, name='VAT Payable', account_type='liability')
        self.other_account = Account.objects.create(company=self.other_company, name='Other Asset', account_type='asset')

    def test_form_limits_journals_and_accounts_to_company(self):
        form = MarketplaceFinanceSettingsForm(company=self.company)

        self.assertEqual(list(form.fields['sales_journal'].queryset), [self.general_journal, self.sales_journal])
        self.assertEqual(list(form.fields['receivable_account'].queryset), [self.receivable_account])
        self.assertEqual(list(form.fields['revenue_account'].queryset), [self.revenue_account])
        self.assertEqual(list(form.fields['tax_account'].queryset), [self.tax_account])
        self.assertNotIn(self.other_journal, form.fields['sales_journal'].queryset)
        self.assertNotIn(self.other_account, form.fields['receivable_account'].queryset)


@override_settings(
    ALLOWED_HOSTS=['testserver', 'localhost', '127.0.0.1'],
    SECURE_SSL_REDIRECT=False,
)
class MarketplaceFinanceSettingsViewTests(TestCase):
    def setUp(self):
        self.company = Company.objects.create(name='ViewCo', domain='viewco')
        self.user = User.objects.create_user(
            email='accountant@example.com',
            password='password',
            company=self.company,
            first_name='View',
            last_name='User',
            role='accountant',
        )
        self.sales_journal = Journal.objects.create(company=self.company, name='Sales Journal', journal_type='sales')
        self.receivable_account = Account.objects.create(
            company=self.company,
            code='1100',
            name='Marketplace Receivable',
            account_type='asset',
            balance=Decimal('0.00'),
        )
        self.revenue_account = Account.objects.create(
            company=self.company,
            code='4100',
            name='Marketplace Revenue',
            account_type='revenue',
            balance=Decimal('0.00'),
        )

    def test_view_creates_company_settings(self):
        self.client.force_login(self.user)

        response = self.client.post(
            reverse('finance:marketplace_finance_settings'),
            {
                'sales_journal': self.sales_journal.pk,
                'receivable_account': self.receivable_account.pk,
                'revenue_account': self.revenue_account.pk,
                'tax_account': '',
                'is_enabled': 'on',
            },
            follow=True,
        )

        self.assertRedirects(response, reverse('finance:marketplace_finance_settings'))
        settings_obj = MarketplaceFinanceSettings.objects.get(company=self.company)
        self.assertEqual(settings_obj.sales_journal, self.sales_journal)
        self.assertTrue(settings_obj.is_enabled)


class ClientInvoicePrintViewTests(TestCase):
    def setUp(self):
        self.company = Company.objects.create(name='PrintCo', domain='printco')
        self.user = User.objects.create_user(
            email='finance_user@example.com',
            password='password',
            company=self.company,
            first_name='Finance',
            last_name='User',
            role='accountant',
        )
        self.account = Account.objects.create(
            company=self.company,
            name='Sales Revenue',
            account_type='revenue',
        )
        self.invoice = ClientInvoice.objects.create(
            company=self.company,
            invoice_number='2026-0001',
            client_name='Test Client',
            date='2026-07-24',
            due_date='2026-08-24',
            status='draft',
        )
        self.line = InvoiceLine.objects.create(
            client_invoice=self.invoice,
            description='Test item',
            quantity=2,
            unit_price=Decimal('100.00'),
            line_total=Decimal('200.00'),
            account=self.account,
        )

    def test_print_view_status_code(self):
        self.client.force_login(self.user)
        response = self.client.get(reverse('finance:client_invoice_print', kwargs={'pk': self.invoice.pk}))
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, 'PROFORMA INVOICE')

    def test_print_view_invoice_type(self):
        self.client.force_login(self.user)
        response = self.client.get(
            reverse('finance:client_invoice_print', kwargs={'pk': self.invoice.pk}) + '?type=invoice'
        )
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, 'INVOICE')
