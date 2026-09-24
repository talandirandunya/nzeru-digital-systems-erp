from django import forms

from .models import ApprovalStep, ApprovalWorkflow


class ApprovalWorkflowForm(forms.ModelForm):
    class Meta:
        model = ApprovalWorkflow
        fields = ['name', 'transaction_type', 'enabled', 'applies_from', 'applies_to', 'allow_self_approval', 'reminder_after_hours', 'escalation_after_hours']


class ApprovalStepForm(forms.ModelForm):
    class Meta:
        model = ApprovalStep
        fields = ['sequence', 'role', 'capability', 'department', 'branch', 'min_amount', 'max_amount', 'approval_limit', 'required']
