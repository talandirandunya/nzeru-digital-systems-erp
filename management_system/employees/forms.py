"""
employees/forms.py
"""

from django import forms
from django.contrib.contenttypes.models import ContentType
from django.core.exceptions import ValidationError
from django.utils import timezone

from governance.models import ApprovalRequest, ApprovalStep, ApprovalWorkflow
from governance.services import submit_for_approval
from hr.models import Position
from .models import Department, Employee


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