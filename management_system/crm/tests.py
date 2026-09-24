from django.core.exceptions import ValidationError
from django.test import TestCase
from accounts.models import Company
from employees.models import Employee
from finance.models import Account, Transaction
from .models import Contact, Note, Opportunity


class CRMModelTests(TestCase):
    def setUp(self):
        self.company = Company.objects.create(name='CRMCo', domain='crmco')
        self.contact = Contact.objects.create(company=self.company, name='Alice', email='alice@example.com')

    def test_opportunity_str(self):
        opp = Opportunity.objects.create(
            company=self.company,
            contact=self.contact,
            title='Big Deal',
            value=10000,
        )
        self.assertEqual(str(opp), 'Big Deal (Alice)')
        # stage helpers
        self.assertFalse(opp.is_won)
        opp.advance_stage('won')
        self.assertTrue(opp.is_won)
        with self.assertRaises(ValueError):
            opp.advance_stage('invalid_stage')

    def test_opportunity_rejects_cross_company_links(self):
        other_company = Company.objects.create(name='Other CRMCo', domain='other-crmco')
        other_contact = Contact.objects.create(company=other_company, name='Other Contact')
        with self.assertRaises(ValidationError):
            Opportunity(
                company=self.company,
                contact=other_contact,
                title='Cross-company deal',
            ).full_clean()

    def test_opportunity_rejects_cross_company_employee_and_revenue(self):
        other_company = Company.objects.create(name='Other CRMCo', domain='other-crmco')
        employee = Employee.objects.create(
            company=other_company,
            first_name='Other',
            last_name='Employee',
            employee_id='OTHER-1',
            date_joined='2026-09-23',
        )
        account = Account.objects.create(company=other_company, name='Other Revenue', account_type='revenue')
        transaction = Transaction.objects.create(
            company=other_company,
            account=account,
            transaction_type='credit',
            amount=100,
            date='2026-09-23',
        )
        with self.assertRaises(ValidationError) as context:
            Opportunity(
                company=self.company,
                contact=self.contact,
                assigned_to=employee,
                revenue_transaction=transaction,
                title='Cross-company links',
            ).full_clean()
        self.assertIn('assigned_to', context.exception.message_dict)
        self.assertIn('revenue_transaction', context.exception.message_dict)

    def test_note_rejects_cross_company_contact(self):
        other_company = Company.objects.create(name='Other CRMCo', domain='other-crmco')
        other_contact = Contact.objects.create(company=other_company, name='Other Contact')
        with self.assertRaises(ValidationError):
            Note(company=self.company, contact=other_contact, content='Invalid note').full_clean()
