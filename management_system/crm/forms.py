import datetime

from django import forms
from django.utils import timezone

from .models import Contact, Note, Opportunity
from employees.models import Employee
from finance.models import Account
from marketplace.models import Client


class ContactForm(forms.ModelForm):
    # Optional: link to existing marketplace client by email lookup
    link_marketplace_email = forms.EmailField(
        required=False,
        label='Link marketplace client (email)',
        help_text='Enter the email of an existing marketplace client to link them.',
    )

    class Meta:
        model = Contact
        fields = ['name', 'email', 'phone', 'organization']
        widgets = {
            'name': forms.TextInput(attrs={'class': 'form-control'}),
            'email': forms.EmailInput(attrs={'class': 'form-control'}),
            'phone': forms.TextInput(attrs={'class': 'form-control'}),
            'organization': forms.TextInput(attrs={'class': 'form-control'}),
        }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields['link_marketplace_email'].widget.attrs['class'] = 'form-control'
        # Pre-fill if already linked
        if self.instance and self.instance.pk and self.instance.marketplace_client:
            self.fields['link_marketplace_email'].initial = self.instance.marketplace_client.email

    def save(self, commit=True):
        contact = super().save(commit=False)
        email = self.cleaned_data.get('link_marketplace_email', '').strip()
        if email:
            try:
                contact.marketplace_client = Client.objects.get(email=email)
            except Client.DoesNotExist:
                pass  # silently ignore — form validation would catch if needed
        else:
            contact.marketplace_client = None
        if commit:
            contact.save()
        return contact


class NoteForm(forms.ModelForm):
    class Meta:
        model = Note
        fields = ['note_type', 'content']
        widgets = {
            'note_type': forms.Select(attrs={'class': 'form-select'}),
            'content': forms.Textarea(attrs={'class': 'form-control', 'rows': 3}),
        }


class OpportunityForm(forms.ModelForm):
    class Meta:
        model = Opportunity
        fields = ['contact', 'title', 'stage', 'value', 'assigned_to', 'follow_up_date', 'follow_up_note']
        widgets = {
            'contact': forms.Select(attrs={'class': 'form-select'}),
            'title': forms.TextInput(attrs={'class': 'form-control'}),
            'stage': forms.Select(attrs={'class': 'form-select'}),
            'value': forms.NumberInput(attrs={'class': 'form-control', 'step': '0.01'}),
            'assigned_to': forms.Select(attrs={'class': 'form-select'}),
            'follow_up_date': forms.DateInput(attrs={'class': 'form-control', 'type': 'date'}),
            'follow_up_note': forms.Textarea(attrs={'class': 'form-control', 'rows': 2}),
        }

    def __init__(self, *args, **kwargs):
        company = kwargs.pop('company', None)
        super().__init__(*args, **kwargs)
        if company:
            self.fields['contact'].queryset = Contact.objects.filter(company=company)
            self.fields['assigned_to'].queryset = Employee.objects.filter(company=company, status='active')
        self.fields['assigned_to'].required = False
        self.fields['follow_up_date'].required = False
        self.fields['follow_up_note'].required = False


class MarkPaidForm(forms.Form):
    account = forms.ModelChoiceField(
        queryset=Account.objects.none(),
        label='Revenue Account',
        help_text='Select the revenue account this payment should be credited to.',
        widget=forms.Select(attrs={'class': 'form-select'}),
    )
    date = forms.DateField(
        label='Payment Date',
        widget=forms.DateInput(attrs={'class': 'form-control', 'type': 'date'}),
    )
    notes = forms.CharField(
        required=False,
        label='Notes',
        widget=forms.Textarea(attrs={'class': 'form-control', 'rows': 2}),
    )

    def __init__(self, company, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields['account'].queryset = Account.objects.filter(
            company=company, account_type='revenue'
        ).order_by('code', 'name')
        self.fields['date'].initial = datetime.date.today()