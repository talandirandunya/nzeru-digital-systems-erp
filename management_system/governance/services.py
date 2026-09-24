from datetime import timedelta
from decimal import Decimal
from types import SimpleNamespace

from django.contrib.contenttypes.models import ContentType
from django.core.exceptions import ValidationError
from django.db import transaction
from django.utils import timezone

from notifications.models import Notification
from notifications.utils import create_notification

from .models import ApprovalDecision, ApprovalDelegation, ApprovalRequest, ApprovalWorkflow, AuditEvent, UserApprovalAuthority, has_capability


def _target_amount(target):
    for field in ('total', 'amount', 'value', 'budget'):
        value = getattr(target, field, None)
        if value is not None:
            return Decimal(str(value))
    return None


def _target_company_id(target):
    if getattr(getattr(target, '_meta', None), 'label_lower', None) == 'accounts.company':
        return target.pk
    company_id = getattr(target, 'company_id', None)
    if company_id is not None:
        return company_id
    company = getattr(target, 'company', None)
    return getattr(company, 'pk', None)


def _step_matches(step, user, amount, department='', branch=''):
    if step.role and user.role != step.role:
        return False
    if step.department and (user.department != step.department or step.department != department):
        return False
    if step.branch and step.branch != branch:
        return False
    if step.capability and not has_capability(user, step.capability):
        return False
    if amount is not None:
        if step.min_amount is not None and amount < step.min_amount:
            return False
        if step.max_amount is not None and amount > step.max_amount:
            return False
        if step.approval_limit is not None and amount > step.approval_limit:
            return False
    return True


def _user_has_explicit_authority(user, transaction_type, step, amount, target=None):
    if not user.is_authenticated or not user.is_active or user.company_id is None:
        return False
    required_capability = step.capability or 'approvals.decide'
    if not has_capability(user, required_capability):
        return False
    department = getattr(getattr(target, 'department', None), 'name', '') or getattr(target, 'department', '') or ''
    branch = getattr(getattr(target, 'branch', None), 'name', '') or getattr(target, 'branch', '') or ''

    authorities = UserApprovalAuthority.objects.filter(
        company=user.company,
        user=user,
        transaction_type=transaction_type,
        enabled=True,
    )
    has_matching_authority = any(
        authority.matches(user, amount, department=department, branch=branch)
        and authority.capability == required_capability
        and (not step.department or authority.department in {'', step.department})
        and (not step.branch or authority.branch in {'', step.branch})
        for authority in authorities
    )
    if has_matching_authority:
        return True

    # Default role capabilities are valid only when there are no approval
    # authority or delegation records for this transaction type. If a user has a
    # related approval record, it means the workflow explicitly constrains access.
    related_authorities = UserApprovalAuthority.objects.filter(
        company=user.company,
        user=user,
        transaction_type=transaction_type,
    )
    related_delegations = ApprovalDelegation.objects.filter(
        company=user.company,
        delegate=user,
        transaction_type=transaction_type,
    )
    if not related_authorities.exists() and not related_delegations.exists():
        return True

    now = timezone.now()
    delegations = ApprovalDelegation.objects.filter(
        company=user.company,
        delegate=user,
        transaction_type=transaction_type,
        capability=required_capability,
        enabled=True,
        starts_at__lte=now,
        ends_at__gt=now,
    )
    for delegation in delegations:
        if delegation.department and delegation.department != department:
            continue
        if delegation.branch and delegation.branch != branch:
            continue
        if step.department and delegation.department not in {'', step.department}:
            continue
        if step.branch and delegation.branch not in {'', step.branch}:
            continue
        delegator_authority = UserApprovalAuthority.objects.filter(
            company=user.company,
            user=delegation.delegator,
            transaction_type=transaction_type,
            capability=required_capability,
            enabled=True,
        )
        if any(
            authority.matches(delegation.delegator, amount, department=department, branch=branch)
            and (not step.department or authority.department in {'', step.department})
            and (not step.branch or authority.branch in {'', step.branch})
            for authority in delegator_authority
        ):
            return True
    return False


def _eligible_users(company, step, amount, transaction_type, target=None):
    users = company.users.filter(is_active=True).exclude(is_superuser=False, company__isnull=True)
    return [
        user for user in users
        if _step_matches(
            step,
            user,
            amount,
            department=getattr(getattr(target, 'department', None), 'name', '') or getattr(target, 'department', '') or '',
            branch=getattr(getattr(target, 'branch', None), 'name', '') or getattr(target, 'branch', '') or '',
        )
        and _user_has_explicit_authority(user, transaction_type, step, amount, target)
    ]


def _snapshot_for_workflow(workflow):
    return {
        'transaction_type': workflow.transaction_type,
        'reminder_after_hours': workflow.reminder_after_hours,
        'escalation_after_hours': workflow.escalation_after_hours,
        'allow_self_approval': workflow.allow_self_approval,
        'steps': [
            {
                'sequence': step.sequence,
                'role': step.role,
                'capability': step.capability,
                'department': step.department,
                'branch': step.branch,
                'min_amount': str(step.min_amount) if step.min_amount is not None else None,
                'max_amount': str(step.max_amount) if step.max_amount is not None else None,
                'approval_limit': str(step.approval_limit) if step.approval_limit is not None else None,
                'required': step.required,
            }
            for step in workflow.steps.order_by('sequence')
        ],
    }


def _request_steps(approval):
    snapshot = approval.workflow_snapshot or {}
    steps = snapshot.get('steps') or _snapshot_for_workflow(approval.workflow)['steps']
    return [SimpleNamespace(
        sequence=item['sequence'],
        role=item.get('role', ''),
        capability=item.get('capability', ''),
        department=item.get('department', ''),
        branch=item.get('branch', ''),
        min_amount=Decimal(item['min_amount']) if item.get('min_amount') is not None else None,
        max_amount=Decimal(item['max_amount']) if item.get('max_amount') is not None else None,
        approval_limit=Decimal(item['approval_limit']) if item.get('approval_limit') is not None else None,
        required=item.get('required', True),
    ) for item in steps]


def maybe_submit_user_account_approval(*, user, requester, request=None):
    """Use the governance approval workflow when the company mandates approval for account activation."""
    if user.company_id is None:
        return None
    workflow = ApprovalWorkflow.objects.filter(
        company=user.company,
        transaction_type='user_account_creation',
        enabled=True,
    ).first()
    if workflow is None:
        return None
    if user.is_active:
        user.is_active = False
        user.save(update_fields=['is_active'])
    return submit_for_approval(
        target=user,
        requester=requester,
        transaction_type='user_account_creation',
        reason='User account created pending manager/HR approval.',
        request=request,
    )


def _move_to_next_actionable_step(approval, target, start_sequence):
    amount = _target_amount(target)
    steps = [step for step in _request_steps(approval) if step.sequence >= start_sequence]
    for step in steps:
        eligible = _eligible_users(approval.company, step, amount, approval.workflow.transaction_type, target)
        if eligible:
            approval.current_step = step.sequence
            return step, eligible
        if step.required:
            # Keep the request pending at this step so administrators can fix
            # routing without losing the business transaction.
            approval.current_step = step.sequence
            return step, []
    approval.status = 'approved'
    approval.completed_at = timezone.now()
    return None, []


@transaction.atomic
def submit_for_approval(*, target, requester, transaction_type, reason='', request=None):
    if not requester.is_authenticated or requester.company_id is None:
        raise ValidationError('The requester must belong to a company.')
    target_company_id = _target_company_id(target)
    if target_company_id is None:
        raise ValidationError('Approval targets must belong to a company.')
    if target_company_id != requester.company_id:
        raise ValidationError('Approval target belongs to another company.')
    if not getattr(target, 'pk', None):
        raise ValidationError('Approval targets must be saved before submission.')
    company = requester.company
    amount = _target_amount(target)
    workflow = next((item for item in ApprovalWorkflow.objects.filter(company=company, transaction_type=transaction_type, enabled=True).prefetch_related('steps') if item.matches(amount)), None)
    if workflow is None:
        raise ValidationError(f'No approval workflow is configured for {transaction_type}.')
    existing_pending = ApprovalRequest.objects.filter(
        company=company,
        workflow__transaction_type=transaction_type,
        content_type=ContentType.objects.get_for_model(target),
        object_id=target.pk,
        status='pending',
    ).order_by('-submitted_at').first()
    if existing_pending is not None:
        return existing_pending
    content_type = ContentType.objects.get_for_model(target)
    approval = ApprovalRequest.objects.create(
        company=company,
        workflow=workflow,
        requester=requester,
        content_type=content_type,
        object_id=target.pk,
        workflow_snapshot=_snapshot_for_workflow(workflow),
    )
    first_step, eligible = _move_to_next_actionable_step(approval, target, approval.current_step)
    if first_step is None and not _request_steps(approval):
        raise ValidationError('Approval workflow has no steps.')
    approval.save(update_fields=['current_step', 'status', 'completed_at', 'updated_at'])
    if first_step is not None and not eligible:
        AuditEvent.record(
            actor=requester,
            company=company,
            module='approvals',
            action='routing_failed',
            obj=target,
            after={'approval_id': approval.pk, 'status': approval.status, 'current_step': approval.current_step},
            reason='No eligible approver is currently configured for the required step.',
            request=request,
        )
    for user in eligible:
        create_notification(
            user=user,
            notification_type='approval_required',
            title=f'Approval required: {transaction_type}',
            message=f'{requester.get_full_name()} submitted {transaction_type} for your review.',
            related_object=target,
        )
    AuditEvent.record(actor=requester, company=company, module='approvals', action='submitted', obj=target, after={'approval_id': approval.pk, 'status': approval.status}, reason=reason, request=request)
    return approval


@transaction.atomic
def decide_approval(*, approval, actor, decision, reason='', request=None):
    if approval.company_id != actor.company_id:
        raise ValidationError('Approval belongs to another company.')
    approval = ApprovalRequest.objects.select_for_update().select_related('workflow').get(pk=approval.pk)
    if approval.status != 'pending':
        raise ValidationError('This approval is no longer pending.')
    if _target_company_id(approval.target) != approval.company_id:
        raise ValidationError('Approval target belongs to another company.')
    step = next((item for item in _request_steps(approval) if item.sequence == approval.current_step), None)
    target = approval.target
    department = getattr(getattr(target, 'department', None), 'name', '') or getattr(target, 'department', '') or ''
    branch = getattr(getattr(target, 'branch', None), 'name', '') or getattr(target, 'branch', '') or ''
    if step is None or not _step_matches(step=step, user=actor, amount=_target_amount(target), department=department, branch=branch) or not _user_has_explicit_authority(
        actor,
        approval.workflow.transaction_type,
        step,
        _target_amount(approval.target),
        approval.target,
    ):
        raise ValidationError('You are not authorised for the current approval step.')
    allow_self_approval = (approval.workflow_snapshot or {}).get('allow_self_approval', approval.workflow.allow_self_approval)
    if actor.pk == approval.requester_id and not allow_self_approval:
        raise ValidationError('The requester cannot approve their own work.')
    if decision in ('rejected', 'returned') and not reason.strip():
        raise ValidationError('A reason is required for rejection or return for correction.')
    step_record = approval.workflow.steps.filter(sequence=approval.current_step).first()
    if step_record is None:
        raise ValidationError('The original approval step is unavailable.')
    ApprovalDecision.objects.create(request=approval, step=step_record, actor=actor, decision=decision, reason=reason)
    if decision == 'approved':
        next_step, eligible = _move_to_next_actionable_step(approval, target, approval.current_step + 1)
        if next_step:
            approval.save(update_fields=['current_step', 'updated_at'])
            for user in eligible:
                create_notification(user=user, notification_type='approval_required', title='Approval required', message=f'Approval step {next_step.sequence} is ready.', related_object=target)
        else:
            apply_decision = getattr(target, 'apply_approval_decision', None)
            if apply_decision is not None:
                apply_decision('approved')
            approval.save(update_fields=['status', 'completed_at', 'updated_at'])
    else:
        apply_decision = getattr(target, 'apply_approval_decision', None)
        if apply_decision is not None:
            apply_decision(decision)
        approval.status = decision
        approval.completed_at = timezone.now()
        approval.save(update_fields=['status', 'completed_at', 'updated_at'])
    AuditEvent.record(actor=actor, company=approval.company, module='approvals', action=decision, obj=target, after={'approval_id': approval.pk, 'status': approval.status, 'current_step': approval.current_step}, reason=reason, request=request)
    if approval.status in ('rejected', 'returned'):
        create_notification(user=approval.requester, notification_type='approval_decision', title=f'Approval {approval.status}', message=reason, related_object=target)
    return approval


def latest_approval_for(target, company=None):
    content_type = ContentType.objects.get_for_model(target)
    target_company_id = _target_company_id(target)
    queryset = ApprovalRequest.objects.filter(
        content_type=content_type,
        object_id=target.pk,
    )
    if company is None:
        company_id = target_company_id
    else:
        company_id = getattr(company, 'pk', company)
    if company_id is None:
        return None
    return queryset.filter(company_id=company_id).order_by('-submitted_at').first()


def actionable_approvals_for_user(user):
    """Return pending requests the user can currently decide, in tenant scope."""
    if not getattr(user, 'company_id', None):
        return ApprovalRequest.objects.none()
    pending = ApprovalRequest.objects.filter(
        company_id=user.company_id,
        status='pending',
    ).select_related('requester', 'workflow').prefetch_related('workflow__steps')
    return [
        item for item in pending
        if next((step for step in _request_steps(item) if step.sequence == item.current_step), None)
        and _step_matches(
            next((step for step in _request_steps(item) if step.sequence == item.current_step), None),
            user,
            _target_amount(item.target),
            department=getattr(getattr(item.target, 'department', None), 'name', '') or getattr(item.target, 'department', '') or '',
            branch=getattr(getattr(item.target, 'branch', None), 'name', '') or getattr(item.target, 'branch', '') or '',
        )
        and _user_has_explicit_authority(
            user,
            (item.workflow_snapshot or {}).get('transaction_type', item.workflow.transaction_type),
            next((step for step in _request_steps(item) if step.sequence == item.current_step), None),
            _target_amount(item.target),
            item.target,
        )
        and not (item.requester_id == user.pk and not (item.workflow_snapshot or {}).get('allow_self_approval', item.workflow.allow_self_approval))
    ]


@transaction.atomic
def process_overdue_approvals(*, company=None, now=None):
    """Send due reminders and escalation notices for pending approvals.

    This operation is safe to run repeatedly. Existing unread approval
    notifications in the current reminder window suppress duplicates.
    """
    now = now or timezone.now()
    queryset = ApprovalRequest.objects.filter(status='pending').select_related('company', 'workflow', 'requester')
    if company is not None:
        queryset = queryset.filter(company=company)

    processed = {'reminded': 0, 'escalated': 0}
    for approval in queryset:
        age_hours = (now - approval.submitted_at).total_seconds() / 3600
        workflow = approval.workflow
        snapshot = approval.workflow_snapshot or {}
        reminder_after_hours = snapshot.get('reminder_after_hours', workflow.reminder_after_hours)
        escalation_after_hours = snapshot.get('escalation_after_hours', workflow.escalation_after_hours)
        transaction_type = snapshot.get('transaction_type', workflow.transaction_type)
        if age_hours < reminder_after_hours:
            continue
        target = approval.target
        step = next((item for item in _request_steps(approval) if item.sequence == approval.current_step), None)
        if step is None:
            continue
        amount = _target_amount(target)
        eligible = [
            user for user in approval.company.users.filter(is_active=True)
            if _step_matches(
                step,
                user,
                amount,
                department=getattr(getattr(target, 'department', None), 'name', '') or getattr(target, 'department', '') or '',
                branch=getattr(getattr(target, 'branch', None), 'name', '') or getattr(target, 'branch', '') or '',
            ) and _user_has_explicit_authority(user, transaction_type, step, amount, target)
        ]
        if not eligible:
            continue
        notification_type = 'approval_required'
        escalation = age_hours >= escalation_after_hours
        title = 'Approval escalation' if escalation else 'Approval reminder'
        message = (
            f'Approval APR-{approval.pk} has been pending for {int(age_hours)} hours. '
            f'Please review step {step.sequence}.'
        )
        cutoff = now - timedelta(hours=max(reminder_after_hours, 1))
        for user in eligible:
            already_notified = Notification.objects.filter(
                user=user,
                notification_type=notification_type,
                related_object_id=target.pk,
                related_object_type=f'{target._meta.app_label}.{target._meta.model_name}',
                created_at__gte=cutoff,
                data__approval_id=approval.pk,
            ).exists()
            if not already_notified:
                create_notification(
                    user=user,
                    notification_type=notification_type,
                    title=title,
                    message=message,
                    data={'approval_id': approval.pk, 'escalated': escalation},
                    related_object=target,
                )
                processed['escalated' if escalation else 'reminded'] += 1
        AuditEvent.record(
            actor=None,
            company=approval.company,
            module='approvals',
            action='escalated' if escalation else 'reminder_sent',
            obj=target,
            after={'approval_id': approval.pk, 'current_step': step.sequence},
            reason='Scheduled approval follow-up.',
        )
    return processed
