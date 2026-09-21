"""
crm/models.py

Models:
  - Contact       : An external person/lead, optionally linked to a marketplace Client
  - Note          : Activity log entry on a Contact
  - Opportunity   : A deal in the sales pipeline, assigned to an employee
"""

import logging

from django.conf import settings
from django.core.validators import MinValueValidator
from django.db import models
from django.utils import timezone

logger = logging.getLogger(__name__)


class Contact(models.Model):
    """An external contact / lead for the company."""

    company = models.ForeignKey(
        'accounts.Company',
        on_delete=models.CASCADE,
        related_name='contacts',
    )
    name = models.CharField(max_length=200)
    email = models.EmailField(blank=True)
    phone = models.CharField(max_length=50, blank=True)
    organization = models.CharField(max_length=200, blank=True)

    # Optional link to a marketplace Client
    marketplace_client = models.OneToOneField(
        'marketplace.Client',
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='crm_contact',
        help_text='Link this contact to an existing marketplace client account.',
    )

    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ['name']
        unique_together = [('company', 'email')]
        indexes = [
            models.Index(fields=['company', 'organization']),
        ]

    def __str__(self) -> str:
        return f'{self.name} ({self.company.name})'

    @property
    def open_opportunities_count(self) -> int:
        return self.opportunities.exclude(stage__in=['won', 'lost']).count()

    @property
    def pipeline_value(self):
        return (
            self.opportunities
            .exclude(stage__in=['won', 'lost'])
            .aggregate(total=models.Sum('value'))['total'] or 0
        )


class Note(models.Model):
    """Activity log / note attached to a Contact."""

    TYPE_CHOICES = [
        ('note', 'Note'),
        ('call', 'Phone Call'),
        ('email', 'Email'),
        ('meeting', 'Meeting'),
        ('other', 'Other'),
    ]

    company = models.ForeignKey(
        'accounts.Company',
        on_delete=models.CASCADE,
        related_name='crm_notes',
    )
    contact = models.ForeignKey(
        Contact,
        on_delete=models.CASCADE,
        related_name='notes',
    )
    author = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        related_name='crm_notes',
    )
    note_type = models.CharField(max_length=20, choices=TYPE_CHOICES, default='note')
    content = models.TextField()
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ['-created_at']

    def __str__(self) -> str:
        preview = (self.content[:40] + '...') if len(self.content) > 40 else self.content
        return f'[{self.get_note_type_display()}] {preview}'


class Opportunity(models.Model):
    """A sales opportunity / deal in the pipeline."""

    STAGE_CHOICES = [
        ('prospect', 'Prospect'),
        ('qualified', 'Qualified'),
        ('proposal', 'Proposal'),
        ('won', 'Won'),
        ('lost', 'Lost'),
    ]

    company = models.ForeignKey(
        'accounts.Company',
        on_delete=models.CASCADE,
        related_name='opportunities',
    )
    contact = models.ForeignKey(
        Contact,
        on_delete=models.CASCADE,
        related_name='opportunities',
    )
    title = models.CharField(max_length=200)
    stage = models.CharField(
        max_length=20, choices=STAGE_CHOICES, default='prospect', db_index=True
    )
    value = models.DecimalField(
        max_digits=12,
        decimal_places=2,
        default=0,
        validators=[MinValueValidator(0)],
    )
    assigned_to = models.ForeignKey(
        'employees.Employee',
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='assigned_opportunities',
    )
    follow_up_date = models.DateField(null=True, blank=True)
    follow_up_note = models.TextField(blank=True)
    created_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        related_name='created_opportunities',
    )
    PAYMENT_STATUS_CHOICES = [
        ('unpaid', 'Unpaid'),
        ('invoiced', 'Invoiced'),
        ('paid', 'Paid'),
    ]

    payment_status = models.CharField(
        max_length=20,
        choices=PAYMENT_STATUS_CHOICES,
        default='unpaid',
        db_index=True,
    )
    revenue_transaction = models.OneToOneField(
        'finance.Transaction',
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='crm_opportunity',
    )

    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ['-created_at']
        indexes = [
            models.Index(fields=['company', 'stage']),
            models.Index(fields=['company', 'payment_status']),
            models.Index(fields=['follow_up_date']),
        ]

    def __str__(self) -> str:
        return f'{self.title} ({self.contact.name})'

    @property
    def is_won(self) -> bool:
        return self.stage == 'won'

    @property
    def is_lost(self) -> bool:
        return self.stage == 'lost'

    @property
    def is_open(self) -> bool:
        return self.stage not in ('won', 'lost')

    @property
    def is_overdue_followup(self) -> bool:
        return (
            self.follow_up_date is not None
            and self.is_open
            and self.follow_up_date < timezone.localdate()
        )

    def advance_stage(self, new_stage: str) -> None:
        allowed = {choice[0] for choice in self.STAGE_CHOICES}
        if new_stage not in allowed:
            raise ValueError(f"Invalid stage '{new_stage}'")
        self.stage = new_stage
        self.save(update_fields=['stage', 'updated_at'])