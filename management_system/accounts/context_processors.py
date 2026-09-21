from django.http import HttpRequest
from notifications.models import Notification


def company_context(request: HttpRequest) -> dict:
    """
    Inject company and role helpers into every template context.

    Available in all templates:
        {{ company }}            – Company instance or None
        {{ is_company_admin }}   – bool
        {{ user_role }}          – role string e.g. 'admin', 'manager'
        {{ user_has_role }}      – callable: {% if user_has_role 'admin' %}
        {{ unread_notifications }} – int: count of unread notifications
    """
    company = None
    is_company_admin = False
    user_role = ''
    unread_notifications = 0

    user = getattr(request, 'user', None)

    if user and user.is_authenticated:
        company = user.company
        is_company_admin = user.is_company_admin
        user_role = user.role
        unread_notifications = Notification.objects.filter(
            user=user,
            is_read=False
        ).count()

    return {
        'company': company,
        'is_company_admin': is_company_admin,
        'user_role': user_role,
        'unread_notifications': unread_notifications,
    }