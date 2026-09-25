"""
employees/views.py

All views are login-required and scoped to request.user.company.
Import/export uses pandas + openpyxl (must be installed).
"""

import io
import logging
from datetime import timedelta

from django.contrib import messages
from django.core.paginator import EmptyPage, PageNotAnInteger, Paginator
from django.db import transaction
from django.db.models import Avg, Count, Max, Min, Q, Sum
from django.http import HttpResponse
from django.shortcuts import get_object_or_404, redirect, render
from django.utils import timezone
from django.views.decorators.http import require_http_methods

from accounts.models import User
from accounts.permissions import (
    DEPARTMENT_DELETE_ROLES,
    DEPARTMENT_WRITE_ROLES,
    EMPLOYEE_DELETE_ROLES,
    EMPLOYEE_EXPORT_ROLES,
    EMPLOYEE_VIEW_ROLES,
    EMPLOYEE_WRITE_ROLES,
    role_required,
)
from .forms import DepartmentForm, EmployeeForm
from .models import Department, Employee
from governance.models import ApprovalStep, ApprovalWorkflow, AuditEvent
from governance.services import submit_for_approval

logger = logging.getLogger(__name__)

PAGE_SIZE = 25


def _ensure_employee_onboarding_workflow(company):
    """Ensure a basic manager approval workflow exists for employee onboarding."""
    workflow, created = ApprovalWorkflow.objects.get_or_create(
        company=company,
        transaction_type='employee_onboarding',
        defaults={
            'name': 'Employee onboarding approval',
            'enabled': True,
            'allow_self_approval': False,
        },
    )
    if created or not workflow.steps.exists():
        ApprovalStep.objects.get_or_create(
            workflow=workflow,
            sequence=1,
            defaults={'role': 'manager', 'required': True},
        )
    return workflow


def _paginate(qs, page_number, per_page=PAGE_SIZE):
    paginator = Paginator(qs, per_page)
    try:
        return paginator.page(page_number)
    except PageNotAnInteger:
        return paginator.page(1)
    except EmptyPage:
        return paginator.page(paginator.num_pages)


# ---------------------------------------------------------------------------
# Employees
# ---------------------------------------------------------------------------

@role_required(*EMPLOYEE_VIEW_ROLES)
def employee_list(request):
    """List employees with search, filtering, and pagination."""
    company = request.user.company
    qs = Employee.objects.filter(company=company).select_related('user', 'department')

    query = request.GET.get('q', '').strip()
    if query:
        qs = qs.filter(
            Q(user__first_name__icontains=query)
            | Q(user__last_name__icontains=query)
            | Q(employee_id__icontains=query)
            | Q(user__email__icontains=query)
            | Q(department__name__icontains=query)
        )

    department_id = request.GET.get('department', '')
    if department_id:
        qs = qs.filter(department_id=department_id)

    status = request.GET.get('status', '')
    if status in dict(Employee.STATUS_CHOICES):
        qs = qs.filter(status=status)

    role = request.GET.get('role', '')
    if role in dict(Employee.ROLE_CHOICES):
        qs = qs.filter(role=role)

    # Stats are computed on the *unfiltered* company queryset so the counts
    # always reflect company totals, not the current search result.
    company_qs = Employee.objects.filter(company=company)
    stats = company_qs.aggregate(
        total=Count('id'),
        active=Count('id', filter=Q(status='active')),
        on_leave=Count('id', filter=Q(status='on_leave')),
        terminated=Count('id', filter=Q(status='terminated')),
    )

    departments = Department.objects.filter(company=company, is_active=True).order_by('name')

    context = {
        'employees': _paginate(qs.order_by('-created_at'), request.GET.get('page')),
        'departments': departments,
        'query': query,
        'selected_department': department_id,
        'selected_status': status,
        'selected_role': role,
        'stats': stats,
        # Flat variables expected by the template stat cards
        'total_employees': stats['total'],
        'active_employees': stats['active'],
        'on_leave_employees': stats['on_leave'],
        'ROLE_CHOICES': Employee.ROLE_CHOICES,
        'STATUS_CHOICES': Employee.STATUS_CHOICES,
    }
    return render(request, 'employees/employee_list.html', context)


@role_required(*EMPLOYEE_VIEW_ROLES)
def employee_detail(request, pk):
    company = request.user.company
    employee = get_object_or_404(
        Employee.objects.select_related('user', 'department'),
        pk=pk,
        company=company,
    )
    # Salary is sensitive: only HR, admin, and managers see it.
    # An employee can see their own salary.
    can_see_salary = (
        request.user.is_superuser
        or request.user.role in ('admin', 'hr_manager', 'manager', 'accountant')
        or (hasattr(request.user, 'employee_profile') and request.user.employee_profile.pk == employee.pk)
    )
    can_see_private = (
        request.user.is_superuser
        or request.user.role in ('admin', 'hr_manager')
        or (hasattr(request.user, 'employee_profile') and request.user.employee_profile.pk == employee.pk)
    )
    return render(request, 'employees/employee_detail.html', {
        'employee': employee,
        'can_see_salary': can_see_salary,
        'can_see_private': can_see_private,
    })


@role_required(*EMPLOYEE_WRITE_ROLES)
@require_http_methods(['GET', 'POST'])
def employee_create(request):
    company = request.user.company
    if request.method == 'POST':
        form = EmployeeForm(request.POST, request.FILES, company=company)
        if form.is_valid():
            form.requester = request.user
            employee = form.save()

            messages.success(request, f'Employee {employee.employee_id} submitted for manager approval.')
            logger.info('Employee submitted for approval: %s (company: %s)', employee.employee_id, company)
            AuditEvent.record(actor=request.user, company=company, module='employees', action='employee_created_pending_approval', obj=employee, request=request)
            return redirect('employees:employee_list')
    else:
        form = EmployeeForm(company=company)
    return render(request, 'employees/employee_form.html', {'form': form, 'title': 'Add Employee'})


@role_required(*EMPLOYEE_WRITE_ROLES)
@require_http_methods(['GET', 'POST'])
def employee_edit(request, pk):
    company = request.user.company
    employee = get_object_or_404(Employee, pk=pk, company=company)
    if request.method == 'POST':
        form = EmployeeForm(request.POST, request.FILES, instance=employee, company=company)
        if form.is_valid():
            form.save()
            messages.success(request, f'Employee {employee.employee_id} updated.')
            return redirect('employees:employee_detail', pk=employee.pk)
    else:
        form = EmployeeForm(instance=employee, company=company)
    return render(request, 'employees/employee_form.html', {
        'form': form,
        'employee': employee,
        'title': 'Edit Employee',
    })


@role_required(*EMPLOYEE_DELETE_ROLES)
@require_http_methods(['GET', 'POST'])
def employee_delete(request, pk):
    company = request.user.company
    employee = get_object_or_404(Employee, pk=pk, company=company)
    if request.method == 'POST':
        if employee.user_id and employee.user.is_active:
            messages.error(request, 'This employee is linked to an active ERP account. Suspend or terminate the account before deleting the employee record.')
            return redirect('employees:employee_detail', pk=employee.pk)
        label = f'{employee.employee_id} — {employee.full_name}'
        employee.delete()
        messages.success(request, f'Employee {label} deleted.')
        return redirect('employees:employee_list')
    return render(request, 'employees/employee_confirm_delete.html', {'employee': employee})


# ---------------------------------------------------------------------------
# Departments
# ---------------------------------------------------------------------------

@role_required(*EMPLOYEE_VIEW_ROLES)
def department_list(request):
    company = request.user.company
    departments = (
        Department.objects
        .filter(company=company)
        .annotate(
            employee_count=Count('employees'),
            active_count=Count('employees', filter=Q(employees__status='active')),
        )
        .order_by('name')
    )
    return render(request, 'employees/department_list.html', {'departments': departments})


@role_required(*DEPARTMENT_WRITE_ROLES)
@require_http_methods(['GET', 'POST'])
def department_create(request):
    company = request.user.company
    if request.method == 'POST':
        form = DepartmentForm(request.POST, company=company)
        if form.is_valid():
            dept = form.save()
            messages.success(request, f'Department "{dept.name}" created.')
            return redirect('employees:department_list')
    else:
        form = DepartmentForm(company=company)
    return render(request, 'employees/department_form.html', {'form': form, 'title': 'Add Department'})


@role_required(*DEPARTMENT_WRITE_ROLES)
@require_http_methods(['GET', 'POST'])
def department_edit(request, pk):
    company = request.user.company
    department = get_object_or_404(Department, pk=pk, company=company)
    if request.method == 'POST':
        form = DepartmentForm(request.POST, instance=department, company=company)
        if form.is_valid():
            form.save()
            messages.success(request, f'Department "{department.name}" updated.')
            return redirect('employees:department_list')
    else:
        form = DepartmentForm(instance=department, company=company)
    return render(request, 'employees/department_form.html', {
        'form': form,
        'department': department,
        'title': 'Edit Department',
    })


@role_required(*DEPARTMENT_DELETE_ROLES)
@require_http_methods(['GET', 'POST'])
def department_delete(request, pk):
    company = request.user.company
    department = get_object_or_404(Department, pk=pk, company=company)
    if request.method == 'POST':
        name = department.name
        department.delete()
        messages.success(request, f'Department "{name}" deleted.')
        return redirect('employees:department_list')
    return render(request, 'employees/department_confirm_delete.html', {'department': department})


# ---------------------------------------------------------------------------
# Import / Export
# ---------------------------------------------------------------------------

@role_required(*EMPLOYEE_EXPORT_ROLES)
def employee_export(request):
    """Export all company employees to an .xlsx file."""
    import pandas as pd

    company = request.user.company
    employees = (
        Employee.objects
        .filter(company=company)
        .select_related('user', 'department')
        .order_by('employee_id')
    )

    rows = [
        {
            'Employee ID': emp.employee_id,
            'First Name': emp.user.first_name,
            'Last Name': emp.user.last_name,
            'Email': emp.user.email,
            'Phone': emp.user.phone,
            'Department': emp.department.name if emp.department else '',
            'Role': emp.get_role_display(),
            'Status': emp.get_status_display(),
            'Date Joined': emp.date_joined.strftime('%Y-%m-%d') if emp.date_joined else '',
            'Salary': float(emp.salary or 0),
            'Date of Birth': emp.date_of_birth.strftime('%Y-%m-%d') if emp.date_of_birth else '',
        }
        for emp in employees
    ]

    buffer = io.BytesIO()
    df = pd.DataFrame(rows)
    with pd.ExcelWriter(buffer, engine='openpyxl') as writer:
        df.to_excel(writer, sheet_name='Employees', index=False)
        ws = writer.sheets['Employees']
        for col in ws.columns:
            width = max((len(str(c.value)) for c in col if c.value), default=10) + 2
            ws.column_dimensions[col[0].column_letter].width = min(width, 50)
    buffer.seek(0)

    response = HttpResponse(
        buffer.getvalue(),
        content_type='application/vnd.openxmlformats-officedocument.spreadsheetml.sheet',
    )
    response['Content-Disposition'] = 'attachment; filename="employees_export.xlsx"'
    logger.info('Employee export by %s (%d rows)', request.user.email, len(rows))
    return response


@role_required(*EMPLOYEE_WRITE_ROLES)
@require_http_methods(['GET', 'POST'])
def employee_import(request):
    """Import employees from an .xlsx/.xls file."""
    import pandas as pd

    company = request.user.company

    if request.method == 'POST':
        excel_file = request.FILES.get('excel_file')
        if not excel_file:
            messages.error(request, 'No file was uploaded.')
            return redirect('employees:employee_import')

        if not excel_file.name.lower().endswith(('.xlsx', '.xls')):
            messages.error(request, 'Please upload a valid Excel file (.xlsx or .xls).')
            return redirect('employees:employee_import')

        # Reject suspiciously large uploads (10 MB cap)
        if excel_file.size > 10 * 1024 * 1024:
            messages.error(request, 'File is too large (max 10 MB).')
            return redirect('employees:employee_import')

        try:
            df = pd.read_excel(excel_file)
        except Exception as exc:
            messages.error(request, f'Could not read Excel file: {exc}')
            return redirect('employees:employee_import')

        required_columns = ['Employee ID', 'First Name', 'Last Name', 'Email']
        missing = [c for c in required_columns if c not in df.columns]
        if missing:
            messages.error(request, f'Missing required columns: {", ".join(missing)}')
            return redirect('employees:employee_import')

        success_count = 0
        errors = []

        # Each row is processed in its own savepoint so one bad row doesn't
        # roll back successful rows.
        for idx, row in df.iterrows():
            row_num = idx + 2
            try:
                emp_id = str(row['Employee ID']).strip()
                first_name = str(row['First Name']).strip()
                last_name = str(row['Last Name']).strip()
                email = str(row['Email']).strip().lower()
                salary = float(row.get('Salary') or 0)

                if not all([emp_id, first_name, last_name, email]):
                    errors.append(f'Row {row_num}: Missing required fields.')
                    continue

                if Employee.objects.filter(company=company, employee_id=emp_id).exists():
                    errors.append(f'Row {row_num}: Employee ID "{emp_id}" already exists.')
                    continue

                with transaction.atomic():
                    user, _ = User.objects.get_or_create(
                        email=email,
                        defaults={
                            'first_name': first_name,
                            'last_name': last_name,
                            'company': company,
                        },
                    )
                    # If user already existed, update name fields
                    if not _:
                        user.first_name = first_name
                        user.last_name = last_name
                        user.save(update_fields=['first_name', 'last_name'])

                    if hasattr(user, 'employee_profile'):
                        errors.append(f'Row {row_num}: User {email} already has an employee profile.')
                        continue

                    if 'Phone' in df.columns and pd.notna(row.get('Phone')):
                        user.phone = str(row['Phone']).strip()
                        user.save(update_fields=['phone'])

                    department = None
                    if 'Department' in df.columns and pd.notna(row.get('Department')):
                        dept_name = str(row['Department']).strip().title()
                        department, _ = Department.objects.get_or_create(
                            name=dept_name,
                            company=company,
                            defaults={'description': ''},
                        )

                    role = str(row.get('Role', 'other')).strip().lower()
                    if role not in dict(Employee.ROLE_CHOICES):
                        role = 'other'

                    status = str(row.get('Status', 'active')).strip().lower()
                    if status not in dict(Employee.STATUS_CHOICES):
                        status = 'active'

                    date_joined = timezone.now().date()
                    if 'Date Joined' in df.columns and pd.notna(row.get('Date Joined')):
                        try:
                            date_joined = pd.to_datetime(row['Date Joined']).date()
                        except Exception:
                            pass

                    emp = Employee(
                        company=company,
                        user=user,
                        employee_id=emp_id,
                        department=department,
                        role=role,
                        status=status,
                        date_joined=date_joined,
                        salary=salary,
                    )

                    if 'Date of Birth' in df.columns and pd.notna(row.get('Date of Birth')):
                        try:
                            emp.date_of_birth = pd.to_datetime(row['Date of Birth']).date()
                        except Exception:
                            pass

                    emp.save()
                    success_count += 1

            except Exception as exc:
                errors.append(f'Row {row_num}: {exc}')

        if success_count:
            messages.success(request, f'Successfully imported {success_count} employee(s).')
        if errors:
            messages.warning(
                request,
                f'{len(errors)} row(s) had errors. First few: {"; ".join(errors[:5])}',
            )

        logger.info(
            'Employee import by %s: %d success, %d errors',
            request.user.email, success_count, len(errors),
        )
        return redirect('employees:employee_list')

    return render(request, 'employees/employee_import.html')


@role_required(*EMPLOYEE_WRITE_ROLES)
def download_employee_template(request):
    """Download a blank Excel template for bulk import."""
    import pandas as pd

    sample = [{
        'Employee ID': 'EMP-001',
        'First Name': 'John',
        'Last Name': 'Doe',
        'Email': 'john.doe@company.com',
        'Phone': '+1234567890',
        'Department': 'Engineering',
        'Role': 'developer',
        'Status': 'active',
        'Date Joined': '2024-01-15',
        'Salary': 50000,
        'Date of Birth': '1990-05-20',
    }]

    instructions = pd.DataFrame({
        'Column': ['Employee ID', 'First Name', 'Last Name', 'Email', 'Phone',
                   'Department', 'Role', 'Status', 'Date Joined', 'Salary', 'Date of Birth'],
        'Required': ['Yes', 'Yes', 'Yes', 'Yes', 'No', 'No', 'No', 'No', 'No', 'No', 'No'],
        'Notes': [
            'Unique ID per company', 'First name', 'Last name', 'Unique email',
            'E.g. +1234567890', 'Created if not exists',
            'manager | developer | designer | analyst | engineer | intern | hr | accountant | secretary | other',
            'active | inactive | on_leave | terminated',
            'YYYY-MM-DD', 'Annual gross salary', 'YYYY-MM-DD',
        ],
    })

    buffer = io.BytesIO()
    with pd.ExcelWriter(buffer, engine='openpyxl') as writer:
        pd.DataFrame(sample).to_excel(writer, sheet_name='Template', index=False)
        instructions.to_excel(writer, sheet_name='Instructions', index=False)
    buffer.seek(0)

    response = HttpResponse(
        buffer.getvalue(),
        content_type='application/vnd.openxmlformats-officedocument.spreadsheetml.sheet',
    )
    response['Content-Disposition'] = 'attachment; filename="employee_import_template.xlsx"'
    return response


# ---------------------------------------------------------------------------
# Reports
# ---------------------------------------------------------------------------

@role_required(*EMPLOYEE_EXPORT_ROLES)
def employee_summary_report(request):
    company = request.user.company
    employees = Employee.objects.filter(company=company)
    total = employees.count()

    status_counts = employees.aggregate(
        active=Count('id', filter=Q(status='active')),
        inactive=Count('id', filter=Q(status='inactive')),
        on_leave=Count('id', filter=Q(status='on_leave')),
        terminated=Count('id', filter=Q(status='terminated')),
    )

    role_distribution = [
        {
            'role': rc['role'],
            'count': rc['count'],
            'percentage': round(rc['count'] / total * 100, 1) if total else 0,
        }
        for rc in employees.values('role').annotate(count=Count('id')).order_by('-count')
    ]

    dept_distribution = [
        {
            'department': dc['department__name'] or 'Unassigned',
            'count': dc['count'],
            'percentage': round(dc['count'] / total * 100, 1) if total else 0,
        }
        for dc in employees.values('department__name').annotate(count=Count('id')).order_by('-count')
    ]

    salary_stats = employees.aggregate(
        avg=Avg('salary'),
        total=Sum('salary'),
        minimum=Min('salary'),
        maximum=Max('salary'),
    )

    thirty_days_ago = timezone.localdate() - timedelta(days=30)
    recent_hires = (
        employees
        .filter(date_joined__gte=thirty_days_ago)
        .select_related('user', 'department')
        .order_by('-date_joined')[:10]
    )

    return render(request, 'employees/employee_summary_report.html', {
        'total_employees': total,
        'status_counts': status_counts,
        'role_distribution': role_distribution,
        'dept_distribution': dept_distribution,
        'salary_stats': salary_stats,
        'recent_hires': recent_hires,
        'report_date': timezone.localdate(),
    })


@role_required(*EMPLOYEE_EXPORT_ROLES)
def department_report(request):
    company = request.user.company
    departments = (
        Department.objects
        .filter(company=company)
        .annotate(
            employee_count=Count('employees'),
            avg_salary=Avg('employees__salary'),
            total_salary=Sum('employees__salary'),
            min_salary=Min('employees__salary'),
            max_salary=Max('employees__salary'),
            active_count=Count('employees', filter=Q(employees__status='active')),
            on_leave_count=Count('employees', filter=Q(employees__status='on_leave')),
        )
        .order_by('name')
    )

    totals = {
        'employees': sum(d.employee_count for d in departments),
        'active': sum(d.active_count or 0 for d in departments),
        'on_leave': sum(d.on_leave_count or 0 for d in departments),
        'salary': sum(d.total_salary or 0 for d in departments),
    }

    return render(request, 'employees/department_report.html', {
        'departments': departments,
        'totals': totals,
        'report_date': timezone.localdate(),
    })