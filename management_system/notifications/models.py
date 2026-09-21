from django.db import models
from django.conf import settings
from django.urls import reverse
from django.utils import timezone


class Notification(models.Model):
    """Model for user notifications across the ERP system."""

    # Notification Types
    LEAVE_REQUEST = 'leave_request'
    LEAVE_APPROVED = 'leave_approved'
    LEAVE_DENIED = 'leave_denied'
    PERFORMANCE_REVIEW = 'performance_review'
    PERFORMANCE_GOAL = 'performance_goal'
    TRAINING_ENROLLMENT = 'training_enrollment'
    TRAINING_COMPLETED = 'training_completed'
    PAYROLL_PROCESSED = 'payroll_processed'
    MEETING_INVITATION = 'meeting_invitation'
    MEETING_SCHEDULED = 'meeting_scheduled'
    ACTION_ITEM_ASSIGNED = 'action_item_assigned'
    ACTION_ITEM_COMPLETED = 'action_item_completed'
    PROJECT_UPDATE = 'project_update'
    CRM_OPPORTUNITY = 'crm_opportunity'
    INVENTORY_LOW = 'inventory_low'
    MARKETPLACE_ORDER = 'marketplace_order'
    SYSTEM_ALERT = 'system_alert'
    APPROVAL_REQUIRED = 'approval_required'
    APPROVAL_DECISION = 'approval_decision'

    NOTIFICATION_TYPES = [
        (LEAVE_REQUEST, 'Leave Request Submitted'),
        (LEAVE_APPROVED, 'Leave Request Approved'),
        (LEAVE_DENIED, 'Leave Request Denied'),
        (PERFORMANCE_REVIEW, 'Performance Review'),
        (PERFORMANCE_GOAL, 'Performance Goal Update'),
        (TRAINING_ENROLLMENT, 'Training Enrollment'),
        (TRAINING_COMPLETED, 'Training Completed'),
        (PAYROLL_PROCESSED, 'Payroll Processed'),
        (MEETING_INVITATION, 'Meeting Invitation'),
        (MEETING_SCHEDULED, 'Meeting Scheduled'),
        (ACTION_ITEM_ASSIGNED, 'Action Item Assigned'),
        (ACTION_ITEM_COMPLETED, 'Action Item Completed'),
        (PROJECT_UPDATE, 'Project Update'),
        (CRM_OPPORTUNITY, 'CRM Opportunity'),
        (INVENTORY_LOW, 'Low Inventory Alert'),
        (MARKETPLACE_ORDER, 'Marketplace Order'),
        (SYSTEM_ALERT, 'System Alert'),
        (APPROVAL_REQUIRED, 'Approval Required'),
        (APPROVAL_DECISION, 'Approval Decision'),
    ]

    # Recipients
    user = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name='notifications'
    )

    # Notification Content
    notification_type = models.CharField(
        max_length=50,
        choices=NOTIFICATION_TYPES,
        default=SYSTEM_ALERT
    )
    title = models.CharField(max_length=200)
    message = models.TextField()
    data = models.JSONField(blank=True, null=True)  # Additional data for the notification

    # Status
    is_read = models.BooleanField(default=False)
    is_archived = models.BooleanField(default=False)

    # Timestamps
    created_at = models.DateTimeField(default=timezone.now)
    read_at = models.DateTimeField(blank=True, null=True)

    # Related Object (optional)
    related_object_id = models.PositiveIntegerField(blank=True, null=True)
    related_object_type = models.CharField(max_length=100, blank=True, null=True)

    class Meta:
        ordering = ['-created_at']
        indexes = [
            models.Index(fields=['user', 'is_read', 'created_at']),
            models.Index(fields=['user', 'notification_type']),
            models.Index(fields=['created_at']),
        ]

    def __str__(self):
        return f"{self.user.get_full_name()}: {self.title}"

    def mark_as_read(self):
        """Mark the notification as read."""
        if not self.is_read:
            self.is_read = True
            self.read_at = timezone.now()
            self.save(update_fields=['is_read', 'read_at'])

    def mark_as_unread(self):
        """Mark the notification as unread."""
        if self.is_read:
            self.is_read = False
            self.read_at = None
            self.save(update_fields=['is_read', 'read_at'])

    def archive(self):
        """Archive the notification."""
        self.is_archived = True
        self.save(update_fields=['is_archived'])

    def unarchive(self):
        """Unarchive the notification."""
        self.is_archived = False
        self.save(update_fields=['is_archived'])

    @property
    def is_recent(self):
        """Check if notification is recent (within last 24 hours)."""
        return (timezone.now() - self.created_at).days < 1

    @property
    def time_since(self):
        """Get human-readable time since creation."""
        now = timezone.now()
        diff = now - self.created_at

        if diff.days > 0:
            return f"{diff.days} day{'s' if diff.days > 1 else ''} ago"
        elif diff.seconds >= 3600:
            hours = diff.seconds // 3600
            return f"{hours} hour{'s' if hours > 1 else ''} ago"
        elif diff.seconds >= 60:
            minutes = diff.seconds // 60
            return f"{minutes} minute{'s' if minutes > 1 else ''} ago"
        else:
            return "Just now"

    def get_related_url(self):
        """Get URL to the related object if applicable."""
        if not self.related_object_type or not self.related_object_id:
            return None

        # Map notification types to their URL patterns
        url_mapping = {
            self.LEAVE_REQUEST: 'hr:leave_list',
            self.LEAVE_APPROVED: 'hr:leave_list',
            self.LEAVE_DENIED: 'hr:leave_list',
            self.PERFORMANCE_REVIEW: 'hr:performance_review_list',
            self.PERFORMANCE_GOAL: 'hr:performance_goal_list',
            self.TRAINING_ENROLLMENT: 'hr:employee_training_list',
            self.TRAINING_COMPLETED: 'hr:employee_training_list',
            self.PAYROLL_PROCESSED: 'hr:payslip_list',
            self.MEETING_INVITATION: 'meetings:meeting_list',
            self.PROJECT_UPDATE: 'projects:project_list',
            self.CRM_OPPORTUNITY: 'crm:opportunity_list',
            self.INVENTORY_LOW: 'inventory:product_list',
            self.MARKETPLACE_ORDER: 'marketplace:order_list',
            self.APPROVAL_REQUIRED: 'governance:my_work',
            self.APPROVAL_DECISION: 'governance:my_work',
        }

        url_name = url_mapping.get(self.notification_type)
        if url_name:
            try:
                return reverse(url_name)
            except:
                pass
        return None


class NotificationPreference(models.Model):
    """User preferences for notification types."""

    user = models.OneToOneField(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name='notification_preferences'
    )

    # Email preferences
    email_leave_requests = models.BooleanField(default=True)
    email_performance_reviews = models.BooleanField(default=True)
    email_training_updates = models.BooleanField(default=True)
    email_payroll_updates = models.BooleanField(default=True)
    email_meeting_invitations = models.BooleanField(default=True)
    email_system_alerts = models.BooleanField(default=True)

    # In-app preferences
    in_app_leave_requests = models.BooleanField(default=True)
    in_app_performance_reviews = models.BooleanField(default=True)
    in_app_training_updates = models.BooleanField(default=True)
    in_app_payroll_updates = models.BooleanField(default=True)
    in_app_meeting_invitations = models.BooleanField(default=True)
    in_app_system_alerts = models.BooleanField(default=True)

    created_at = models.DateTimeField(default=timezone.now)
    updated_at = models.DateTimeField(auto_now=True)

    def __str__(self):
        return f"{self.user.get_full_name()}'s notification preferences"

    @classmethod
    def get_or_create_for_user(cls, user):
        """Get or create notification preferences for a user."""
        prefs, created = cls.objects.get_or_create(user=user)
        return prefs
