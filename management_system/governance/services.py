from decimal import Decimal

from django.contrib.contenttypes.models import ContentType
from django.core.exceptions import ValidationError
from django.db import transaction
from django.utils import timezone

from notifications.models import Notification
from notifications.utils import create_notification

from .models import ApprovalDecision, ApprovalRequest, ApprovalWorkflow, AuditEvent, UserApprovalAuthority, has_capability


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


def _user_has_explicit_authority(user, transaction_type, step, amount, target=None):
    if user.is_superuser or not getattr(user, 'access_controlled', False):
        return True
    department = getattr(getattr(target, 'department', None), 'name', '') or getattr(target, 'department', '') or ''
    authorities = UserApprovalAuthority.objects.filter(
        company=user.company,
        user=user,
        transaction_type=transaction_type,
        enabled=True,
    )
    return any(
        authority.matches(user, amount, department=department)
        and (not step.capability or authority.capability == step.capability)
        for authority in authorities
    )


def _eligible_users(company, step, amount, transaction_type, target=None):
    users = company.users.filter(is_active=True).exclude(is_superuser=False, company__isnull=True)
    return [
        user for user in users
        if step.matches(user, amount)
        and _user_has_explicit_authority(user, transaction_type, step, amount, target)
    ]


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
    steps = approval.workflow.steps.filter(sequence__gte=start_sequence).order_by('sequence')
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
    content_type = ContentType.objects.get_for_model(target)
    approval = ApprovalRequest.objects.create(
        company=company,
        workflow=workflow,
        requester=requester,
        content_type=content_type,
        object_id=target.pk,
    )
    first_step, eligible = _move_to_next_actionable_step(approval, target, approval.current_step)
    if first_step is None and not approval.workflow.steps.exists():
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
    step = approval.current_step_config
    if step is None or not step.matches(actor, _target_amount(approval.target)) or not _user_has_explicit_authority(
        actor,
        approval.workflow.transaction_type,
        step,
        _target_amount(approval.target),
        approval.target,
    ):
        raise ValidationError('You are not authorised for the current approval step.')
    if actor.pk == approval.requester_id and not approval.workflow.allow_self_approval:
        raise ValidationError('The requester cannot approve their own work.')
    if decision in ('rejected', 'returned') and not reason.strip():
        raise ValidationError('A reason is required for rejection or return for correction.')
    ApprovalDecision.objects.create(request=approval, step=step, actor=actor, decision=decision, reason=reason)
    target = approval.target
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
        if item.current_step_config
        and item.current_step_config.matches(user, _target_amount(item.target))
        and _user_has_explicit_authority(
            user,
            item.workflow.transaction_type,
            item.current_step_config,
            _target_amount(item.target),
            item.target,
        )
        and not (item.requester_id == user.pk and not item.workflow.allow_self_approval)
    ]
