from django.test import TestCase
from accounts.models import Company
from .models import Contact, Opportunity


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
