"""
meetings/admin.py

Django admin configuration for meeting models.
"""

from django.contrib import admin
from .models import Meeting, MeetingNote, ActionItem, MeetingAttachment


@admin.register(Meeting)
class MeetingAdmin(admin.ModelAdmin):
    list_display = ('title', 'scheduled_date', 'meeting_type', 'status', 'organizer', 'company')
    list_filter = ('status', 'meeting_type', 'priority', 'scheduled_date', 'company')
    search_fields = ('title', 'description', 'location')
    readonly_fields = ('created_by', 'created_at', 'updated_at')
    
    fieldsets = (
        ('Basic Info', {
            'fields': ('title', 'description', 'meeting_type', 'company')
        }),
        ('Schedule', {
            'fields': ('scheduled_date', 'actual_start', 'actual_end', 'location')
        }),
        ('Participants', {
            'fields': ('organizer', 'attendees')
        }),
        ('Status', {
            'fields': ('status', 'priority')
        }),
        ('Audit', {
            'fields': ('created_by', 'created_at', 'updated_at'),
            'classes': ('collapse',)
        }),
    )
    
    filter_horizontal = ('attendees',)
    
    def save_model(self, request, obj, form, change):
        if not change:
            obj.created_by = request.user
        super().save_model(request, obj, form, change)


@admin.register(MeetingNote)
class MeetingNoteAdmin(admin.ModelAdmin):
    list_display = ('meeting', 'created_at', 'last_edited_by')
    list_filter = ('created_at', 'updated_at')
    search_fields = ('meeting__title', 'discussion_summary')
    readonly_fields = ('created_at', 'updated_at')
    
    fieldsets = (
        ('Meeting', {
            'fields': ('meeting',)
        }),
        ('Content', {
            'fields': (
                'agenda', 'discussion_summary', 'decisions_made',
                'risks_identified', 'next_steps'
            )
        }),
        ('Documents', {
            'fields': ('report_document',)
        }),
        ('Audit', {
            'fields': ('created_at', 'updated_at', 'last_edited_by'),
            'classes': ('collapse',)
        }),
    )


@admin.register(ActionItem)
class ActionItemAdmin(admin.ModelAdmin):
    list_display = ('title', 'meeting', 'assigned_to', 'due_date', 'status', 'priority')
    list_filter = ('status', 'priority', 'due_date', 'created_at')
    search_fields = ('title', 'description', 'meeting__title')
    readonly_fields = ('created_at', 'updated_at')
    
    fieldsets = (
        ('Basic Info', {
            'fields': ('meeting', 'title', 'description')
        }),
        ('Assignment', {
            'fields': ('assigned_to',)
        }),
        ('Timeline', {
            'fields': ('due_date', 'actual_completion_date')
        }),
        ('Status', {
            'fields': ('status', 'priority', 'completion_percentage')
        }),
        ('Notes', {
            'fields': ('notes',)
        }),
        ('Audit', {
            'fields': ('created_at', 'updated_at'),
            'classes': ('collapse',)
        }),
    )
    
    list_editable = ('status', 'priority')


@admin.register(MeetingAttachment)
class MeetingAttachmentAdmin(admin.ModelAdmin):
    list_display = ('title', 'meeting', 'file_type', 'uploaded_by', 'uploaded_at')
    list_filter = ('file_type', 'uploaded_at')
    search_fields = ('title', 'meeting__title', 'description')
    readonly_fields = ('uploaded_at', 'uploaded_by')
    
    fieldsets = (
        ('File Info', {
            'fields': ('meeting', 'title', 'file_type', 'file')
        }),
        ('Description', {
            'fields': ('description',)
        }),
        ('Audit', {
            'fields': ('uploaded_by', 'uploaded_at'),
            'classes': ('collapse',)
        }),
    )
    
    def save_model(self, request, obj, form, change):
        if not change:
            obj.uploaded_by = request.user
        super().save_model(request, obj, form, change)
