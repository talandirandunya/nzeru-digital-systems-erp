"""
meetings/models.py

Meeting Reports Management System.

Models:
  - Meeting       : Core meeting info with date, attendees, location, status
  - ActionItem    : Tracked tasks from meetings with owners and due dates
  - MeetingNote   : Detailed meeting notes and summaries
  - MeetingAttachment : File uploads (Word, PDF, images, etc.)
"""

import logging
from django.conf import settings
from django.core.exceptions import ValidationError
from django.db import models
from django.utils import timezone
from django.core.validators import FileExtensionValidator, MinValueValidator, MaxValueValidator

logger = logging.getLogger(__name__)


class Meeting(models.Model):
    """Represents a scheduled or completed meeting."""
    
    STATUS_CHOICES = [
        ('scheduled', 'Scheduled'),
        ('in_progress', 'In Progress'),
        ('completed', 'Completed'),
        ('cancelled', 'Cancelled'),
        ('rescheduled', 'Rescheduled'),
    ]
    
    MEETING_TYPE_CHOICES = [
        ('team', 'Team Meeting'),
        ('one_on_one', '1-on-1'),
        ('stakeholder', 'Stakeholder'),
        ('board', 'Board'),
        ('client', 'Client'),
        ('training', 'Training'),
        ('brainstorm', 'Brainstorm'),
        ('review', 'Review'),
        ('planning', 'Planning'),
        ('other', 'Other'),
    ]
    
    company = models.ForeignKey(
        'accounts.Company',
        on_delete=models.CASCADE,
        related_name='meetings',
    )
    
    title = models.CharField(max_length=200)
    description = models.TextField(blank=True, help_text='Meeting objectives and overview')
    meeting_type = models.CharField(
        max_length=20,
        choices=MEETING_TYPE_CHOICES,
        default='team',
    )
    
    scheduled_date = models.DateTimeField()
    actual_start = models.DateTimeField(null=True, blank=True)
    actual_end = models.DateTimeField(null=True, blank=True)
    
    location = models.CharField(
        max_length=255,
        blank=True,
        help_text='Physical location, conference room, or Zoom link'
    )
    
    organizer = models.ForeignKey(
        'employees.Employee',
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='organized_meetings',
    )
    
    attendees = models.ManyToManyField(
        'employees.Employee',
        related_name='attended_meetings',
        help_text='Select meeting participants'
    )
    
    status = models.CharField(
        max_length=20,
        choices=STATUS_CHOICES,
        default='scheduled',
        db_index=True,
    )
    
    priority = models.CharField(
        max_length=10,
        choices=[('low', 'Low'), ('medium', 'Medium'), ('high', 'High')],
        default='medium',
    )
    
    # Meeting metadata
    created_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        related_name='created_meetings',
    )
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    
    class Meta:
        ordering = ['-scheduled_date']
        indexes = [
            models.Index(fields=['company', 'status']),
            models.Index(fields=['scheduled_date']),
            models.Index(fields=['company', 'scheduled_date']),
        ]
    
    def __str__(self):
        return f"{self.title} - {self.scheduled_date.strftime('%Y-%m-%d %H:%M')}"
    
    def get_duration(self):
        """Calculate meeting duration in minutes."""
        if self.actual_start and self.actual_end:
            duration = (self.actual_end - self.actual_start).total_seconds() / 60
            return int(duration)
        return None
    
    def mark_completed(self):
        """Mark meeting as completed and set actual times if not set."""
        self.status = 'completed'
        if not self.actual_start:
            self.actual_start = timezone.now()
        self.actual_end = timezone.now()
        self.save()
    
    def get_pending_action_items(self):
        """Get all pending action items from this meeting."""
        return self.action_items.filter(status='pending').order_by('due_date')
    
    def get_action_items_by_owner(self):
        """Group action items by owner."""
        items = {}
        for action in self.action_items.filter(status__in=['pending', 'in_progress']).order_by('assigned_to__user__first_name'):
            owner = action.assigned_to
            if owner not in items:
                items[owner] = []
            items[owner].append(action)
        return items


class MeetingNote(models.Model):
    """Detailed notes and minutes for a meeting."""
    
    meeting = models.OneToOneField(
        Meeting,
        on_delete=models.CASCADE,
        related_name='notes',
    )
    
    agenda = models.TextField(blank=True, help_text='Meeting agenda topics')
    discussion_summary = models.TextField(blank=True, help_text='Detailed summary of discussions')
    decisions_made = models.TextField(blank=True, help_text='Key decisions and resolutions')
    risks_identified = models.TextField(blank=True, help_text='Risks or issues identified')
    next_steps = models.TextField(blank=True, help_text='Follow-up items and next meeting plan')
    
    # Attached documents
    report_document = models.FileField(
        upload_to='meetings/',
        null=True,
        blank=True,
        validators=[FileExtensionValidator(
            allowed_extensions=['pdf', 'doc', 'docx', 'xls', 'xlsx', 'ppt', 'pptx', 'txt']
        )],
        help_text='Upload meeting report (Word, Excel, PDF, PowerPoint, etc.)'
    )
    
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    last_edited_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
    )
    
    class Meta:
        verbose_name_plural = 'Meeting Notes'
    
    def __str__(self):
        return f"Notes for {self.meeting.title}"


class ActionItem(models.Model):
    """Action items and task tracking from meetings."""
    
    STATUS_CHOICES = [
        ('pending', 'Pending'),
        ('in_progress', 'In Progress'),
        ('completed', 'Completed'),
        ('on_hold', 'On Hold'),
        ('cancelled', 'Cancelled'),
        ('overdue', 'Overdue'),
    ]
    
    PRIORITY_CHOICES = [
        ('low', 'Low'),
        ('medium', 'Medium'),
        ('high', 'High'),
        ('critical', 'Critical'),
    ]
    
    meeting = models.ForeignKey(
        Meeting,
        on_delete=models.CASCADE,
        related_name='action_items',
    )
    
    title = models.CharField(max_length=255)
    description = models.TextField(blank=True)
    
    assigned_to = models.ForeignKey(
        'employees.Employee',
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='assigned_actions',
    )
    
    due_date = models.DateField()
    status = models.CharField(
        max_length=20,
        choices=STATUS_CHOICES,
        default='pending',
        db_index=True,
    )
    
    priority = models.CharField(
        max_length=10,
        choices=PRIORITY_CHOICES,
        default='medium',
    )
    
    # Completion tracking
    actual_completion_date = models.DateField(null=True, blank=True)
    is_completed = models.BooleanField(default=False)
    
    notes = models.TextField(blank=True, help_text='Internal notes or progress updates')
    
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    
    class Meta:
        ordering = ['due_date', '-priority']
        indexes = [
            models.Index(fields=['meeting', 'status']),
            models.Index(fields=['assigned_to', 'status']),
            models.Index(fields=['due_date', 'status']),
        ]
    
    def __str__(self):
        return f"{self.title} - {self.meeting.title}"
    
    def is_overdue(self):
        """Check if action item is overdue."""
        if self.status not in ['completed', 'cancelled']:
            return timezone.now().date() > self.due_date
        return False
    
    def mark_completed(self):
        """Mark action item as completed."""
        self.status = 'completed'
        self.actual_completion_date = timezone.now().date()
        self.is_completed = True
        self.save()


class MeetingAttachment(models.Model):
    """Supporting documents and files for a meeting."""
    
    FILE_TYPE_CHOICES = [
        ('agenda', 'Agenda'),
        ('handout', 'Handout'),
        ('presentation', 'Presentation'),
        ('minutes', 'Minutes'),
        ('report', 'Report'),
        ('spreadsheet', 'Spreadsheet'),
        ('other', 'Other'),
    ]
    
    meeting = models.ForeignKey(
        Meeting,
        on_delete=models.CASCADE,
        related_name='attachments',
    )
    
    title = models.CharField(max_length=255)
    file_type = models.CharField(
        max_length=20,
        choices=FILE_TYPE_CHOICES,
        default='other',
    )
    
    file = models.FileField(
        upload_to='meetings/',
        validators=[FileExtensionValidator(
            allowed_extensions=[
                'pdf', 'doc', 'docx', 'xls', 'xlsx', 'ppt', 'pptx',
                'txt', 'png', 'jpg', 'jpeg', 'gif', 'zip', 'csv'
            ]
        )],
    )
    
    uploaded_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
    )
    
    uploaded_at = models.DateTimeField(auto_now_add=True)
    description = models.TextField(blank=True)
    
    class Meta:
        ordering = ['-uploaded_at']
        verbose_name_plural = 'Meeting Attachments'
    
    def __str__(self):
        return f"{self.title} ({self.meeting.title})"
    
    def get_file_icon(self):
        """Return file type icon class for display."""
        ext = self.file.name.split('.')[-1].lower()
        icons = {
            'pdf': '📄',
            'doc': '📝',
            'docx': '📝',
            'xls': '📊',
            'xlsx': '📊',
            'ppt': '🎯',
            'pptx': '🎯',
            'txt': '📄',
            'jpg': '🖼️',
            'jpeg': '🖼️',
            'png': '🖼️',
            'gif': '🖼️',
            'zip': '📦',
            'csv': '📋',
        }
        return icons.get(ext, '📎')
