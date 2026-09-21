from functools import wraps

from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.http import HttpResponseForbidden
from django.shortcuts import redirect

from .models import has_capability


def capability_required(capability, redirect_url='core:dashboard'):
    def decorator(view_func):
        @wraps(view_func)
        @login_required
        def wrapper(request, *args, **kwargs):
            if has_capability(request.user, capability):
                return view_func(request, *args, **kwargs)
            if getattr(request.user, 'access_controlled', False):
                return HttpResponseForbidden('This module or function is not assigned to your account.')
            messages.error(request, 'You do not have permission to perform that action.')
            return redirect(redirect_url)
        return wrapper
    return decorator
