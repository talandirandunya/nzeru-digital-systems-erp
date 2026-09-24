from django import forms
from django.contrib.auth import get_user_model
from django.db import transaction

from employees.models import Department, Employee
from hr.models import Position
from .access_catalog import CAPABILITY_LABELS, MODULE_ACCESS_CATALOG
from .models import CAPABILITIES, ApprovalWorkflow, UserApprovalAuthority, UserCapability


User = get_user_model()


class ManagedUserForm(forms.ModelForm):
    password = forms.CharField(required=False, widget=forms.PasswordInput)

    class Meta:
        model = User
        fields = ['first_name', 'last_name', 'email', 'phone', 'department', 'position', 'role', 'is_active', 'is_company_admin', 'access_controlled']
        widgets = {'email': forms.EmailInput(attrs={'readonly': True})}

    def __init__(self, *args, company=None, **kwargs):
        self.company = company
        super().__init__(*args, **kwargs)
        department_names = sorted({
            value for value in Department.objects.filter(company=company).values_list('name', flat=True)
            if value
        }) if company else []
        position_titles = sorted({
            value for value in Position.objects.filter(company=company).values_list('title', flat=True)
            if value
        }) if company else []
        self.fields['department'].widget = forms.TextInput(attrs={
            'class': 'form-control',
            'list': 'department-suggestions',
            'placeholder': 'Select or type department',
        })
        self.fields['position'].widget = forms.TextInput(attrs={
            'class': 'form-control',
            'list': 'position-suggestions',
            'placeholder': 'Select or type position',
        })
        self.fields['department'].help_text = 'Use a department already in this company or add a new one.'
        self.fields['position'].help_text = 'Use a position already in this company or add a new one.'
        self.department_options = department_names
        self.position_options = position_titles

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
        department_names = sorted({
            value for value in Department.objects.filter(company=company).values_list('name', flat=True)
            if value
        }) if company else []
        position_titles = sorted({
            value for value in Position.objects.filter(company=company).values_list('title', flat=True)
            if value
        }) if company else []
        self.fields['department'].widget = forms.TextInput(attrs={
            'class': 'form-control',
            'list': 'department-suggestions',
            'placeholder': 'Select or type department',
        })
        self.fields['position'].widget = forms.TextInput(attrs={
            'class': 'form-control',
            'list': 'position-suggestions',
            'placeholder': 'Select or type position',
        })
        self.fields['department'].help_text = 'Use a department already in this company or add a new one.'
        self.fields['position'].help_text = 'Use a position already in this company or add a new one.'
        self.department_options = department_names
        self.position_options = position_titles
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
    module = forms.ChoiceField(
        required=False,
        choices=[('', 'Any module')] + [(module['key'], module['label']) for module in MODULE_ACCESS_CATALOG],
        label='Module',
        help_text='Choose the business module this approval belongs to.',
    )
    capability = forms.ChoiceField(
        choices=[(capability, CAPABILITY_LABELS.get(capability, capability)) for capability in sorted(CAPABILITY_LABELS)],
        initial='approvals.decide',
        label='Capability',
        help_text='This comes from the same capability catalog used in access assignments.',
    )
    transaction_type = forms.CharField(
        max_length=100,
        label='Transaction type',
        help_text='Use an existing workflow type or type a new one.',
        widget=forms.TextInput(attrs={'class': 'form-control', 'placeholder': 'e.g. purchase_requisition', 'list': 'known_transaction_types'}),
    )

    class Meta:
        model = UserApprovalAuthority
        fields = ['transaction_type', 'module', 'capability', 'min_amount', 'max_amount', 'department', 'branch', 'enabled']
        widgets = {
            'min_amount': forms.NumberInput(attrs={'step': '0.01', 'class': 'form-control'}),
            'max_amount': forms.NumberInput(attrs={'step': '0.01', 'class': 'form-control'}),
            'department': forms.TextInput(attrs={'class': 'form-control'}),
            'branch': forms.TextInput(attrs={'class': 'form-control'}),
            'enabled': forms.CheckboxInput(attrs={'class': 'form-check-input'}),
        }

    def __init__(self, *args, company=None, user=None, **kwargs):
        self.company = company
        self.user = user
        super().__init__(*args, **kwargs)
        self.fields['transaction_type'].widget.attrs.setdefault('class', 'form-control')
        self.fields['module'].widget.attrs.setdefault('class', 'form-select')
        self.fields['capability'].widget.attrs.setdefault('class', 'form-select')
        self.fields['min_amount'].widget.attrs.setdefault('class', 'form-control')
        self.fields['max_amount'].widget.attrs.setdefault('class', 'form-control')
        self.fields['department'].widget.attrs.setdefault('class', 'form-control')
        self.fields['branch'].widget.attrs.setdefault('class', 'form-control')
        self.fields['enabled'].widget.attrs.setdefault('class', 'form-check-input')
        if not self.initial.get('capability'):
            self.initial['capability'] = 'approvals.decide'

    def save(self, commit=True, granted_by=None):
        authority = super().save(commit=False)
        authority.company = self.company
        authority.user = self.user
        authority.granted_by = granted_by
        if commit:
            authority.save()
        return authority
