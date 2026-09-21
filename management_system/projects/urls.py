from django.urls import path
from . import views

app_name = 'projects'

urlpatterns = [
    # Project list and management
    path('', views.project_list, name='project_list'),
    path('create/', views.project_create, name='project_create'),
    path('<int:pk>/', views.project_detail, name='project_detail'),
    path('<int:pk>/edit/', views.project_edit, name='project_edit'),
    path('<int:pk>/delete/', views.project_delete, name='project_delete'),
    path('<int:pk>/update-progress/', views.update_project_progress, name='update_project_progress'),
    path('<int:pk>/update-status/', views.project_update_status, name='project_update_status'),
    
    # Sous-tâches (Subtasks)
    path('<int:project_id>/task/create/', views.sous_tache_create, name='sous_tache_create'),
    path('task/<int:pk>/edit/', views.sous_tache_edit, name='sous_tache_edit'),
    path('task/<int:pk>/delete/', views.sous_tache_delete, name='sous_tache_delete'),
    path('task/<int:pk>/change-status/', views.sous_tache_change_status, name='sous_tache_change_status'),
    path('task/<int:pk>/toggle-complete/', views.toggle_subtask_completion, name='toggle_subtask_completion'),
    path('task/<int:pk>/detail/', views.sous_tache_detail, name='sous_tache_detail'),
    
    # Comments
    path('task/<int:tache_id>/comment/', views.add_comment, name='add_comment'),
    path('comment/<int:pk>/delete/', views.delete_comment, name='delete_comment'),
    
    # Reports and exports
    path('export/', views.project_export, name='project_export'),
    path('reports/summary/', views.project_summary_report, name='project_summary_report'),
    path('reports/gantt/', views.project_gantt_chart, name='project_gantt_chart'),
    
    # Kanban board view
    path('kanban/', views.project_kanban, name='project_kanban'),
    
    # Calendar view
    path('calendar/', views.project_calendar, name='project_calendar'),
]