from django.urls import path
from . import views

app_name = 'inventory'

urlpatterns = [
    # Stock list and management
    path('', views.stock_list, name='stock_list'),
    path('create/', views.stock_create, name='stock_create'),
    path('<int:pk>/', views.stock_detail, name='stock_detail'),
    path('<int:pk>/edit/', views.stock_edit, name='stock_edit'),
    path('<int:pk>/delete/', views.stock_delete, name='stock_delete'),
    
    # Stock transactions
    path('<int:pk>/transaction/', views.stock_transaction, name='stock_transaction'),
    path('transactions/', views.stock_transaction_journal, name='stock_transaction_journal'),
    path('transactions/export/', views.stock_transaction_export, name='stock_transaction_export'),
    
    # Bulk operations
    path('import/', views.stock_import, name='stock_import'),
    path('export/', views.stock_export, name='stock_export'),
    path('download-template/', views.stock_download_template, name='stock_download_template'),
    path('bulk-remove/', views.stock_bulk_remove, name='stock_bulk_remove'),
    path('download-removal-template/', views.stock_download_removal_template, name='stock_download_removal_template'),
    
    # Category management
    path('categories/', views.category_list, name='category_list'),
    path('categories/create/', views.category_create, name='category_create'),
    path('categories/<int:pk>/edit/', views.category_edit, name='category_edit'),
    path('categories/<int:pk>/delete/', views.category_delete, name='category_delete'),
    
    # Reports
    path('reports/low-stock/', views.low_stock_report, name='low_stock_report'),
    path('reports/valuation/', views.stock_valuation_report, name='stock_valuation_report'),
    path('reports/movement/', views.stock_movement_report, name='stock_movement_report'),
    
    # Dashboard
    path('dashboard/', views.inventory_dashboard, name='inventory_dashboard'),
]