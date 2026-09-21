from django import forms
from django.contrib.auth.forms import UserCreationForm, AuthenticationForm
from django.contrib.auth import authenticate
from django.core.exceptions import ValidationError

from .models import User, Company, Invitation, CompanyEmailSettings
from employees.models import Employee
from marketplace.models import CompanyPaymentSettings


# ---------------------------------------------------------------------------
# Shared widget defaults
# ---------------------------------------------------------------------------

_PASSWORD_WIDGET = forms.PasswordInput(attrs={'autocomplete': 'new-password'})
_CURRENT_PASSWORD_WIDGET = forms.PasswordInput(attrs={'autocomplete': 'current-password'})


# ---------------------------------------------------------------------------
# Company registration
# ---------------------------------------------------------------------------

class CompanyCreationForm(forms.ModelForm):
    """Register a new company and its initial admin user in one step."""

    admin_first_name = forms.CharField(max_length=30)
    admin_last_name = forms.CharField(max_length=30)
    admin_email = forms.EmailField()
    admin_password = forms.CharField(
        widget=_PASSWORD_WIDGET,
        label='Admin Password',
        min_length=8,
    )
    confirm_admin_password = forms.CharField(
        widget=_PASSWORD_WIDGET,
        label='Confirm Admin Password',
    )

    class Meta:
        model = Company
        fields = ['name', 'domain', 'contact_email', 'contact_phone', 'address']
        widgets = {
            'address': forms.Textarea(attrs={'rows': 3}),
        }

    def clean_domain(self):
        domain = self.cleaned_data['domain'].lower().strip()
        if Company.objects.filter(domain=domain).exists():
            raise ValidationError('This domain is already taken.')
        return domain

    def clean_admin_email(self):
        email = self.cleaned_data['admin_email'].lower().strip()
        if User.objects.filter(email=email).exists():
            raise ValidationError('This email is already registered.')
        return email

    def clean(self):
        cleaned_data = super().clean()
        admin_pw = cleaned_data.get('admin_password')
        confirm_admin = cleaned_data.get('confirm_admin_password')
        if admin_pw and confirm_admin and admin_pw != confirm_admin:
            self.add_error('confirm_admin_password', 'Admin passwords do not match.')
        return cleaned_data

    def save(self, commit=True):
        company = super().save(commit=False)
        if commit:
            company.save()
        return company


# ---------------------------------------------------------------------------
# Invitation forms
# ---------------------------------------------------------------------------

class InvitationForm(forms.Form):
    """Admin sends an invitation to an email address."""

    email = forms.EmailField(
        label='Email address',
        widget=forms.EmailInput(attrs={'placeholder': 'colleague@example.com'}),
    )
    employee = forms.ModelChoiceField(
        queryset=Employee.objects.none(),
        required=False,
        label='Link existing employee (optional)',
        help_text='Select an unlinked employee in this company if this invitation should map to an existing HR record.',
    )

    def __init__(self, company, *args, **kwargs):
        self.company = company
        super().__init__(*args, **kwargs)
        self.fields['employee'].queryset = (
            Employee.objects.filter(company=company, user__isnull=True).order_by('first_name', 'last_name', 'employee_id')
            if company else Employee.objects.none()
        )

    def clean_email(self):
        email = self.cleaned_data['email'].lower().strip()

        if User.objects.filter(email=email, company=self.company).exists():
            raise ValidationError('This person already has an account in your company.')

        # If a pending invite exists, we'll reset it (handled in create_for)
        return email

    def clean_employee(self):
        employee = self.cleaned_data.get('employee')
        if employee and employee.company_id != self.company.pk:
            raise ValidationError('Employee must belong to your company.')
        if employee and employee.user_id:
            raise ValidationError('This employee already has a linked user account.')
        return employee


class InvitationAcceptForm(UserCreationForm):
    """Recipient sets up their account when accepting an invitation."""

    class Meta(UserCreationForm.Meta):
        model = User
        fields = ['first_name', 'last_name', 'phone']

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields['first_name'].required = True
        self.fields['last_name'].required = True
        self.fields['phone'].required = False


# ---------------------------------------------------------------------------
# Login
# ---------------------------------------------------------------------------

class CompanyLoginForm(AuthenticationForm):
    """Login requiring company domain + user email + password."""

    company_domain = forms.CharField(
        max_length=200,
        widget=forms.TextInput(attrs={'placeholder': 'your-company-domain', 'autocomplete': 'organization'}),
    )

    field_order = ['company_domain', 'username', 'password']

    def clean(self):
        cleaned_data = super().clean()
        domain = cleaned_data.get('company_domain', '').lower().strip()
        email = cleaned_data.get('username', '').lower().strip()
        password = cleaned_data.get('password')

        if not (domain and email and password):
            return cleaned_data

        try:
            company = Company.objects.get(domain=domain, is_active=True)
        except Company.DoesNotExist:
            raise ValidationError('No active company found with that domain.')

        if not User.objects.filter(email=email, company=company, is_active=True).exists():
            raise ValidationError('Invalid credentials.')

        user = authenticate(self.request, username=email, password=password)
        if user is None:
            raise ValidationError('Invalid credentials.')

        cleaned_data['user'] = user
        cleaned_data['company'] = company
        return cleaned_data


# ---------------------------------------------------------------------------
# Profile forms
# ---------------------------------------------------------------------------

class UserProfileForm(forms.ModelForm):
    """Let users edit their own profile. Email is read-only."""

    class Meta:
        model = User
        fields = ['first_name', 'last_name', 'email', 'phone', 'department', 'position']
        widgets = {
            'email': forms.EmailInput(attrs={'readonly': True}),
        }

    def clean_email(self):
        return self.instance.email


class UserManagementForm(forms.ModelForm):
    """Allow company admins to manage user roles and details."""

    class Meta:
        model = User
        fields = ['first_name', 'last_name', 'email', 'phone', 'department', 'position', 'role', 'is_active']
        widgets = {
            'email': forms.EmailInput(attrs={'readonly': True}),
        }

    def clean_email(self):
        return self.instance.email


class CompanyProfileForm(forms.ModelForm):
    """Allow company admins to edit company details. Domain is read-only."""

    class Meta:
        model = Company
        fields = [
            'name', 'domain', 'contact_email', 'contact_phone', 
            'whatsapp_number', 'orange_money_number', 'mtn_momo_number',
            'address', 'subscription_plan', 'is_active'
        ]
        widgets = {
            'domain': forms.TextInput(attrs={'readonly': True}),
            'address': forms.Textarea(attrs={'rows': 3}),
        }

    def clean_domain(self):
        return self.instance.domain


class CompanyEmailSettingsForm(forms.ModelForm):
    class Meta:
        model = CompanyEmailSettings
        fields = ['email_host', 'email_port', 'email_use_tls', 'email_host_user', 'email_host_password', 'default_from_email', 'is_active']
        widgets = {
            'email_host_password': forms.PasswordInput(render_value=True),
        }


class CompanyPaymentSettingsForm(forms.ModelForm):
    class Meta:
        model = CompanyPaymentSettings
        fields = ['whatsapp_number', 'orange_money_number', 'mtn_momo_number', 'payment_instructions', 'is_active']
        widgets = {
            'whatsapp_number': forms.TextInput(attrs={'class': 'form-control', 'placeholder': '+237690000000'}),
            'orange_money_number': forms.TextInput(attrs={'class': 'form-control', 'placeholder': '690000000'}),
            'mtn_momo_number': forms.TextInput(attrs={'class': 'form-control', 'placeholder': '670000000'}),
            'payment_instructions': forms.Textarea(attrs={'class': 'form-control', 'rows': 3, 'placeholder': 'Payment instructions for customers'}),
        }
