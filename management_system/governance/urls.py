from django.urls import path

from . import views

app_name = 'governance'

urlpatterns = [
    path('users/', views.user_list, name='user_list'),
    path('users/new/', views.user_create, name='user_create'),
    path('users/<int:pk>/edit/', views.user_edit, name='user_edit'),
    path('users/<int:pk>/toggle-active/', views.user_toggle_active, name='user_toggle_active'),
    path('users/<int:pk>/capabilities/', views.user_capabilities, name='user_capabilities'),
    path('approval-authority/<int:pk>/delete/', views.user_approval_authority_delete, name='user_approval_authority_delete'),
    path('audit/', views.audit_list, name='audit_list'),
    path('workflows/', views.workflow_list, name='workflow_list'),
    path('workflows/new/', views.workflow_create, name='workflow_create'),
    path('workflows/<int:pk>/', views.workflow_detail, name='workflow_detail'),
    path('approvals/<int:pk>/decide/', views.approval_decide, name='approval_decide'),
    path('approvals/<int:pk>/', views.approval_detail, name='approval_detail'),
    path('my-work/', views.my_work, name='my_work'),
]
