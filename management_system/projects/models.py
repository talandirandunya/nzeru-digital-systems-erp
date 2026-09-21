"""
projects/models.py — Projects, sub-tasks (SousTache), and task comments.

Design notes:
  - Project.update_completion_from_subtasks() uses a single DB aggregate
    instead of loading all subtask objects into Python memory.
  - SousTache.change_status() centralises the status-transition logic that
    was previously duplicated across several views.
  - CommentaireTache.__str__ no longer risks an IndexError on very short
    content strings.
"""

import logging

from django.conf import settings
from django.core.exceptions import ValidationError
from django.core.validators import MaxValueValidator, MinValueValidator
from django.db import models
from django.db.models import Avg
from django.utils import timezone

logger = logging.getLogger(__name__)


class Project(models.Model):
    STATUS_CHOICES = [
        ('planning', 'Planning'),
        ('in_progress', 'In Progress'),
        ('on_hold', 'On Hold'),
        ('completed', 'Completed'),
        ('cancelled', 'Cancelled'),
    ]

    PRIORITY_CHOICES = [
        ('low', 'Low'),
        ('medium', 'Medium'),
        ('high', 'High'),
        ('critical', 'Critical'),
    ]

    company = models.ForeignKey(
        'accounts.Company',
        on_delete=models.CASCADE,
        related_name='projects',
    )
    name = models.CharField(max_length=200)
    description = models.TextField(blank=True)
    status = models.CharField(
        max_length=20, choices=STATUS_CHOICES, default='planning', db_index=True
    )
    priority = models.CharField(
        max_length=20, choices=PRIORITY_CHOICES, default='medium', db_index=True
    )
    manager = models.ForeignKey(
        'employees.Employee',
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='managed_projects',
    )
    team_members = models.ManyToManyField(
        'employees.Employee',
        related_name='projects',
        blank=True,
    )
    budget = models.DecimalField(
        max_digits=12,
        decimal_places=2,
        validators=[MinValueValidator(0)],
    )
    start_date = models.DateField()
    end_date = models.DateField()
    completion_percentage = models.IntegerField(
        default=0,
        validators=[MinValueValidator(0), MaxValueValidator(100)],
    )
    created_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        related_name='created_projects',
    )
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        constraints = [
            models.UniqueConstraint(
                fields=['company', 'name'],
                name='unique_project_name_per_company',
            )
        ]
        ordering = ['-created_at']
        indexes = [
            models.Index(fields=['company', 'status']),
            models.Index(fields=['company', 'priority']),
        ]

    def __str__(self) -> str:
        return f'{self.name} ({self.company.name})'

    def clean(self):
        if self.start_date and self.end_date and self.start_date > self.end_date:
            raise ValidationError({'end_date': 'End date must be after start date.'})

    # ------------------------------------------------------------------
    # Computed properties
    # ------------------------------------------------------------------

    @property
    def is_overdue(self) -> bool:
        return (
            self.end_date is not None
            and self.status in ('planning', 'in_progress')
            and self.end_date < timezone.localdate()
        )

    @property
    def task_count(self) -> int:
        return self.sous_taches.count()

    # ------------------------------------------------------------------
    # Progress sync
    # ------------------------------------------------------------------

    def update_completion_from_subtasks(self) -> None:
        """
        Recalculate completion_percentage as the average of all linked
        SousTache.completion_percentage values.

        Uses a single DB aggregate instead of loading all objects into memory.
        Called after any task create / update / delete / toggle.
        """
        result = self.sous_taches.aggregate(avg=Avg('completion_percentage'))
        new_pct = int(result['avg'] or 0)
        if new_pct != self.completion_percentage:
            self.completion_percentage = new_pct
            self.save(update_fields=['completion_percentage', 'updated_at'])
        self.sync_status_from_subtasks()

    def sync_status_from_subtasks(self) -> None:
        """
        When every subtask is terminé, set project workflow status to completed.
        If any subtask is not done and the project was completed, set back to in progress.
        Skips projects with no subtasks or cancelled projects.
        """
        if self.status == 'cancelled':
            return
        task_qs = self.sous_taches.all()
        if not task_qs.exists():
            return
        any_open = task_qs.exclude(status='termine').exists()
        new_status = None
        if not any_open:
            new_status = 'completed'
        elif self.status == 'completed':
            new_status = 'in_progress'
        if new_status is not None and new_status != self.status:
            self.status = new_status
            self.save(update_fields=['status', 'updated_at'])


class SousTache(models.Model):
    """A sub-task (checklist item) belonging to a Project."""

    STATUS_CHOICES = [
        ('a_faire', 'À faire'),
        ('en_cours', 'En cours'),
        ('termine', 'Terminé'),
        ('en_attente', 'En attente'),
        ('annule', 'Annulé'),
    ]

    PRIORITE_CHOICES = [
        ('faible', 'Faible'),
        ('moyenne', 'Moyenne'),
        ('elevee', 'Élevée'),
        ('urgente', 'Urgente'),
    ]

    company = models.ForeignKey(
        'accounts.Company',
        on_delete=models.CASCADE,
        related_name='sous_taches',
    )
    projet = models.ForeignKey(
        Project,
        on_delete=models.CASCADE,
        related_name='sous_taches',
    )
    titre = models.CharField(max_length=200)
    description = models.TextField(blank=True)
    assigne_a = models.ForeignKey(
        'employees.Employee',
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='taches_assignees',
    )
    status = models.CharField(
        max_length=20, choices=STATUS_CHOICES, default='a_faire', db_index=True
    )
    priorite = models.CharField(
        max_length=20, choices=PRIORITE_CHOICES, default='moyenne'
    )
    date_debut = models.DateField(null=True, blank=True)
    date_echeance = models.DateField(null=True, blank=True)
    date_achevement = models.DateField(null=True, blank=True)
    duree_estimee = models.PositiveIntegerField(
        help_text='Durée estimée en heures',
        default=0,
    )
    ordre = models.IntegerField(default=0, db_index=True)
    depend_de = models.ForeignKey(
        'self',
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='dependances',
    )
    completion_percentage = models.IntegerField(
        default=0,
        validators=[MinValueValidator(0), MaxValueValidator(100)],
    )
    created_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
    )
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ['ordre', 'created_at']
        verbose_name = 'Sous-tâche'
        verbose_name_plural = 'Sous-tâches'
        indexes = [
            models.Index(fields=['projet', 'status']),
        ]

    def __str__(self) -> str:
        return f'{self.titre} — {self.get_status_display()}'

    def clean(self):
        if self.date_debut and self.date_echeance and self.date_debut > self.date_echeance:
            raise ValidationError({'date_echeance': 'Due date must be after start date.'})

    # ------------------------------------------------------------------
    # Status transition
    # ------------------------------------------------------------------

    def change_status(self, new_status: str) -> None:
        """
        Change task status with side-effects:
          - Sets date_achevement when moving to 'termine'
          - Clears date_achevement when moving away from 'termine'
          - Syncs completion_percentage (100 for termine, 0 otherwise)
          - Recalculates the parent project's completion

        Centralises logic previously duplicated across
        sous_tache_change_status() and toggle_subtask_completion().
        """
        valid = {choice[0] for choice in self.STATUS_CHOICES}
        if new_status not in valid:
            raise ValidationError(f"'{new_status}' is not a valid status.")

        self.status = new_status
        if new_status == 'termine':
            self.completion_percentage = 100
            self.date_achevement = timezone.localdate()
        else:
            self.completion_percentage = 0
            self.date_achevement = None

        self.save(update_fields=[
            'status', 'completion_percentage', 'date_achevement', 'updated_at'
        ])
        self.projet.update_completion_from_subtasks()


class CommentaireTache(models.Model):
    """A comment on a SousTache."""

    company = models.ForeignKey(
        'accounts.Company',
        on_delete=models.CASCADE,
        related_name='commentaires',
    )
    tache = models.ForeignKey(
        SousTache,
        on_delete=models.CASCADE,
        related_name='commentaires',
    )
    auteur = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
    )
    contenu = models.TextField()
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ['-created_at']

    def __str__(self) -> str:
        # Avoid IndexError on very short content; truncate safely
        preview = (self.contenu[:30] + '…') if len(self.contenu) > 30 else self.contenu
        return f'Comment by {self.auteur} on "{self.tache.titre}": {preview}'