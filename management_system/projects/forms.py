"""
projects/forms.py
"""

from django import forms
from django.core.exceptions import ValidationError

from employees.models import Employee
from .models import CommentaireTache, Project, SousTache


class ProjectForm(forms.ModelForm):
    class Meta:
        model = Project
        fields = [
            'name', 'description', 'status', 'priority', 'manager',
            'team_members', 'budget', 'start_date', 'end_date',
            'completion_percentage',
        ]
        widgets = {
            'name': forms.TextInput(attrs={'class': 'form-control'}),
            'description': forms.Textarea(attrs={'class': 'form-control', 'rows': 4}),
            'status': forms.Select(attrs={'class': 'form-select'}),
            'priority': forms.Select(attrs={'class': 'form-select'}),
            'manager': forms.Select(attrs={'class': 'form-select'}),
            'team_members': forms.SelectMultiple(attrs={
                'class': 'form-select',
                'size': '6',
                'id': 'id_team_members',
            }),
            'start_date': forms.DateInput(attrs={'class': 'form-control', 'type': 'date'}),
            'end_date': forms.DateInput(attrs={'class': 'form-control', 'type': 'date'}),
            'budget': forms.NumberInput(attrs={'class': 'form-control', 'step': '0.01', 'min': '0'}),
            'completion_percentage': forms.NumberInput(attrs={
                'class': 'form-control', 'min': 0, 'max': 100,
            }),
        }

    def __init__(self, *args, company=None, **kwargs):
        super().__init__(*args, **kwargs)
        self.company = company
        if company:
            employees = Employee.objects.filter(
                company=company, status='active'
            ).select_related('user').order_by('user__first_name', 'user__last_name')
            self.fields['manager'].queryset = employees
            self.fields['team_members'].queryset = employees

    def clean_name(self):
        return self.cleaned_data['name'].strip()

    def clean(self):
        cleaned_data = super().clean()
        start_date = cleaned_data.get('start_date')
        end_date = cleaned_data.get('end_date')
        if start_date and end_date and start_date > end_date:
            self.add_error('end_date', 'End date must be after start date.')
        return cleaned_data


class SousTacheForm(forms.ModelForm):
    class Meta:
        model = SousTache
        fields = [
            'titre', 'description', 'assigne_a', 'status', 'priorite',
            'date_debut', 'date_echeance', 'duree_estimee', 'ordre', 'depend_de',
        ]
        widgets = {
            'titre': forms.TextInput(attrs={'class': 'form-control'}),
            'description': forms.Textarea(attrs={'class': 'form-control', 'rows': 4}),
            'assigne_a': forms.Select(attrs={'class': 'form-select'}),
            'status': forms.Select(attrs={'class': 'form-select'}),
            'priorite': forms.Select(attrs={'class': 'form-select'}),
            'depend_de': forms.Select(attrs={'class': 'form-select'}),
            'date_debut': forms.DateInput(attrs={'class': 'form-control', 'type': 'date'}),
            'date_echeance': forms.DateInput(attrs={'class': 'form-control', 'type': 'date'}),
            'duree_estimee': forms.NumberInput(attrs={
                'class': 'form-control',
                'min': 0, 'placeholder': 'Estimated hours',
            }),
            'ordre': forms.NumberInput(attrs={
                'class': 'form-control',
                'min': 0, 'placeholder': 'Display order',
            }),
        }

    def __init__(self, *args, company=None, projet_id=None, **kwargs):
        super().__init__(*args, **kwargs)
        self.company = company
        self.projet_id = projet_id

        self.fields['assigne_a'].required = False
        self.fields['assigne_a'].empty_label = '— Unassigned —'

        if company:
            self.fields['assigne_a'].queryset = (
                Employee.objects.filter(company=company, status='active')
                .select_related('user')
                .order_by('user__first_name', 'user__last_name')
            )

        self.fields['depend_de'].required = False
        self.fields['depend_de'].empty_label = '— None —'

        if company and projet_id:
            exclude_pk = self.instance.pk if self.instance.pk else None
            dep_qs = SousTache.objects.filter(
                company=company, projet_id=projet_id
            )
            if exclude_pk:
                dep_qs = dep_qs.exclude(pk=exclude_pk)
            self.fields['depend_de'].queryset = dep_qs

            # Auto-increment order for new tasks
            if not self.instance.pk:
                last = (
                    SousTache.objects.filter(company=company, projet_id=projet_id)
                    .order_by('-ordre')
                    .values_list('ordre', flat=True)
                    .first()
                )
                self.fields['ordre'].initial = (last + 1) if last is not None else 0

    def clean_titre(self):
        return self.cleaned_data['titre'].strip()

    def clean(self):
        cleaned_data = super().clean()
        date_debut = cleaned_data.get('date_debut')
        date_echeance = cleaned_data.get('date_echeance')
        if date_debut and date_echeance and date_debut > date_echeance:
            self.add_error('date_echeance', 'Due date must be after start date.')
        return cleaned_data


class CommentaireForm(forms.ModelForm):
    class Meta:
        model = CommentaireTache
        fields = ['contenu']
        widgets = {
            'contenu': forms.Textarea(attrs={
                'rows': 3,
                'placeholder': 'Add a comment…',
            }),
        }

    def clean_contenu(self):
        contenu = self.cleaned_data.get('contenu', '').strip()
        if not contenu:
            raise ValidationError('Comment cannot be empty.')
        return contenu