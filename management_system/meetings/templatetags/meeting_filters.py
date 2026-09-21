from django import template

register = template.Library()


@register.filter
def endswith(value, arg):
    """
    Returns True if the value ends with the given suffix.
    Usage: {{ value|endswith:'.txt' }}
    """
    return str(value).endswith(arg)
