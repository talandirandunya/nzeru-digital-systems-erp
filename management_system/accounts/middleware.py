from datetime import timedelta

from django.utils import timezone, translation
from django.utils.deprecation import MiddlewareMixin
from django.shortcuts import redirect
from django.urls import reverse


class HealthCheckMiddleware(MiddlewareMixin):
    """Allow Railway's internal HTTP healthcheck through HTTPS redirects."""

    def process_request(self, request) -> None:
        if request.path == '/health/':
            request.META['HTTP_X_FORWARDED_PROTO'] = 'https'


class CompanyContextMiddleware(MiddlewareMixin):
    """
    Attach the authenticated user's company to every request object.

    Usage in views / templates:
        request.company  →  Company instance or None
    """

    def process_request(self, request) -> None:
        request.company = None

        user = getattr(request, 'user', None)
        if user is None or not user.is_authenticated:
            return

        request.company = user.company

        # Activate the user's preferred language.
        lang = getattr(user, 'language', 'en') or 'en'
        translation.activate(lang)
        request.LANGUAGE_CODE = lang

        # Update last_seen at most once per minute to avoid a DB write on every request.
        # Wrapped in try/except so a pending migration never takes down the whole app.
        try:
            now = timezone.now()
            if not user.last_seen or (now - user.last_seen) > timedelta(seconds=60):
                type(user).objects.filter(pk=user.pk).update(last_seen=now)
                user.last_seen = now
        except Exception:
            pass


class RequireLoginMiddleware(MiddlewareMixin):
    """
    Enforce authentication for private ERP routes.

    Public endpoints (login/register/reset, marketplace, admin auth, static/media)
    remain accessible without Django user authentication.
    """

    def process_request(self, request):
        if request.user.is_authenticated:
            return None

        path = request.path

        public_prefixes = (
            '/admin/',
            '/marketplace/',
            '/static/',
            '/media/',
            '/password-reset/',
            '/reset/',
            '/register/',
            '/invite/accept/',
        )
        public_exact_paths = (
            '/',
            '/login/',
            '/health/',
        )

        if path in public_exact_paths or path.startswith(public_prefixes):
            return None

        login_url = reverse('accounts:company_login')
        return redirect(f'{login_url}?next={request.get_full_path()}')
