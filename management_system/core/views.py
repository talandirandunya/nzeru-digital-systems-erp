"""
core/views.py

Central dashboard view. All queries are scoped to request.user.company
so no data leaks across tenants.
"""

import logging

from django.contrib.auth.decorators import login_required
from django.db.models import Count, F, Q, Sum
from django.shortcuts import redirect, render
from django.utils import timezone

from datetime import timedelta

from django.contrib.auth.decorators import login_required
from django.http import HttpResponseForbidden, JsonResponse

from employees.models import Employee
from finance.models import Account, Transaction
from inventory.models import Stock
from projects.models import Project
from accounts.models import User, Company
from accounts.permissions import (
    DASHBOARD_EMPLOYEE_ROLES,
    DASHBOARD_FINANCE_ROLES,
    DASHBOARD_HR_ROLES,
)
from governance.models import ApprovalDecision, ApprovalRequest, has_capability
from governance.services import actionable_approvals_for_user
from governance.decorators import capability_required

logger = logging.getLogger(__name__)


def health_check(request):
    return JsonResponse({'status': 'ok'})


@capability_required('dashboard.view')
def dashboard(request):
    """
    Main dashboard — company-scoped statistics and recent activity.
    Stats are filtered based on the user's role so sensitive data
    (finance totals, full employee lists) are only shown to relevant roles.
    """
    company = request.user.company
    role = request.user.role
    is_super = request.user.is_superuser

    if company is None:
        logger.warning('User %s has no company on dashboard access.', request.user.email)
        return redirect('accounts:company_register')

    dashboard_label = 'NZERU ERP'
    if is_super:
        dashboard_label = 'NZERU ERP • System Administration'
    elif role == 'employee':
        dashboard_label = 'NZERU ERP • My Workspace'
    elif role == 'manager':
        dashboard_label = 'NZERU ERP • Team Operations'
    elif role == 'accountant':
        dashboard_label = 'NZERU ERP • Finance'
    elif role == 'hr_manager':
        dashboard_label = 'NZERU ERP • HR'
    elif role == 'stock_manager':
        dashboard_label = 'NZERU ERP • Inventory'
    elif role == 'admin':
        dashboard_label = 'NZERU ERP • Organisation Administration'

    context = {
        'company': company,
        'now': timezone.now(),
        'dashboard_label': dashboard_label,
        'user_greeting': f"Good morning, {request.user.first_name or request.user.email.split('@')[0].title()}",
        'show_employee_stats': is_super or role in DASHBOARD_EMPLOYEE_ROLES,
        'show_finance_stats':  is_super or role in DASHBOARD_FINANCE_ROLES,
        'show_hr_stats':       is_super or role in DASHBOARD_HR_ROLES,
        'is_employee_dashboard': role == 'employee',
        'is_manager_dashboard': role == 'manager',
        'is_finance_dashboard': role == 'accountant' or role == 'admin',
        'show_project_stats': is_super or has_capability(request.user, 'projects.view'),
        'show_inventory_stats': is_super or has_capability(request.user, 'inventory.view'),
    }

    actionable_approvals = actionable_approvals_for_user(request.user)
    submitted_approvals = ApprovalRequest.objects.filter(
        company=company,
        requester=request.user,
        status='pending',
    )
    context.update({
        'approval_requests': actionable_approvals[:10],
        'pending_my_approval_count': len(actionable_approvals),
        'submitted_for_approval_count': submitted_approvals.count(),
        'returned_approval_count': ApprovalRequest.objects.filter(
            company=company,
            requester=request.user,
            status__in=['returned', 'rejected'],
        ).count(),
        'recent_approval_count': ApprovalDecision.objects.filter(
            request__company=company,
            actor=request.user,
            decision='approved',
            created_at__gte=timezone.now() - timedelta(days=30),
        ).count(),
    })

    # --- Employee stats (HR / admin / manager / accountant) ---
    if context['show_employee_stats']:
        employee_stats = (
            Employee.objects
            .filter(company=company)
            .aggregate(
                total=Count('id'),
                active=Count('id', filter=Q(status='active')),
                on_leave=Count('id', filter=Q(status='on_leave')),
            )
        )
        context.update({
            'total_employees': employee_stats['total'],
            'active_employees': employee_stats['active'],
            'on_leave_count': employee_stats['on_leave'],
            'recent_employees': (
                Employee.objects
                .filter(company=company)
                .select_related('user')
                .order_by('-created_at')[:5]
            ),
        })

    # --- Project stats (users with project access) ---
    today = timezone.localdate()
    if context['show_project_stats']:
        project_stats = (
            Project.objects
            .filter(company=company)
            .aggregate(
                total=Count('id'),
                active=Count('id', filter=Q(status='in_progress')),
                completed=Count('id', filter=Q(status='completed')),
                overdue=Count('id', filter=Q(
                    end_date__lt=today, status__in=['planning', 'in_progress']
                )),
            )
        )
        context.update({
            'total_projects': project_stats['total'],
            'active_projects': project_stats['active'],
            'completed_projects': project_stats['completed'],
            'overdue_projects': project_stats['overdue'],
            'recent_projects': (
                Project.objects
                .filter(company=company)
                .order_by('-created_at')[:5]
            ),
        })

    # --- Inventory stats (users with inventory access) ---
    if context['show_inventory_stats']:
        stock_stats = (
            Stock.objects
            .filter(company=company)
            .aggregate(
                total=Count('id'),
                low=Count('id', filter=Q(quantity__lte=F('reorder_level'))),
            )
        )
        context.update({
            'total_stock_items': stock_stats['total'],
            'low_stock_count': stock_stats['low'],
            'low_stock_items': (
                Stock.objects
                .filter(company=company, quantity__lte=F('reorder_level'))
                .order_by('quantity')[:10]
            ),
        })

    # --- Finance stats (admin / accountant / manager) ---
    if context['show_finance_stats']:
        accounts = Account.objects.filter(company=company)
        total_balance = accounts.aggregate(total=Sum('balance'))['total'] or 0
        from datetime import date
        month_start = date.today().replace(day=1)
        monthly_credits = (
            Transaction.objects
            .filter(company=company, transaction_type='credit', date__gte=month_start)
            .aggregate(total=Sum('amount'))['total'] or 0
        )
        monthly_debits = (
            Transaction.objects
            .filter(company=company, transaction_type='debit', date__gte=month_start)
            .aggregate(total=Sum('amount'))['total'] or 0
        )
        context.update({
            'total_balance': total_balance,
            'monthly_credits': monthly_credits,
            'monthly_debits': monthly_debits,
        })

    # --- Online users (active in last 5 minutes, same company) ---
    try:
        online_cutoff = timezone.now() - timedelta(minutes=5)
        context['online_users'] = (
            User.objects
            .filter(company=company, last_seen__gte=online_cutoff, is_active=True)
            .order_by('-last_seen')
        )
    except Exception:
        context['online_users'] = []

    return render(request, 'core/dashboard.html', context)


@login_required
def platform_dashboard(request):
    """Superuser-only view — global stats across all companies."""
    if not request.user.is_superuser:
        return HttpResponseForbidden()

    online_cutoff = timezone.now() - timedelta(minutes=5)

    companies = (
        Company.objects
        .annotate(
            user_count=Count('users'),
            online_count=Count('users', filter=Q(users__last_seen__gte=online_cutoff)),
        )
        .order_by('-created_at')
    )

    total_users   = User.objects.filter(is_active=True).count()
    online_users  = User.objects.filter(last_seen__gte=online_cutoff, is_active=True)
    total_companies = companies.count()

    return render(request, 'core/platform_dashboard.html', {
        'companies':       companies,
        'total_companies': total_companies,
        'total_users':     total_users,
        'online_users':    online_users,
        'online_count':    online_users.count(),
    })