from django import forms

from .models import ApprovalStep, ApprovalWorkflow


class ApprovalWorkflowForm(forms.ModelForm):
    class Meta:
        model = ApprovalWorkflow
        fields = ['name', 'transaction_type', 'enabled', 'applies_from', 'applies_to', 'allow_self_approval']


class ApprovalStepForm(forms.ModelForm):
    class Meta:
        model = ApprovalStep
        fields = ['sequence', 'role', 'capability', 'department', 'min_amount', 'max_amount', 'approval_limit', 'required']
