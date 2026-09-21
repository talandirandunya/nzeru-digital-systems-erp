from django.urls import path
from . import views
from . import admin_views  # Import the admin views

app_name = 'marketplace'

urlpatterns = [
    # Client Auth
    path('', views.client_login, name='client_login'),
    path('login/', views.client_login, name='client_login'),
    path('register/', views.client_register, name='client_register'),
    path('logout/', views.client_logout, name='client_logout'),
    
    # Client Shop
    path('shop/', views.shop, name='shop'),
    path('shop/<int:pk>/', views.product_detail, name='product_detail'),
    path('shop/category/<int:category_id>/', views.shop_by_category, name='shop_by_category'),
    
    # Client Cart
    path('cart/', views.view_cart, name='view_cart'),
    path('cart/add/<int:stock_id>/', views.add_to_cart, name='add_to_cart'),
    path('cart/update/<int:item_id>/', views.update_cart_item, name='update_cart_item'),
    path('cart/remove/<int:item_id>/', views.remove_from_cart, name='remove_from_cart'),
    path('cart/clear/', views.clear_cart, name='clear_cart'),
    
    # Client Wishlist
    path('wishlist/', views.view_wishlist, name='view_wishlist'),
    path('wishlist/add/<int:stock_id>/', views.add_to_wishlist, name='add_to_wishlist'),
    path('wishlist/remove/<int:item_id>/', views.remove_from_wishlist, name='remove_from_wishlist'),
    
    # Client Checkout & Orders
    path('checkout/', views.checkout, name='checkout'),
    path('orders/', views.order_list, name='order_list'),
    path('orders/<int:pk>/', views.order_detail, name='order_detail'),
    path('orders/<int:pk>/cancel/', views.cancel_order, name='cancel_order'),
    path('orders/<int:pk>/pay/', views.payment_gateway, name='payment_gateway'),
    path('orders/<int:pk>/print/', views.order_print, name='order_print'),
    path('orders/<int:pk>/pdf/', views.order_pdf, name='order_pdf'),
    path('orders/<int:order_id>/return/', views.request_return, name='request_return'),
    path('product/<int:stock_id>/review/', views.add_product_review, name='add_product_review'),
    
    # Client Profile
    path('profile/', views.client_profile, name='client_profile'),
    path('profile/edit/', views.edit_client_profile, name='edit_client_profile'),
    
    # ========== COMPANY ADMIN ORDER MANAGEMENT ==========
    path('admin/orders/', admin_views.admin_order_dashboard, name='admin_order_dashboard'),
    path('admin/orders/quick-create/', admin_views.admin_order_quick_create, name='admin_order_quick_create'),
    path('admin/orders/list/', admin_views.admin_order_list, name='admin_order_list'),
    path('admin/orders/<int:pk>/', admin_views.admin_order_detail, name='admin_order_detail'),
    path('admin/orders/<int:pk>/confirm/', admin_views.admin_order_confirm, name='admin_order_confirm'),
    path('admin/orders/<int:pk>/ship/', admin_views.admin_order_ship, name='admin_order_ship'),
    path('admin/orders/<int:pk>/deliver/', admin_views.admin_order_deliver, name='admin_order_deliver'),
    path('admin/orders/<int:pk>/cancel/', admin_views.admin_order_cancel, name='admin_order_cancel'),
    path('admin/orders/<int:pk>/payment/', admin_views.admin_order_update_payment, name='admin_order_update_payment'),
    path('admin/orders/<int:pk>/pdf/', views.admin_order_pdf, name='admin_order_pdf'),
    path('admin/clients/', admin_views.admin_client_list, name='admin_client_list'),
]