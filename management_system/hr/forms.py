from django import forms
from django.contrib.auth import get_user_model
from django.core.exceptions import ValidationError
from django.forms import inlineformset_factory

from .models import (
    LeaveRequest, Position, SalaryComponent, PayrollPeriod,
    PayrollEntry, PayrollEntryComponent,
    PerformanceGoal, PerformanceReview, PerformanceReviewComment,
    TrainingCourse, TrainingSession, EmployeeTraining, Skill, EmployeeSkill,
    AttendanceRecord, JobOpening, Applicant, JobApplication, EmployeeDocument,
    BenefitPlan, EmployeeBenefit, DisciplinaryCase,
)
from employees.models import Employee


class CompanyScopedModelForm(forms.ModelForm):
    def __init__(self, *args, company=None, **kwargs):
        self.company = company
        super().__init__(*args, **kwargs)


class JobOpeningForm(CompanyScopedModelForm):
    class Meta:
        model = JobOpening
        fields = ['position', 'title', 'description', 'requirements', 'openings', 'closing_date', 'status']
        widgets = {'closing_date': forms.DateInput(attrs={'type': 'date'})}

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        if self.company:
            self.fields['position'].queryset = Position.objects.filter(company=self.company)


class ApplicantForm(forms.ModelForm):
    class Meta:
        model = Applicant
        fields = ['name', 'email', 'phone', 'resume', 'notes']


class JobApplicationForm(CompanyScopedModelForm):
    class Meta:
        model = JobApplication
        fields = ['opening', 'applicant', 'status', 'interview_date', 'rating', 'notes']
        widgets = {'interview_date': forms.DateTimeInput(attrs={'type': 'datetime-local'})}

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        if self.company:
            self.fields['opening'].queryset = JobOpening.objects.filter(company=self.company)
            self.fields['applicant'].queryset = Applicant.objects.filter(company=self.company)


class EmployeeDocumentForm(CompanyScopedModelForm):
    class Meta:
        model = EmployeeDocument
        fields = ['employee', 'title', 'document_type', 'file', 'expiry_date', 'notes']
        widgets = {'expiry_date': forms.DateInput(attrs={'type': 'date'})}

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        if self.company:
            self.fields['employee'].queryset = Employee.objects.filter(company=self.company)


class BenefitPlanForm(forms.ModelForm):
    class Meta:
        model = BenefitPlan
        fields = ['name', 'plan_type', 'provider', 'employer_contribution', 'employee_contribution', 'is_active']


class EmployeeBenefitForm(CompanyScopedModelForm):
    class Meta:
        model = EmployeeBenefit
        fields = ['employee', 'plan', 'start_date', 'end_date', 'status', 'notes']
        widgets = {'start_date': forms.DateInput(attrs={'type': 'date'}), 'end_date': forms.DateInput(attrs={'type': 'date'})}

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        if self.company:
            self.fields['employee'].queryset = Employee.objects.filter(company=self.company)
            self.fields['plan'].queryset = BenefitPlan.objects.filter(company=self.company, is_active=True)


class DisciplinaryCaseForm(CompanyScopedModelForm):
    class Meta:
        model = DisciplinaryCase
        fields = ['employee', 'title', 'description', 'severity', 'status', 'outcome']

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        if self.company:
            self.fields['employee'].queryset = Employee.objects.filter(company=self.company)


class PositionForm(forms.ModelForm):
    class Meta:
        model = Position
        fields = ['title', 'description', 'salary_grade']
        widgets = {
            'title': forms.TextInput(attrs={'class': 'form-control'}),
            'description': forms.Textarea(attrs={'class': 'form-control', 'rows': 3}),
            'salary_grade': forms.NumberInput(attrs={'class': 'form-control', 'min': 0}),
        }


class AttendanceRecordForm(forms.ModelForm):
    class Meta:
        model = AttendanceRecord
        fields = ['employee', 'attendance_date', 'clock_in', 'clock_out', 'status', 'late_minutes', 'early_leave_minutes', 'notes']
        widgets = {
            'attendance_date': forms.DateInput(attrs={'type': 'date'}),
            'clock_in': forms.DateTimeInput(attrs={'type': 'datetime-local'}),
            'clock_out': forms.DateTimeInput(attrs={'type': 'datetime-local'}),
        }

    def __init__(self, *args, company=None, **kwargs):
        self.company = company
        super().__init__(*args, **kwargs)
        if company:
            self.fields['employee'].queryset = Employee.objects.filter(
                company=company, status__in=['active', 'on_leave']
            ).select_related('user')


class LeaveRequestForm(forms.ModelForm):
    class Meta:
        model = LeaveRequest
        fields = ['employee', 'leave_type', 'start_date', 'end_date', 'reason']
        widgets = {
            'employee': forms.Select(attrs={'class': 'form-select'}),
            'leave_type': forms.Select(attrs={'class': 'form-select'}),
            'start_date': forms.DateInput(attrs={'class': 'form-control', 'type': 'date'}),
            'end_date': forms.DateInput(attrs={'class': 'form-control', 'type': 'date'}),
            'reason': forms.Textarea(attrs={'class': 'form-control', 'rows': 3}),
        }

    def __init__(self, *args, **kwargs):
        company = kwargs.pop('company', None)
        self_employee = kwargs.pop('self_employee', None)  # for employee self-service
        super().__init__(*args, **kwargs)
        if company:
            self.fields['employee'].queryset = Employee.objects.filter(
                company=company, status__in=['active', 'on_leave']
            ).select_related('user')
        if self_employee:
            # Lock the employee field for self-service submissions
            self.fields['employee'].initial = self_employee
            self.fields['employee'].widget = forms.HiddenInput()
        self.fields['reason'].required = False

    def clean(self):
        cleaned = super().clean()
        start = cleaned.get('start_date')
        end = cleaned.get('end_date')
        if start and end and end < start:
            raise ValidationError({'end_date': 'End date must be on or after the start date.'})
        return cleaned


class LeaveStatusForm(forms.ModelForm):
    """Minimal form used only to update status via approve/deny buttons."""
    class Meta:
        model = LeaveRequest
        fields = ['status']


# ---------------------------------------------------------------------------
# Payroll Forms (Phase 1)
# ---------------------------------------------------------------------------

class SalaryComponentForm(forms.ModelForm):
    """Form for creating/editing salary components."""

    class Meta:
        model = SalaryComponent
        fields = ['name', 'component_type', 'description', 'is_active']
        widgets = {
            'name': forms.TextInput(attrs={'class': 'form-control'}),
            'component_type': forms.Select(attrs={'class': 'form-select'}),
            'description': forms.Textarea(attrs={'class': 'form-control', 'rows': 3}),
            'is_active': forms.CheckboxInput(attrs={'class': 'form-check-input'}),
        }


class PayrollPeriodForm(forms.ModelForm):
    """Form for creating/editing payroll periods."""

    class Meta:
        model = PayrollPeriod
        fields = ['period_type', 'start_date', 'end_date']
        widgets = {
            'period_type': forms.Select(attrs={'class': 'form-select'}),
            'start_date': forms.DateInput(attrs={'class': 'form-control', 'type': 'date'}),
            'end_date': forms.DateInput(attrs={'class': 'form-control', 'type': 'date'}),
        }

    def clean(self):
        cleaned = super().clean()
        start = cleaned.get('start_date')
        end = cleaned.get('end_date')
        if start and end and end < start:
            raise ValidationError({'end_date': 'End date must be on or after the start date.'})
        return cleaned


class PayrollEntryForm(forms.ModelForm):
    """Form for creating/editing payroll entries."""

    class Meta:
        model = PayrollEntry
        fields = ['employee', 'base_salary', 'working_days', 'notes']
        widgets = {
            'employee': forms.Select(attrs={'class': 'form-select'}),
            'base_salary': forms.NumberInput(attrs={'class': 'form-control', 'step': '0.01'}),
            'working_days': forms.NumberInput(attrs={'class': 'form-control', 'step': '0.5'}),
            'notes': forms.Textarea(attrs={'class': 'form-control', 'rows': 3}),
        }

    def __init__(self, *args, **kwargs):
        self.company = kwargs.pop('company', None)
        self.payroll_period = kwargs.pop('payroll_period', None)
        super().__init__(*args, **kwargs)

        if self.company:
            # Only show active employees from the company
            self.fields['employee'].queryset = Employee.objects.filter(
                company=self.company,
                status__in=['active', 'on_leave']
            ).select_related('user').order_by('user__last_name', 'user__first_name')

        if self.instance.pk:
            # Pre-populate base salary if available
            self.fields['base_salary'].initial = self.instance.base_salary or self.instance.employee.salary


class PayrollEntryComponentForm(forms.ModelForm):
    """Form for adding components to a payroll entry."""

    class Meta:
        model = PayrollEntryComponent
        fields = ['component', 'amount', 'notes']
        widgets = {
            'component': forms.Select(attrs={'class': 'form-select'}),
            'amount': forms.NumberInput(attrs={'class': 'form-control', 'step': '0.01'}),
            'notes': forms.TextInput(attrs={'class': 'form-control', 'placeholder': 'Optional notes'}),
        }

    def __init__(self, *args, **kwargs):
        self.company = kwargs.pop('company', None)
        super().__init__(*args, **kwargs)

        if self.company:
            self.fields['component'].queryset = SalaryComponent.objects.filter(
                company=self.company,
                is_active=True
            ).order_by('component_type', 'name')


class BasePayrollComponentFormSet(forms.BaseInlineFormSet):
    """Custom formset for payroll entry components with component-scoped filtering."""

    def _construct_form(self, i, **kwargs):
        """Filter components by company."""
        form = super()._construct_form(i, **kwargs)
        if hasattr(self, 'instance') and self.instance.payroll_period:
            company = self.instance.payroll_period.company
            form.fields['component'].queryset = SalaryComponent.objects.filter(
                company=company,
                is_active=True
            ).order_by('component_type', 'name')
        return form


PayrollEntryComponentFormSet = inlineformset_factory(
    PayrollEntry,
    PayrollEntryComponent,
    form=PayrollEntryComponentForm,
    formset=BasePayrollComponentFormSet,
    extra=3,
    can_delete=True,
)


class PerformanceGoalForm(forms.ModelForm):
    """Form for creating or editing employee performance goals."""

    class Meta:
        model = PerformanceGoal
        fields = ['employee', 'title', 'description', 'start_date', 'end_date', 'status', 'progress']
        widgets = {
            'employee': forms.Select(attrs={'class': 'form-select'}),
            'title': forms.TextInput(attrs={'class': 'form-control'}),
            'description': forms.Textarea(attrs={'class': 'form-control', 'rows': 3}),
            'start_date': forms.DateInput(attrs={'class': 'form-control', 'type': 'date'}),
            'end_date': forms.DateInput(attrs={'class': 'form-control', 'type': 'date'}),
            'status': forms.Select(attrs={'class': 'form-select'}),
            'progress': forms.NumberInput(attrs={'class': 'form-control', 'min': 0, 'max': 100}),
        }

    def __init__(self, *args, **kwargs):
        self.company = kwargs.pop('company', None)
        super().__init__(*args, **kwargs)
        if self.company:
            self.fields['employee'].queryset = Employee.objects.filter(
                company=self.company,
                status__in=['active', 'on_leave']
            ).select_related('user')


class PerformanceReviewForm(forms.ModelForm):
    """Form for creating or editing performance reviews."""

    class Meta:
        model = PerformanceReview
        fields = [
            'employee', 'reviewer', 'period_start', 'period_end', 'review_date',
            'rating', 'strengths', 'improvements', 'summary', 'status'
        ]
        widgets = {
            'employee': forms.Select(attrs={'class': 'form-select'}),
            'reviewer': forms.Select(attrs={'class': 'form-select'}),
            'period_start': forms.DateInput(attrs={'class': 'form-control', 'type': 'date'}),
            'period_end': forms.DateInput(attrs={'class': 'form-control', 'type': 'date'}),
            'review_date': forms.DateInput(attrs={'class': 'form-control', 'type': 'date'}),
            'rating': forms.Select(attrs={'class': 'form-select'}),
            'strengths': forms.Textarea(attrs={'class': 'form-control', 'rows': 3}),
            'improvements': forms.Textarea(attrs={'class': 'form-control', 'rows': 3}),
            'summary': forms.Textarea(attrs={'class': 'form-control', 'rows': 3}),
            'status': forms.Select(attrs={'class': 'form-select'}),
        }

    def __init__(self, *args, **kwargs):
        self.company = kwargs.pop('company', None)
        super().__init__(*args, **kwargs)
        if self.company:
            self.fields['employee'].queryset = Employee.objects.filter(
                company=self.company,
                status__in=['active', 'on_leave']
            ).select_related('user')
            User = get_user_model()
            self.fields['reviewer'].queryset = User.objects.filter(
                employee_profile__company=self.company,
                employee_profile__status='active'
            ).order_by('first_name', 'last_name')


class PerformanceReviewCommentForm(forms.ModelForm):
    """Form for adding comments to a performance review."""

    class Meta:
        model = PerformanceReviewComment
        fields = ['comment']
        widgets = {
            'comment': forms.Textarea(attrs={'class': 'form-control', 'rows': 3}),
        }


class TrainingCourseForm(forms.ModelForm):
    """Form for creating or editing training courses."""

    class Meta:
        model = TrainingCourse
        fields = [
            'title', 'description', 'course_type', 'provider', 'duration_hours',
            'cost', 'max_participants', 'location', 'is_active'
        ]
        widgets = {
            'title': forms.TextInput(attrs={'class': 'form-control'}),
            'description': forms.Textarea(attrs={'class': 'form-control', 'rows': 3}),
            'course_type': forms.Select(attrs={'class': 'form-select'}),
            'provider': forms.TextInput(attrs={'class': 'form-control'}),
            'duration_hours': forms.NumberInput(attrs={'class': 'form-control', 'min': 0}),
            'cost': forms.NumberInput(attrs={'class': 'form-control', 'step': '0.01', 'min': 0}),
            'max_participants': forms.NumberInput(attrs={'class': 'form-control', 'min': 1}),
            'location': forms.TextInput(attrs={'class': 'form-control'}),
            'is_active': forms.CheckboxInput(attrs={'class': 'form-check-input'}),
        }


class TrainingSessionForm(forms.ModelForm):
    """Form for creating or editing training sessions."""

    class Meta:
        model = TrainingSession
        fields = [
            'course', 'start_date', 'end_date', 'start_time', 'end_time',
            'instructor', 'location', 'status', 'notes'
        ]
        widgets = {
            'course': forms.Select(attrs={'class': 'form-select'}),
            'start_date': forms.DateInput(attrs={'class': 'form-control', 'type': 'date'}),
            'end_date': forms.DateInput(attrs={'class': 'form-control', 'type': 'date'}),
            'start_time': forms.TimeInput(attrs={'class': 'form-control', 'type': 'time'}),
            'end_time': forms.TimeInput(attrs={'class': 'form-control', 'type': 'time'}),
            'instructor': forms.TextInput(attrs={'class': 'form-control'}),
            'location': forms.TextInput(attrs={'class': 'form-control'}),
            'status': forms.Select(attrs={'class': 'form-select'}),
            'notes': forms.Textarea(attrs={'class': 'form-control', 'rows': 3}),
        }

    def __init__(self, *args, **kwargs):
        self.company = kwargs.pop('company', None)
        super().__init__(*args, **kwargs)
        if self.company:
            self.fields['course'].queryset = TrainingCourse.objects.filter(
                company=self.company,
                is_active=True
            ).order_by('title')


class EmployeeTrainingForm(forms.ModelForm):
    """Form for enrolling employees in training sessions."""

    class Meta:
        model = EmployeeTraining
        fields = ['employee', 'session', 'status', 'notes']
        widgets = {
            'employee': forms.Select(attrs={'class': 'form-select'}),
            'session': forms.Select(attrs={'class': 'form-select'}),
            'status': forms.Select(attrs={'class': 'form-select'}),
            'notes': forms.Textarea(attrs={'class': 'form-control', 'rows': 3}),
        }

    def __init__(self, *args, **kwargs):
        self.company = kwargs.pop('company', None)
        super().__init__(*args, **kwargs)
        if self.company:
            self.fields['employee'].queryset = Employee.objects.filter(
                company=self.company,
                status__in=['active', 'on_leave']
            ).select_related('user').order_by('user__last_name', 'user__first_name')
            self.fields['session'].queryset = TrainingSession.objects.filter(
                course__company=self.company,
                status__in=['planned', 'confirmed']
            ).select_related('course').order_by('start_date')


class TrainingCompletionForm(forms.ModelForm):
    """Form for marking training completion."""

    class Meta:
        model = EmployeeTraining
        fields = ['completion_date', 'score', 'grade', 'certificate_issued', 'notes']
        widgets = {
            'completion_date': forms.DateInput(attrs={'class': 'form-control', 'type': 'date'}),
            'score': forms.NumberInput(attrs={'class': 'form-control', 'step': '0.01', 'min': 0, 'max': 100}),
            'grade': forms.TextInput(attrs={'class': 'form-control'}),
            'certificate_issued': forms.CheckboxInput(attrs={'class': 'form-check-input'}),
            'notes': forms.Textarea(attrs={'class': 'form-control', 'rows': 3}),
        }


class SkillForm(forms.ModelForm):
    """Form for creating or editing skills."""

    class Meta:
        model = Skill
        fields = ['name', 'category', 'description', 'is_active']
        widgets = {
            'name': forms.TextInput(attrs={'class': 'form-control'}),
            'category': forms.TextInput(attrs={'class': 'form-control'}),
            'description': forms.Textarea(attrs={'class': 'form-control', 'rows': 3}),
            'is_active': forms.CheckboxInput(attrs={'class': 'form-check-input'}),
        }


class EmployeeSkillForm(forms.ModelForm):
    """Form for assessing employee skills."""

    class Meta:
        model = EmployeeSkill
        fields = ['employee', 'skill', 'proficiency_level', 'assessment_date', 'notes']
        widgets = {
            'employee': forms.Select(attrs={'class': 'form-select'}),
            'skill': forms.Select(attrs={'class': 'form-select'}),
            'proficiency_level': forms.Select(attrs={'class': 'form-select'}),
            'assessment_date': forms.DateInput(attrs={'class': 'form-control', 'type': 'date'}),
            'notes': forms.Textarea(attrs={'class': 'form-control', 'rows': 3}),
        }

    def __init__(self, *args, **kwargs):
        self.company = kwargs.pop('company', None)
        super().__init__(*args, **kwargs)
        if self.company:
            self.fields['employee'].queryset = Employee.objects.filter(
                company=self.company,
                status__in=['active', 'on_leave']
            ).select_related('user').order_by('user__last_name', 'user__first_name')
            self.fields['skill'].queryset = Skill.objects.filter(
                company=self.company,
                is_active=True
            ).order_by('category', 'name')