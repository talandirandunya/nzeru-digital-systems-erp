from django.test import TestCase

from accounts.forms import InvitationAcceptForm
from accounts.models import Company, User


class InvitationAcceptanceTests(TestCase):
    def test_invitation_accept_form_allows_short_local_phone_numbers(self):
        form = InvitationAcceptForm(data={
            'first_name': 'Ada',
            'last_name': 'Smith',
            'phone': '12345',
            'password1': 'StrongPass123',
            'password2': 'StrongPass123',
        })

        self.assertTrue(form.is_valid(), form.errors)


class CompanyLoginCompatibilityTests(TestCase):
    def test_legacy_accounts_login_route_authenticates_company_user(self):
        company = Company.objects.create(
            name='Nzeru Digital Systems',
            domain='nzeru-digital-systems',
            contact_email='hello@nzeru.io',
        )
        user = User.objects.create_user(
            email='ndegejoel2000@gmail.com',
            password='Ndegejoel2000..',
            company=company,
            first_name='Joel',
            last_name='Ndege',
            is_company_admin=True,
            role='admin',
            is_active=True,
        )

        response = self.client.post(
            '/accounts/login/',
            {
                'company_domain': 'nzeru-digital-systems',
                'username': 'ndegejoel2000@gmail.com',
                'password': 'Ndegejoel2000..',
            },
        )

        self.assertEqual(response.status_code, 302)
        self.assertNotIn('/login/?next=/accounts/login/', response.url)
        self.assertTrue(response.wsgi_request.user.is_authenticated)
        self.assertEqual(response.wsgi_request.user.email, user.email)
