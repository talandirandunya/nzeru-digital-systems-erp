"""
hr/models.py

Models:
  - Position        : Job title + salary grade, now linkable to Employee
  - LeaveRequest    : Time-off workflow with approve/deny, duration calc,
                      date validation, and automatic employee status sync
  - SalaryComponent : Payroll components (base, allowances, deductions)
  - PayrollPeriod   : Monthly/weekly payroll cycles
  - PayrollEntry    : Individual employee payroll calculations
  - Payslip         : Generated payslips with line items
"""

import logging
from datetime import date
from decimal import Decimal

from django.conf import settings
from django.core.exceptions import ValidationError
from django.core.validators import MinValueValidator
from django.db import models
from django.utils import timezone

logger = logging.getLogger(__name__)


class Position(models.Model):
    """A named job title with a salary grade, scoped per company."""

    company = models.ForeignKey(
        'accounts.Company',
        on_delete=models.CASCADE,
        related_name='positions',
    )
    title = models.CharField(max_length=100)
    description = models.TextField(blank=True)
    salary_grade = models.IntegerField(validators=[MinValueValidator(0)])

    class Meta:
        unique_together = [('company', 'title')]
        ordering = ['title']

    def __str__(self) -> str:
        return f'{self.title} (Grade {self.salary_grade})'

    @property
    def employee_count(self) -> int:
        return self.employees.filter(status='active').count()


class LeaveRequest(models.Model):
    LEAVE_TYPES = [
        ('vacation',  'Vacation'),
        ('sick',      'Sick Leave'),
        ('unpaid',    'Unpaid Leave'),
        ('maternity', 'Maternity Leave'),
        ('paternity', 'Paternity Leave'),
        ('other',     'Other'),
    ]
    STATUS_CHOICES = [
        ('pending',  'Pending'),
        ('approved', 'Approved'),
        ('denied',   'Denied'),
    ]

    company = models.ForeignKey(
        'accounts.Company',
        on_delete=models.CASCADE,
        related_name='leaves',
    )
    employee = models.ForeignKey(
        'employees.Employee',
        on_delete=models.CASCADE,
        related_name='leaves',
    )
    leave_type = models.CharField(max_length=20, choices=LEAVE_TYPES)
    start_date = models.DateField()
    end_date = models.DateField()
    reason = models.TextField(blank=True, help_text='Optional reason for the leave request.')
    status = models.CharField(
        max_length=20, choices=STATUS_CHOICES, default='pending', db_index=True
    )
    reviewed_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True, blank=True,
        related_name='reviewed_leaves',
    )
    reviewed_at = models.DateTimeField(null=True, blank=True)
    submitted_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True, blank=True,
        related_name='submitted_leaves',
    )
    requested_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ['-requested_at']
        indexes = [
            models.Index(fields=['company', 'status']),
            models.Index(fields=['employee', 'status']),
            models.Index(fields=['start_date', 'end_date']),
        ]

    def __str__(self) -> str:
        return (
            f'{self.employee.full_name} — {self.get_leave_type_display()} '
            f'({self.start_date} → {self.end_date})'
        )

    # ------------------------------------------------------------------
    # Validation
    # ------------------------------------------------------------------

    def clean(self):
        if self.start_date and self.end_date:
            if self.end_date < self.start_date:
                raise ValidationError({
                    'end_date': 'End date must be on or after the start date.'
                })

    # ------------------------------------------------------------------
    # Computed properties
    # ------------------------------------------------------------------

    @property
    def duration_days(self) -> int:
        """Number of calendar days covered by the request (inclusive)."""
        if self.start_date and self.end_date:
            return (self.end_date - self.start_date).days + 1
        return 0

    @property
    def is_active(self) -> bool:
        """True if the leave is approved and currently ongoing."""
        today = timezone.localdate()
        return (
            self.status == 'approved'
            and self.start_date <= today <= self.end_date
        )

    @property
    def is_upcoming(self) -> bool:
        today = timezone.localdate()
        return self.status == 'approved' and self.start_date > today

    def apply_approval_decision(self, decision):
        """Apply a completed governance decision to the leave record."""
        if decision == 'approved':
            self.approve()
        elif decision in {'rejected', 'returned'}:
            self.deny()

    # ------------------------------------------------------------------
    # Approve / Deny
    # ------------------------------------------------------------------

    def approve(self, reviewed_by=None) -> None:
        """
        Approve the leave request and optionally set the employee's
        status to 'on_leave' if the leave starts today or earlier.
        """
        self.status = 'approved'
        self.reviewed_by = reviewed_by
        self.reviewed_at = timezone.now()
        self.save(update_fields=['status', 'reviewed_by', 'reviewed_at'])

        # Auto-update employee status if leave is current
        today = timezone.localdate()
        if self.start_date <= today <= self.end_date:
            self.employee.__class__.objects.filter(pk=self.employee_id).update(status='on_leave')
            logger.info(
                'Employee %s set to on_leave after leave approval.',
                self.employee_id,
            )

    def deny(self, reviewed_by=None) -> None:
        """
        Deny the leave request. If the employee was set to on_leave
        because of this request, revert them to active.
        """
        was_approved = self.status == 'approved'
        self.status = 'denied'
        self.reviewed_by = reviewed_by
        self.reviewed_at = timezone.now()
        self.save(update_fields=['status', 'reviewed_by', 'reviewed_at'])

        if was_approved:
            # Only revert if no other approved leave is currently active
            today = timezone.localdate()
            other_active = LeaveRequest.objects.filter(
                employee=self.employee,
                status='approved',
                start_date__lte=today,
                end_date__gte=today,
            ).exclude(pk=self.pk).exists()
            if not other_active:
                self.employee.__class__.objects.filter(
                    pk=self.employee_id, status='on_leave'
                ).update(status='active')


# ---------------------------------------------------------------------------
# Payroll System (Phase 1)
# ---------------------------------------------------------------------------

class SalaryComponent(models.Model):
    """Payroll component like base salary, allowances, deductions."""

    COMPONENT_TYPES = [
        ('earning', 'Earning'),
        ('deduction', 'Deduction'),
        ('tax', 'Tax'),
    ]

    company = models.ForeignKey(
        'accounts.Company',
        on_delete=models.CASCADE,
        related_name='salary_components'
    )
    name = models.CharField(max_length=100)
    component_type = models.CharField(max_length=20, choices=COMPONENT_TYPES)
    description = models.TextField(blank=True)
    is_active = models.BooleanField(default=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        unique_together = [('company', 'name')]
        ordering = ['component_type', 'name']
        indexes = [
            models.Index(fields=['company', 'component_type']),
        ]

    def __str__(self) -> str:
        return f'{self.name} ({self.get_component_type_display()})'


class PayrollPeriod(models.Model):
    """Monthly or weekly payroll cycle."""

    PERIOD_TYPES = [
        ('weekly', 'Weekly'),
        ('biweekly', 'Bi-weekly'),
        ('monthly', 'Monthly'),
    ]

    STATUS_CHOICES = [
        ('draft', 'Draft'),
        ('locked', 'Locked'),
        ('processing', 'Processing'),
        ('completed', 'Completed'),
        ('cancelled', 'Cancelled'),
    ]

    company = models.ForeignKey(
        'accounts.Company',
        on_delete=models.CASCADE,
        related_name='payroll_periods'
    )
    period_type = models.CharField(max_length=20, choices=PERIOD_TYPES, default='monthly')
    start_date = models.DateField()
    end_date = models.DateField()
    status = models.CharField(max_length=20, choices=STATUS_CHOICES, default='draft', db_index=True)
    total_earnings = models.DecimalField(max_digits=15, decimal_places=2, default=0)
    total_deductions = models.DecimalField(max_digits=15, decimal_places=2, default=0)
    total_net_pay = models.DecimalField(max_digits=15, decimal_places=2, default=0)
    processed_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='processed_payroll_periods'
    )
    processed_at = models.DateTimeField(null=True, blank=True)
    posted_to_finance = models.BooleanField(default=False)
    finance_journal_entry = models.ForeignKey('finance.JournalEntry', on_delete=models.SET_NULL, null=True, blank=True, related_name='payroll_periods')
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        unique_together = [('company', 'start_date', 'end_date')]
        ordering = ['-end_date']
        indexes = [
            models.Index(fields=['company', 'status']),
            models.Index(fields=['start_date', 'end_date']),
        ]

    def __str__(self) -> str:
        return f'{self.get_period_type_display()} - {self.start_date} to {self.end_date}'

    def can_lock(self) -> bool:
        """Check if period can be locked for processing."""
        return self.status == 'draft' and self.payroll_entries.exists()

    def can_process(self) -> bool:
        """Check if period can be moved to processing."""
        return self.status == 'locked'

    def lock(self) -> None:
        """Lock the payroll period to prevent further edits."""
        self.status = 'locked'
        self.save(update_fields=['status'])

    def process(self, processed_by=None) -> None:
        """Process payroll and generate payslips."""
        if not self.can_process():
            raise ValidationError('Payroll period must be locked before processing.')
        
        self.status = 'processing'
        self.processed_by = processed_by
        self.processed_at = timezone.now()
        self.save(update_fields=['status', 'processed_by', 'processed_at'])

        # Generate payslips for all entries
        for entry in self.payroll_entries.all():
            Payslip.objects.get_or_create(payroll_entry=entry)

        # Update totals
        entries = self.payroll_entries.all()
        self.total_earnings = sum(e.gross_earnings for e in entries) or 0
        self.total_deductions = sum(e.total_deductions for e in entries) or 0
        self.total_net_pay = sum(e.net_pay for e in entries) or 0
        self.status = 'completed'
        self.save(update_fields=['total_earnings', 'total_deductions', 'total_net_pay', 'status'])

    def post_to_finance(self, user):
        from finance.models import Account, Journal, JournalEntry, JournalEntryLine
        if self.status != 'completed':
            raise ValidationError('Only completed payroll periods can be posted to finance.')
        if self.posted_to_finance:
            raise ValidationError('This payroll period has already been posted to finance.')
        expense, _ = Account.objects.get_or_create(company=self.company, name='Payroll Expense', defaults={'account_type': 'expense'})
        payable, _ = Account.objects.get_or_create(company=self.company, name='Payroll Payable', defaults={'account_type': 'liability'})
        deductions, _ = Account.objects.get_or_create(company=self.company, name='Payroll Deductions Payable', defaults={'account_type': 'liability'})
        journal, _ = Journal.objects.get_or_create(company=self.company, name='Payroll Journal', defaults={'journal_type': 'general'})
        entry = JournalEntry.objects.create(company=self.company, journal=journal, reference=f'PAY-{self.pk}', description=f'Payroll {self.start_date} to {self.end_date}', date=self.end_date, entered_by=user)
        JournalEntryLine.objects.create(entry=entry, account=expense, description='Payroll gross earnings', debit=self.total_earnings)
        JournalEntryLine.objects.create(entry=entry, account=payable, description='Net payroll payable', credit=self.total_net_pay)
        if self.total_deductions:
            JournalEntryLine.objects.create(entry=entry, account=deductions, description='Payroll deductions payable', credit=self.total_deductions)
        entry.post()
        self.posted_to_finance = True
        self.finance_journal_entry = entry
        self.save(update_fields=['posted_to_finance', 'finance_journal_entry'])
        return entry


class PayrollEntry(models.Model):
    """Individual employee payroll calculation for a period."""

    payroll_period = models.ForeignKey(
        PayrollPeriod,
        on_delete=models.CASCADE,
        related_name='payroll_entries'
    )
    employee = models.ForeignKey(
        'employees.Employee',
        on_delete=models.CASCADE,
        related_name='payroll_entries'
    )
    base_salary = models.DecimalField(max_digits=12, decimal_places=2, default=0)
    working_days = models.DecimalField(max_digits=5, decimal_places=2, default=0)
    gross_earnings = models.DecimalField(max_digits=12, decimal_places=2, default=0)
    total_deductions = models.DecimalField(max_digits=12, decimal_places=2, default=0)
    tax_amount = models.DecimalField(max_digits=12, decimal_places=2, default=0)
    net_pay = models.DecimalField(max_digits=12, decimal_places=2, default=0)
    notes = models.TextField(blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        unique_together = [('payroll_period', 'employee')]
        ordering = ['employee']
        indexes = [
            models.Index(fields=['payroll_period', 'employee']),
        ]

    def __str__(self) -> str:
        return f'{self.employee.full_name} - {self.payroll_period}'

    def calculate_totals(self) -> None:
        """Recalculate all payroll totals."""
        # Sum earnings, deductions, and tax from components
        earnings = self.components.filter(component__component_type='earning').aggregate(
            total=models.Sum('amount')
        )['total'] or Decimal('0.00')
        
        deductions = self.components.filter(component__component_type='deduction').aggregate(
            total=models.Sum('amount')
        )['total'] or Decimal('0.00')
        
        taxes = self.components.filter(component__component_type='tax').aggregate(
            total=models.Sum('amount')
        )['total'] or Decimal('0.00')

        self.gross_earnings = earnings
        self.total_deductions = deductions + taxes
        self.tax_amount = taxes
        self.net_pay = earnings - self.total_deductions
        self.save(update_fields=['gross_earnings', 'total_deductions', 'tax_amount', 'net_pay'])

    def save(self, *args, **kwargs):
        """Auto-populate base salary on first save."""
        if not self.base_salary and self.employee.salary:
            self.base_salary = self.employee.salary
        super().save(*args, **kwargs)


class PayrollEntryComponent(models.Model):
    """Individual component (earning/deduction/tax) line in a payroll entry."""

    payroll_entry = models.ForeignKey(
        PayrollEntry,
        on_delete=models.CASCADE,
        related_name='components'
    )
    component = models.ForeignKey(
        SalaryComponent,
        on_delete=models.PROTECT,
        related_name='payroll_components'
    )
    amount = models.DecimalField(max_digits=12, decimal_places=2, default=0)
    notes = models.TextField(blank=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        unique_together = [('payroll_entry', 'component')]
        ordering = ['component__component_type', 'component__name']

    def __str__(self) -> str:
        return f'{self.component.name}: {self.amount}'

    def save(self, *args, **kwargs):
        """Recalculate payroll totals after component change."""
        super().save(*args, **kwargs)
        self.payroll_entry.calculate_totals()


class Payslip(models.Model):
    """Generated payslip for an employee for a payroll period."""

    payroll_entry = models.OneToOneField(
        PayrollEntry,
        on_delete=models.CASCADE,
        related_name='payslip'
    )
    payslip_number = models.CharField(max_length=50, unique=True)
    issued_date = models.DateField(auto_now_add=True)
    email_sent = models.BooleanField(default=False)
    email_sent_at = models.DateTimeField(null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ['-issued_date']
        indexes = [
            models.Index(fields=['payslip_number']),
            models.Index(fields=['issued_date']),
        ]

    def __str__(self) -> str:
        return self.payslip_number

    def save(self, *args, **kwargs):
        """Auto-generate payslip number on first save."""
        if not self.payslip_number:
            period = self.payroll_entry.payroll_period
            emp_id = self.payroll_entry.employee.employee_id
            year_month = period.end_date.strftime('%Y%m')
            self.payslip_number = f'PS-{year_month}-{emp_id}'
        super().save(*args, **kwargs)

    def mark_email_sent(self) -> None:
        """Mark payslip as sent via email."""
        self.email_sent = True
        self.email_sent_at = timezone.now()
        self.save(update_fields=['email_sent', 'email_sent_at'])


# ---------------------------------------------------------------------------
# Performance Management (Phase 2)
# ---------------------------------------------------------------------------

class PerformanceGoal(models.Model):
    """Employee goal used for performance tracking."""

    STATUS_CHOICES = [
        ('planned', 'Planned'),
        ('in_progress', 'In Progress'),
        ('completed', 'Completed'),
        ('cancelled', 'Cancelled'),
    ]

    company = models.ForeignKey(
        'accounts.Company',
        on_delete=models.CASCADE,
        related_name='performance_goals'
    )
    employee = models.ForeignKey(
        'employees.Employee',
        on_delete=models.CASCADE,
        related_name='performance_goals'
    )
    title = models.CharField(max_length=150)
    description = models.TextField(blank=True)
    start_date = models.DateField()
    end_date = models.DateField()
    status = models.CharField(max_length=20, choices=STATUS_CHOICES, default='planned', db_index=True)
    progress = models.PositiveIntegerField(default=0)
    created_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='created_performance_goals'
    )
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ['-end_date', 'employee']
        indexes = [
            models.Index(fields=['company', 'status']),
            models.Index(fields=['employee', 'status']),
        ]

    def __str__(self) -> str:
        return f'{self.employee.full_name} — {self.title}'

    def clean(self):
        if self.start_date and self.end_date and self.end_date < self.start_date:
            raise ValidationError({'end_date': 'End date must be on or after the start date.'})

    @property
    def is_overdue(self) -> bool:
        return self.status != 'completed' and self.end_date < timezone.localdate()


class PerformanceReview(models.Model):
    """Periodic performance review with summary and rating."""

    STATUS_CHOICES = [
        ('draft', 'Draft'),
        ('submitted', 'Submitted'),
        ('completed', 'Completed'),
    ]

    RATING_CHOICES = [
        (1, '1 - Poor'),
        (2, '2 - Needs Improvement'),
        (3, '3 - Meets Expectations'),
        (4, '4 - Exceeds Expectations'),
        (5, '5 - Outstanding'),
    ]

    company = models.ForeignKey(
        'accounts.Company',
        on_delete=models.CASCADE,
        related_name='performance_reviews'
    )
    employee = models.ForeignKey(
        'employees.Employee',
        on_delete=models.CASCADE,
        related_name='performance_reviews'
    )
    reviewer = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='reviewed_performance_reviews'
    )
    period_start = models.DateField()
    period_end = models.DateField()
    review_date = models.DateField(default=timezone.localdate)
    rating = models.PositiveSmallIntegerField(choices=RATING_CHOICES, null=True, blank=True)
    strengths = models.TextField(blank=True)
    improvements = models.TextField(blank=True)
    summary = models.TextField(blank=True)
    status = models.CharField(max_length=20, choices=STATUS_CHOICES, default='draft', db_index=True)
    submitted_at = models.DateTimeField(null=True, blank=True)
    completed_at = models.DateTimeField(null=True, blank=True)
    created_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='created_performance_reviews'
    )
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ['-review_date']
        indexes = [
            models.Index(fields=['company', 'status']),
            models.Index(fields=['employee', 'status']),
        ]

    def __str__(self) -> str:
        return f'{self.employee.full_name} Review ({self.period_start} → {self.period_end})'

    def clean(self):
        if self.period_start and self.period_end and self.period_end < self.period_start:
            raise ValidationError({'period_end': 'Period end must be on or after the start date.'})

    def submit(self, reviewer=None):
        if self.status != 'draft':
            raise ValidationError('Only draft reviews may be submitted.')
        self.status = 'submitted'
        self.reviewer = reviewer or self.reviewer
        self.submitted_at = timezone.now()
        self.save(update_fields=['status', 'reviewer', 'submitted_at'])

    def complete(self):
        if self.status != 'submitted':
            raise ValidationError('Only submitted reviews may be completed.')
        self.status = 'completed'
        self.completed_at = timezone.now()
        self.save(update_fields=['status', 'completed_at'])


class PerformanceReviewComment(models.Model):
    """Comments on a performance review."""

    review = models.ForeignKey(
        PerformanceReview,
        on_delete=models.CASCADE,
        related_name='comments'
    )
    author = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='performance_review_comments'
    )
    comment = models.TextField()
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ['created_at']

    def __str__(self) -> str:
        return f'Comment by {self.author} on {self.review}'


# ---------------------------------------------------------------------------
# Training & Development (Phase 3)
# ---------------------------------------------------------------------------

class TrainingCourse(models.Model):
    """Training courses available to employees."""

    COURSE_TYPES = [
        ('internal', 'Internal Training'),
        ('external', 'External Training'),
        ('certification', 'Certification'),
        ('workshop', 'Workshop'),
        ('seminar', 'Seminar'),
        ('webinar', 'Webinar'),
        ('other', 'Other'),
    ]

    company = models.ForeignKey(
        'accounts.Company',
        on_delete=models.CASCADE,
        related_name='training_courses'
    )
    title = models.CharField(max_length=200)
    description = models.TextField(blank=True)
    course_type = models.CharField(max_length=20, choices=COURSE_TYPES, default='internal')
    provider = models.CharField(max_length=100, blank=True, help_text='Training provider or instructor')
    duration_hours = models.PositiveIntegerField(default=0)
    cost = models.DecimalField(max_digits=10, decimal_places=2, default=0)
    max_participants = models.PositiveIntegerField(null=True, blank=True)
    location = models.CharField(max_length=200, blank=True)
    is_active = models.BooleanField(default=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ['title']
        indexes = [
            models.Index(fields=['company', 'is_active']),
            models.Index(fields=['company', 'course_type']),
        ]

    def __str__(self) -> str:
        return f'{self.title} ({self.get_course_type_display()})'


class TrainingSession(models.Model):
    """Scheduled training session."""

    STATUS_CHOICES = [
        ('planned', 'Planned'),
        ('confirmed', 'Confirmed'),
        ('in_progress', 'In Progress'),
        ('completed', 'Completed'),
        ('cancelled', 'Cancelled'),
    ]

    course = models.ForeignKey(
        TrainingCourse,
        on_delete=models.CASCADE,
        related_name='sessions'
    )
    start_date = models.DateField()
    end_date = models.DateField()
    start_time = models.TimeField(null=True, blank=True)
    end_time = models.TimeField(null=True, blank=True)
    instructor = models.CharField(max_length=100, blank=True)
    location = models.CharField(max_length=200, blank=True)
    status = models.CharField(max_length=20, choices=STATUS_CHOICES, default='planned', db_index=True)
    notes = models.TextField(blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ['start_date', 'start_time']
        indexes = [
            models.Index(fields=['course', 'status']),
            models.Index(fields=['start_date', 'status']),
        ]

    def __str__(self) -> str:
        return f'{self.course.title} - {self.start_date}'

    def clean(self):
        if self.start_date and self.end_date and self.end_date < self.start_date:
            raise ValidationError({'end_date': 'End date must be on or after the start date.'})

    @property
    def duration_days(self) -> int:
        if self.start_date and self.end_date:
            return (self.end_date - self.start_date).days + 1
        return 0


class EmployeeTraining(models.Model):
    """Employee enrollment in training sessions."""

    STATUS_CHOICES = [
        ('enrolled', 'Enrolled'),
        ('confirmed', 'Confirmed'),
        ('attended', 'Attended'),
        ('completed', 'Completed'),
        ('cancelled', 'Cancelled'),
        ('no_show', 'No Show'),
    ]

    employee = models.ForeignKey(
        'employees.Employee',
        on_delete=models.CASCADE,
        related_name='trainings'
    )
    session = models.ForeignKey(
        TrainingSession,
        on_delete=models.CASCADE,
        related_name='enrollments'
    )
    status = models.CharField(max_length=20, choices=STATUS_CHOICES, default='enrolled', db_index=True)
    enrollment_date = models.DateField(auto_now_add=True)
    completion_date = models.DateField(null=True, blank=True)
    score = models.DecimalField(max_digits=5, decimal_places=2, null=True, blank=True)
    grade = models.CharField(max_length=10, blank=True)
    certificate_issued = models.BooleanField(default=False)
    notes = models.TextField(blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        unique_together = [('employee', 'session')]
        ordering = ['-enrollment_date']
        indexes = [
            models.Index(fields=['employee', 'status']),
            models.Index(fields=['session', 'status']),
        ]

    def __str__(self) -> str:
        return f'{self.employee.full_name} - {self.session.course.title}'

    def mark_completed(self, completion_date=None, score=None, grade=None):
        self.status = 'completed'
        self.completion_date = completion_date or timezone.localdate()
        if score is not None:
            self.score = score
        if grade:
            self.grade = grade
        self.save(update_fields=['status', 'completion_date', 'score', 'grade'])


class Skill(models.Model):
    """Employee skills and competencies."""

    PROFICIENCY_LEVELS = [
        (1, 'Beginner'),
        (2, 'Intermediate'),
        (3, 'Advanced'),
        (4, 'Expert'),
        (5, 'Master'),
    ]

    company = models.ForeignKey(
        'accounts.Company',
        on_delete=models.CASCADE,
        related_name='skills'
    )
    name = models.CharField(max_length=100)
    category = models.CharField(max_length=50, blank=True)
    description = models.TextField(blank=True)
    is_active = models.BooleanField(default=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        unique_together = [('company', 'name')]
        ordering = ['category', 'name']
        indexes = [
            models.Index(fields=['company', 'is_active']),
            models.Index(fields=['company', 'category']),
        ]

    def __str__(self) -> str:
        return f'{self.name}'


class EmployeeSkill(models.Model):
    """Employee skill assessments."""

    employee = models.ForeignKey(
        'employees.Employee',
        on_delete=models.CASCADE,
        related_name='skills'
    )
    skill = models.ForeignKey(
        Skill,
        on_delete=models.CASCADE,
        related_name='employee_skills'
    )
    proficiency_level = models.PositiveSmallIntegerField(choices=Skill.PROFICIENCY_LEVELS)
    assessed_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='skill_assessments'
    )
    assessment_date = models.DateField(default=timezone.localdate)
    notes = models.TextField(blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        unique_together = [('employee', 'skill')]
        ordering = ['-assessment_date']
        indexes = [
            models.Index(fields=['employee', 'proficiency_level']),
            models.Index(fields=['skill', 'proficiency_level']),
        ]

    def __str__(self) -> str:
        return f'{self.employee.full_name} - {self.skill.name} ({self.get_proficiency_level_display()})'


class AttendanceRecord(models.Model):
    """One attendance record per employee and calendar day."""

    STATUS_CHOICES = [
        ('present', 'Present'),
        ('late', 'Late'),
        ('absent', 'Absent'),
        ('leave', 'On Leave'),
    ]

    company = models.ForeignKey(
        'accounts.Company', on_delete=models.CASCADE, related_name='attendance_records'
    )
    employee = models.ForeignKey(
        'employees.Employee', on_delete=models.PROTECT, related_name='attendance_records'
    )
    attendance_date = models.DateField()
    clock_in = models.DateTimeField(null=True, blank=True)
    clock_out = models.DateTimeField(null=True, blank=True)
    status = models.CharField(max_length=20, choices=STATUS_CHOICES, default='present')
    late_minutes = models.PositiveIntegerField(default=0)
    early_leave_minutes = models.PositiveIntegerField(default=0)
    notes = models.TextField(blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        constraints = [
            models.UniqueConstraint(
                fields=('company', 'employee', 'attendance_date'),
                name='unique_employee_attendance_day',
            ),
        ]
        indexes = [
            models.Index(fields=('company', 'attendance_date')),
            models.Index(fields=('employee', 'attendance_date')),
        ]

    def clean(self):
        if self.employee_id and self.company_id and self.employee.company_id != self.company_id:
            raise ValidationError('Attendance employee must belong to the same company.')
        if self.clock_in and self.clock_out and self.clock_out < self.clock_in:
            raise ValidationError({'clock_out': 'Clock-out cannot precede clock-in.'})

    def clock_in_now(self):
        if self.clock_in:
            raise ValidationError('This attendance record is already clocked in.')
        self.clock_in = timezone.now()
        self.status = 'present'
        self.save(update_fields=['clock_in', 'status', 'updated_at'])

    def clock_out_now(self):
        if not self.clock_in:
            raise ValidationError('Clock in before clocking out.')
        if self.clock_out:
            raise ValidationError('This attendance record is already clocked out.')
        self.clock_out = timezone.now()
        self.save(update_fields=['clock_out', 'updated_at'])


# ---------------------------------------------------------------------------
# Employee lifecycle extensions
# ---------------------------------------------------------------------------

class JobOpening(models.Model):
    STATUS_CHOICES = [('draft', 'Draft'), ('open', 'Open'), ('paused', 'Paused'), ('closed', 'Closed')]
    company = models.ForeignKey('accounts.Company', on_delete=models.CASCADE, related_name='job_openings')
    position = models.ForeignKey(Position, on_delete=models.PROTECT, related_name='job_openings')
    title = models.CharField(max_length=150)
    description = models.TextField(blank=True)
    requirements = models.TextField(blank=True)
    openings = models.PositiveIntegerField(default=1)
    closing_date = models.DateField(null=True, blank=True)
    status = models.CharField(max_length=20, choices=STATUS_CHOICES, default='draft', db_index=True)
    created_by = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.PROTECT, related_name='created_job_openings')
    created_at = models.DateTimeField(auto_now_add=True)

    def clean(self):
        if self.position_id and self.position.company_id != self.company_id:
            raise ValidationError('Position must belong to the opening company.')
        if self.openings < 1:
            raise ValidationError('At least one opening is required.')


class Applicant(models.Model):
    company = models.ForeignKey('accounts.Company', on_delete=models.CASCADE, related_name='applicants')
    name = models.CharField(max_length=160)
    email = models.EmailField()
    phone = models.CharField(max_length=40, blank=True)
    resume = models.FileField(upload_to='hr/resumes/', blank=True)
    notes = models.TextField(blank=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ('name',)


class JobApplication(models.Model):
    STATUS_CHOICES = [('applied', 'Applied'), ('screening', 'Screening'), ('interview', 'Interview'), ('offered', 'Offered'), ('hired', 'Hired'), ('rejected', 'Rejected'), ('withdrawn', 'Withdrawn')]
    opening = models.ForeignKey(JobOpening, on_delete=models.CASCADE, related_name='applications')
    applicant = models.ForeignKey(Applicant, on_delete=models.CASCADE, related_name='applications')
    status = models.CharField(max_length=20, choices=STATUS_CHOICES, default='applied', db_index=True)
    interview_date = models.DateTimeField(null=True, blank=True)
    rating = models.PositiveSmallIntegerField(null=True, blank=True)
    notes = models.TextField(blank=True)
    applied_at = models.DateTimeField(auto_now_add=True)

    def clean(self):
        if self.applicant_id and self.opening_id:
            if self.applicant.company_id != self.opening.company_id:
                raise ValidationError('Applicant must belong to the opening company.')
            if self.opening.company_id != self.applicant.company_id:
                raise ValidationError('Application records must remain within one company.')


class EmployeeDocument(models.Model):
    DOCUMENT_TYPES = [('identity', 'Identity'), ('contract', 'Contract'), ('certificate', 'Certificate'), ('policy', 'Policy'), ('other', 'Other')]
    company = models.ForeignKey('accounts.Company', on_delete=models.CASCADE, related_name='employee_documents')
    employee = models.ForeignKey('employees.Employee', on_delete=models.CASCADE, related_name='documents')
    title = models.CharField(max_length=160)
    document_type = models.CharField(max_length=20, choices=DOCUMENT_TYPES, default='other')
    file = models.FileField(upload_to='hr/employee-documents/')
    expiry_date = models.DateField(null=True, blank=True)
    notes = models.TextField(blank=True)
    uploaded_by = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.PROTECT, related_name='uploaded_employee_documents')
    uploaded_at = models.DateTimeField(auto_now_add=True)

    def clean(self):
        if self.employee_id and self.company_id and self.employee.company_id != self.company_id:
            raise ValidationError('Employee must belong to the document company.')


class BenefitPlan(models.Model):
    PLAN_TYPES = [('medical', 'Medical'), ('insurance', 'Insurance'), ('pension', 'Pension'), ('allowance', 'Allowance'), ('other', 'Other')]
    company = models.ForeignKey('accounts.Company', on_delete=models.CASCADE, related_name='benefit_plans')
    name = models.CharField(max_length=120)
    plan_type = models.CharField(max_length=20, choices=PLAN_TYPES)
    provider = models.CharField(max_length=120, blank=True)
    employer_contribution = models.DecimalField(max_digits=12, decimal_places=2, default=0)
    employee_contribution = models.DecimalField(max_digits=12, decimal_places=2, default=0)
    is_active = models.BooleanField(default=True)

    class Meta:
        constraints = [models.UniqueConstraint(fields=('company', 'name'), name='unique_benefit_company_name')]


class EmployeeBenefit(models.Model):
    STATUS_CHOICES = [('active', 'Active'), ('suspended', 'Suspended'), ('ended', 'Ended')]
    employee = models.ForeignKey('employees.Employee', on_delete=models.CASCADE, related_name='benefits')
    plan = models.ForeignKey(BenefitPlan, on_delete=models.PROTECT, related_name='enrollments')
    start_date = models.DateField(default=timezone.localdate)
    end_date = models.DateField(null=True, blank=True)
    status = models.CharField(max_length=20, choices=STATUS_CHOICES, default='active', db_index=True)
    notes = models.TextField(blank=True)

    class Meta:
        constraints = [models.UniqueConstraint(fields=('employee', 'plan'), name='unique_employee_benefit_plan')]

    def clean(self):
        if self.employee_id and self.plan_id and self.employee.company_id != self.plan.company_id:
            raise ValidationError('Employee and benefit plan must belong to the same company.')
        if self.end_date and self.end_date < self.start_date:
            raise ValidationError('Benefit end date must follow its start date.')


class DisciplinaryCase(models.Model):
    STATUS_CHOICES = [('open', 'Open'), ('investigating', 'Investigating'), ('resolved', 'Resolved'), ('closed', 'Closed')]
    SEVERITY_CHOICES = [('low', 'Low'), ('medium', 'Medium'), ('high', 'High'), ('critical', 'Critical')]
    company = models.ForeignKey('accounts.Company', on_delete=models.CASCADE, related_name='disciplinary_cases')
    employee = models.ForeignKey('employees.Employee', on_delete=models.PROTECT, related_name='disciplinary_cases')
    title = models.CharField(max_length=160)
    description = models.TextField()
    severity = models.CharField(max_length=20, choices=SEVERITY_CHOICES, default='medium')
    status = models.CharField(max_length=20, choices=STATUS_CHOICES, default='open', db_index=True)
    outcome = models.TextField(blank=True)
    opened_by = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.PROTECT, related_name='opened_disciplinary_cases')
    resolved_at = models.DateTimeField(null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)

    def clean(self):
        if self.employee_id and self.company_id and self.employee.company_id != self.company_id:
            raise ValidationError('Employee must belong to the disciplinary case company.')