from django.contrib.auth import get_user_model
from django.core.exceptions import ValidationError
from .models import Notification, NotificationPreference

User = get_user_model()


def _related_company_id(related_object):
    if getattr(getattr(related_object, '_meta', None), 'label_lower', None) == 'accounts.company':
        return related_object.pk
    company_id = getattr(related_object, 'company_id', None)
    if company_id is not None:
        return company_id
    related_company = getattr(related_object, 'company', None)
    company_id = getattr(related_company, 'pk', None)
    if company_id is not None:
        return company_id
    parent_meeting = getattr(related_object, 'meeting', None)
    return getattr(parent_meeting, 'company_id', None)


def create_notification(user, notification_type, title, message, data=None, related_object=None):
    """
    Create a notification for a user.

    Args:
        user: User instance to receive the notification
        notification_type: Type of notification (from Notification.NOTIFICATION_TYPES)
        title: Notification title
        message: Notification message
        data: Optional JSON data for additional information
        related_object: Optional related object instance
    """
    if not getattr(user, 'is_authenticated', False) or user.company_id is None:
        raise ValidationError('Notifications require a recipient who belongs to a company.')

    related_object_id = None
    related_object_type = None

    if related_object:
        related_company_id = _related_company_id(related_object)
        if related_company_id is None:
            raise ValidationError('Related notification objects must belong to a company.')
        if related_company_id != user.company_id:
            raise ValidationError('Notification object belongs to another company.')
        related_object_id = related_object.pk
        related_object_type = f"{related_object._meta.app_label}.{related_object._meta.model_name}"

    if not should_send_notification(user, notification_type):
        return None

    notification = Notification.objects.create(
        user=user,
        notification_type=notification_type,
        title=title,
        message=message,
        data=data,
        related_object_id=related_object_id,
        related_object_type=related_object_type,
    )
    return notification


def notify_users(users, notification_type, title, message, data=None, related_object=None):
    """
    Create notifications for multiple users.

    Args:
        users: QuerySet or list of User instances
        notification_type: Type of notification
        title: Notification title
        message: Notification message
        data: Optional JSON data
        related_object: Optional related object instance
    """
    notifications = []
    for user in users:
        notification = create_notification(
            user=user,
            notification_type=notification_type,
            title=title,
            message=message,
            data=data,
            related_object=related_object
        )
        if notification is not None:
            notifications.append(notification)
    return notifications


def get_user_notification_preferences(user):
    """
    Get notification preferences for a user.

    Args:
        user: User instance

    Returns:
        NotificationPreference instance
    """
    return NotificationPreference.get_or_create_for_user(user)


def should_send_notification(user, notification_type, delivery_method='in_app'):
    """
    Check if a user should receive a notification based on their preferences.

    Args:
        user: User instance
        notification_type: Type of notification
        delivery_method: 'in_app' or 'email'

    Returns:
        Boolean indicating if notification should be sent
    """
    prefs = get_user_notification_preferences(user)

    # Map notification types to preference fields
    type_mapping = {
        Notification.LEAVE_REQUEST: f'{delivery_method}_leave_requests',
        Notification.LEAVE_APPROVED: f'{delivery_method}_leave_requests',
        Notification.LEAVE_DENIED: f'{delivery_method}_leave_requests',
        Notification.PERFORMANCE_REVIEW: f'{delivery_method}_performance_reviews',
        Notification.PERFORMANCE_GOAL: f'{delivery_method}_performance_reviews',
        Notification.TRAINING_ENROLLMENT: f'{delivery_method}_training_updates',
        Notification.TRAINING_COMPLETED: f'{delivery_method}_training_updates',
        Notification.PAYROLL_PROCESSED: f'{delivery_method}_payroll_updates',
        Notification.MEETING_INVITATION: f'{delivery_method}_meeting_invitations',
        Notification.PROJECT_UPDATE: f'{delivery_method}_system_alerts',
        Notification.CRM_OPPORTUNITY: f'{delivery_method}_system_alerts',
        Notification.INVENTORY_LOW: f'{delivery_method}_system_alerts',
        Notification.MARKETPLACE_ORDER: f'{delivery_method}_system_alerts',
        Notification.SYSTEM_ALERT: f'{delivery_method}_system_alerts',
        Notification.APPROVAL_REQUIRED: f'{delivery_method}_system_alerts',
        Notification.APPROVAL_DECISION: f'{delivery_method}_system_alerts',
    }

    pref_field = type_mapping.get(notification_type)
    if pref_field:
        return getattr(prefs, pref_field, True)  # Default to True if field doesn't exist
    return True  # Default to sending if type not mapped


def get_unread_notification_count(user):
    """
    Get the count of unread notifications for a user.

    Args:
        user: User instance

    Returns:
        Integer count of unread notifications
    """
    return Notification.objects.filter(
        user=user,
        is_read=False,
        is_archived=False
    ).count()


def mark_notifications_read(user, notification_ids=None):
    """
    Mark notifications as read for a user.

    Args:
        user: User instance
        notification_ids: Optional list of notification IDs to mark as read.
                         If None, marks all unread notifications as read.
    """
    from django.utils import timezone

    queryset = Notification.objects.filter(
        user=user,
        is_read=False,
        is_archived=False
    )

    if notification_ids:
        queryset = queryset.filter(id__in=notification_ids)

    queryset.update(
        is_read=True,
        read_at=timezone.now()
    )