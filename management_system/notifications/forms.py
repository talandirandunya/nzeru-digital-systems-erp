from django import forms
from .models import NotificationPreference


class NotificationPreferenceForm(forms.ModelForm):
    """Form for managing user notification preferences."""

    class Meta:
        model = NotificationPreference
        fields = [
            'email_leave_requests', 'email_performance_reviews', 'email_training_updates',
            'email_payroll_updates', 'email_meeting_invitations', 'email_system_alerts',
            'in_app_leave_requests', 'in_app_performance_reviews', 'in_app_training_updates',
            'in_app_payroll_updates', 'in_app_meeting_invitations', 'in_app_system_alerts',
        ]
        widgets = {
            'email_leave_requests': forms.CheckboxInput(attrs={'class': 'form-check-input'}),
            'email_performance_reviews': forms.CheckboxInput(attrs={'class': 'form-check-input'}),
            'email_training_updates': forms.CheckboxInput(attrs={'class': 'form-check-input'}),
            'email_payroll_updates': forms.CheckboxInput(attrs={'class': 'form-check-input'}),
            'email_meeting_invitations': forms.CheckboxInput(attrs={'class': 'form-check-input'}),
            'email_system_alerts': forms.CheckboxInput(attrs={'class': 'form-check-input'}),
            'in_app_leave_requests': forms.CheckboxInput(attrs={'class': 'form-check-input'}),
            'in_app_performance_reviews': forms.CheckboxInput(attrs={'class': 'form-check-input'}),
            'in_app_training_updates': forms.CheckboxInput(attrs={'class': 'form-check-input'}),
            'in_app_payroll_updates': forms.CheckboxInput(attrs={'class': 'form-check-input'}),
            'in_app_meeting_invitations': forms.CheckboxInput(attrs={'class': 'form-check-input'}),
            'in_app_system_alerts': forms.CheckboxInput(attrs={'class': 'form-check-input'}),
        }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        # Group fields for better display
        self.field_groups = {
            'Email Notifications': [
                'email_leave_requests', 'email_performance_reviews', 'email_training_updates',
                'email_payroll_updates', 'email_meeting_invitations', 'email_system_alerts'
            ],
            'In-App Notifications': [
                'in_app_leave_requests', 'in_app_performance_reviews', 'in_app_training_updates',
                'in_app_payroll_updates', 'in_app_meeting_invitations', 'in_app_system_alerts'
            ]
        }