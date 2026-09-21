from django.test import TestCase

from accounts.forms import InvitationAcceptForm


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
