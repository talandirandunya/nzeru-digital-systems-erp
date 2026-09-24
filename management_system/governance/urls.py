from django.urls import path

from . import views

app_name = 'governance'

urlpatterns = [
    path('', views.admin_dashboard, name='admin_dashboard'),
    path('users/', views.user_list, name='user_list'),
    path('users/new/', views.user_create, name='user_create'),
    path('users/<int:pk>/edit/', views.user_edit, name='user_edit'),
    path('users/<int:pk>/toggle-active/', views.user_toggle_active, name='user_toggle_active'),
    path('users/<int:pk>/capabilities/', views.user_capabilities, name='user_capabilities'),
    path('approval-authority/<int:pk>/delete/', views.user_approval_authority_delete, name='user_approval_authority_delete'),
    path('audit/', views.audit_list, name='audit_list'),
    path('reports/', views.reporting_dashboard, name='reporting_dashboard'),
    path('reports/export/', views.reporting_export, name='reporting_export'),
    path('workflows/', views.workflow_list, name='workflow_list'),
    path('workflows/new/', views.workflow_create, name='workflow_create'),
    path('workflows/<int:pk>/', views.workflow_detail, name='workflow_detail'),
    path('workflows/<int:pk>/edit/', views.workflow_edit, name='workflow_edit'),
    path('workflow-steps/<int:pk>/edit/', views.workflow_step_edit, name='workflow_step_edit'),
    path('workflow-steps/<int:pk>/delete/', views.workflow_step_delete, name='workflow_step_delete'),
    path('approvals/<int:pk>/decide/', views.approval_decide, name='approval_decide'),
    path('approvals/<int:pk>/cancel/', views.approval_cancel, name='approval_cancel'),
    path('approvals/<int:pk>/', views.approval_detail, name='approval_detail'),
    path('my-work/', views.my_work, name='my_work'),
]
