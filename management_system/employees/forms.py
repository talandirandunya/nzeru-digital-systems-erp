"""
employees/forms.py
"""

from django import forms
from django.contrib.contenttypes.models import ContentType
from django.core.exceptions import ValidationError
from django.utils import timezone

from accounts.models import User
from governance.models import ApprovalRequest, ApprovalStep, ApprovalWorkflow
from governance.services import submit_for_approval
from hr.models import Position
from .models import CompanyAsset, Department, Employee


class EmployeeForm(forms.ModelForm):
    """
    Create or edit an employee.

    Pass ``company=<Company>`` as a keyword argument so the department
    queryset is scoped to the correct tenant.
    """

    first_name = forms.CharField(max_length=30, required=True, label='First name')
    last_name = forms.CharField(max_length=30, required=True, label='Last name')

    class Meta:
        model = Employee
        fields = [
            'employee_id', 'department', 'role', 'position', 'status',
            'date_of_birth', 'date_joined', 'salary',
            'bank_name', 'bank_account_name', 'bank_account_number',
            'tax_identification_number', 'next_of_kin_name',
            'next_of_kin_relationship', 'next_of_kin_phone', 'medical_notes',
            'photo',
        ]
        widgets = {
            'date_of_birth': forms.DateInput(attrs={'type': 'date'}),
            'date_joined': forms.DateInput(attrs={'type': 'date'}),
            'salary': forms.NumberInput(attrs={'step': '0.01', 'min': '0'}),
            'medical_notes': forms.Textarea(attrs={'rows': 3}),
        }
        help_texts = {
            'employee_id': 'Unique employee ID within your company (e.g. EMP-001).',
            'salary': 'Annual gross salary.',
            'position': 'HR job position / grade (optional — created in the HR module).',
        }

    def __init__(self, *args, company=None, **kwargs):
        self.company = company
        super().__init__(*args, **kwargs)

        if company:
            self.fields['department'].queryset = (
                Department.objects
                .filter(company=company, is_active=True)
                .order_by('name')
            )
            self.fields['position'].queryset = (
                Position.objects
                .filter(company=company)
                .order_by('title')
            )
            self.fields['position'].empty_label = '— No position assigned —'

        if self.instance and self.instance.pk:
            self.fields['first_name'].initial = self.instance.first_name
            self.fields['last_name'].initial = self.instance.last_name

    # ------------------------------------------------------------------
    # Validation
    # ------------------------------------------------------------------

    def clean_date_joined(self):
        date_joined = self.cleaned_data.get('date_joined')
        if date_joined and date_joined > timezone.localdate():
            raise ValidationError('Date joined cannot be in the future.')
        return date_joined

    def clean(self):
        cleaned_data = super().clean()
        if not cleaned_data.get('first_name', '').strip() or not cleaned_data.get('last_name', '').strip():
            raise ValidationError('Employee first name and last name are required.')

        # Validate unique employee_id within the company
        employee_id = cleaned_data.get('employee_id', '').strip()
        if employee_id and self.company:
            qs = Employee.objects.filter(company=self.company, employee_id=employee_id)
            if self.instance and self.instance.pk:
                qs = qs.exclude(pk=self.instance.pk)
            if qs.exists():
                self.add_error('employee_id', f'Employee ID "{employee_id}" is already in use.')

        return cleaned_data

    # ------------------------------------------------------------------
    # Save
    # ------------------------------------------------------------------

    # Maps Employee.role (job title) → User.role (access level).
    # Employee roles with no special privileges map to 'employee'.
    EMPLOYEE_ROLE_TO_USER_ROLE = {
        'manager':         'manager',
        'project_manager': 'manager',
        'hr':              'hr_manager',
        'accountant':      'accountant',
        'secretary':       'secretary',
        'stock_manager':   'stock_manager',
        # developer, designer, analyst, engineer, intern, other → standard employee access
    }

    def _sync_user_role(self, user, employee_role: str) -> None:
        """Update User.role to match the Employee.role, then save."""
        new_user_role = self.EMPLOYEE_ROLE_TO_USER_ROLE.get(employee_role, 'employee')
        if user.role != new_user_role:
            user.role = new_user_role
            user.save(update_fields=['role'])

    def _submit_employee_for_approval(self, employee):
        if not employee.company_id:
            return None

        workflow, _ = ApprovalWorkflow.objects.get_or_create(
            company=employee.company,
            transaction_type='employee_onboarding',
            defaults={
                'name': 'Employee onboarding approval',
                'enabled': True,
                'allow_self_approval': False,
            },
        )
        if not workflow.steps.exists():
            ApprovalStep.objects.get_or_create(
                workflow=workflow,
                sequence=1,
                defaults={'role': 'manager', 'required': True},
            )

        first_step = workflow.steps.filter(sequence=1).first()
        if first_step is None or not employee.company.users.filter(is_active=True, role='manager').exists():
            return None

        content_type = ContentType.objects.get_for_model(employee)
        if ApprovalRequest.objects.filter(company=employee.company, content_type=content_type, object_id=employee.pk).exists():
            return None

        requester = getattr(self, 'requester', None) or employee.company.users.filter(role='manager').order_by('pk').first() or employee.company.users.order_by('pk').first()
        if requester is None:
            return None

        return submit_for_approval(
            target=employee,
            requester=requester,
            transaction_type='employee_onboarding',
        )

    def save(self, commit=True):
        employee = super().save(commit=False)
        employee.company = self.company
        employee.first_name = self.cleaned_data['first_name'].strip()
        employee.last_name = self.cleaned_data['last_name'].strip()

        employee.company = self.company
        employee.department = self.cleaned_data.get('department')
        employee.role = self.cleaned_data.get('role')
        employee.status = self.cleaned_data.get('status')
        employee.position = self.cleaned_data.get('position')
        employee.date_of_birth = self.cleaned_data.get('date_of_birth')
        employee.date_joined = self.cleaned_data.get('date_joined')
        employee.salary = self.cleaned_data.get('salary') or 0
        employee.photo = self.cleaned_data.get('photo')

        if not employee.salary:
            employee.salary = 0

        if commit:
            employee.save()
            self._submit_employee_for_approval(employee)
        return employee


class CompanyAssetForm(forms.ModelForm):
    class Meta:
        model = CompanyAsset
        fields = [
            'asset_tag', 'name', 'asset_type', 'serial_number', 'description',
            'purchase_date', 'purchase_cost', 'status', 'assigned_user',
            'assigned_employee', 'notes',
        ]
        widgets = {
            'asset_tag': forms.TextInput(attrs={'class': 'form-control', 'placeholder': 'e.g. NDS-LAP-001'}),
            'name': forms.TextInput(attrs={'class': 'form-control', 'placeholder': 'e.g. Lenovo ThinkPad T14'}),
            'asset_type': forms.Select(attrs={'class': 'form-select'}),
            'serial_number': forms.TextInput(attrs={'class': 'form-control', 'placeholder': 'Manufacturer serial number'}),
            'description': forms.Textarea(attrs={'class': 'form-control', 'rows': 3, 'placeholder': 'Model, specifications, or identifying details'}),
            'purchase_date': forms.DateInput(attrs={'class': 'form-control', 'type': 'date'}),
            'purchase_cost': forms.NumberInput(attrs={'class': 'form-control', 'min': '0', 'step': '0.01', 'placeholder': '0.00'}),
            'status': forms.Select(attrs={'class': 'form-select'}),
            'assigned_user': forms.Select(attrs={'class': 'form-select'}),
            'assigned_employee': forms.Select(attrs={'class': 'form-select'}),
            'notes': forms.Textarea(attrs={'class': 'form-control', 'rows': 3, 'placeholder': 'Handover notes, condition, or return details'}),
        }

    def __init__(self, *args, company=None, **kwargs):
        self.company = company
        super().__init__(*args, **kwargs)
        if company:
            self.instance.company = company
        self.fields['assigned_user'].queryset = User.objects.filter(company=company, is_active=True).order_by('first_name', 'last_name', 'email') if company else User.objects.none()
        self.fields['assigned_employee'].queryset = Employee.objects.filter(company=company, status__in=['active', 'on_leave']).select_related('user').order_by('user__first_name', 'user__last_name') if company else Employee.objects.none()
        self.fields['assigned_user'].required = False
        self.fields['assigned_employee'].required = False
        self.fields['serial_number'].required = False
        self.fields['description'].required = False
        self.fields['purchase_date'].required = False
        self.fields['purchase_cost'].required = False
        self.fields['notes'].required = False

    def clean(self):
        cleaned = super().clean()
        assigned_user = cleaned.get('assigned_user')
        assigned_employee = cleaned.get('assigned_employee')
        status = cleaned.get('status')
        if assigned_user and assigned_employee:
            raise forms.ValidationError('Choose either an assigned user or an assigned employee, not both.')
        if status == 'assigned' and not (assigned_user or assigned_employee):
            raise forms.ValidationError('Choose a user or employee before marking this asset as assigned.')
        if status != 'assigned' and (assigned_user or assigned_employee):
            raise forms.ValidationError('Set the status to Assigned when an asset has an assignee.')
        return cleaned


class DepartmentForm(forms.ModelForm):
    """Create or edit a department. Pass ``company=<Company>`` as a kwarg."""

    class Meta:
        model = Department
        fields = ['name', 'description', 'is_active']
        widgets = {'description': forms.Textarea(attrs={'rows': 3})}

    def __init__(self, *args, company=None, **kwargs):
        self.company = company
        super().__init__(*args, **kwargs)

    def clean_name(self):
        name = self.cleaned_data['name'].strip().title()
        if self.company:
            qs = Department.objects.filter(company=self.company, name=name)
            if self.instance.pk:
                qs = qs.exclude(pk=self.instance.pk)
            if qs.exists():
                raise ValidationError(f'Department "{name}" already exists in your company.')
        return name

    def save(self, commit=True):
        department = super().save(commit=False)
        if self.company:
            department.company = self.company
        if commit:
            department.save()
        return department