from django.urls import path

from . import views

app_name = 'procurement'

urlpatterns = [
    path('', views.dashboard, name='dashboard'),
    path('suppliers/', views.supplier_list, name='supplier_list'),
    path('suppliers/new/', views.supplier_create, name='supplier_create'),
    path('rfqs/', views.rfq_list, name='rfq_list'),
    path('rfqs/new/', views.rfq_create, name='rfq_create'),
    path('quotations/', views.quotation_list, name='quotation_list'),
    path('quotations/new/', views.quotation_create, name='quotation_create'),
    path('contracts/', views.contract_list, name='contract_list'),
    path('contracts/new/', views.contract_create, name='contract_create'),
    path('risks/', views.risk_list, name='risk_list'),
    path('risks/new/', views.risk_create, name='risk_create'),
    path('requisitions/', views.requisition_list, name='requisition_list'),
    path('requisitions/new/', views.requisition_create, name='requisition_create'),
    path('requisitions/<int:pk>/decide/', views.requisition_decide, name='requisition_decide'),
    path('requisitions/<int:pk>/submit/', views.requisition_submit, name='requisition_submit'),
    path('requisitions/<int:requisition_pk>/order/', views.purchase_order_create, name='purchase_order_create'),
    path('orders/', views.order_list, name='order_list'),
    path('orders/<int:pk>/approve/', views.order_approve, name='order_approve'),
    path('orders/<int:pk>/submit/', views.order_submit, name='order_submit'),
    path('orders/<int:order_pk>/receive/', views.goods_receipt_create, name='goods_receipt_create'),
    path('receipts/<int:receipt_pk>/inspection/', views.inspection_create, name='inspection_create'),
    path('invoice-matches/', views.invoice_match_list, name='invoice_match_list'),
    path('invoice-matches/new/', views.invoice_match_create, name='invoice_match_create'),
    path('invoice-matches/<int:pk>/approve/', views.invoice_match_approve, name='invoice_match_approve'),
    path('invoice-matches/<int:pk>/paid/', views.invoice_match_paid, name='invoice_match_paid'),
]
