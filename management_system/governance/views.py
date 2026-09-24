import csv
from datetime import timedelta

from django.contrib import messages
from django.contrib.auth import get_user_model
from django.contrib.auth.decorators import login_required
from django.db.models import F, Sum
from django.http import HttpResponse, HttpResponseForbidden
from django.shortcuts import get_object_or_404, redirect, render
from django.utils import timezone
from django.views.decorators.http import require_http_methods, require_POST

from .decorators import capability_required
from .access_catalog import MODULE_ACCESS_CATALOG
from .forms import ApprovalAuthorityForm, CapabilityOverrideForm, CreateManagedUserForm, ManagedUserForm
from .models import ApprovalStep, ApprovalWorkflow, ApprovalRequest
from .services import actionable_approvals_for_user, _target_amount, decide_approval, maybe_submit_user_account_approval
from .workflow_forms import ApprovalStepForm, ApprovalWorkflowForm
from .models import AuditEvent, UserApprovalAuthority, UserCapability, effective_capabilities
from employees.models import Employee
from finance.models import Transaction
from inventory.models import Stock
from projects.models import Project
from crm.models import Contact, Opportunity


User = get_user_model()


@capability_required('admin.manage_users')
def user_list(request):
    users = User.objects.filter(company=request.user.company).order_by('email')
    return render(request, 'governance/user_list.html', {'users': users})


@capability_required('admin.manage_users')
@require_http_methods(['GET', 'POST'])
def user_create(request):
    form = CreateManagedUserForm(request.POST or None, company=request.user.company)
    if request.method == 'POST' and form.is_valid():
        user = form.save(request.user.company)
        employee = form.cleaned_data.get('employee')
        if employee:
            employee.link_user(user)
        approval = maybe_submit_user_account_approval(user=user, requester=request.user, request=request)
        if approval is not None:
            user.refresh_from_db()
            messages.success(request, 'User created and submitted for manager/HR approval.')
        else:
            messages.success(request, 'User created.')
        AuditEvent.record(actor=request.user, company=request.user.company, module='accounts', action='user_created', obj=user, after={'role': user.role, 'is_active': user.is_active, 'employee_id': employee.pk if employee else None, 'approval_id': getattr(approval, 'pk', None)}, request=request)
        if employee:
            AuditEvent.record(actor=request.user, company=request.user.company, module='accounts', action='employee_user_linked', obj=user, after={'employee_id': employee.pk}, request=request)
        return redirect('governance:user_list')
    return render(request, 'governance/user_form.html', {'form': form, 'managed_user': None})


@capability_required('admin.manage_users')
@require_http_methods(['GET', 'POST'])
def user_edit(request, pk):
    user = get_object_or_404(User, pk=pk, company=request.user.company)
    before = {'role': user.role, 'is_active': user.is_active, 'is_company_admin': user.is_company_admin}
    if request.method == 'POST':
        form = ManagedUserForm(request.POST, instance=user)
        if form.is_valid():
            user = form.save()
            AuditEvent.record(
                actor=request.user, company=request.user.company, module='accounts', action='user_updated',
                obj=user, before=before,
                after={'role': user.role, 'is_active': user.is_active, 'is_company_admin': user.is_company_admin},
                request=request,
            )
            messages.success(request, 'User updated.')
            return redirect('governance:user_list')
    else:
        form = ManagedUserForm(instance=user)
    return render(request, 'governance/user_form.html', {'form': form, 'managed_user': user})


@capability_required('admin.manage_users')
@require_POST
def user_toggle_active(request, pk):
    user = get_object_or_404(User, pk=pk, company=request.user.company)
    if user.pk == request.user.pk:
        messages.error(request, 'You cannot deactivate your own account.')
        return redirect('governance:user_list')
    before = {'is_active': user.is_active}
    user.is_active = not user.is_active
    user.save(update_fields=['is_active'])
    AuditEvent.record(actor=request.user, company=request.user.company, module='accounts', action='user_status_changed', obj=user, before=before, after={'is_active': user.is_active}, request=request)
    messages.success(request, 'User status updated.')
    return redirect('governance:user_list')


@capability_required('admin.manage_roles')
@require_http_methods(['GET', 'POST'])
def user_capabilities(request, pk):
    user = get_object_or_404(User, pk=pk, company=request.user.company)
    if request.method == 'POST':
        if request.POST.get('action') == 'save_authority':
            authority_form = ApprovalAuthorityForm(request.POST, company=request.user.company, user=user)
            form = CapabilityOverrideForm(company=request.user.company, user=user)
            if authority_form.is_valid():
                authority = authority_form.save(granted_by=request.user)
                AuditEvent.record(
                    actor=request.user, company=request.user.company, module='access',
                    action='approval_authority_changed', obj=authority,
                    after={'user_id': user.pk, 'transaction_type': authority.transaction_type, 'max_amount': str(authority.max_amount)},
                    request=request,
                )
                messages.success(request, 'Approval authority saved.')
                return redirect('governance:user_capabilities', pk=user.pk)
        else:
            before = {
                'access_controlled': user.access_controlled,
                'capabilities': sorted(effective_capabilities(user)),
            }
            form = CapabilityOverrideForm(request.POST, company=request.user.company, user=user)
            authority_form = ApprovalAuthorityForm(company=request.user.company, user=user)
            if form.is_valid():
                selected = form.save(granted_by=request.user)
                if user.pk == request.user.pk and user.access_controlled and not {
                    'admin.manage_users', 'admin.manage_roles'
                }.issubset(selected):
                    user.access_controlled = False
                    user.save(update_fields=['access_controlled'])
                    messages.error(request, 'Your own administrator access cannot be removed from this page.')
                    return redirect('governance:user_capabilities', pk=user.pk)
                AuditEvent.record(
                    actor=request.user, company=request.user.company, module='access',
                    action='capability_assignments_changed', obj=user,
                    before=before,
                    after={'access_controlled': user.access_controlled, 'capabilities': sorted(selected)},
                    request=request,
                )
                messages.success(request, 'Explicit access assignments saved.')
                return redirect('governance:user_capabilities', pk=user.pk)
    else:
        form = CapabilityOverrideForm(company=request.user.company, user=user)
        authority_form = ApprovalAuthorityForm(company=request.user.company, user=user)
    return render(request, 'governance/user_capabilities.html', {
        'managed_user': user,
        'form': form,
        'overrides': UserCapability.objects.filter(user=user, company=request.user.company),
        'effective_capabilities': sorted(effective_capabilities(user)),
        'assigned_capabilities': set(
            UserCapability.objects.filter(
                user=user,
                company=request.user.company,
                enabled=True,
            ).values_list('capability', flat=True)
        ),
        'authority_form': authority_form,
        'authorities': UserApprovalAuthority.objects.filter(user=user, company=request.user.company).order_by('transaction_type', 'module'),
        'module_access_catalog': MODULE_ACCESS_CATALOG,
    })


@capability_required('admin.manage_roles')
@require_POST
def user_approval_authority_delete(request, pk):
    authority = get_object_or_404(UserApprovalAuthority, pk=pk, company=request.user.company)
    before = {'transaction_type': authority.transaction_type, 'module': authority.module, 'enabled': authority.enabled}
    authority.delete()
    AuditEvent.record(
        actor=request.user, company=request.user.company, module='access',
        action='approval_authority_removed', object_id=str(pk), before=before,
        after={'user_id': authority.user_id}, request=request,
    )
    messages.success(request, 'Approval authority removed.')
    return redirect('governance:user_capabilities', pk=authority.user_id)


@capability_required('reporting.view')
def audit_list(request):
    events = AuditEvent.objects.filter(company=request.user.company).select_related('actor')
    return render(request, 'governance/audit_list.html', {'events': events[:200]})


def _reporting_context(request):
    company = request.user.company
    today = timezone.localdate()
    range_days = request.GET.get('days', '30')
    if range_days not in {'30', '90', '365'}:
        range_days = '30'
    since = today - timedelta(days=int(range_days))
    module_filter = request.GET.get('module', '').strip()

    employees = Employee.objects.filter(company=company)
    projects = Project.objects.filter(company=company)
    opportunities = Opportunity.objects.filter(company=company)
    audit_events = AuditEvent.objects.filter(company=company, created_at__date__gte=since)
    if module_filter:
        audit_events = audit_events.filter(module=module_filter)

    revenue = Transaction.objects.filter(
        company=company,
        account__account_type='revenue',
        transaction_type='credit',
        date__gte=since,
        date__lte=today,
    ).aggregate(total=Sum('amount'))['total'] or 0

    return {
        'company': company,
        'report_date': today,
        'since': since,
        'range_days': range_days,
        'module_filter': module_filter,
        'module_choices': AuditEvent.objects.filter(company=company).values_list('module', flat=True).distinct().order_by('module'),
        'employees_total': employees.count(),
        'employees_active': employees.filter(status='active').count(),
        'projects_total': projects.count(),
        'projects_active': projects.filter(status='in_progress').count(),
        'projects_overdue': projects.filter(end_date__lt=today, status__in=['planning', 'in_progress']).count(),
        'low_stock_items': Stock.objects.filter(company=company, quantity__lte=F('reorder_level')).count(),
        'contacts_total': Contact.objects.filter(company=company).count(),
        'open_opportunities': opportunities.exclude(stage__in=['won', 'lost']).count(),
        'open_pipeline_value': opportunities.exclude(stage__in=['won', 'lost']).aggregate(total=Sum('value'))['total'] or 0,
        'revenue_total': revenue,
        'pending_approvals': ApprovalRequest.objects.filter(company=company, status='pending').count(),
        'audit_events': audit_events.select_related('actor').order_by('-created_at')[:100],
    }


@capability_required('reporting.view')
def reporting_dashboard(request):
    context = _reporting_context(request)
    return render(request, 'governance/reporting_dashboard.html', context)


@capability_required('reporting.export')
def reporting_export(request):
    context = _reporting_context(request)
    response = HttpResponse(content_type='text/csv')
    period_suffix = f"{context['since']} to {context['report_date']}"
    module_label = context['module_filter'] or 'all_modules'
    company_slug = ''.join(ch if ch.isalnum() else '_' for ch in context['company'].name.lower())
    filename = f"erp_reporting_{company_slug}_{module_label}_{context['range_days']}.csv"
    response['Content-Disposition'] = f'attachment; filename="{filename}"'
    writer = csv.writer(response)
    writer.writerow(['Company', 'Module filter', 'Period', 'Metric', 'Value'])
    writer.writerow([context['company'].name, module_label, period_suffix, 'Scope', 'Company-scoped'])
    for label, value in (
        ('Employees', context['employees_total']),
        ('Active employees', context['employees_active']),
        ('Projects', context['projects_total']),
        ('Active projects', context['projects_active']),
        ('Overdue projects', context['projects_overdue']),
        ('Low-stock items', context['low_stock_items']),
        ('Contacts', context['contacts_total']),
        ('Open opportunities', context['open_opportunities']),
        ('Open pipeline value', context['open_pipeline_value']),
        ('Revenue credited', context['revenue_total']),
        ('Pending approvals', context['pending_approvals']),
        ('Audit events', len(context['audit_events'])),
    ):
        writer.writerow([context['company'].name, module_label, period_suffix, label, value])
    return response


@capability_required('admin.manage_organisation')
def admin_dashboard(request):
    company = request.user.company
    user_count = User.objects.filter(company=company).count()
    active_user_count = User.objects.filter(company=company, is_active=True).count()
    workflow_count = ApprovalWorkflow.objects.filter(company=company).count()
    pending_approval_count = ApprovalRequest.objects.filter(company=company, status='pending').count()
    recent_users = User.objects.filter(company=company).order_by('-last_login', '-date_joined')[:5]
    recent_events = AuditEvent.objects.filter(company=company).select_related('actor').order_by('-created_at')[:8]

    return render(request, 'governance/admin_dashboard.html', {
        'company': company,
        'user_count': user_count,
        'active_user_count': active_user_count,
        'workflow_count': workflow_count,
        'pending_approval_count': pending_approval_count,
        'recent_users': recent_users,
        'recent_events': recent_events,
    })


@capability_required('admin.manage_organisation')
def workflow_list(request):
    workflows = ApprovalWorkflow.objects.filter(company=request.user.company).prefetch_related('steps')
    return render(request, 'governance/workflow_list.html', {'workflows': workflows})


@capability_required('admin.manage_organisation')
@require_http_methods(['GET', 'POST'])
def workflow_create(request):
    form = ApprovalWorkflowForm(request.POST or None)
    if request.method == 'POST' and form.is_valid():
        workflow = form.save(commit=False)
        workflow.company = request.user.company
        workflow.save()
        AuditEvent.record(actor=request.user, company=request.user.company, module='approvals', action='workflow_created', obj=workflow, request=request)
        return redirect('governance:workflow_detail', pk=workflow.pk)
    return render(request, 'governance/workflow_form.html', {'form': form, 'title': 'New approval workflow'})


@capability_required('admin.manage_organisation')
@require_http_methods(['GET', 'POST'])
def workflow_edit(request, pk):
    workflow = get_object_or_404(ApprovalWorkflow, pk=pk, company=request.user.company)
    has_pending = workflow.requests.filter(status='pending').exists()
    if request.method == 'POST':
        form = ApprovalWorkflowForm(request.POST, instance=workflow)
        if form.is_valid():
            if has_pending and any(
                form.cleaned_data[field] != getattr(workflow, field)
                for field in ('transaction_type', 'applies_from', 'applies_to', 'allow_self_approval')
            ):
                form.add_error(None, 'Transaction scope cannot change while requests are pending.')
            else:
                form.save()
                AuditEvent.record(actor=request.user, company=request.user.company, module='approvals', action='workflow_updated', obj=workflow, request=request)
                messages.success(request, 'Approval workflow updated.')
                return redirect('governance:workflow_detail', pk=workflow.pk)
    else:
        form = ApprovalWorkflowForm(instance=workflow)
    return render(request, 'governance/workflow_form.html', {'form': form, 'title': 'Edit approval workflow', 'workflow': workflow})


@capability_required('admin.manage_organisation')
@require_http_methods(['GET', 'POST'])
def workflow_detail(request, pk):
    workflow = get_object_or_404(ApprovalWorkflow, pk=pk, company=request.user.company)
    form = ApprovalStepForm(request.POST or None)
    if request.method == 'POST' and form.is_valid():
        if workflow.requests.filter(status='pending').exists():
            form.add_error(None, 'Workflow steps cannot change while requests are pending.')
        else:
            step = form.save(commit=False)
            step.workflow = workflow
            step.save()
            AuditEvent.record(actor=request.user, company=request.user.company, module='approvals', action='workflow_step_created', obj=step, request=request)
            return redirect('governance:workflow_detail', pk=workflow.pk)
    return render(request, 'governance/workflow_detail.html', {'workflow': workflow, 'steps': workflow.steps.all(), 'form': form})


@capability_required('admin.manage_organisation')
@require_http_methods(['GET', 'POST'])
def workflow_step_edit(request, pk):
    step = get_object_or_404(ApprovalStep, pk=pk, workflow__company=request.user.company)
    if step.workflow.requests.filter(status='pending').exists():
        messages.error(request, 'Workflow steps cannot be changed while requests are pending.')
        return redirect('governance:workflow_detail', pk=step.workflow_id)
    form = ApprovalStepForm(request.POST or None, instance=step)
    if request.method == 'POST' and form.is_valid():
        form.save()
        AuditEvent.record(actor=request.user, company=request.user.company, module='approvals', action='workflow_step_updated', obj=step, request=request)
        messages.success(request, 'Approval step updated.')
        return redirect('governance:workflow_detail', pk=step.workflow_id)
    return render(request, 'governance/workflow_form.html', {'form': form, 'title': 'Edit approval step', 'workflow': step.workflow})


@capability_required('admin.manage_organisation')
@require_POST
def workflow_step_delete(request, pk):
    step = get_object_or_404(ApprovalStep, pk=pk, workflow__company=request.user.company)
    workflow_id = step.workflow_id
    if step.workflow.requests.filter(status='pending').exists():
        messages.error(request, 'Workflow steps cannot be deleted while requests are pending.')
    else:
        step.delete()
        AuditEvent.record(actor=request.user, company=request.user.company, module='approvals', action='workflow_step_deleted', object_id=str(pk), request=request)
        messages.success(request, 'Approval step deleted.')
    return redirect('governance:workflow_detail', pk=workflow_id)


@capability_required('approvals.decide')
@require_POST
def approval_decide(request, pk):
    approval = get_object_or_404(ApprovalRequest, pk=pk, company=request.user.company)
    decision = request.POST.get('decision')
    if decision not in {'approved', 'rejected', 'returned'}:
        messages.error(request, 'Invalid approval decision.')
        return redirect('governance:my_work')
    try:
        decide_approval(approval=approval, actor=request.user, decision=decision, reason=request.POST.get('reason', ''), request=request)
        messages.success(request, 'Approval decision saved.')
    except Exception as exc:
        messages.error(request, str(exc))
    return redirect('governance:my_work')


@login_required
@require_POST
def approval_cancel(request, pk):
    approval = get_object_or_404(
        ApprovalRequest,
        pk=pk,
        company=request.user.company,
        requester=request.user,
        status='pending',
    )
    approval.status = 'cancelled'
    approval.completed_at = timezone.now()
    approval.save(update_fields=['status', 'completed_at', 'updated_at'])
    AuditEvent.record(
        actor=request.user,
        company=request.user.company,
        module='approvals',
        action='cancelled',
        obj=approval.target,
        after={'approval_id': approval.pk, 'status': approval.status},
        reason='Approval cancelled by requester.',
        request=request,
    )
    messages.success(request, 'Approval request cancelled.')
    return redirect('governance:my_work')


@login_required
def approval_detail(request, pk):
    approval = get_object_or_404(
        ApprovalRequest.objects.select_related('requester', 'workflow'),
        pk=pk,
        company=request.user.company,
    )
    actionable = approval in actionable_approvals_for_user(request.user)
    if not actionable and approval.requester_id != request.user.pk and request.user.role != 'admin' and not request.user.is_superuser:
        return HttpResponseForbidden('You are not authorised to view this approval.')
    return render(request, 'governance/approval_detail.html', {
        'approval': approval,
        'target': approval.target,
        'actionable': actionable,
    })


@login_required
def my_work(request):
    actionable = actionable_approvals_for_user(request.user)
    return render(request, 'governance/my_work.html', {'approvals': actionable, 'notifications': request.user.notifications.filter(is_read=False, is_archived=False)[:10]})
