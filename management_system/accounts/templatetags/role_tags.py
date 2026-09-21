from django import template

from governance.models import has_capability

register = template.Library()


@register.filter(name='has_role')
def has_role(user, roles_str):
    """
    Usage: {% if user|has_role:"admin,hr_manager,stock_manager" %}

    Returns True if the user's role is in the comma-separated list,
    or if the user is a superuser.
    Avoids the substring-match pitfall of Django's 'in' operator on strings
    (e.g. 'manager' in 'stock_manager' would be True with plain 'in').
    """
    if not user or not user.is_authenticated:
        return False
    if user.is_superuser:
        return True
    allowed = {r.strip() for r in roles_str.split(',')}
    return user.role in allowed


@register.filter(name='has_capability')
def has_capability_filter(user, capability_name):
    if not user or not user.is_authenticated:
        return False
    return has_capability(user, capability_name)