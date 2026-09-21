"""
accounts/permissions.py

Single source of truth for role-based access control across all apps.

Role hierarchy (highest → lowest):
    superuser  — Django superuser, bypasses all checks
    admin      — Full company admin
    manager    — Full access to all modules (departments, employees, projects, finance, inventory, HR, CRM, meetings, marketplace)
    hr_manager — HR management
    accountant — Finance read/write
    secretary  — CRM, scheduling
    stock_manager — Inventory management
    employee   — Self-service only
"""

from functools import wraps

from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.http import HttpResponseForbidden
from django.shortcuts import redirect

# ---------------------------------------------------------------------------
# Role group constants
# ---------------------------------------------------------------------------

# Employees app
EMPLOYEE_VIEW_ROLES   = ('admin', 'hr_manager', 'manager', 'accountant', 'secretary', 'stock_manager', 'employee')
EMPLOYEE_WRITE_ROLES  = ('admin', 'hr_manager', 'manager')
EMPLOYEE_DELETE_ROLES = ('admin', 'manager')
EMPLOYEE_EXPORT_ROLES = ('admin', 'hr_manager', 'accountant', 'manager')

# Departments
DEPARTMENT_WRITE_ROLES  = ('admin', 'hr_manager', 'manager')
DEPARTMENT_DELETE_ROLES = ('admin', 'manager')

# Projects app
PROJECT_VIEW_ROLES   = ('admin', 'manager', 'hr_manager', 'accountant', 'secretary', 'stock_manager', 'employee')
PROJECT_WRITE_ROLES  = ('admin', 'manager', 'hr_manager')
PROJECT_DELETE_ROLES = ('admin', 'manager')
PROJECT_REPORT_ROLES = ('admin', 'manager', 'accountant')

# Tasks (sous-tâches) — broader, team members should be able to update their tasks
TASK_WRITE_ROLES  = ('admin', 'manager', 'hr_manager', 'secretary', 'stock_manager', 'employee')
TASK_DELETE_ROLES = ('admin', 'manager')

# Inventory app
INVENTORY_VIEW_ROLES    = ('admin', 'manager', 'hr_manager', 'accountant', 'secretary', 'stock_manager', 'employee')
INVENTORY_WRITE_ROLES   = ('admin', 'stock_manager', 'manager')
INVENTORY_MANAGE_ROLES  = ('admin', 'manager', 'stock_manager')
INVENTORY_REPORT_ROLES  = ('admin', 'manager', 'accountant', 'stock_manager')

# Finance app (defined here for completeness; also used in finance/views.py)
FINANCE_ROLES = ('admin', 'accountant', 'manager')

# HR app
HR_ROLES           = ('admin', 'hr_manager', 'manager')
LEAVE_SUBMIT_ROLES = ('admin', 'hr_manager', 'manager', 'secretary', 'accountant', 'stock_manager', 'employee')

# CRM app
CRM_ROLES = ('admin', 'manager', 'secretary')

# Meetings app
MEETINGS_VIEW_ROLES   = ('admin', 'hr_manager', 'manager', 'secretary', 'accountant', 'employee')
MEETINGS_WRITE_ROLES  = ('admin', 'hr_manager', 'manager', 'secretary')
MEETINGS_DELETE_ROLES = ('admin', 'manager')
MEETINGS_REPORT_ROLES = ('admin', 'manager', 'accountant')

# Marketplace admin
MARKETPLACE_ADMIN_ROLES = ('admin', 'manager', 'stock_manager')

# Dashboard sections — which roles see which stat blocks
DASHBOARD_FINANCE_ROLES  = ('admin', 'accountant', 'manager')
DASHBOARD_HR_ROLES       = ('admin', 'hr_manager', 'manager')
DASHBOARD_EMPLOYEE_ROLES = ('admin', 'hr_manager', 'manager', 'accountant')

# Sensitive legacy role groups retain their existing role compatibility while
# also honoring the company's effective capability overrides.
ROLE_GROUP_CAPABILITIES = {
    frozenset(EMPLOYEE_WRITE_ROLES): 'employees.manage',
    frozenset(EMPLOYEE_DELETE_ROLES): 'employees.manage',
    frozenset(EMPLOYEE_EXPORT_ROLES): 'reporting.export',
    frozenset(DEPARTMENT_WRITE_ROLES): 'employees.manage',
    frozenset(DEPARTMENT_DELETE_ROLES): 'employees.manage',
    frozenset(PROJECT_WRITE_ROLES): 'projects.manage',
    frozenset(PROJECT_DELETE_ROLES): 'projects.manage',
    frozenset(PROJECT_REPORT_ROLES): 'reporting.view',
    frozenset(INVENTORY_WRITE_ROLES): 'inventory.manage',
    frozenset(INVENTORY_MANAGE_ROLES): 'inventory.manage',
    frozenset(INVENTORY_REPORT_ROLES): 'reporting.view',
    frozenset(FINANCE_ROLES): 'finance.manage',
    frozenset(HR_ROLES): 'hr.manage',
    frozenset(CRM_ROLES): 'crm.manage',
}


def _explicit_view_capability(view_func, roles):
    """Translate legacy role decorators into capability checks for controlled users."""
    module = view_func.__module__.split('.')[-2]
    name = view_func.__name__
    role_set = frozenset(roles)

    if module == 'employees':
        return 'reporting.export' if 'export' in name or 'report' in name else ('employees.view' if role_set == frozenset(EMPLOYEE_VIEW_ROLES) else 'employees.manage')
    if module == 'finance':
        read_names = ('index', 'list', 'detail', 'report')
        return 'finance.view' if any(token in name for token in read_names) and not any(token in name for token in ('create', 'edit', 'delete', 'generate', 'upload')) else 'finance.manage'
    if module == 'hr':
        if 'payroll' in name or 'salary_component' in name or 'payslip' in name:
            return 'hr.manage_payroll'
        return 'hr.view' if (
            role_set == frozenset(LEAVE_SUBMIT_ROLES)
            or name.startswith('my_')
            or name in {'index', 'leave_list', 'position_list', 'attendance_list'}
        ) else 'hr.manage'
    if module == 'inventory':
        if role_set == frozenset(INVENTORY_VIEW_ROLES):
            return 'inventory.view'
        if role_set == frozenset(INVENTORY_REPORT_ROLES):
            return 'reporting.view'
        if role_set == frozenset(INVENTORY_MANAGE_ROLES):
            return 'inventory.manage'
        return 'inventory.issue' if 'transaction' in name or 'remove' in name else 'inventory.manage'
    if module == 'crm':
        return 'crm.view' if any(token in name for token in ('index', 'list', 'detail', 'pipeline')) and not any(token in name for token in ('create', 'edit', 'delete', 'advance', 'paid', 'add')) else 'crm.manage'
    if module == 'projects':
        return 'projects.view' if any(token in name for token in ('list', 'detail', 'calendar', 'kanban', 'gantt', 'summary')) and not any(token in name for token in ('create', 'edit', 'delete', 'toggle', 'status')) else 'projects.manage'
    if module == 'meetings':
        return 'meetings.view' if any(token in name for token in ('dashboard', 'list', 'detail', 'report', 'view')) and not any(token in name for token in ('create', 'edit', 'delete', 'toggle', 'upload')) else 'meetings.manage'
    return ROLE_GROUP_CAPABILITIES.get(role_set)


# ---------------------------------------------------------------------------
# Decorators
# ---------------------------------------------------------------------------

def role_required(*allowed_roles, redirect_url: str = 'core:dashboard'):
    """
    Restrict a view to users whose role is in ``allowed_roles``.
    Superusers always pass.

    Usage:
        @role_required('admin', 'hr_manager')
        def my_view(request): ...

        @role_required(*EMPLOYEE_WRITE_ROLES)
        def create_employee(request): ...
    """
    # Flatten in case a list/tuple is passed by mistake
    flattened = []
    for role in allowed_roles:
        if isinstance(role, (list, tuple)):
            flattened.extend(role)
        else:
            flattened.append(role)
    roles = set(flattened)
    required_capability = ROLE_GROUP_CAPABILITIES.get(frozenset(roles))

    def decorator(view_func):
        @wraps(view_func)
        @login_required
        def wrapper(request, *args, **kwargs):
            has_required_capability = True
            if getattr(request.user, 'access_controlled', False):
                from governance.models import has_capability
                explicit_capability = _explicit_view_capability(view_func, roles)
                has_required_capability = bool(explicit_capability and has_capability(request.user, explicit_capability))
            elif required_capability:
                from governance.models import has_capability
                has_required_capability = has_capability(request.user, required_capability)
            if request.user.is_superuser or (request.user.role in roles and has_required_capability):
                return view_func(request, *args, **kwargs)
            if getattr(request.user, 'access_controlled', False):
                return HttpResponseForbidden('This module or function is not assigned to your account.')
            messages.error(
                request,
                'You do not have permission to access that page. '
                f'Required role(s): {", ".join(sorted(roles))}.',
            )
            return redirect(redirect_url)
        return wrapper
    return decorator


def company_admin_required(view_func=None, *, redirect_url: str = 'core:dashboard'):
    """
    Only company admins (or superusers) may access the view.

    Usage:
        @company_admin_required
        def admin_view(request): ...

        @company_admin_required(redirect_url='accounts:company_login')
        def sensitive_view(request): ...
    """
    def decorator(func):
        @wraps(func)
        @login_required
        def wrapper(request, *args, **kwargs):
            if request.user.is_superuser or request.user.is_company_admin:
                return func(request, *args, **kwargs)
            messages.error(request, 'Only company administrators can access this page.')
            return redirect(redirect_url)
        return wrapper

    if view_func is not None:
        return decorator(view_func)
    return decorator