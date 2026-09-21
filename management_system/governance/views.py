from django.contrib import messages
from django.contrib.auth import get_user_model
from django.contrib.auth.decorators import login_required
from django.http import HttpResponseForbidden
from django.shortcuts import get_object_or_404, redirect, render
from django.views.decorators.http import require_http_methods, require_POST

from .decorators import capability_required
from .access_catalog import MODULE_ACCESS_CATALOG
from .forms import ApprovalAuthorityForm, CapabilityOverrideForm, CreateManagedUserForm, ManagedUserForm
from .models import ApprovalStep, ApprovalWorkflow, ApprovalRequest
from .services import actionable_approvals_for_user, _target_amount, decide_approval, maybe_submit_user_account_approval
from .workflow_forms import ApprovalStepForm, ApprovalWorkflowForm
from .models import AuditEvent, UserApprovalAuthority, UserCapability, effective_capabilities


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
def workflow_detail(request, pk):
    workflow = get_object_or_404(ApprovalWorkflow, pk=pk, company=request.user.company)
    form = ApprovalStepForm(request.POST or None)
    if request.method == 'POST' and form.is_valid():
        step = form.save(commit=False)
        step.workflow = workflow
        step.save()
        AuditEvent.record(actor=request.user, company=request.user.company, module='approvals', action='workflow_step_created', obj=step, request=request)
        return redirect('governance:workflow_detail', pk=workflow.pk)
    return render(request, 'governance/workflow_detail.html', {'workflow': workflow, 'steps': workflow.steps.all(), 'form': form})


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
