from django.urls import path

from . import views

app_name = 'procurement'

urlpatterns = [
    path('suppliers/', views.supplier_list, name='supplier_list'),
    path('suppliers/new/', views.supplier_create, name='supplier_create'),
    path('requisitions/', views.requisition_list, name='requisition_list'),
    path('requisitions/new/', views.requisition_create, name='requisition_create'),
    path('requisitions/<int:pk>/decide/', views.requisition_decide, name='requisition_decide'),
    path('requisitions/<int:pk>/submit/', views.requisition_submit, name='requisition_submit'),
    path('requisitions/<int:requisition_pk>/order/', views.purchase_order_create, name='purchase_order_create'),
    path('orders/', views.order_list, name='order_list'),
    path('orders/<int:pk>/approve/', views.order_approve, name='order_approve'),
    path('orders/<int:pk>/submit/', views.order_submit, name='order_submit'),
    path('orders/<int:order_pk>/receive/', views.goods_receipt_create, name='goods_receipt_create'),
]
