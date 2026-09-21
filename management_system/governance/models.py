import json

from django.conf import settings
from django.contrib.contenttypes.fields import GenericForeignKey
from django.contrib.contenttypes.models import ContentType
from django.core.exceptions import ValidationError
from django.db import models
from django.utils import timezone


CAPABILITIES = (
    'dashboard.view',
    'employees.view', 'employees.manage',
    'finance.view', 'finance.manage', 'finance.post_journal', 'finance.reverse_journal',
    'inventory.view', 'inventory.manage', 'inventory.issue',
    'procurement.view', 'procurement.manage', 'procurement.approve',
    'hr.view', 'hr.manage', 'hr.manage_payroll',
    'crm.view', 'crm.manage', 'projects.view', 'projects.manage',
    'meetings.view', 'meetings.manage', 'notifications.view', 'governance.view',
    'approvals.decide', 'reporting.view', 'reporting.export',
    'admin.manage_users', 'admin.manage_roles', 'admin.manage_organisation',
    'finance.approve_payment',
)

ROLE_DEFAULT_CAPABILITIES = {
    'admin': frozenset(CAPABILITIES),
    'hr_manager': frozenset({'dashboard.view', 'employees.view', 'employees.manage', 'hr.view', 'hr.manage', 'hr.manage_payroll', 'approvals.decide', 'reporting.view', 'meetings.view', 'notifications.view'}),
    'accountant': frozenset({'dashboard.view', 'employees.view', 'finance.view', 'finance.manage', 'finance.post_journal', 'approvals.decide', 'reporting.view', 'reporting.export', 'meetings.view', 'notifications.view'}),
    'manager': frozenset({'dashboard.view', 'employees.view', 'employees.manage', 'finance.view', 'finance.manage', 'inventory.view', 'inventory.manage', 'inventory.issue', 'procurement.view', 'procurement.manage', 'approvals.decide', 'hr.manage', 'crm.view', 'crm.manage', 'projects.view', 'projects.manage', 'reporting.view', 'meetings.view', 'meetings.manage', 'notifications.view'}),
    'stock_manager': frozenset({'dashboard.view', 'inventory.view', 'inventory.manage', 'inventory.issue', 'procurement.view', 'reporting.view', 'meetings.view', 'notifications.view'}),
    'secretary': frozenset({'dashboard.view', 'employees.view', 'crm.view', 'crm.manage', 'projects.view', 'meetings.view', 'meetings.manage', 'notifications.view'}),
    'employee': frozenset({'dashboard.view', 'employees.view', 'inventory.view', 'projects.view', 'meetings.view', 'notifications.view'}),
}


class RoleCapability(models.Model):
    """Capability granted to a role within an organisation."""

    company = models.ForeignKey('accounts.Company', on_delete=models.CASCADE, related_name='role_capabilities')
    role = models.CharField(max_length=30)
    capability = models.CharField(max_length=100, choices=[(value, value) for value in CAPABILITIES])
    enabled = models.BooleanField(default=True)

    class Meta:
        constraints = [models.UniqueConstraint(fields=('company', 'role', 'capability'), name='unique_role_capability')]
        indexes = [models.Index(fields=('company', 'role'))]


class UserCapability(models.Model):
    """Explicit per-user capability override."""

    company = models.ForeignKey('accounts.Company', on_delete=models.CASCADE, related_name='user_capabilities')
    user = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name='capability_overrides')
    capability = models.CharField(max_length=100, choices=[(value, value) for value in CAPABILITIES])
    enabled = models.BooleanField(default=True)
    granted_by = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.SET_NULL, null=True, blank=True, related_name='+')
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        constraints = [models.UniqueConstraint(fields=('user', 'capability'), name='unique_user_capability')]
        indexes = [models.Index(fields=('company', 'user'))]


class UserApprovalAuthority(models.Model):
    """Explicit approval authority assigned to one user by governance administrators."""

    company = models.ForeignKey('accounts.Company', on_delete=models.CASCADE, related_name='user_approval_authorities')
    user = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name='approval_authorities')
    transaction_type = models.CharField(max_length=100)
    module = models.CharField(max_length=80, blank=True)
    capability = models.CharField(max_length=100, default='approvals.decide', choices=[(value, value) for value in CAPABILITIES])
    min_amount = models.DecimalField(max_digits=14, decimal_places=2, null=True, blank=True)
    max_amount = models.DecimalField(max_digits=14, decimal_places=2, null=True, blank=True)
    department = models.CharField(max_length=100, blank=True)
    branch = models.CharField(max_length=100, blank=True)
    enabled = models.BooleanField(default=True)
    granted_by = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.SET_NULL, null=True, blank=True, related_name='+')
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        constraints = [models.UniqueConstraint(fields=('user', 'transaction_type', 'module'), name='unique_user_approval_authority')]
        indexes = [models.Index(fields=('company', 'user', 'transaction_type'))]

    def matches(self, user, amount=None, department='', branch=''):
        if not self.enabled or self.user_id != user.pk:
            return False
        if self.min_amount is not None and (amount is None or amount < self.min_amount):
            return False
        if self.max_amount is not None and (amount is None or amount > self.max_amount):
            return False
        if self.department and self.department != department:
            return False
        if self.branch and self.branch != branch:
            return False
        return True


class ApprovalWorkflow(models.Model):
    """Company configuration for a transaction approval route."""

    company = models.ForeignKey('accounts.Company', on_delete=models.CASCADE, related_name='approval_workflows')
    name = models.CharField(max_length=160)
    transaction_type = models.CharField(max_length=100)
    enabled = models.BooleanField(default=True)
    applies_from = models.DecimalField(max_digits=14, decimal_places=2, null=True, blank=True)
    applies_to = models.DecimalField(max_digits=14, decimal_places=2, null=True, blank=True)
    allow_self_approval = models.BooleanField(default=False)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        constraints = [models.UniqueConstraint(fields=('company', 'name'), name='unique_approval_workflow_name')]

    def matches(self, amount):
        if amount is None:
            return True
        return ((self.applies_from is None or amount >= self.applies_from) and
                (self.applies_to is None or amount <= self.applies_to))


class ApprovalStep(models.Model):
    workflow = models.ForeignKey(ApprovalWorkflow, on_delete=models.CASCADE, related_name='steps')
    sequence = models.PositiveIntegerField()
    role = models.CharField(max_length=30, blank=True)
    capability = models.CharField(max_length=100, blank=True)
    department = models.CharField(max_length=100, blank=True)
    min_amount = models.DecimalField(max_digits=14, decimal_places=2, null=True, blank=True)
    max_amount = models.DecimalField(max_digits=14, decimal_places=2, null=True, blank=True)
    approval_limit = models.DecimalField(max_digits=14, decimal_places=2, null=True, blank=True)
    required = models.BooleanField(default=True)

    class Meta:
        ordering = ('sequence',)
        constraints = [models.UniqueConstraint(fields=('workflow', 'sequence'), name='unique_approval_step_sequence')]

    def matches(self, user, amount):
        if self.role and user.role != self.role:
            return False
        if self.department and user.department != self.department:
            return False
        if self.capability and not has_capability(user, self.capability):
            return False
        if amount is not None:
            if self.min_amount is not None and amount < self.min_amount:
                return False
            if self.max_amount is not None and amount > self.max_amount:
                return False
            if self.approval_limit is not None and amount > self.approval_limit:
                return False
        return True


class ApprovalRequest(models.Model):
    STATUS_CHOICES = [
        ('pending', 'Pending approval'),
        ('approved', 'Approved'),
        ('rejected', 'Rejected'),
        ('returned', 'Returned for correction'),
        ('cancelled', 'Cancelled'),
    ]

    company = models.ForeignKey('accounts.Company', on_delete=models.PROTECT, related_name='approval_requests')
    workflow = models.ForeignKey(ApprovalWorkflow, on_delete=models.PROTECT, related_name='requests')
    requester = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.PROTECT, related_name='approval_requests')
    content_type = models.ForeignKey(ContentType, on_delete=models.PROTECT)
    object_id = models.PositiveBigIntegerField()
    target = GenericForeignKey('content_type', 'object_id')
    status = models.CharField(max_length=20, choices=STATUS_CHOICES, default='pending', db_index=True)
    current_step = models.PositiveIntegerField(default=1)
    submitted_at = models.DateTimeField(default=timezone.now)
    completed_at = models.DateTimeField(null=True, blank=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        indexes = [models.Index(fields=('company', 'status')), models.Index(fields=('content_type', 'object_id'))]

    @property
    def current_step_config(self):
        return self.workflow.steps.filter(sequence=self.current_step).first()


class ApprovalDecision(models.Model):
    DECISIONS = [('approved', 'Approved'), ('rejected', 'Rejected'), ('returned', 'Returned for correction')]
    request = models.ForeignKey(ApprovalRequest, on_delete=models.PROTECT, related_name='decisions')
    step = models.ForeignKey(ApprovalStep, on_delete=models.PROTECT)
    actor = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.PROTECT)
    decision = models.CharField(max_length=20, choices=DECISIONS)
    reason = models.TextField(blank=True)
    created_at = models.DateTimeField(default=timezone.now)

    class Meta:
        ordering = ('created_at',)


class AuditEvent(models.Model):
    """Append-only record of sensitive business and security actions."""

    company = models.ForeignKey('accounts.Company', on_delete=models.PROTECT, null=True, blank=True, related_name='audit_events')
    actor = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.SET_NULL, null=True, blank=True, related_name='audit_events')
    module = models.CharField(max_length=80)
    action = models.CharField(max_length=80)
    object_type = models.CharField(max_length=120, blank=True)
    object_id = models.CharField(max_length=80, blank=True)
    before_state = models.JSONField(null=True, blank=True)
    after_state = models.JSONField(null=True, blank=True)
    reason = models.TextField(blank=True)
    ip_address = models.GenericIPAddressField(null=True, blank=True)
    created_at = models.DateTimeField(default=timezone.now, db_index=True)

    class Meta:
        ordering = ('-created_at',)
        indexes = [models.Index(fields=('company', 'module', 'action'))]

    def save(self, *args, **kwargs):
        if self.pk:
            raise ValidationError('Audit events are immutable.')
        super().save(*args, **kwargs)

    def delete(self, *args, **kwargs):
        raise ValidationError('Audit events cannot be deleted.')

    @classmethod
    def record(cls, *, actor=None, company=None, module, action, obj=None, before=None, after=None, reason='', request=None):
        if obj is not None:
            object_type = f'{obj.__class__._meta.app_label}.{obj.__class__._meta.model_name}'
            object_id = str(obj.pk)
        else:
            object_type = ''
            object_id = ''
        ip_address = None
        if request is not None:
            ip_address = request.META.get('REMOTE_ADDR')
        return cls.objects.create(
            company=company or getattr(actor, 'company', None),
            actor=actor,
            module=module,
            action=action,
            object_type=object_type,
            object_id=object_id,
            before_state=before,
            after_state=after,
            reason=reason,
            ip_address=ip_address,
        )


def effective_capabilities(user):
    if not getattr(user, 'is_authenticated', False):
        return frozenset()
    if user.is_superuser:
        return frozenset(CAPABILITIES)
    if getattr(user, 'access_controlled', False):
        return frozenset(
            UserCapability.objects.filter(user=user, company=user.company, enabled=True)
            .values_list('capability', flat=True)
        )
    defaults = set(ROLE_DEFAULT_CAPABILITIES.get(user.role, ()))
    company = getattr(user, 'company', None)
    if company is None:
        return frozenset(defaults)
    overrides = UserCapability.objects.filter(user=user, company=company)
    for override in overrides:
        if override.enabled:
            defaults.add(override.capability)
        else:
            defaults.discard(override.capability)
    role_overrides = RoleCapability.objects.filter(company=company, role=user.role)
    for override in role_overrides:
        if override.enabled:
            defaults.add(override.capability)
        else:
            defaults.discard(override.capability)
    return frozenset(defaults)


def has_capability(user, capability):
    return capability in effective_capabilities(user)
