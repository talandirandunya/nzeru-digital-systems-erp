from django.urls import path
from . import views

app_name = 'employees'

urlpatterns = [
    # Employee list and management
    path('', views.employee_list, name='employee_list'),
    path('create/', views.employee_create, name='employee_create'),
    path('new/', views.employee_create, name='employee_new'),
    path('<int:pk>/', views.employee_detail, name='employee_detail'),
    path('<int:pk>/edit/', views.employee_edit, name='employee_edit'),
    path('<int:pk>/delete/', views.employee_delete, name='employee_delete'),
    
    # Department management
    path('departments/', views.department_list, name='department_list'),
    path('departments/create/', views.department_create, name='department_create'),
    path('departments/<int:pk>/edit/', views.department_edit, name='department_edit'),
    path('departments/<int:pk>/delete/', views.department_delete, name='department_delete'),
    
    # Bulk operations
    path('export/', views.employee_export, name='employee_export'),
    path('import/', views.employee_import, name='employee_import'),
    path('download-template/', views.download_employee_template, name='download_employee_template'),
    
    # Reports
    path('reports/summary/', views.employee_summary_report, name='employee_summary_report'),
    path('reports/department/', views.department_report, name='department_report'),
]