from django import forms
from django.contrib.auth import get_user_model
from django.db import transaction

from employees.models import Employee
from .access_catalog import CAPABILITY_LABELS, MODULE_ACCESS_CATALOG
from .models import CAPABILITIES, ApprovalWorkflow, UserApprovalAuthority, UserCapability


User = get_user_model()


class ManagedUserForm(forms.ModelForm):
    password = forms.CharField(required=False, widget=forms.PasswordInput)

    class Meta:
        model = User
        fields = ['first_name', 'last_name', 'email', 'phone', 'department', 'position', 'role', 'is_active', 'is_company_admin', 'access_controlled']
        widgets = {'email': forms.EmailInput(attrs={'readonly': True})}

    def save(self, commit=True):
        user = super().save(commit=False)
        password = self.cleaned_data.get('password')
        if password:
            user.set_password(password)
        if commit:
            user.save()
        return user


class CreateManagedUserForm(forms.ModelForm):
    password = forms.CharField(min_length=8, widget=forms.PasswordInput)
    employee_search = forms.CharField(
        required=False,
        label='Search existing employee',
        help_text='Filter the employee list by name or employee ID.',
        widget=forms.TextInput(attrs={'autocomplete': 'off', 'data-employee-search': 'true'}),
    )
    employee = forms.ModelChoiceField(
        queryset=Employee.objects.none(),
        required=False,
        label='Link existing employee',
        help_text='Optional. Select an employee already registered in this company.',
    )

    class Meta:
        model = User
        fields = ['first_name', 'last_name', 'email', 'phone', 'department', 'position', 'role', 'is_active', 'is_company_admin']

    def __init__(self, *args, company=None, **kwargs):
        self.company = company
        super().__init__(*args, **kwargs)
        self.fields['employee'].queryset = (
            Employee.objects.filter(company=company, user__isnull=True).order_by('first_name', 'last_name', 'employee_id')
            if company else Employee.objects.none()
        )

    def clean_employee(self):
        employee = self.cleaned_data.get('employee')
        if employee and (not self.company or employee.company_id != self.company.pk):
            raise forms.ValidationError('Employee must belong to your company.')
        if employee and employee.user_id:
            raise forms.ValidationError('This employee already has a linked user account.')
        return employee

    @transaction.atomic
    def save(self, company=None, commit=True):
        company = company or self.company
        user = super().save(commit=False)
        user.company = company
        user.set_password(self.cleaned_data['password'])
        user._skip_employee_profile = True
        user.access_controlled = True

        approval_required = bool(
            company and ApprovalWorkflow.objects.filter(
                company=company,
                transaction_type='user_account_creation',
                enabled=True,
            ).exists()
        )
        if approval_required:
            user.is_active = False

        if commit:
            user.save()
            employee = self.cleaned_data.get('employee')
            if employee:
                employee.link_user(user)
        return user


class CapabilityOverrideForm(forms.Form):
    access_controlled = forms.BooleanField(
        required=False,
        label='Use explicit assignments for this user',
        help_text='When enabled, the user receives only the checked capabilities below; job title defaults no longer grant access.',
    )

    def __init__(self, *args, company=None, user=None, **kwargs):
        self.company = company
        self.user = user
        super().__init__(*args, **kwargs)
        enabled = set(
            UserCapability.objects.filter(user=user, company=company, enabled=True)
            .values_list('capability', flat=True)
        )
        for module in MODULE_ACCESS_CATALOG:
            for capability, label in module['capabilities']:
                self.fields[f'capability__{capability}'] = forms.BooleanField(
                    required=False,
                    label=label,
                    initial=capability in enabled,
                )
        self.fields['access_controlled'].initial = bool(getattr(user, 'access_controlled', False))

    def selected_capabilities(self):
        return {
            capability
            for capability in CAPABILITY_LABELS
            if self.cleaned_data.get(f'capability__{capability}', False)
        }

    def save(self, granted_by):
        from django.db import transaction

        selected = self.selected_capabilities()
        with transaction.atomic():
            self.user.access_controlled = self.cleaned_data['access_controlled']
            self.user.save(update_fields=['access_controlled'])
            current = {
                item.capability: item
                for item in UserCapability.objects.filter(user=self.user, company=self.company)
            }
            for capability in CAPABILITY_LABELS:
                enabled = capability in selected
                override = current.get(capability)
                if override is None:
                    if enabled:
                        UserCapability.objects.create(
                            company=self.company, user=self.user, capability=capability,
                            enabled=True, granted_by=granted_by,
                        )
                elif override.enabled != enabled or override.granted_by_id != granted_by.pk:
                    override.enabled = enabled
                    override.granted_by = granted_by
                    override.save(update_fields=['enabled', 'granted_by'])
        return selected


class ApprovalAuthorityForm(forms.ModelForm):
    class Meta:
        model = UserApprovalAuthority
        fields = ['transaction_type', 'module', 'capability', 'min_amount', 'max_amount', 'department', 'branch', 'enabled']
        widgets = {
            'transaction_type': forms.TextInput(attrs={'placeholder': 'e.g. purchase_requisition'}),
            'module': forms.TextInput(attrs={'placeholder': 'e.g. procurement'}),
            'min_amount': forms.NumberInput(attrs={'step': '0.01'}),
            'max_amount': forms.NumberInput(attrs={'step': '0.01'}),
        }

    def __init__(self, *args, company=None, user=None, **kwargs):
        self.company = company
        self.user = user
        super().__init__(*args, **kwargs)

    def save(self, commit=True, granted_by=None):
        authority = super().save(commit=False)
        authority.company = self.company
        authority.user = self.user
        authority.granted_by = granted_by
        if commit:
            authority.save()
        return authority
