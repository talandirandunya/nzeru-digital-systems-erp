"""
meetings/forms.py
"""

from django import forms
from django.core.exceptions import ValidationError
from django.utils import timezone
from employees.models import Employee
from .models import Meeting, MeetingNote, ActionItem, MeetingAttachment


class MeetingForm(forms.ModelForm):
    """Form for creating and editing meetings."""
    
    attendees = forms.ModelMultipleChoiceField(
        queryset=Employee.objects.none(),
        widget=forms.CheckboxSelectMultiple,
        required=False,
        help_text='Select all meeting participants'
    )
    
    class Meta:
        model = Meeting
        fields = [
            'title', 'description', 'meeting_type', 'scheduled_date',
            'location', 'organizer', 'attendees', 'priority', 'status'
        ]
        widgets = {
            'title': forms.TextInput(attrs={
                'class': 'form-control',
                'placeholder': 'Meeting title'
            }),
            'description': forms.Textarea(attrs={
                'class': 'form-control',
                'rows': 3,
                'placeholder': 'Meeting objectives and overview'
            }),
            'meeting_type': forms.Select(attrs={'class': 'form-select'}),
            'scheduled_date': forms.DateTimeInput(attrs={
                'class': 'form-control',
                'type': 'datetime-local'
            }),
            'location': forms.TextInput(attrs={
                'class': 'form-control',
                'placeholder': 'Room, building, or video link'
            }),
            'organizer': forms.Select(attrs={'class': 'form-select'}),
            'priority': forms.Select(attrs={'class': 'form-select'}),
            'status': forms.Select(attrs={'class': 'form-select'}),
        }
    
    def __init__(self, *args, company=None, **kwargs):
        super().__init__(*args, **kwargs)
        self.company = company
        
        if company:
            employees = Employee.objects.filter(
                company=company, status='active'
            ).select_related('user').order_by('user__first_name', 'user__last_name')
            self.fields['organizer'].queryset = employees
            self.fields['attendees'].queryset = employees
        
        # Set minimum datetime to now for new meetings
        if not self.instance.pk:
            self.fields['scheduled_date'].widget.attrs['min'] = timezone.now().strftime('%Y-%m-%dT%H:%M')
    
    def clean_scheduled_date(self):
        scheduled_date = self.cleaned_data.get('scheduled_date')
        if scheduled_date and scheduled_date < timezone.now():
            raise ValidationError('Scheduled date must be in the future.')
        return scheduled_date
    
    def clean_title(self):
        return self.cleaned_data.get('title', '').strip()


class MeetingNoteForm(forms.ModelForm):
    """Form for meeting notes and report."""
    
    class Meta:
        model = MeetingNote
        fields = [
            'agenda', 'discussion_summary', 'decisions_made',
            'risks_identified', 'next_steps', 'report_document'
        ]
        widgets = {
            'agenda': forms.Textarea(attrs={
                'class': 'form-control',
                'rows': 3,
                'placeholder': 'Meeting agenda topics',
            }),
            'discussion_summary': forms.Textarea(attrs={
                'class': 'form-control',
                'rows': 4,
                'placeholder': 'Detailed summary of discussions',
            }),
            'decisions_made': forms.Textarea(attrs={
                'class': 'form-control',
                'rows': 3,
                'placeholder': 'Key decisions and resolutions',
            }),
            'risks_identified': forms.Textarea(attrs={
                'class': 'form-control',
                'rows': 3,
                'placeholder': 'Risks or issues identified during the meeting',
            }),
            'next_steps': forms.Textarea(attrs={
                'class': 'form-control',
                'rows': 3,
                'placeholder': 'Follow-up items and next meeting plan',
            }),
            'report_document': forms.FileInput(attrs={
                'class': 'form-control',
                'accept': '.pdf,.doc,.docx,.xls,.xlsx,.ppt,.pptx,.txt'
            }),
        }


class ActionItemForm(forms.ModelForm):
    """Form for creating and editing action items."""
    
    class Meta:
        model = ActionItem
        fields = [
            'title', 'description', 'assigned_to', 'due_date',
            'priority', 'status', 'is_completed', 'notes'
        ]
        widgets = {
            'title': forms.TextInput(attrs={
                'class': 'form-control',
                'placeholder': 'Action item title'
            }),
            'description': forms.Textarea(attrs={
                'class': 'form-control',
                'rows': 2,
                'placeholder': 'Detailed description'
            }),
            'assigned_to': forms.Select(attrs={'class': 'form-select'}),
            'due_date': forms.DateInput(attrs={
                'class': 'form-control',
                'type': 'date'
            }),
            'priority': forms.Select(attrs={'class': 'form-select'}),
            'status': forms.Select(attrs={'class': 'form-select'}),
            'is_completed': forms.CheckboxInput(attrs={
                'class': 'form-check-input',
            }),
            'notes': forms.Textarea(attrs={
                'class': 'form-control',
                'rows': 2,
                'placeholder': 'Progress notes or updates'
            }),
        }
    
    def __init__(self, *args, company=None, **kwargs):
        super().__init__(*args, **kwargs)
        if company:
            self.fields['assigned_to'].queryset = Employee.objects.filter(
                company=company, status='active'
            ).select_related('user').order_by('user__first_name', 'user__last_name')
    
    def clean(self):
        cleaned_data = super().clean()
        due_date = cleaned_data.get('due_date')
        
        if due_date and due_date < timezone.now().date():
            self.add_error('due_date', 'Due date must be in the future.')
        
        return cleaned_data


class MeetingAttachmentForm(forms.ModelForm):
    """Form for uploading meeting attachments."""
    
    class Meta:
        model = MeetingAttachment
        fields = ['title', 'file_type', 'file', 'description']
        widgets = {
            'title': forms.TextInput(attrs={
                'class': 'form-control',
                'placeholder': 'Document title'
            }),
            'file_type': forms.Select(attrs={'class': 'form-select'}),
            'file': forms.FileInput(attrs={
                'class': 'form-control',
                'accept': '.pdf,.doc,.docx,.xls,.xlsx,.ppt,.pptx,.txt,.png,.jpg,.jpeg,.gif,.zip,.csv'
            }),
            'description': forms.Textarea(attrs={
                'class': 'form-control',
                'rows': 2,
                'placeholder': 'Optional file description'
            }),
        }


class QuickMeetingForm(forms.ModelForm):
    """Simplified form for quick meeting creation."""
    
    class Meta:
        model = Meeting
        fields = ['title', 'meeting_type', 'scheduled_date', 'location', 'organizer']
        widgets = {
            'title': forms.TextInput(attrs={
                'class': 'form-control',
                'placeholder': 'Meeting title'
            }),
            'meeting_type': forms.Select(attrs={'class': 'form-select'}),
            'scheduled_date': forms.DateTimeInput(attrs={
                'class': 'form-control',
                'type': 'datetime-local'
            }),
            'location': forms.TextInput(attrs={
                'class': 'form-control',
                'placeholder': 'Location (optional)'
            }),
            'organizer': forms.Select(attrs={'class': 'form-select'}),
        }
    
    def __init__(self, *args, company=None, **kwargs):
        super().__init__(*args, **kwargs)
        if company:
            employees = Employee.objects.filter(
                company=company, status='active'
            ).select_related('user').order_by('user__first_name', 'user__last_name')
            self.fields['organizer'].queryset = employees


class MeetingFilterForm(forms.Form):
    """Form for filtering meetings."""
    
    status = forms.MultipleChoiceField(
        choices=Meeting.STATUS_CHOICES,
        widget=forms.CheckboxSelectMultiple,
        required=False,
        label='Status'
    )
    
    meeting_type = forms.MultipleChoiceField(
        choices=Meeting.MEETING_TYPE_CHOICES,
        widget=forms.CheckboxSelectMultiple,
        required=False,
        label='Meeting Type'
    )
    
    priority = forms.MultipleChoiceField(
        choices=[('low', 'Low'), ('medium', 'Medium'), ('high', 'High')],
        widget=forms.CheckboxSelectMultiple,
        required=False,
        label='Priority'
    )
    
    date_from = forms.DateField(
        required=False,
        widget=forms.DateInput(attrs={'class': 'form-control', 'type': 'date'}),
        label='From'
    )
    
    date_to = forms.DateField(
        required=False,
        widget=forms.DateInput(attrs={'class': 'form-control', 'type': 'date'}),
        label='To'
    )
    
    search = forms.CharField(
        required=False,
        widget=forms.TextInput(attrs={
            'class': 'form-control',
            'placeholder': 'Search meetings...'
        }),
        label='Search'
    )
