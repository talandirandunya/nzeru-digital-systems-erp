"""
employees/models.py — Department and Employee models, scoped per company tenant.
"""

import logging

from django.conf import settings
from django.core.exceptions import ValidationError
from django.core.validators import MinValueValidator
from django.db import models
from django.utils import timezone

logger = logging.getLogger(__name__)


class Department(models.Model):
    """A department within a company."""

    company = models.ForeignKey(
        'accounts.Company',
        on_delete=models.CASCADE,
        related_name='departments',
    )
    name = models.CharField(max_length=100)
    description = models.TextField(blank=True)
    is_active = models.BooleanField(default=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        unique_together = [('company', 'name')]
        ordering = ['name']
        indexes = [
            models.Index(fields=['company', 'is_active']),
        ]

    def __str__(self) -> str:
        return f'{self.name} ({self.company.name})'

    @property
    def active_employee_count(self) -> int:
        return self.employees.filter(status='active').count()


class Employee(models.Model):
    ROLE_CHOICES = [
        ('manager', 'Manager'),
        ('developer', 'Developer'),
        ('designer', 'Designer'),
        ('analyst', 'Analyst'),
        ('engineer', 'Engineer'),
        ('intern', 'Intern'),
        ('hr', 'Human Resource'),
        ('accountant', 'Accountant'),
        ('secretary', 'Secretary'),
        ('project_manager', 'Project Manager'),
        ('stock_manager', 'Stock Manager'),
        ('other', 'Other'),
    ]

    STATUS_CHOICES = [
        ('active', 'Active'),
        ('inactive', 'Inactive'),
        ('on_leave', 'On Leave'),
        ('terminated', 'Terminated'),
    ]

    company = models.ForeignKey(
        'accounts.Company',
        on_delete=models.CASCADE,
        related_name='employees',
    )
    user = models.OneToOneField(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        related_name='employee_profile',
        null=True,
        blank=True,
    )
    employee_id = models.CharField(max_length=20)
    first_name = models.CharField(max_length=30, blank=True)
    last_name = models.CharField(max_length=30, blank=True)
    department = models.ForeignKey(
        Department,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='employees',
    )
    role = models.CharField(max_length=20, choices=ROLE_CHOICES, default='other', db_index=True)
    status = models.CharField(max_length=20, choices=STATUS_CHOICES, default='active', db_index=True)
    position = models.ForeignKey(
        'hr.Position',
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='employees',
        help_text='HR job position/grade for this employee.',
    )
    date_of_birth = models.DateField(null=True, blank=True)
    date_joined = models.DateField()
    salary = models.DecimalField(
        max_digits=12,           # raised from 10 → 12 to accommodate higher salaries
        decimal_places=2,
        validators=[MinValueValidator(0)],
        default=0,
    )
    bank_name = models.CharField(max_length=120, blank=True)
    bank_account_name = models.CharField(max_length=120, blank=True)
    bank_account_number = models.CharField(max_length=64, blank=True)
    tax_identification_number = models.CharField(max_length=64, blank=True)
    next_of_kin_name = models.CharField(max_length=120, blank=True)
    next_of_kin_relationship = models.CharField(max_length=80, blank=True)
    next_of_kin_phone = models.CharField(max_length=40, blank=True)
    medical_notes = models.TextField(blank=True)
    photo = models.ImageField(upload_to='employees/photos/', blank=True, null=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        unique_together = [('company', 'employee_id')]
        ordering = ['-created_at']
        indexes = [
            models.Index(fields=['company', 'status']),
            models.Index(fields=['company', 'role']),
            models.Index(fields=['company', 'department']),
        ]

    def __str__(self) -> str:
        return f'{self.employee_id} — {self.full_name}'

    # ------------------------------------------------------------------
    # Convenience proxies to the related User
    # ------------------------------------------------------------------

    @property
    def full_name(self) -> str:
        if self.user_id:
            return self.user.get_full_name()
        return f'{self.first_name} {self.last_name}'.strip() or self.employee_id

    @property
    def email(self) -> str:
        return self.user.email if self.user_id else ''

    @property
    def phone(self) -> str:
        return self.user.phone if self.user_id else ''

    # ------------------------------------------------------------------
    # Status helpers
    # ------------------------------------------------------------------

    @property
    def is_active(self) -> bool:
        return self.status == 'active'

    def apply_approval_decision(self, decision):
        """Update employee activation after a manager approval decision."""
        if decision == 'approved':
            self.status = 'active'
        elif decision in {'rejected', 'returned'}:
            self.status = 'inactive'
        self.save(update_fields=['status', 'updated_at'])

    def can_link_user(self, user) -> bool:
        """Validate that a user can be linked to this employee without violating company or one-to-one rules."""
        if not user or not getattr(user, 'company_id', None):
            return False
        if self.company_id != user.company_id:
            return False
        if self.user_id and self.user_id != user.pk:
            return False
        if user.pk and hasattr(user, 'employee_profile'):
            try:
                linked_employee = user.employee_profile
            except Exception:
                linked_employee = None
            if linked_employee and linked_employee.pk != self.pk:
                return False
        return True

    def link_user(self, user):
        """Link an existing user to this employee only when the relationship is valid and explicit."""
        if not self.can_link_user(user):
            raise ValueError('The selected user cannot be linked to this employee in the current company.')
        self.user = user
        self.save(update_fields=['user', 'updated_at'])
        return self

    def unlink_user(self):
        """Remove the user relationship without deleting either object."""
        if self.user_id:
            self.user = None
            self.save(update_fields=['user', 'updated_at'])
        return self

    def terminate(self) -> None:
        """Mark the employee as terminated and deactivate their user account."""
        self.status = 'terminated'
        self.save(update_fields=['status', 'updated_at'])
        # Prevent the user from logging in after termination
        if self.user_id:
            self.user.__class__.objects.filter(pk=self.user.pk).update(is_active=False)

    def reactivate(self) -> None:
        """Reactivate a previously terminated or inactive employee."""
        self.status = 'active'
        self.save(update_fields=['status', 'updated_at'])
        if self.user_id:
            self.user.__class__.objects.filter(pk=self.user.pk).update(is_active=True)

# Automatic user -> employee creation is intentionally disabled.
# Employee records are created explicitly via the employee workflow, and
# user-to-employee linking is performed only through the authorized governance
# flow or a controlled explicit link operation.


class CompanyAsset(models.Model):
    """Company-owned equipment that can be assigned to a user or employee."""

    ASSET_TYPES = [
        ('laptop', 'Laptop'),
        ('desktop', 'Desktop'),
        ('phone', 'Phone'),
        ('tablet', 'Tablet'),
        ('vehicle', 'Vehicle'),
        ('equipment', 'Equipment'),
        ('other', 'Other'),
    ]
    STATUS_CHOICES = [
        ('available', 'Available'),
        ('assigned', 'Assigned'),
        ('maintenance', 'In maintenance'),
        ('retired', 'Retired'),
        ('lost', 'Lost'),
    ]

    company = models.ForeignKey('accounts.Company', on_delete=models.CASCADE, related_name='company_assets')
    asset_tag = models.CharField(max_length=50)
    name = models.CharField(max_length=160)
    asset_type = models.CharField(max_length=20, choices=ASSET_TYPES, default='other')
    serial_number = models.CharField(max_length=120, blank=True)
    description = models.TextField(blank=True)
    purchase_date = models.DateField(null=True, blank=True)
    purchase_cost = models.DecimalField(max_digits=14, decimal_places=2, default=0, validators=[MinValueValidator(0)])
    status = models.CharField(max_length=20, choices=STATUS_CHOICES, default='available', db_index=True)
    assigned_user = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.SET_NULL, null=True, blank=True, related_name='assigned_company_assets')
    assigned_employee = models.ForeignKey('Employee', on_delete=models.SET_NULL, null=True, blank=True, related_name='assigned_company_assets')
    assigned_at = models.DateTimeField(null=True, blank=True)
    assigned_by = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.SET_NULL, null=True, blank=True, related_name='asset_assignments_made')
    notes = models.TextField(blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        constraints = [
            models.UniqueConstraint(fields=('company', 'asset_tag'), name='unique_company_asset_tag'),
        ]
        ordering = ['name', 'asset_tag']
        indexes = [models.Index(fields=['company', 'status'])]

    def __str__(self):
        return f'{self.asset_tag} - {self.name}'

    @property
    def assignee_name(self):
        if self.assigned_employee_id:
            return self.assigned_employee.full_name
        if self.assigned_user_id:
            return self.assigned_user.get_full_name() or self.assigned_user.email
        return ''

    def clean(self):
        if self.assigned_user_id and self.assigned_user.company_id != self.company_id:
            raise ValidationError('Assigned user must belong to the same company.')
        if self.assigned_employee_id and self.assigned_employee.company_id != self.company_id:
            raise ValidationError('Assigned employee must belong to the same company.')
        if self.assigned_user_id and self.assigned_employee_id:
            raise ValidationError('Assign an asset to either a user or an employee, not both.')
        if self.status == 'assigned' and not (self.assigned_user_id or self.assigned_employee_id):
            raise ValidationError('Assigned assets must have a user or employee assignee.')
        if self.status != 'assigned' and (self.assigned_user_id or self.assigned_employee_id):
            raise ValidationError('Only assigned assets can have an assignee.')
