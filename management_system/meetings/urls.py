"""
meetings/urls.py
"""

from django.urls import path
from . import views

app_name = 'meetings'

urlpatterns = [
    # Dashboard
    path('', views.meeting_dashboard, name='dashboard'),
    path('report/', views.meeting_report, name='report'),
    
    # Meeting management
    path('list/', views.meeting_list, name='meeting_list'),
    path('create/', views.meeting_create, name='meeting_create'),
    path('<int:pk>/', views.meeting_detail, name='meeting_detail'),
    path('<int:pk>/edit/', views.meeting_edit, name='meeting_edit'),
    path('<int:pk>/delete/', views.meeting_delete, name='meeting_delete'),
    
    # Meeting notes
    path('<int:meeting_pk>/notes/create/', views.meeting_notes_create, name='meeting_notes_create'),
    path('notes/<int:pk>/edit/', views.meeting_notes_edit, name='meeting_notes_edit'),
    path('notes/<int:pk>/view/', views.meeting_notes_view, name='meeting_notes_view'),
    
    # Action items
    path('<int:meeting_pk>/action/create/', views.action_item_create, name='action_item_create'),
    path('action/<int:pk>/edit/', views.action_item_edit, name='action_item_edit'),
    path('action/<int:pk>/delete/', views.action_item_delete, name='action_item_delete'),
    path('action/<int:pk>/toggle/', views.action_item_toggle_status, name='action_item_toggle'),
    path('action-item/<int:pk>/toggle-completion/', views.action_item_toggle_completion, name='action_item_toggle_completion'),
    
    # Attachments
    path('<int:meeting_pk>/attachment/upload/', views.attachment_upload, name='attachment_upload'),
    path('attachment/<int:pk>/view/', views.attachment_view, name='attachment_view'),
    path('attachment/<int:pk>/download/', views.attachment_download, name='attachment_download'),
    path('attachment/<int:pk>/delete/', views.attachment_delete, name='attachment_delete'),
]
