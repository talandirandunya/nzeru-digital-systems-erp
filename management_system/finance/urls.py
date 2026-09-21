from django.urls import path
from . import views

app_name = 'finance'

urlpatterns = [
    path('', views.index, name='index'),

    # Accounts
    path('accounts/', views.account_list, name='account_list'),
    path('accounts/new/', views.account_create, name='account_create'),
    path('accounts/<int:pk>/', views.account_detail, name='account_detail'),
    path('accounts/<int:pk>/edit/', views.account_edit, name='account_edit'),
    path('accounts/<int:pk>/delete/', views.account_delete, name='account_delete'),

    # Transactions
    path('transactions/', views.transaction_list, name='transaction_list'),
    path('transactions/new/', views.transaction_create, name='transaction_create'),
    path('transactions/<int:pk>/edit/', views.transaction_edit, name='transaction_edit'),
    path('transactions/<int:pk>/delete/', views.transaction_delete, name='transaction_delete'),

    # Journals
    path('journals/', views.journal_list, name='journal_list'),
    path('journals/new/', views.journal_create, name='journal_create'),
    path('journals/<int:pk>/', views.journal_detail, name='journal_detail'),
    path('journals/<int:pk>/edit/', views.journal_edit, name='journal_edit'),
    path('journals/<int:pk>/delete/', views.journal_delete, name='journal_delete'),

    # Journal entries
    path('journal-entries/', views.journal_entry_list, name='journal_entry_list'),
    path('journal-entries/new/', views.journal_entry_create, name='journal_entry_create'),
    path('journal-entries/<int:pk>/', views.journal_entry_detail, name='journal_entry_detail'),
    path('journal-entries/<int:pk>/edit/', views.journal_entry_edit, name='journal_entry_edit'),
    path('journal-entries/<int:pk>/delete/', views.journal_entry_delete, name='journal_entry_delete'),

    # Client invoices
    path('client-invoices/', views.client_invoice_list, name='client_invoice_list'),
    path('client-invoices/new/', views.client_invoice_create, name='client_invoice_create'),
    path('client-invoices/<int:pk>/', views.client_invoice_detail, name='client_invoice_detail'),
    path('client-invoices/<int:pk>/edit/', views.client_invoice_edit, name='client_invoice_edit'),
    path('client-invoices/<int:pk>/delete/', views.client_invoice_delete, name='client_invoice_delete'),
    path('client-invoices/<int:pk>/print/', views.client_invoice_print, name='client_invoice_print'),

    # Supplier invoices
    path('supplier-invoices/', views.supplier_invoice_list, name='supplier_invoice_list'),
    path('supplier-invoices/new/', views.supplier_invoice_create, name='supplier_invoice_create'),
    path('supplier-invoices/<int:pk>/', views.supplier_invoice_detail, name='supplier_invoice_detail'),
    path('supplier-invoices/<int:pk>/edit/', views.supplier_invoice_edit, name='supplier_invoice_edit'),
    path('supplier-invoices/<int:pk>/delete/', views.supplier_invoice_delete, name='supplier_invoice_delete'),

    # Bank accounts
    path('bank-accounts/', views.bank_account_list, name='bank_account_list'),
    path('bank-accounts/new/', views.bank_account_create, name='bank_account_create'),
    path('bank-accounts/<int:pk>/edit/', views.bank_account_edit, name='bank_account_edit'),
    path('bank-accounts/<int:pk>/delete/', views.bank_account_delete, name='bank_account_delete'),

    # Bank statements
    path('bank-statements/upload/', views.bank_statement_upload, name='bank_statement_upload'),

    # Bank reconciliations
    path('reconciliations/', views.bank_reconciliation_list, name='bank_reconciliation_list'),
    path('reconciliations/new/', views.bank_reconciliation_create, name='bank_reconciliation_create'),
    path('reconciliations/<int:pk>/', views.bank_reconciliation_detail, name='bank_reconciliation_detail'),

    # Financial reports
    path('reports/', views.financial_report_list, name='financial_report_list'),
    path('reports/generate/', views.financial_report_generate, name='financial_report_generate'),
    path('reports/<int:pk>/', views.financial_report_detail, name='financial_report_detail'),

    # Marketplace finance integration
    path('marketplace-settings/', views.marketplace_finance_settings_edit, name='marketplace_finance_settings'),
]
