from decimal import Decimal

from django.contrib.auth import get_user_model
from django.test import Client as HttpClient, TestCase, override_settings
from django.urls import reverse

from accounts.models import Company
from inventory.models import Stock
from finance.models import Account, Journal, JournalEntry, JournalEntryLine, MarketplaceFinanceSettings, Transaction
from marketplace.models import Cart, CartItem, Client, Order


@override_settings(
    ALLOWED_HOSTS=['testserver', 'localhost', '127.0.0.1'],
    SECURE_SSL_REDIRECT=False,
)
class MarketplaceSingleCompanyOrderTests(TestCase):
    def setUp(self):
        self.http_client = HttpClient()
        self.company_a = Company.objects.create(
            name='Alpha Stores',
            domain='alpha',
            contact_email='alpha@example.com',
        )
        self.company_b = Company.objects.create(
            name='Beta Stores',
            domain='beta',
            contact_email='beta@example.com',
        )
        self.client_user = Client.objects.create(
            email='buyer@example.com',
            password='hashed',
            first_name='Buyer',
            last_name='One',
        )
        self.cart = Cart.objects.create(client=self.client_user)
        self.stock_a = Stock.objects.create(
            company=self.company_a,
            item_code='ALPHA-1',
            name='Alpha Product',
            category=None,
            quantity=10,
            unit='pcs',
            cost_price=Decimal('10.00'),
            selling_price=Decimal('25.00'),
            reorder_level=1,
            supplier_name='Supplier A',
        )
        self.stock_b = Stock.objects.create(
            company=self.company_b,
            item_code='BETA-1',
            name='Beta Product',
            category=None,
            quantity=10,
            unit='pcs',
            cost_price=Decimal('12.00'),
            selling_price=Decimal('30.00'),
            reorder_level=1,
            supplier_name='Supplier B',
        )

        session = self.http_client.session
        session['client_id'] = self.client_user.id
        session.save()

    def test_add_to_cart_blocks_second_company(self):
        CartItem.objects.create(cart=self.cart, stock=self.stock_a, quantity=1)

        response = self.http_client.post(
            reverse('marketplace:add_to_cart', args=[self.stock_b.pk]),
            {'quantity': 1},
            follow=True,
        )

        self.assertRedirects(response, reverse('marketplace:view_cart'))
        self.assertFalse(CartItem.objects.filter(cart=self.cart, stock=self.stock_b).exists())
        messages = [message.message for message in response.context['messages']]
        self.assertTrue(any('clear the cart' in message.lower() for message in messages))

    def test_checkout_creates_order_with_company(self):
        CartItem.objects.create(cart=self.cart, stock=self.stock_a, quantity=2)

        response = self.http_client.post(
            reverse('marketplace:checkout'),
            {
                'shipping_address': '1 Example Road',
                'shipping_city': 'Lagos',
                'shipping_country': 'Nigeria',
                'shipping_phone': '+23400000000',
                'notes': 'Handle with care',
            },
            follow=False,
        )

        order = Order.objects.get()
        self.assertRedirects(response, reverse('marketplace:payment_gateway', kwargs={'pk': order.pk}))
        self.assertEqual(order.company, self.company_a)
        self.assertEqual(order.total, Decimal('50.00'))
        self.stock_a.refresh_from_db()
        self.assertEqual(self.stock_a.quantity, 8)

    def test_checkout_rejects_mixed_company_cart(self):
        CartItem.objects.create(cart=self.cart, stock=self.stock_a, quantity=1)
        CartItem.objects.create(cart=self.cart, stock=self.stock_b, quantity=1)

        response = self.http_client.get(reverse('marketplace:checkout'), follow=True)

        self.assertRedirects(response, reverse('marketplace:view_cart'))
        self.assertEqual(Order.objects.count(), 0)
        messages = [message.message for message in response.context['messages']]
        self.assertTrue(any('multiple companies' in message.lower() for message in messages))


@override_settings(
    ALLOWED_HOSTS=['testserver', 'localhost', '127.0.0.1'],
    SECURE_SSL_REDIRECT=False,
)
class MarketplaceAdminCompanyScopeTests(TestCase):
    def setUp(self):
        user_model = get_user_model()
        self.http_client = HttpClient()
        self.company_a = Company.objects.create(
            name='Alpha Stores',
            domain='alpha-admin',
            contact_email='alpha-admin@example.com',
        )
        self.company_b = Company.objects.create(
            name='Beta Stores',
            domain='beta-admin',
            contact_email='beta-admin@example.com',
        )
        self.admin_user = user_model.objects.create_user(
            email='admin@alpha.com',
            password='password123',
            first_name='Alpha',
            last_name='Admin',
            company=self.company_a,
            is_company_admin=True,
            role='admin',
        )
        self.client_user = Client.objects.create(
            email='buyer-admin@example.com',
            password='hashed',
            first_name='Buyer',
            last_name='Admin',
        )
        self.order_a = Order.objects.create(
            order_number='ORD-A',
            client=self.client_user,
            company=self.company_a,
            subtotal=Decimal('25.00'),
            tax=Decimal('0.00'),
            shipping=Decimal('0.00'),
            total=Decimal('25.00'),
            shipping_address='1 Example Road',
            shipping_city='Lagos',
            shipping_country='Nigeria',
            shipping_phone='+23400000000',
        )
        self.order_b = Order.objects.create(
            order_number='ORD-B',
            client=self.client_user,
            company=self.company_b,
            subtotal=Decimal('30.00'),
            tax=Decimal('0.00'),
            shipping=Decimal('0.00'),
            total=Decimal('30.00'),
            shipping_address='2 Example Road',
            shipping_city='Abuja',
            shipping_country='Nigeria',
            shipping_phone='+23411111111',
        )

    def test_admin_order_list_shows_only_own_company_orders(self):
        self.http_client.force_login(self.admin_user)

        response = self.http_client.get(reverse('marketplace:admin_order_list'))

        orders = list(response.context['orders'])
        self.assertEqual(orders, [self.order_a])

    def test_admin_cannot_access_other_company_order(self):
        self.http_client.force_login(self.admin_user)

        response = self.http_client.get(reverse('marketplace:admin_order_detail', args=[self.order_b.pk]))

        self.assertEqual(response.status_code, 404)


@override_settings(
    ALLOWED_HOSTS=['testserver', 'localhost', '127.0.0.1'],
    SECURE_SSL_REDIRECT=False,
)
class MarketplaceFinancePostingTests(TestCase):
    def setUp(self):
        user_model = get_user_model()
        self.http_client = HttpClient()
        self.company = Company.objects.create(
            name='Posting Co',
            domain='posting-co',
            contact_email='posting@example.com',
        )
        self.admin_user = user_model.objects.create_user(
            email='posting-admin@example.com',
            password='password123',
            first_name='Posting',
            last_name='Admin',
            company=self.company,
            is_company_admin=True,
            role='admin',
        )
        self.client_user = Client.objects.create(
            email='posting-buyer@example.com',
            password='hashed',
            first_name='Posting',
            last_name='Buyer',
        )
        self.order = Order.objects.create(
            order_number='ORD-POST-1',
            client=self.client_user,
            company=self.company,
            subtotal=Decimal('100.00'),
            tax=Decimal('10.00'),
            shipping=Decimal('5.00'),
            total=Decimal('115.00'),
            shipping_address='1 Finance Street',
            shipping_city='Lagos',
            shipping_country='Nigeria',
            shipping_phone='+23499999999',
        )
        self.sales_journal = Journal.objects.create(
            company=self.company,
            name='Marketplace Sales',
            journal_type='sales',
        )
        self.receivable_account = Account.objects.create(
            company=self.company,
            code='1100',
            name='Marketplace Receivable',
            account_type='asset',
        )
        self.revenue_account = Account.objects.create(
            company=self.company,
            code='4100',
            name='Marketplace Revenue',
            account_type='revenue',
        )
        self.tax_account = Account.objects.create(
            company=self.company,
            code='2200',
            name='VAT Payable',
            account_type='liability',
        )

    def test_mark_paid_posts_balanced_journal_entry(self):
        MarketplaceFinanceSettings.objects.create(
            company=self.company,
            sales_journal=self.sales_journal,
            receivable_account=self.receivable_account,
            revenue_account=self.revenue_account,
            tax_account=self.tax_account,
            is_enabled=True,
        )
        self.http_client.force_login(self.admin_user)

        response = self.http_client.post(
            reverse('marketplace:admin_order_update_payment', args=[self.order.pk]),
            {'payment_status': 'paid'},
            follow=True,
        )

        self.assertRedirects(response, reverse('marketplace:admin_order_detail', args=[self.order.pk]))
        self.order.refresh_from_db()
        self.assertEqual(self.order.payment_status, 'paid')
        self.assertEqual(self.order.finance_sync_status, 'posted')
        self.assertIsNotNone(self.order.finance_journal_entry)

        entry = self.order.finance_journal_entry
        self.assertEqual(entry.reference, self.order.order_number)
        lines = list(entry.lines.order_by('id'))
        self.assertEqual(len(lines), 3)
        self.assertEqual(lines[0].account, self.receivable_account)
        self.assertEqual(lines[0].debit, Decimal('115.00'))
        self.assertEqual(lines[1].account, self.revenue_account)
        self.assertEqual(lines[1].credit, Decimal('105.00'))
        self.assertEqual(lines[2].account, self.tax_account)
        self.assertEqual(lines[2].credit, Decimal('10.00'))
        self.assertEqual(Transaction.objects.count(), 3)
        self.receivable_account.refresh_from_db()
        self.revenue_account.refresh_from_db()
        self.tax_account.refresh_from_db()
        self.assertEqual(self.receivable_account.balance, Decimal('115.00'))
        self.assertEqual(self.revenue_account.balance, Decimal('105.00'))
        self.assertEqual(self.tax_account.balance, Decimal('10.00'))

    def test_mark_paid_is_idempotent(self):
        MarketplaceFinanceSettings.objects.create(
            company=self.company,
            sales_journal=self.sales_journal,
            receivable_account=self.receivable_account,
            revenue_account=self.revenue_account,
            tax_account=self.tax_account,
            is_enabled=True,
        )
        self.http_client.force_login(self.admin_user)

        url = reverse('marketplace:admin_order_update_payment', args=[self.order.pk])
        self.http_client.post(url, {'payment_status': 'paid'}, follow=True)
        self.http_client.post(url, {'payment_status': 'paid'}, follow=True)

        self.order.refresh_from_db()
        self.assertEqual(JournalEntry.objects.count(), 1)
        self.assertEqual(JournalEntryLine.objects.count(), 3)
        self.assertEqual(self.order.finance_sync_status, 'posted')

    def test_mark_paid_records_sync_failure_when_settings_missing(self):
        self.http_client.force_login(self.admin_user)

        response = self.http_client.post(
            reverse('marketplace:admin_order_update_payment', args=[self.order.pk]),
            {'payment_status': 'paid'},
            follow=True,
        )

        self.assertRedirects(response, reverse('marketplace:admin_order_detail', args=[self.order.pk]))
        self.order.refresh_from_db()
        self.assertEqual(self.order.payment_status, 'paid')
        self.assertEqual(self.order.finance_sync_status, 'failed')
        self.assertIsNone(self.order.finance_journal_entry)
        self.assertIn('not configured', self.order.finance_sync_error.lower())
        self.assertEqual(JournalEntry.objects.count(), 0)

    def test_mark_refunded_creates_reversal_entry(self):
        MarketplaceFinanceSettings.objects.create(
            company=self.company,
            sales_journal=self.sales_journal,
            receivable_account=self.receivable_account,
            revenue_account=self.revenue_account,
            tax_account=self.tax_account,
            is_enabled=True,
        )
        self.http_client.force_login(self.admin_user)
        url = reverse('marketplace:admin_order_update_payment', args=[self.order.pk])

        self.http_client.post(url, {'payment_status': 'paid'}, follow=True)
        response = self.http_client.post(url, {'payment_status': 'refunded'}, follow=True)

        self.assertRedirects(response, reverse('marketplace:admin_order_detail', args=[self.order.pk]))
        self.order.refresh_from_db()
        self.assertEqual(self.order.payment_status, 'refunded')
        self.assertEqual(self.order.finance_sync_status, 'reversed')
        self.assertIsNotNone(self.order.finance_reversal_journal_entry)
        self.assertEqual(JournalEntry.objects.count(), 2)
        reversal_lines = {
            line.account_id: line
            for line in self.order.finance_reversal_journal_entry.lines.all()
        }
        self.assertEqual(len(reversal_lines), 3)
        self.assertEqual(reversal_lines[self.receivable_account.id].credit, Decimal('115.00'))
        self.assertEqual(reversal_lines[self.revenue_account.id].debit, Decimal('105.00'))
        self.assertEqual(reversal_lines[self.tax_account.id].debit, Decimal('10.00'))
        self.assertEqual(Transaction.objects.count(), 6)
        self.receivable_account.refresh_from_db()
        self.revenue_account.refresh_from_db()
        self.tax_account.refresh_from_db()
        self.assertEqual(self.receivable_account.balance, Decimal('0.00'))
        self.assertEqual(self.revenue_account.balance, Decimal('0.00'))
        self.assertEqual(self.tax_account.balance, Decimal('0.00'))

    def test_cancelling_paid_order_creates_finance_reversal(self):
        stock = Stock.objects.create(
            company=self.company,
            item_code='POST-STOCK',
            name='Posted Item',
            category=None,
            quantity=2,
            unit='pcs',
            cost_price=Decimal('40.00'),
            selling_price=Decimal('100.00'),
            reorder_level=1,
            supplier_name='Supplier',
        )
        self.order.items.create(
            stock=stock,
            item_name=stock.name,
            item_code=stock.item_code,
            quantity=1,
            unit_price=Decimal('100.00'),
            subtotal=Decimal('100.00'),
        )
        stock.quantity = 1
        stock.save(update_fields=['quantity'])
        MarketplaceFinanceSettings.objects.create(
            company=self.company,
            sales_journal=self.sales_journal,
            receivable_account=self.receivable_account,
            revenue_account=self.revenue_account,
            tax_account=self.tax_account,
            is_enabled=True,
        )
        self.http_client.force_login(self.admin_user)
        payment_url = reverse('marketplace:admin_order_update_payment', args=[self.order.pk])
        cancel_url = reverse('marketplace:admin_order_cancel', args=[self.order.pk])

        self.http_client.post(payment_url, {'payment_status': 'paid'}, follow=True)
        response = self.http_client.post(cancel_url, follow=True)

        self.assertRedirects(response, reverse('marketplace:admin_order_detail', args=[self.order.pk]))
        self.order.refresh_from_db()
        stock.refresh_from_db()
        self.assertEqual(self.order.status, 'cancelled')
        self.assertEqual(self.order.payment_status, 'refunded')
        self.assertEqual(self.order.finance_sync_status, 'reversed')
        self.assertEqual(stock.quantity, 2)
        self.assertEqual(JournalEntry.objects.count(), 2)

    def test_posted_order_cannot_switch_directly_to_failed(self):
        MarketplaceFinanceSettings.objects.create(
            company=self.company,
            sales_journal=self.sales_journal,
            receivable_account=self.receivable_account,
            revenue_account=self.revenue_account,
            tax_account=self.tax_account,
            is_enabled=True,
        )
        self.http_client.force_login(self.admin_user)
        url = reverse('marketplace:admin_order_update_payment', args=[self.order.pk])

        self.http_client.post(url, {'payment_status': 'paid'}, follow=True)
        response = self.http_client.post(url, {'payment_status': 'failed'}, follow=True)

        self.assertRedirects(response, reverse('marketplace:admin_order_detail', args=[self.order.pk]))
        self.order.refresh_from_db()
        self.assertEqual(self.order.payment_status, 'paid')
        self.assertEqual(self.order.finance_sync_status, 'posted')
        self.assertEqual(JournalEntry.objects.count(), 1)

    def test_reversed_order_cannot_switch_back_to_failed(self):
        MarketplaceFinanceSettings.objects.create(
            company=self.company,
            sales_journal=self.sales_journal,
            receivable_account=self.receivable_account,
            revenue_account=self.revenue_account,
            tax_account=self.tax_account,
            is_enabled=True,
        )
        self.http_client.force_login(self.admin_user)
        url = reverse('marketplace:admin_order_update_payment', args=[self.order.pk])

        self.http_client.post(url, {'payment_status': 'paid'}, follow=True)
        self.http_client.post(url, {'payment_status': 'refunded'}, follow=True)
        response = self.http_client.post(url, {'payment_status': 'failed'}, follow=True)

        self.assertRedirects(response, reverse('marketplace:admin_order_detail', args=[self.order.pk]))
        self.order.refresh_from_db()
        self.assertEqual(self.order.payment_status, 'refunded')
        self.assertEqual(self.order.finance_sync_status, 'reversed')
        self.assertIsNotNone(self.order.finance_reversal_journal_entry)
        self.assertEqual(JournalEntry.objects.count(), 2)
