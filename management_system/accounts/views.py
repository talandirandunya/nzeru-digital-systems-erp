import logging

from django.contrib import messages
from django.contrib.auth import login, logout, authenticate, update_session_auth_hash
from django.contrib.auth.decorators import login_required
from django.contrib.auth.forms import PasswordChangeForm
from django.contrib.auth.views import PasswordChangeView
from django.core.exceptions import PermissionDenied
from django.core.mail import send_mail, get_connection, EmailMessage
from django.conf import settings
from django.shortcuts import render, redirect, get_object_or_404
from django.template.loader import render_to_string
from django.urls import reverse, reverse_lazy
from django.views.decorators.http import require_http_methods

from .decorators import company_admin_required
from .forms import (
    CompanyCreationForm,
    CompanyLoginForm,
    InvitationForm,
    InvitationAcceptForm,
    UserProfileForm,
    CompanyProfileForm,
    CompanyEmailSettingsForm,
    CompanyPaymentSettingsForm,
)
from .models import Company, User, Invitation, CompanyEmailSettings
from marketplace.models import CompanyPaymentSettings
from governance.models import AuditEvent
from governance.services import maybe_submit_user_account_approval

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Authentication
# ---------------------------------------------------------------------------

@require_http_methods(['GET', 'POST'])
def company_login(request):
    """Login with company domain + email + password."""
    if request.user.is_authenticated:
        return redirect('core:dashboard')

    if request.method == 'POST':
        form = CompanyLoginForm(request, data=request.POST)
        if form.is_valid():
            user = form.cleaned_data['user']
            login(request, user)

            if user.company:
                request.session['company_id'] = user.company.id

            _record_login_ip(request, user)
            AuditEvent.record(actor=user, company=user.company, module='security', action='login_success', request=request)

            messages.success(request, f'Welcome back, {user.first_name or user.email}!')
            next_url = request.GET.get('next') or 'core:dashboard'
            return redirect(next_url)
    else:
        form = CompanyLoginForm(request)

    return render(request, 'accounts/company_login.html', {
        'form': form,
        'title': 'Company Login',
    })


@require_http_methods(['GET', 'POST'])
def company_register(request):
    """Register a new company and its admin user."""
    if request.user.is_authenticated:
        return redirect('core:dashboard')

    if request.method == 'POST':
        form = CompanyCreationForm(request.POST)
        if form.is_valid():
            company = form.save()

            email = form.cleaned_data['admin_email']
            password = form.cleaned_data['admin_password']

            user = User.objects.create_user(
                email=email,
                password=password,
                first_name=form.cleaned_data['admin_first_name'],
                last_name=form.cleaned_data['admin_last_name'],
                company=company,
                is_company_admin=True,
                role='admin',
            )

            authenticated_user = authenticate(request, username=email, password=password)
            if authenticated_user is not None:
                login(request, authenticated_user)
                request.session['company_id'] = company.id
                messages.success(
                    request,
                    f'Welcome to {company.name}! Your company has been registered successfully.',
                )
                logger.info('New company registered: %s (admin: %s)', company.name, email)
                return redirect('core:dashboard')

            logger.warning('Auto-login failed after company registration for %s', email)
            messages.success(request, f'Company "{company.name}" registered! Please log in.')
            return redirect('accounts:company_login')
    else:
        form = CompanyCreationForm()

    return render(request, 'accounts/company_register.html', {
        'form': form,
        'title': 'Register Company',
    })


@require_http_methods(['GET', 'POST'])
@login_required
def custom_logout(request):
    """Log out and clear company session data."""
    request.session.pop('company_id', None)
    logout(request)
    messages.success(request, 'You have been successfully logged out.')
    return redirect('accounts:company_login')


# ---------------------------------------------------------------------------
# Invitation views
# ---------------------------------------------------------------------------

def send_company_email(company, subject, body, recipient_list, html_message=None):
    """Send an email dynamically using company SMTP settings or default backend."""
    try:
        email_settings = CompanyEmailSettings.objects.get(company=company, is_active=True)
        connection = get_connection(
            backend='django.core.mail.backends.smtp.EmailBackend',
            host=email_settings.email_host,
            port=email_settings.email_port,
            username=email_settings.email_host_user,
            password=email_settings.email_host_password,
            use_tls=email_settings.email_use_tls,
        )
        from_email = email_settings.default_from_email or settings.DEFAULT_FROM_EMAIL
        if 'gmail.com' in email_settings.email_host.lower():
            from_email = email_settings.email_host_user
    except CompanyEmailSettings.DoesNotExist:
        connection = get_connection()
        from_email = getattr(settings, 'EMAIL_HOST_USER', None) or settings.DEFAULT_FROM_EMAIL

    email = EmailMessage(
        subject=subject,
        body=body,
        from_email=from_email,
        to=recipient_list,
        connection=connection,
    )
    if html_message:
        email.content_subtype = "html"
        email.body = html_message
    
    email.send()


@login_required
@company_admin_required
@require_http_methods(['GET', 'POST'])
def invite_user(request):
    """Send an email invitation to a new team member."""
    company = request.user.company

    if request.method == 'POST':
        form = InvitationForm(company, request.POST)
        if form.is_valid():
            email = form.cleaned_data['email']
            employee = form.cleaned_data.get('employee')
            invitation = Invitation.create_for(company, email, invited_by=request.user, employee=employee)

            accept_url = request.build_absolute_uri(
                reverse('accounts:accept_invitation', kwargs={'token': invitation.token})
            )
            subject = f"You've been invited to join {company.name} on NZERU ERP"
            body = render_to_string('accounts/invitation_email.html', {
                'company': company,
                'invited_by': request.user,
                'accept_url': accept_url,
                'expiry_days': 7,
            })

            try:
                send_company_email(company, subject, body, [email])
                messages.success(request, f'Invitation sent to {email}.')
                logger.info('Invitation sent to %s for company %s by %s', email, company.name, request.user.email)
            except Exception as e:
                logger.error('Failed to send invitation email to %s: %s', email, e)
                # Invitation is saved — share the link manually as fallback
                messages.warning(
                    request,
                    f'Invitation created but email could not be sent ({type(e).__name__}). '
                    f'Share this link manually: {accept_url}'
                )

            return redirect('accounts:invite_user')
    else:
        form = InvitationForm(company)

    invitations = Invitation.objects.filter(company=company).order_by('-created_at')[:50]

    return render(request, 'accounts/invite_user.html', {
        'form': form,
        'invitations': invitations,
        'title': 'Invite Team Member',
    })


@require_http_methods(['GET', 'POST'])
def accept_invitation(request, token):
    """Public view — recipient clicks email link and creates their account."""
    invitation = get_object_or_404(Invitation, token=token)

    if invitation.accepted_at is not None:
        messages.info(request, 'This invitation has already been used. Please log in.')
        return redirect('accounts:company_login')

    if invitation.is_expired:
        return render(request, 'accounts/invitation_expired.html', {
            'company': invitation.company,
        })

    if request.method == 'POST':
        form = InvitationAcceptForm(request.POST)
        if form.is_valid():
            user = form.save(commit=False)
            user.email = invitation.email
            user.company = invitation.company
            user.role = 'employee'
            user._skip_employee_profile = True
            user.save()

            if invitation.employee_id:
                employee = invitation.employee
                if employee.company_id != invitation.company_id:
                    raise PermissionDenied('Invitation employee does not belong to this company.')
                if employee.user_id and employee.user_id != user.pk:
                    raise PermissionDenied('This employee is already linked to another account.')
                employee.link_user(user)

            approval = maybe_submit_user_account_approval(user=user, requester=user, request=request)
            if approval is not None:
                user.refresh_from_db()
                from django.utils import timezone
                invitation.accepted_at = timezone.now()
                invitation.save(update_fields=['accepted_at'])
                messages.info(request, 'Your account was created and is pending manager/HR approval before you can log in.')
                logger.info('Invitation accepted pending approval: %s for %s', user.email, user.company.name)
                return redirect('accounts:company_login')

            from django.utils import timezone
            invitation.accepted_at = timezone.now()
            invitation.save(update_fields=['accepted_at'])

            login(request, user)
            if user.company:
                request.session['company_id'] = user.company.id
            _record_login_ip(request, user)

            messages.success(request, f'Welcome to {user.company.name}, {user.first_name}!')
            logger.info('Invitation accepted: %s joined %s', user.email, user.company.name)
            return redirect('core:dashboard')
    else:
        form = InvitationAcceptForm()

    return render(request, 'accounts/accept_invitation.html', {
        'form': form,
        'invitation': invitation,
        'title': f'Join {invitation.company.name}',
    })


# ---------------------------------------------------------------------------
# Profile views
# ---------------------------------------------------------------------------

@login_required
@require_http_methods(['GET', 'POST'])
def company_profile(request):
    """View/edit company profile — company admins only."""
    if not request.user.is_company_admin:
        raise PermissionDenied('Only company administrators can access this page.')

    company = request.user.company
    if company is None:
        messages.error(request, 'You are not associated with any company.')
        return redirect('core:dashboard')

    if request.method == 'POST':
        form = CompanyProfileForm(request.POST, instance=company)
        if form.is_valid():
            form.save()
            messages.success(request, 'Company profile updated successfully!')
            return redirect('accounts:company_profile')
    else:
        form = CompanyProfileForm(instance=company)

    return render(request, 'accounts/company_profile.html', {
        'form': form,
        'company': company,
        'title': 'Company Profile',
    })


@login_required
@require_http_methods(['GET', 'POST'])
def company_email_settings(request):
    """Manage company specific SMTP/email settings."""
    if not request.user.is_company_admin:
        raise PermissionDenied('Only company administrators can access this page.')

    company = request.user.company
    if company is None:
        messages.error(request, 'You are not associated with any company.')
        return redirect('core:dashboard')

    email_settings, created = CompanyEmailSettings.objects.get_or_create(company=company)

    if request.method == 'POST':
        form = CompanyEmailSettingsForm(request.POST, instance=email_settings)
        if form.is_valid():
            form.save()
            messages.success(request, 'Company email settings updated successfully!')
            return redirect('accounts:company_email_settings')
    else:
        form = CompanyEmailSettingsForm(instance=email_settings)

    return render(request, 'accounts/company_email_settings.html', {
        'form': form,
        'company': company,
        'title': 'Company Email Settings',
    })


@login_required
@require_http_methods(['GET', 'POST'])
def company_payment_settings(request):
    """Manage company specific payment keys (Stripe and Flutterwave)."""
    if not request.user.is_company_admin:
        raise PermissionDenied('Only company administrators can access this page.')

    company = request.user.company
    if company is None:
        messages.error(request, 'You are not associated with any company.')
        return redirect('core:dashboard')

    payment_settings, created = CompanyPaymentSettings.objects.get_or_create(company=company)

    if request.method == 'POST':
        form = CompanyPaymentSettingsForm(request.POST, instance=payment_settings)
        if form.is_valid():
            form.save()
            messages.success(request, 'Company payment settings updated successfully!')
            return redirect('accounts:company_payment_settings')
    else:
        form = CompanyPaymentSettingsForm(instance=payment_settings)

    return render(request, 'accounts/company_payment_settings.html', {
        'form': form,
        'company': company,
        'title': 'Company Payment Settings',
    })


@login_required
def user_profile(request):
    """Display the current user's profile."""
    return render(request, 'accounts/user_profile.html', {
        'profile_user': request.user,
        'title': 'My Profile',
    })


@login_required
@require_http_methods(['GET', 'POST'])
def edit_profile(request):
    """Edit the current user's profile."""
    if request.method == 'POST':
        form = UserProfileForm(request.POST, instance=request.user)
        if form.is_valid():
            form.save()
            messages.success(request, 'Profile updated successfully!')
            return redirect('accounts:user_profile')
    else:
        form = UserProfileForm(instance=request.user)

    return render(request, 'accounts/edit_profile.html', {
        'form': form,
        'title': 'Edit Profile',
    })


# ---------------------------------------------------------------------------
# Password management
# ---------------------------------------------------------------------------

class CustomPasswordChangeView(PasswordChangeView):
    form_class = PasswordChangeForm
    template_name = 'accounts/password_change.html'
    success_url = reverse_lazy('accounts:password_change_done')

    def form_valid(self, form):
        messages.success(self.request, 'Your password was successfully updated!')
        return super().form_valid(form)


# ---------------------------------------------------------------------------
# Internal helpers
# ---------------------------------------------------------------------------

@login_required
@require_http_methods(['POST'])
def set_language(request):
    """Switch the current user's interface language."""
    lang = request.POST.get('language', 'en')
    allowed = {code for code, _ in User.LANGUAGE_CHOICES}
    if lang in allowed:
        User.objects.filter(pk=request.user.pk).update(language=lang)
        request.user.language = lang
    next_url = request.POST.get('next') or request.META.get('HTTP_REFERER') or '/'
    return redirect(next_url)


def _record_login_ip(request, user: User) -> None:
    ip = _get_client_ip(request)
    if ip:
        User.objects.filter(pk=user.pk).update(last_login_ip=ip)


def _get_client_ip(request) -> str | None:
    x_forwarded = request.META.get('HTTP_X_FORWARDED_FOR')
    if x_forwarded:
        return x_forwarded.split(',')[0].strip()
    return request.META.get('REMOTE_ADDR')
