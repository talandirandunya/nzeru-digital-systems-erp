"""
hr/views.py

HR module views:
  - Dashboard with stats
  - Position management (CRUD), linked to employees
  - Leave request management (CRUD + approve/deny)
  - Employee self-service leave submission
  - Payroll management (CRUD + processing)
  - Salary component management
  - Payslip generation and delivery
"""

import logging
from datetime import timedelta
from calendar import monthrange

from django.contrib import messages
from django.core.exceptions import ValidationError
from django.core.paginator import EmptyPage, PageNotAnInteger, Paginator
from django.db import transaction
from django.db.models import Count, Q, Sum
from django.http import HttpResponseForbidden
from django.shortcuts import get_object_or_404, redirect, render
from django.urls import reverse
from django.utils import timezone
from django.views.decorators.http import require_POST

from accounts.decorators import role_required
from employees.models import Employee
from governance.models import ApprovalStep, ApprovalWorkflow, AuditEvent
from governance.services import decide_approval, latest_approval_for, submit_for_approval

from .forms import (
    LeaveRequestForm, PositionForm, SalaryComponentForm, PayrollPeriodForm,
    PayrollEntryForm, PayrollEntryComponentFormSet,
    PerformanceGoalForm, PerformanceReviewForm, PerformanceReviewCommentForm,
    TrainingCourseForm, TrainingSessionForm, EmployeeTrainingForm,
    TrainingCompletionForm, SkillForm, EmployeeSkillForm, AttendanceRecordForm,
)
from .models import (
    LeaveRequest, Position, SalaryComponent, PayrollPeriod, PayrollEntry,
    PayrollEntryComponent, Payslip,
    PerformanceGoal, PerformanceReview, PerformanceReviewComment,
    TrainingCourse, TrainingSession, EmployeeTraining, Skill, EmployeeSkill,
    AttendanceRecord,
)

HR_ROLES = ['admin', 'hr_manager']
# Employees can submit their own leave requests
LEAVE_SUBMIT_ROLES = ['admin', 'hr_manager', 'manager', 'employee', 'secretary', 'accountant']


@role_required(*HR_ROLES)
def attendance_list(request):
    company = request.user.company
    records = AttendanceRecord.objects.filter(company=company).select_related('employee__user')
    date_filter = request.GET.get('date', '').strip()
    if date_filter:
        records = records.filter(attendance_date=date_filter)
    return render(request, 'hr/attendance_list.html', {'records': records.order_by('-attendance_date', 'employee__employee_id'), 'date_filter': date_filter})


@role_required(*HR_ROLES)
def attendance_create(request):
    company = request.user.company
    if request.method == 'POST':
        form = AttendanceRecordForm(request.POST, company=company)
        if form.is_valid():
            record = form.save(commit=False)
            record.company = company
            record.full_clean()
            record.save()
            messages.success(request, 'Attendance record saved.')
            return redirect('hr:attendance_list')
    else:
        form = AttendanceRecordForm(company=company)
    return render(request, 'hr/attendance_form.html', {'form': form, 'title': 'Attendance record'})


@role_required(*LEAVE_SUBMIT_ROLES)
@require_POST
def attendance_clock_in(request):
    employee = get_object_or_404(Employee, user=request.user, company=request.user.company)
    record, _ = AttendanceRecord.objects.get_or_create(
        company=request.user.company,
        employee=employee,
        attendance_date=timezone.localdate(),
    )
    try:
        record.clock_in_now()
        messages.success(request, 'Clocked in.')
    except Exception as exc:
        messages.error(request, str(exc))
    return redirect('hr:my_attendance')


@role_required(*LEAVE_SUBMIT_ROLES)
@require_POST
def attendance_clock_out(request):
    employee = get_object_or_404(Employee, user=request.user, company=request.user.company)
    record = get_object_or_404(AttendanceRecord, company=request.user.company, employee=employee, attendance_date=timezone.localdate())
    try:
        record.clock_out_now()
        messages.success(request, 'Clocked out.')
    except Exception as exc:
        messages.error(request, str(exc))
    return redirect('hr:my_attendance')


@role_required(*LEAVE_SUBMIT_ROLES)
def my_attendance(request):
    employee = get_object_or_404(Employee, user=request.user, company=request.user.company)
    records = AttendanceRecord.objects.filter(employee=employee).order_by('-attendance_date')[:60]
    today = records.filter(attendance_date=timezone.localdate()).first()
    return render(request, 'hr/my_attendance.html', {'records': records, 'today': today})

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Dashboard
# ---------------------------------------------------------------------------

@role_required(*HR_ROLES)
def index(request):
    company = request.user.company
    today = timezone.localdate()

    # Leave stats
    all_leaves = LeaveRequest.objects.filter(company=company)
    pending_count = all_leaves.filter(status='pending').count()
    approved_count = all_leaves.filter(status='approved').count()
    denied_count = all_leaves.filter(status='denied').count()

    # Currently on leave
    on_leave_now = all_leaves.filter(
        status='approved',
        start_date__lte=today,
        end_date__gte=today,
    ).select_related('employee__user').order_by('end_date')

    # Upcoming approved leaves (next 30 days)
    upcoming = all_leaves.filter(
        status='approved',
        start_date__gt=today,
        start_date__lte=today + timedelta(days=30),
    ).select_related('employee__user').order_by('start_date')[:5]

    # Pending requests needing review
    pending_requests = all_leaves.filter(status='pending').select_related(
        'employee__user'
    ).order_by('start_date')[:10]

    # Position stats
    position_count = Position.objects.filter(company=company).count()

    # Performance stats
    active_goals_count = PerformanceGoal.objects.filter(
        company=company,
        status__in=['planned', 'in_progress']
    ).count()
    pending_reviews_count = PerformanceReview.objects.filter(
        company=company,
        status__in=['draft', 'submitted']
    ).count()

    # Training stats
    active_courses_count = TrainingCourse.objects.filter(
        company=company,
        is_active=True
    ).count()

    # Enrolled this month
    start_of_month = today.replace(day=1)
    enrolled_this_month_count = EmployeeTraining.objects.filter(
        session__course__company=company,
        enrollment_date__gte=start_of_month
    ).count()

    # Recent performance data
    recent_goals = PerformanceGoal.objects.filter(company=company).select_related(
        'employee__user'
    ).order_by('-created_at')[:5]
    recent_reviews = PerformanceReview.objects.filter(company=company).select_related(
        'employee__user'
    ).order_by('-review_date')[:5]

    # Leave by type (for summary)
    leave_by_type = (
        all_leaves.filter(status='approved')
        .values('leave_type')
        .annotate(count=Count('id'))
        .order_by('-count')
    )

    context = {
        'pending_count': pending_count,
        'approved_count': approved_count,
        'denied_count': denied_count,
        'on_leave_now': on_leave_now,
        'upcoming': upcoming,
        'pending_requests': pending_requests,
        'position_count': position_count,
        'active_goals_count': active_goals_count,
        'pending_reviews_count': pending_reviews_count,
        'active_courses_count': active_courses_count,
        'enrolled_this_month_count': enrolled_this_month_count,
        'recent_goals': recent_goals,
        'recent_reviews': recent_reviews,
        'leave_by_type': leave_by_type,
        'today': today,
    }
    return render(request, 'hr/index.html', context)


# ---------------------------------------------------------------------------
# Positions
# ---------------------------------------------------------------------------

@role_required(*HR_ROLES)
def position_list(request):
    company = request.user.company
    positions = (
        Position.objects
        .filter(company=company)
        .annotate(emp_count=Count('employees', filter=Q(employees__status='active')))
        .order_by('salary_grade', 'title')
    )

    query = request.GET.get('q', '').strip()
    if query:
        positions = positions.filter(title__icontains=query)

    paginator = Paginator(positions, 25)
    page = request.GET.get('page')
    try:
        positions_page = paginator.page(page)
    except PageNotAnInteger:
        positions_page = paginator.page(1)
    except EmptyPage:
        positions_page = paginator.page(paginator.num_pages)

    return render(request, 'hr/position_list.html', {
        'positions': positions_page,
        'query': query,
    })


@role_required(*HR_ROLES)
def position_create(request):
    company = request.user.company
    if request.method == 'POST':
        form = PositionForm(request.POST)
        if form.is_valid():
            pos = form.save(commit=False)
            pos.company = company
            pos.save()
            messages.success(request, f'Position "{pos.title}" created.')
            return redirect('hr:position_list')
    else:
        form = PositionForm()
    return render(request, 'hr/position_form.html', {'form': form, 'title': 'New Position'})


@role_required(*HR_ROLES)
def position_edit(request, pk):
    company = request.user.company
    pos = get_object_or_404(Position, pk=pk, company=company)
    if request.method == 'POST':
        form = PositionForm(request.POST, instance=pos)
        if form.is_valid():
            form.save()
            messages.success(request, f'Position "{pos.title}" updated.')
            return redirect('hr:position_list')
    else:
        form = PositionForm(instance=pos)
    return render(request, 'hr/position_form.html', {'form': form, 'title': 'Edit Position'})


@role_required(*HR_ROLES)
def position_delete(request, pk):
    company = request.user.company
    pos = get_object_or_404(Position, pk=pk, company=company)
    if request.method == 'POST':
        title = pos.title
        pos.delete()
        messages.success(request, f'Position "{title}" deleted.')
        return redirect('hr:position_list')
    return render(request, 'hr/position_confirm_delete.html', {'position': pos})


# ---------------------------------------------------------------------------
# Leave Requests — HR management views
# ---------------------------------------------------------------------------

@role_required(*HR_ROLES)
def leave_list(request):
    company = request.user.company
    qs = (
        LeaveRequest.objects
        .filter(company=company)
        .select_related('employee__user', 'reviewed_by')
        .order_by('-requested_at')
    )

    # Filters
    status_filter = request.GET.get('status', '').strip()
    if status_filter:
        qs = qs.filter(status=status_filter)

    type_filter = request.GET.get('leave_type', '').strip()
    if type_filter:
        qs = qs.filter(leave_type=type_filter)

    query = request.GET.get('q', '').strip()
    if query:
        qs = qs.filter(
            Q(employee__user__first_name__icontains=query) |
            Q(employee__user__last_name__icontains=query) |
            Q(employee__employee_id__icontains=query)
        )

    paginator = Paginator(qs, 25)
    page = request.GET.get('page')
    try:
        leaves_page = paginator.page(page)
    except PageNotAnInteger:
        leaves_page = paginator.page(1)
    except EmptyPage:
        leaves_page = paginator.page(paginator.num_pages)

    return render(request, 'hr/leave_list.html', {
        'leaves': leaves_page,
        'status_filter': status_filter,
        'type_filter': type_filter,
        'query': query,
        'status_choices': LeaveRequest.STATUS_CHOICES,
        'leave_types': LeaveRequest.LEAVE_TYPES,
        'today': timezone.localdate(),
    })


@role_required(*HR_ROLES)
def leave_create(request):
    company = request.user.company
    if request.method == 'POST':
        form = LeaveRequestForm(request.POST, company=company)
        if form.is_valid():
            try:
                with transaction.atomic():
                    leave = form.save(commit=False)
                    leave.company = company
                    leave.submitted_by = request.user
                    leave.full_clean()
                    leave.save()
                    workflow, _ = ApprovalWorkflow.objects.get_or_create(
                        company=company,
                        transaction_type='leave_request',
                        name='Leave request approval',
                        defaults={'enabled': True, 'allow_self_approval': False},
                    )
                    step, _ = ApprovalStep.objects.get_or_create(
                        workflow=workflow,
                        sequence=1,
                        defaults={'capability': 'hr.manage', 'required': True},
                    )
                    if step.role == 'manager' and not step.capability:
                        step.role = ''
                        step.capability = 'hr.manage'
                        step.save(update_fields=['role', 'capability'])
                    approval = submit_for_approval(
                        target=leave,
                        requester=request.user,
                        transaction_type='leave_request',
                        reason='Leave request submitted for approval.',
                        request=request,
                    )
                messages.success(request, 'Leave request submitted for approval.')
                return redirect('hr:leave_list')
            except ValidationError as exc:
                form.add_error(None, exc.message if hasattr(exc, 'message') else str(exc))
    else:
        form = LeaveRequestForm(company=company)
    return render(request, 'hr/leave_form.html', {'form': form, 'title': 'New Leave Request'})


@role_required(*HR_ROLES)
def leave_edit(request, pk):
    company = request.user.company
    leave = get_object_or_404(LeaveRequest, pk=pk, company=company)
    if request.method == 'POST':
        form = LeaveRequestForm(request.POST, instance=leave, company=company)
        if form.is_valid():
            leave = form.save(commit=False)
            leave.full_clean()
            leave.save()
            messages.success(request, 'Leave request updated.')
            return redirect('hr:leave_list')
    else:
        form = LeaveRequestForm(instance=leave, company=company)
    return render(request, 'hr/leave_form.html', {'form': form, 'title': 'Edit Leave Request'})


@role_required(*HR_ROLES)
def leave_delete(request, pk):
    company = request.user.company
    leave = get_object_or_404(LeaveRequest, pk=pk, company=company)
    if request.method == 'POST':
        leave.delete()
        messages.success(request, 'Leave request deleted.')
        return redirect('hr:leave_list')
    return render(request, 'hr/leave_confirm_delete.html', {'leave': leave})


@role_required(*HR_ROLES)
@require_POST
def leave_approve(request, pk):
    company = request.user.company
    leave = get_object_or_404(LeaveRequest, pk=pk, company=company)
    approval = latest_approval_for(leave, company=company)
    if approval is None:
        messages.error(request, 'This leave request has no governance approval request.')
    else:
        try:
            decide_approval(approval=approval, actor=request.user, decision='approved', request=request)
            messages.success(request, f'{leave.employee.full_name}\'s leave request approved.')
        except ValidationError as exc:
            messages.error(request, str(exc))

    return redirect('hr:leave_list')


@role_required(*HR_ROLES)
@require_POST
def leave_deny(request, pk):
    company = request.user.company
    leave = get_object_or_404(LeaveRequest, pk=pk, company=company)
    approval = latest_approval_for(leave, company=company)
    if approval is None:
        messages.error(request, 'This leave request has no governance approval request.')
    else:
        try:
            decide_approval(approval=approval, actor=request.user, decision='rejected', reason='Denied by HR.', request=request)
            messages.success(request, f'{leave.employee.full_name}\'s leave request denied.')
        except ValidationError as exc:
            messages.error(request, str(exc))

    return redirect('hr:leave_list')


# ---------------------------------------------------------------------------
# Employee self-service
# ---------------------------------------------------------------------------

@role_required(*LEAVE_SUBMIT_ROLES)
def my_leave_list(request):
    """Employee view: see own leave requests."""
    user = request.user
    try:
        employee = user.employee_profile
    except Exception:
        messages.error(request, 'No employee profile found for your account.')
        return redirect('core:dashboard')

    leaves = (
        LeaveRequest.objects
        .filter(employee=employee)
        .order_by('-requested_at')
    )
    return render(request, 'hr/my_leave_list.html', {
        'leaves': leaves,
        'today': timezone.localdate(),
    })


@role_required(*LEAVE_SUBMIT_ROLES)
def my_leave_create(request):
    """Employee self-service: submit own leave request."""
    user = request.user
    try:
        employee = user.employee_profile
    except Exception:
        messages.error(request, 'No employee profile found for your account.')
        return redirect('core:dashboard')

    company = user.company
    if request.method == 'POST':
        form = LeaveRequestForm(request.POST, company=company, self_employee=employee)
        if form.is_valid():
            leave = form.save(commit=False)
            leave.company = company
            leave.employee = employee
            leave.submitted_by = user
            try:
                leave.full_clean()
            except Exception as e:
                messages.error(request, str(e))
                return render(request, 'hr/my_leave_form.html', {'form': form})
            leave.save()
            messages.success(request, 'Leave request submitted. Awaiting HR approval.')
            return redirect('hr:my_leave_list')
    else:
        form = LeaveRequestForm(company=company, self_employee=employee)
    return render(request, 'hr/my_leave_form.html', {'form': form})


# ---------------------------------------------------------------------------
# Salary Components Management
# ---------------------------------------------------------------------------

@role_required(*HR_ROLES)
def salary_component_list(request):
    """List salary components for the company."""
    company = request.user.company
    components = SalaryComponent.objects.filter(company=company).order_by('component_type', 'name')

    context = {
        'components': components,
        'title': 'Salary Components',
    }
    return render(request, 'hr/salary_component_list.html', context)


@role_required(*HR_ROLES)
def salary_component_create(request):
    """Create a new salary component."""
    company = request.user.company

    if request.method == 'POST':
        form = SalaryComponentForm(request.POST)
        if form.is_valid():
            component = form.save(commit=False)
            component.company = company
            component.save()
            messages.success(request, f'Salary component "{component.name}" created successfully.')
            return redirect('hr:salary_component_list')
    else:
        form = SalaryComponentForm()

    context = {
        'form': form,
        'title': 'Create Salary Component',
    }
    return render(request, 'hr/salary_component_form.html', context)


@role_required(*HR_ROLES)
def salary_component_edit(request, pk):
    """Edit an existing salary component."""
    company = request.user.company
    component = get_object_or_404(SalaryComponent, pk=pk, company=company)

    if request.method == 'POST':
        form = SalaryComponentForm(request.POST, instance=component)
        if form.is_valid():
            form.save()
            messages.success(request, f'Salary component "{component.name}" updated successfully.')
            return redirect('hr:salary_component_list')
    else:
        form = SalaryComponentForm(instance=component)

    context = {
        'form': form,
        'component': component,
        'title': 'Edit Salary Component',
    }
    return render(request, 'hr/salary_component_form.html', context)


@role_required(*HR_ROLES)
def salary_component_delete(request, pk):
    """Delete a salary component."""
    company = request.user.company
    component = get_object_or_404(SalaryComponent, pk=pk, company=company)

    if request.method == 'POST':
        component.delete()
        messages.success(request, f'Salary component "{component.name}" deleted successfully.')
        return redirect('hr:salary_component_list')

    context = {
        'component': component,
        'title': 'Delete Salary Component',
    }
    return render(request, 'hr/salary_component_confirm_delete.html', context)


# ---------------------------------------------------------------------------
# Payroll Period Management
# ---------------------------------------------------------------------------

@role_required(*HR_ROLES)
def payroll_period_list(request):
    """List payroll periods for the company."""
    company = request.user.company
    status_filter = request.GET.get('status', '')

    periods = PayrollPeriod.objects.filter(company=company)
    if status_filter:
        periods = periods.filter(status=status_filter)

    periods = periods.order_by('-end_date')

    context = {
        'periods': periods,
        'status_filter': status_filter,
        'status_choices': PayrollPeriod.STATUS_CHOICES,
        'title': 'Payroll Periods',
    }
    return render(request, 'hr/payroll_period_list.html', context)


@role_required(*HR_ROLES)
def payroll_period_create(request):
    """Create a new payroll period."""
    company = request.user.company

    if request.method == 'POST':
        form = PayrollPeriodForm(request.POST)
        if form.is_valid():
            period = form.save(commit=False)
            period.company = company
            period.save()
            messages.success(request, f'Payroll period created: {period}')
            return redirect('hr:payroll_period_detail', pk=period.pk)
    else:
        form = PayrollPeriodForm()

    context = {
        'form': form,
        'title': 'Create Payroll Period',
    }
    return render(request, 'hr/payroll_period_form.html', context)


@role_required(*HR_ROLES)
def payroll_period_detail(request, pk):
    """View payroll period details with entries."""
    company = request.user.company
    period = get_object_or_404(PayrollPeriod, pk=pk, company=company)

    entries = PayrollEntry.objects.filter(payroll_period=period).select_related('employee')

    context = {
        'period': period,
        'entries': entries,
        'title': f'Payroll Period: {period}',
    }
    return render(request, 'hr/payroll_period_detail.html', context)


@role_required(*HR_ROLES)
def payroll_period_add_entries(request, pk):
    """Add payroll entries to a period for all active employees."""
    company = request.user.company
    period = get_object_or_404(PayrollPeriod, pk=pk, company=company)

    if period.status != 'draft':
        messages.warning(request, 'Can only add entries to draft periods.')
        return redirect('hr:payroll_period_detail', pk=period.pk)

    # Get all active employees not already in this period
    active_employees = Employee.objects.filter(
        company=company,
        status__in=['active', 'on_leave']
    ).exclude(payroll_entries__payroll_period=period)

    count = 0
    for employee in active_employees:
        entry, created = PayrollEntry.objects.get_or_create(
            payroll_period=period,
            employee=employee,
            defaults={'base_salary': employee.salary}
        )
        if created:
            count += 1

    messages.success(request, f'Added payroll entries for {count} employees.')
    return redirect('hr:payroll_period_detail', pk=period.pk)


@role_required(*HR_ROLES)
def payroll_period_lock(request, pk):
    """Lock a payroll period to prevent further edits."""
    company = request.user.company
    period = get_object_or_404(PayrollPeriod, pk=pk, company=company)

    if not period.can_lock():
        messages.warning(request, 'Cannot lock this payroll period.')
    else:
        period.lock()
        messages.success(request, 'Payroll period locked for processing.')

    return redirect('hr:payroll_period_detail', pk=period.pk)


@role_required(*HR_ROLES)
def payroll_period_process(request, pk):
    """Process payroll and generate payslips."""
    company = request.user.company
    period = get_object_or_404(PayrollPeriod, pk=pk, company=company)

    if not period.can_process():
        messages.warning(request, 'Payroll period must be locked before processing.')
        return redirect('hr:payroll_period_detail', pk=period.pk)

    try:
        period.process(processed_by=request.user)
        messages.success(request, 'Payroll processed successfully. Payslips generated.')
    except Exception as e:
        messages.error(request, f'Error processing payroll: {str(e)}')

    return redirect('hr:payroll_period_detail', pk=period.pk)


# ---------------------------------------------------------------------------
# Payroll Entry Management
# ---------------------------------------------------------------------------

@role_required(*HR_ROLES)
def payroll_entry_edit(request, pk):
    """Edit a payroll entry and manage components."""
    company = request.user.company
    entry = get_object_or_404(PayrollEntry, pk=pk, payroll_period__company=company)

    if request.method == 'POST':
        form = PayrollEntryForm(request.POST, instance=entry, company=company, payroll_period=entry.payroll_period)
        formset = PayrollEntryComponentFormSet(request.POST, instance=entry)

        if form.is_valid() and formset.is_valid():
            form.save()
            formset.save()
            entry.calculate_totals()
            messages.success(request, 'Payroll entry updated successfully.')
            return redirect('hr:payroll_period_detail', pk=entry.payroll_period.pk)
    else:
        form = PayrollEntryForm(instance=entry, company=company, payroll_period=entry.payroll_period)
        formset = PayrollEntryComponentFormSet(instance=entry)

    context = {
        'form': form,
        'formset': formset,
        'entry': entry,
        'title': f'Edit Payroll Entry: {entry.employee.full_name}',
    }
    return render(request, 'hr/payroll_entry_form.html', context)


@role_required(*HR_ROLES)
def payroll_entry_delete(request, pk):
    """Delete a payroll entry."""
    company = request.user.company
    entry = get_object_or_404(PayrollEntry, pk=pk, payroll_period__company=company)
    period_pk = entry.payroll_period.pk

    if request.method == 'POST':
        entry.delete()
        messages.success(request, 'Payroll entry deleted successfully.')
        return redirect('hr:payroll_period_detail', pk=period_pk)

    context = {
        'entry': entry,
        'title': 'Delete Payroll Entry',
    }
    return render(request, 'hr/payroll_entry_confirm_delete.html', context)


# ---------------------------------------------------------------------------
# Payslip Management
# ---------------------------------------------------------------------------

@role_required(*HR_ROLES)
def payslip_list(request):
    """List all payslips for the company."""
    company = request.user.company
    
    payslips = Payslip.objects.filter(
        payroll_entry__payroll_period__company=company
    ).select_related(
        'payroll_entry__employee',
        'payroll_entry__payroll_period'
    ).order_by('-issued_date')

    paginator = Paginator(payslips, 25)
    page = request.GET.get('page')
    try:
        payslips_page = paginator.page(page)
    except PageNotAnInteger:
        payslips_page = paginator.page(1)
    except EmptyPage:
        payslips_page = paginator.page(paginator.num_pages)

    context = {
        'payslips': payslips_page,
        'title': 'Payslips',
    }
    return render(request, 'hr/payslip_list.html', context)


@role_required(*HR_ROLES)
def payslip_detail(request, pk):
    """View payslip details."""
    company = request.user.company
    payslip = get_object_or_404(
        Payslip.objects.select_related(
            'payroll_entry__employee',
            'payroll_entry__payroll_period'
        ),
        pk=pk,
        payroll_entry__payroll_period__company=company
    )

    components = PayrollEntryComponent.objects.filter(
        payroll_entry=payslip.payroll_entry
    ).select_related('component')

    context = {
        'payslip': payslip,
        'entry': payslip.payroll_entry,
        'components': components,
        'title': f'Payslip: {payslip.payslip_number}',
    }
    return render(request, 'hr/payslip_detail.html', context)


# ---------------------------------------------------------------------------
# Performance Management (Phase 2)
# ---------------------------------------------------------------------------

@role_required(*HR_ROLES)
def performance_goal_list(request):
    company = request.user.company
    goals = PerformanceGoal.objects.filter(company=company).select_related('employee__user').order_by('-end_date')

    status_filter = request.GET.get('status', '').strip()
    if status_filter:
        goals = goals.filter(status=status_filter)

    query = request.GET.get('q', '').strip()
    if query:
        goals = goals.filter(
            Q(title__icontains=query) |
            Q(description__icontains=query) |
            Q(employee__user__first_name__icontains=query) |
            Q(employee__user__last_name__icontains=query)
        )

    paginator = Paginator(goals, 25)
    page = request.GET.get('page')
    try:
        goals_page = paginator.page(page)
    except PageNotAnInteger:
        goals_page = paginator.page(1)
    except EmptyPage:
        goals_page = paginator.page(paginator.num_pages)

    return render(request, 'hr/performance_goal_list.html', {
        'goals': goals_page,
        'status_filter': status_filter,
        'query': query,
        'status_choices': PerformanceGoal.STATUS_CHOICES,
        'title': 'Performance Goals',
    })


@role_required(*HR_ROLES)
def performance_goal_create(request):
    company = request.user.company
    if request.method == 'POST':
        form = PerformanceGoalForm(request.POST, company=company)
        if form.is_valid():
            goal = form.save(commit=False)
            goal.company = company
            goal.save()
            messages.success(request, 'Performance goal created successfully.')
            return redirect('hr:performance_goal_list')
    else:
        form = PerformanceGoalForm(company=company)

    return render(request, 'hr/performance_goal_form.html', {
        'form': form,
        'title': 'New Performance Goal',
    })


@role_required(*HR_ROLES)
def performance_goal_edit(request, pk):
    company = request.user.company
    goal = get_object_or_404(PerformanceGoal, pk=pk, company=company)
    if request.method == 'POST':
        form = PerformanceGoalForm(request.POST, instance=goal, company=company)
        if form.is_valid():
            form.save()
            messages.success(request, 'Performance goal updated successfully.')
            return redirect('hr:performance_goal_list')
    else:
        form = PerformanceGoalForm(instance=goal, company=company)

    return render(request, 'hr/performance_goal_form.html', {
        'form': form,
        'title': 'Edit Performance Goal',
        'goal': goal,
    })


@role_required(*HR_ROLES)
def performance_goal_delete(request, pk):
    company = request.user.company
    goal = get_object_or_404(PerformanceGoal, pk=pk, company=company)
    if request.method == 'POST':
        goal.delete()
        messages.success(request, 'Performance goal deleted successfully.')
        return redirect('hr:performance_goal_list')

    return render(request, 'hr/performance_goal_confirm_delete.html', {
        'goal': goal,
        'title': 'Delete Performance Goal',
    })


@role_required(*HR_ROLES)
def performance_review_list(request):
    company = request.user.company
    reviews = PerformanceReview.objects.filter(company=company).select_related(
        'employee__user', 'reviewer__user'
    ).order_by('-review_date')

    status_filter = request.GET.get('status', '').strip()
    if status_filter:
        reviews = reviews.filter(status=status_filter)

    query = request.GET.get('q', '').strip()
    if query:
        reviews = reviews.filter(
            Q(employee__user__first_name__icontains=query) |
            Q(employee__user__last_name__icontains=query) |
            Q(reviewer__user__first_name__icontains=query) |
            Q(reviewer__user__last_name__icontains=query)
        )

    paginator = Paginator(reviews, 25)
    page = request.GET.get('page')
    try:
        reviews_page = paginator.page(page)
    except PageNotAnInteger:
        reviews_page = paginator.page(1)
    except EmptyPage:
        reviews_page = paginator.page(paginator.num_pages)

    return render(request, 'hr/performance_review_list.html', {
        'reviews': reviews_page,
        'status_filter': status_filter,
        'query': query,
        'status_choices': PerformanceReview.STATUS_CHOICES,
        'title': 'Performance Reviews',
    })


@role_required(*HR_ROLES)
def performance_review_create(request):
    company = request.user.company
    if request.method == 'POST':
        form = PerformanceReviewForm(request.POST, company=company)
        if form.is_valid():
            review = form.save(commit=False)
            review.company = company
            review.save()
            messages.success(request, 'Performance review created successfully.')
            return redirect('hr:performance_review_list')
    else:
        form = PerformanceReviewForm(company=company)

    return render(request, 'hr/performance_review_form.html', {
        'form': form,
        'title': 'New Performance Review',
    })


@role_required(*HR_ROLES)
def performance_review_detail(request, pk):
    company = request.user.company
    review = get_object_or_404(PerformanceReview, pk=pk, company=company)
    comments = review.comments.select_related('author').order_by('created_at')

    comment_form = PerformanceReviewCommentForm()

    return render(request, 'hr/performance_review_detail.html', {
        'review': review,
        'comments': comments,
        'comment_form': comment_form,
        'title': f'Performance Review: {review.employee.full_name}',
    })


@role_required(*HR_ROLES)
def performance_review_edit(request, pk):
    company = request.user.company
    review = get_object_or_404(PerformanceReview, pk=pk, company=company)
    if request.method == 'POST':
        form = PerformanceReviewForm(request.POST, instance=review, company=company)
        if form.is_valid():
            form.save()
            messages.success(request, 'Performance review updated successfully.')
            return redirect('hr:performance_review_detail', pk=review.pk)
    else:
        form = PerformanceReviewForm(instance=review, company=company)

    return render(request, 'hr/performance_review_form.html', {
        'form': form,
        'review': review,
        'title': 'Edit Performance Review',
    })


@role_required(*HR_ROLES)
def performance_review_delete(request, pk):
    company = request.user.company
    review = get_object_or_404(PerformanceReview, pk=pk, company=company)
    if request.method == 'POST':
        review.delete()
        messages.success(request, 'Performance review deleted successfully.')
        return redirect('hr:performance_review_list')

    return render(request, 'hr/performance_review_confirm_delete.html', {
        'review': review,
        'title': 'Delete Performance Review',
    })


@role_required(*HR_ROLES)
@require_POST
def performance_review_submit(request, pk):
    company = request.user.company
    review = get_object_or_404(PerformanceReview, pk=pk, company=company)
    try:
        review.submit(reviewer=request.user)
        messages.success(request, 'Performance review submitted.')
    except Exception as exc:
        messages.error(request, str(exc))
    return redirect('hr:performance_review_detail', pk=review.pk)


@role_required(*HR_ROLES)
@require_POST
def performance_review_complete(request, pk):
    company = request.user.company
    review = get_object_or_404(PerformanceReview, pk=pk, company=company)
    try:
        review.complete()
        messages.success(request, 'Performance review completed.')
    except Exception as exc:
        messages.error(request, str(exc))
    return redirect('hr:performance_review_detail', pk=review.pk)


@role_required(*HR_ROLES)
def performance_review_comment_create(request, pk):
    company = request.user.company
    review = get_object_or_404(PerformanceReview, pk=pk, company=company)

    if request.method == 'POST':
        form = PerformanceReviewCommentForm(request.POST)
        if form.is_valid():
            comment = form.save(commit=False)
            comment.review = review
            comment.author = request.user
            comment.save()
            messages.success(request, 'Comment added.')
            return redirect('hr:performance_review_detail', pk=review.pk)
    else:
        form = PerformanceReviewCommentForm()

    return render(request, 'hr/performance_review_detail.html', {
        'review': review,
        'comments': review.comments.select_related('author').order_by('created_at'),
        'comment_form': form,
        'title': f'Performance Review: {review.employee.full_name}',
    })


# ---------------------------------------------------------------------------
# Training & Development (Phase 3)
# ---------------------------------------------------------------------------

@role_required(*HR_ROLES)
def training_course_list(request):
    company = request.user.company
    courses = TrainingCourse.objects.filter(company=company).order_by('title')

    query = request.GET.get('q', '').strip()
    if query:
        courses = courses.filter(
            Q(title__icontains=query) |
            Q(description__icontains=query) |
            Q(provider__icontains=query)
        )

    course_type = request.GET.get('type', '').strip()
    if course_type:
        courses = courses.filter(course_type=course_type)

    paginator = Paginator(courses, 25)
    page = request.GET.get('page')
    try:
        courses_page = paginator.page(page)
    except PageNotAnInteger:
        courses_page = paginator.page(1)
    except EmptyPage:
        courses_page = paginator.page(paginator.num_pages)

    return render(request, 'hr/training_course_list.html', {
        'courses': courses_page,
        'query': query,
        'course_type': course_type,
        'course_types': TrainingCourse.COURSE_TYPES,
        'title': 'Training Courses',
    })


@role_required(*HR_ROLES)
def training_course_create(request):
    company = request.user.company
    if request.method == 'POST':
        form = TrainingCourseForm(request.POST)
        if form.is_valid():
            course = form.save(commit=False)
            course.company = company
            course.save()
            messages.success(request, 'Training course created successfully.')
            return redirect('hr:training_course_list')
    else:
        form = TrainingCourseForm()

    return render(request, 'hr/training_course_form.html', {
        'form': form,
        'title': 'New Training Course',
    })


@role_required(*HR_ROLES)
def training_course_edit(request, pk):
    company = request.user.company
    course = get_object_or_404(TrainingCourse, pk=pk, company=company)
    if request.method == 'POST':
        form = TrainingCourseForm(request.POST, instance=course)
        if form.is_valid():
            form.save()
            messages.success(request, 'Training course updated successfully.')
            return redirect('hr:training_course_list')
    else:
        form = TrainingCourseForm(instance=course)

    return render(request, 'hr/training_course_form.html', {
        'form': form,
        'course': course,
        'title': 'Edit Training Course',
    })


@role_required(*HR_ROLES)
def training_course_delete(request, pk):
    company = request.user.company
    course = get_object_or_404(TrainingCourse, pk=pk, company=company)
    if request.method == 'POST':
        course.delete()
        messages.success(request, 'Training course deleted successfully.')
        return redirect('hr:training_course_list')

    return render(request, 'hr/confirm_delete.html', {
        'object_type': 'training course',
        'object_name': course.title,
        'cancel_url': reverse('hr:training_course_list'),
    })


@role_required(*HR_ROLES)
def training_session_list(request):
    company = request.user.company
    sessions = TrainingSession.objects.filter(
        course__company=company
    ).select_related('course').order_by('-start_date')

    status_filter = request.GET.get('status', '').strip()
    if status_filter:
        sessions = sessions.filter(status=status_filter)

    query = request.GET.get('q', '').strip()
    if query:
        sessions = sessions.filter(
            Q(course__title__icontains=query) |
            Q(instructor__icontains=query) |
            Q(location__icontains=query)
        )

    paginator = Paginator(sessions, 25)
    page = request.GET.get('page')
    try:
        sessions_page = paginator.page(page)
    except PageNotAnInteger:
        sessions_page = paginator.page(1)
    except EmptyPage:
        sessions_page = paginator.page(paginator.num_pages)

    return render(request, 'hr/training_session_list.html', {
        'sessions': sessions_page,
        'status_filter': status_filter,
        'query': query,
        'status_choices': TrainingSession.STATUS_CHOICES,
        'title': 'Training Sessions',
    })


@role_required(*HR_ROLES)
def training_session_create(request):
    company = request.user.company
    if request.method == 'POST':
        form = TrainingSessionForm(request.POST, company=company)
        if form.is_valid():
            session = form.save()
            messages.success(request, 'Training session created successfully.')
            return redirect('hr:training_session_list')
    else:
        form = TrainingSessionForm(company=company)

    return render(request, 'hr/training_session_form.html', {
        'form': form,
        'title': 'New Training Session',
    })


@role_required(*HR_ROLES)
def training_session_edit(request, pk):
    company = request.user.company
    session = get_object_or_404(TrainingSession, pk=pk, course__company=company)
    if request.method == 'POST':
        form = TrainingSessionForm(request.POST, instance=session, company=company)
        if form.is_valid():
            form.save()
            messages.success(request, 'Training session updated successfully.')
            return redirect('hr:training_session_list')
    else:
        form = TrainingSessionForm(instance=session, company=company)

    return render(request, 'hr/training_session_form.html', {
        'form': form,
        'session': session,
        'title': 'Edit Training Session',
    })


@role_required(*HR_ROLES)
def training_session_delete(request, pk):
    company = request.user.company
    session = get_object_or_404(TrainingSession, pk=pk, course__company=company)
    if request.method == 'POST':
        session.delete()
        messages.success(request, 'Training session deleted successfully.')
        return redirect('hr:training_session_list')

    return render(request, 'hr/confirm_delete.html', {
        'object_type': 'training session',
        'object_name': session,
        'cancel_url': reverse('hr:training_session_list'),
    })


@role_required(*HR_ROLES)
def training_session_enroll(request, pk):
    company = request.user.company
    session = get_object_or_404(TrainingSession, pk=pk, course__company=company)

    if request.method == 'POST':
        form = EmployeeTrainingForm(request.POST, company=company)
        if form.is_valid():
            enrollment = form.save(commit=False)
            enrollment.session = session
            try:
                enrollment.full_clean()
                enrollment.save()
                messages.success(request, f'{enrollment.employee.full_name} enrolled successfully.')
                return redirect('hr:training_session_list')
            except Exception as e:
                messages.error(request, str(e))
    else:
        form = EmployeeTrainingForm(company=company)

    return render(request, 'hr/training_session_enroll.html', {
        'form': form,
        'session': session,
        'title': f'Enroll in {session.course.title}',
    })


@role_required(*HR_ROLES)
def employee_training_list(request):
    company = request.user.company
    trainings = EmployeeTraining.objects.filter(
        session__course__company=company
    ).select_related('employee__user', 'session__course').order_by('-enrollment_date')

    status_filter = request.GET.get('status', '').strip()
    if status_filter:
        trainings = trainings.filter(status=status_filter)

    query = request.GET.get('q', '').strip()
    if query:
        trainings = trainings.filter(
            Q(employee__user__first_name__icontains=query) |
            Q(employee__user__last_name__icontains=query) |
            Q(session__course__title__icontains=query)
        )

    paginator = Paginator(trainings, 25)
    page = request.GET.get('page')
    try:
        trainings_page = paginator.page(page)
    except PageNotAnInteger:
        trainings_page = paginator.page(1)
    except EmptyPage:
        trainings_page = paginator.page(paginator.num_pages)

    return render(request, 'hr/employee_training_list.html', {
        'trainings': trainings_page,
        'status_filter': status_filter,
        'query': query,
        'status_choices': EmployeeTraining.STATUS_CHOICES,
        'title': 'Training Enrollments',
    })


@role_required(*HR_ROLES)
def employee_training_enroll(request):
    company = request.user.company
    if request.method == 'POST':
        form = EmployeeTrainingForm(request.POST, company=company)
        if form.is_valid():
            training = form.save(commit=False)
            try:
                training.full_clean()
                training.save()
                messages.success(request, 'Employee enrolled in training.')
                return redirect('hr:employee_training_list')
            except Exception as exc:
                form.add_error(None, str(exc))
    else:
        form = EmployeeTrainingForm(company=company)
    return render(request, 'hr/employee_training_form.html', {
        'form': form,
        'title': 'Enroll Employee in Training',
    })


@role_required(*HR_ROLES)
def employee_training_edit(request, pk):
    company = request.user.company
    training = get_object_or_404(EmployeeTraining, pk=pk, session__course__company=company)
    if request.method == 'POST':
        form = EmployeeTrainingForm(request.POST, instance=training, company=company)
        if form.is_valid():
            form.save()
            messages.success(request, 'Training enrollment updated.')
            return redirect('hr:employee_training_list')
    else:
        form = EmployeeTrainingForm(instance=training, company=company)
    return render(request, 'hr/employee_training_form.html', {
        'form': form,
        'training': training,
        'title': 'Edit Training Enrollment',
    })


@role_required(*HR_ROLES)
@require_POST
def employee_training_delete(request, pk):
    company = request.user.company
    training = get_object_or_404(EmployeeTraining, pk=pk, session__course__company=company)
    training.delete()
    messages.success(request, 'Training enrollment deleted.')
    return redirect('hr:employee_training_list')


@role_required(*HR_ROLES)
@require_POST
def employee_training_complete(request, pk):
    company = request.user.company
    training = get_object_or_404(
        EmployeeTraining.objects.select_related('employee__user', 'session__course'),
        pk=pk,
        session__course__company=company
    )

    if request.method == 'POST':
        form = TrainingCompletionForm(request.POST, instance=training)
        if form.is_valid():
            form.save()
            training.mark_completed()
            messages.success(request, f'Training completion recorded for {training.employee.full_name}.')
            return redirect('hr:employee_training_list')
    else:
        form = TrainingCompletionForm(instance=training)

    return render(request, 'hr/training_completion_form.html', {
        'form': form,
        'training': training,
        'title': f'Complete Training: {training.employee.full_name}',
    })


@role_required(*HR_ROLES)
@require_POST
def employee_training_cancel(request, pk):
    company = request.user.company
    training = get_object_or_404(
        EmployeeTraining,
        pk=pk,
        session__course__company=company
    )

    training.status = 'cancelled'
    training.save(update_fields=['status'])
    messages.success(request, f'Training cancelled for {training.employee.full_name}.')
    return redirect('hr:employee_training_list')


@role_required(*HR_ROLES)
def skill_list(request):
    company = request.user.company
    skills = Skill.objects.filter(company=company).order_by('category', 'name')

    query = request.GET.get('q', '').strip()
    if query:
        skills = skills.filter(
            Q(name__icontains=query) |
            Q(description__icontains=query) |
            Q(category__icontains=query)
        )

    category = request.GET.get('category', '').strip()
    if category:
        skills = skills.filter(category=category)

    paginator = Paginator(skills, 25)
    page = request.GET.get('page')
    try:
        skills_page = paginator.page(page)
    except PageNotAnInteger:
        skills_page = paginator.page(1)
    except EmptyPage:
        skills_page = paginator.num_pages

    return render(request, 'hr/skill_list.html', {
        'skills': skills_page,
        'query': query,
        'category': category,
        'categories': Skill.objects.filter(company=company).values_list('category', flat=True).distinct(),
        'title': 'Skills',
    })


@role_required(*HR_ROLES)
def skill_create(request):
    company = request.user.company
    if request.method == 'POST':
        form = SkillForm(request.POST)
        if form.is_valid():
            skill = form.save(commit=False)
            skill.company = company
            skill.save()
            messages.success(request, 'Skill created successfully.')
            return redirect('hr:skill_list')
    else:
        form = SkillForm()

    return render(request, 'hr/skill_form.html', {
        'form': form,
        'title': 'New Skill',
    })


@role_required(*HR_ROLES)
def skill_edit(request, pk):
    company = request.user.company
    skill = get_object_or_404(Skill, pk=pk, company=company)
    if request.method == 'POST':
        form = SkillForm(request.POST, instance=skill)
        if form.is_valid():
            form.save()
            messages.success(request, 'Skill updated successfully.')
            return redirect('hr:skill_list')
    else:
        form = SkillForm(instance=skill)

    return render(request, 'hr/skill_form.html', {
        'form': form,
        'skill': skill,
        'title': 'Edit Skill',
    })


@role_required(*HR_ROLES)
def skill_delete(request, pk):
    company = request.user.company
    skill = get_object_or_404(Skill, pk=pk, company=company)
    if request.method == 'POST':
        skill.delete()
        messages.success(request, 'Skill deleted successfully.')
        return redirect('hr:skill_list')

    return render(request, 'hr/confirm_delete.html', {
        'object_type': 'skill',
        'object_name': skill.name,
        'cancel_url': reverse('hr:skill_list'),
    })


@role_required(*HR_ROLES)
def employee_skill_list(request):
    company = request.user.company
    employee_skills = EmployeeSkill.objects.filter(
        skill__company=company
    ).select_related('employee__user', 'skill', 'assessed_by').order_by('-assessment_date')

    query = request.GET.get('q', '').strip()
    if query:
        employee_skills = employee_skills.filter(
            Q(employee__user__first_name__icontains=query) |
            Q(employee__user__last_name__icontains=query) |
            Q(skill__name__icontains=query)
        )

    proficiency = request.GET.get('proficiency', '').strip()
    if proficiency:
        employee_skills = employee_skills.filter(proficiency_level=proficiency)

    paginator = Paginator(employee_skills, 25)
    page = request.GET.get('page')
    try:
        skills_page = paginator.page(page)
    except PageNotAnInteger:
        skills_page = paginator.page(1)
    except EmptyPage:
        skills_page = paginator.page(paginator.num_pages)

    return render(request, 'hr/employee_skill_list.html', {
        'employee_skills': skills_page,
        'query': query,
        'proficiency': proficiency,
        'proficiency_levels': Skill.PROFICIENCY_LEVELS,
        'title': 'Employee Skills',
    })


@role_required(*HR_ROLES)
def employee_skill_create(request):
    company = request.user.company
    if request.method == 'POST':
        form = EmployeeSkillForm(request.POST, company=company)
        if form.is_valid():
            skill_assessment = form.save(commit=False)
            skill_assessment.assessed_by = request.user
            skill_assessment.save()
            messages.success(request, 'Employee skill assessment created successfully.')
            return redirect('hr:employee_skill_list')
    else:
        form = EmployeeSkillForm(company=company)

    return render(request, 'hr/employee_skill_form.html', {
        'form': form,
        'title': 'New Skill Assessment',
    })


@role_required(*HR_ROLES)
def employee_skill_edit(request, pk):
    company = request.user.company
    employee_skill = get_object_or_404(EmployeeSkill, pk=pk, skill__company=company)
    if request.method == 'POST':
        form = EmployeeSkillForm(request.POST, instance=employee_skill, company=company)
        if form.is_valid():
            skill_assessment = form.save(commit=False)
            skill_assessment.assessed_by = request.user
            skill_assessment.save()
            messages.success(request, 'Employee skill assessment updated successfully.')
            return redirect('hr:employee_skill_list')
    else:
        form = EmployeeSkillForm(instance=employee_skill, company=company)

    return render(request, 'hr/employee_skill_form.html', {
        'form': form,
        'employee_skill': employee_skill,
        'title': 'Edit Skill Assessment',
    })


@role_required(*HR_ROLES)
def employee_skill_delete(request, pk):
    company = request.user.company
    employee_skill = get_object_or_404(EmployeeSkill, pk=pk, skill__company=company)
    if request.method == 'POST':
        employee_skill.delete()
        messages.success(request, 'Employee skill assessment deleted successfully.')
        return redirect('hr:employee_skill_list')

    return render(request, 'hr/confirm_delete.html', {
        'object_type': 'employee skill assessment',
        'object_name': employee_skill,
        'cancel_url': reverse('hr:employee_skill_list'),
    })