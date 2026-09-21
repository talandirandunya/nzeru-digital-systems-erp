import os
import io
from reportlab.lib.pagesizes import letter
from reportlab.pdfgen import canvas
from django.http import HttpResponse
from django.shortcuts import render, redirect, get_object_or_404
from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.views.decorators.http import require_http_methods
from django.urls import reverse
from django.db.models import Q, F,Count, Sum
from django.db import transaction as db_transaction
from django.utils import timezone
from functools import wraps

from .models import Client, Cart, CartItem, Order, OrderItem, Wishlist, WishlistItem, ProductReview, ReturnRequest, CompanyPaymentSettings
from .forms import ClientRegistrationForm, ClientLoginForm, ClientProfileForm, CheckoutForm, AddToCartForm
from inventory.models import Stock, StockCategory, StockTransaction
from accounts.models import Company
from .services import reverse_order_payment_in_finance, post_order_payment_to_finance, MarketplaceFinancePostingError


def get_cart_company(cart):
    """Return the single company represented in a cart, if any."""
    first_item = cart.items.select_related('stock__company').first()
    return first_item.stock.company if first_item else None


# Client Authentication Decorator
def client_login_required(view_func):
    """Decorator to require client login"""
    @wraps(view_func)
    def wrapper(request, *args, **kwargs):
        if 'client_id' not in request.session:
            messages.warning(request, 'Please login to continue.')
            return redirect('marketplace:client_login')
        
        try:
            client = Client.objects.get(id=request.session['client_id'], is_active=True)
            request.client = client
        except Client.DoesNotExist:
            del request.session['client_id']
            messages.error(request, 'Session expired. Please login again.')
            return redirect('marketplace:client_login')
        
        return view_func(request, *args, **kwargs)
    return wrapper


# Authentication Views
def client_login(request):
    """Client login view"""
    if 'client_id' in request.session:
        return redirect('marketplace:shop')

    if request.method == 'POST':
        form = ClientLoginForm(request.POST)
        if form.is_valid():
            client = form.cleaned_data['client']
            request.session['client_id'] = client.id
            messages.success(request, f'Welcome back, {client.first_name}!')
            return redirect('marketplace:shop')
    else:
        form = ClientLoginForm()
    
    return render(request, 'marketplace/client_login.html', {
        'form': form,
        'title': 'Client Login',
    })


def client_register(request):
    """Client registration view"""
    if 'client_id' in request.session:
        return redirect('marketplace:shop')

    if request.method == 'POST':
        form = ClientRegistrationForm(request.POST)
        if form.is_valid():
            client = form.save()
            messages.success(request, f'Account created successfully! Welcome, {client.first_name}!')
            # Auto-login after registration
            request.session['client_id'] = client.id
            return redirect('marketplace:shop')
    else:
        form = ClientRegistrationForm()
    
    return render(request, 'marketplace/client_register.html', {
        'form': form,
        'title': 'Create Account',
    })


@client_login_required
def client_logout(request):
    """Client logout view"""
    if 'client_id' in request.session:
        del request.session['client_id']
    if 'client_company_id' in request.session:
        del request.session['client_company_id']
    
    messages.success(request, 'You have been logged out successfully.')
    return redirect('marketplace:client_login')


# Shop Views
def shop(request):
    """Main shop view - display available products (public view, login required for checkout)"""
    client = None
    company = None

    # determine company selection from GET param
    domain_param = request.GET.get('company')
    if domain_param:
        try:
            company = Company.objects.get(domain=domain_param, is_active=True)
            request.session['marketplace_company'] = domain_param
        except Company.DoesNotExist:
            messages.error(request, 'Selected shop does not exist.')

    # Get client if logged in
    if 'client_id' in request.session:
        try:
            client = Client.objects.get(id=request.session['client_id'], is_active=True)
            request.client = client
        except Client.DoesNotExist:
            del request.session['client_id']

    # if no explicit company yet, look in session
    if not company and 'marketplace_company' in request.session:
        try:
            company = Company.objects.get(domain=request.session['marketplace_company'], is_active=True)
        except Company.DoesNotExist:
            del request.session['marketplace_company']
            company = None

    # Get all active companies for the dropdown menu
    all_companies = Company.objects.filter(is_active=True).order_by('name')
    
    # fallback to first company with stock if no company selected
    companies_with_stock = Company.objects.filter(
        stocks__quantity__gt=0
    ).distinct().order_by('name')
    if not company and companies_with_stock.exists():
        company = companies_with_stock.first()
    
    # If still no company but companies exist, use first active company
    if not company and all_companies.exists():
        company = all_companies.first()

    if not company:
        messages.info(request, 'No shops available currently.')
        return render(request, 'marketplace/shop.html', {'stocks': [], 'is_logged_in': False, 'companies': all_companies})
    
    # Get available stock items from this company
    stocks = Stock.objects.filter(
        company=company,
        quantity__gt=0,
        is_marketplace_visible=True
    ).select_related('category').order_by('-created_at')
    
    # Apply search
    query = request.GET.get('q', '').strip()
    if query:
        stocks = stocks.filter(
            Q(name__icontains=query) |
            Q(description__icontains=query) |
            Q(item_code__icontains=query)
        )
    
    # Apply category filter
    category_id = request.GET.get('category')
    if category_id:
        stocks = stocks.filter(category_id=category_id)
    
    # Get categories for filter
    categories = StockCategory.objects.filter(company=company).order_by('name')
    
    # Get cart count if logged in
    cart_count = 0
    if client:
        cart = Cart.objects.filter(client=client).first()
        cart_count = cart.total_items if cart else 0
    
    context = {
        'stocks': stocks,
        'categories': categories,
        'company': company,
        'query': query,
        'selected_category': category_id,
        'cart_count': cart_count,
        'is_logged_in': client is not None,
    }
    
    return render(request, 'marketplace/shop.html', context)


def product_detail(request, pk):
    """Product detail view (public view, login required for add to cart)"""
    client = None
    
    # Get client if logged in
    if 'client_id' in request.session:
        try:
            client = Client.objects.get(id=request.session['client_id'], is_active=True)
            request.client = client
        except Client.DoesNotExist:
            del request.session['client_id']
    
    stock = get_object_or_404(Stock, pk=pk, is_marketplace_visible=True)
    
    # Check if in wishlist (only if logged in)
    in_wishlist = False
    if client:
        wishlist = Wishlist.objects.filter(client=client).first()
        if wishlist:
            in_wishlist = WishlistItem.objects.filter(wishlist=wishlist, stock=stock).exists()
    
    # Check if client can purchase this product (clients can buy from any company now)
    can_purchase = client is not None
    
    context = {
        'stock': stock,
        'in_wishlist': in_wishlist,
        'is_logged_in': client is not None,
        'can_purchase': can_purchase,
    }
    
    return render(request, 'marketplace/product_detail.html', context)


@client_login_required
def shop_by_category(request, category_id):
    """Filter products by category"""
    return redirect('marketplace:shop' + f'?category={category_id}')


# Cart Views
@client_login_required
def view_cart(request):
    """View shopping cart"""
    client = request.client
    cart, created = Cart.objects.get_or_create(client=client)
    cart_items = cart.items.all().select_related('stock')
    
    context = {
        'cart': cart,
        'cart_items': cart_items,
    }
    
    return render(request, 'marketplace/cart.html', context)


@client_login_required
def add_to_cart(request, stock_id):
    """Add item to cart"""
    client = request.client
    stock = get_object_or_404(Stock, pk=stock_id, is_marketplace_visible=True)
    
    if request.method == 'POST':
        quantity = int(request.POST.get('quantity', 1))
        
        # Check stock availability
        if stock.quantity < quantity:
            messages.error(request, f'Only {stock.quantity} units available.')
            return redirect('marketplace:product_detail', pk=stock_id)
        
        cart, created = Cart.objects.get_or_create(client=client)
        cart_company = get_cart_company(cart)
        if cart_company and cart_company.id != stock.company_id:
            messages.error(
                request,
                f'Your cart already contains items from {cart_company.name}. '
                'Please clear the cart before adding products from another company.'
            )
            return redirect('marketplace:view_cart')
        
        # Check if item already in cart
        cart_item, created = CartItem.objects.get_or_create(
            cart=cart,
            stock=stock,
            defaults={'quantity': quantity}
        )
        
        if not created:
            # Update quantity
            new_quantity = cart_item.quantity + quantity
            if new_quantity > stock.quantity:
                messages.error(request, f'Only {stock.quantity} units available.')
                return redirect('marketplace:view_cart')
            cart_item.quantity = new_quantity
            cart_item.save()
            messages.success(request, f'Updated {stock.name} quantity to {new_quantity}')
        else:
            messages.success(request, f'Added {stock.name} to cart')
        
        return redirect('marketplace:view_cart')
    
    return redirect('marketplace:shop')


@client_login_required
def update_cart_item(request, item_id):
    """Update cart item quantity"""
    client = request.client
    cart_item = get_object_or_404(CartItem, pk=item_id, cart__client=client)
    
    if request.method == 'POST':
        quantity = int(request.POST.get('quantity', 1))
        
        if quantity <= 0:
            cart_item.delete()
            messages.success(request, 'Item removed from cart')
        elif quantity > cart_item.stock.quantity:
            messages.error(request, f'Only {cart_item.stock.quantity} units available')
        else:
            cart_item.quantity = quantity
            cart_item.save()
            messages.success(request, 'Cart updated')
    
    return redirect('marketplace:view_cart')


@client_login_required
def remove_from_cart(request, item_id):
    """Remove item from cart"""
    client = request.client
    cart_item = get_object_or_404(CartItem, pk=item_id, cart__client=client)
    
    if request.method == 'POST':
        item_name = cart_item.stock.name
        cart_item.delete()
        messages.success(request, f'Removed {item_name} from cart')
    
    return redirect('marketplace:view_cart')


@client_login_required
def clear_cart(request):
    """Clear all items from cart"""
    client = request.client
    
    if request.method == 'POST':
        cart = Cart.objects.filter(client=client).first()
        if cart:
            cart.items.all().delete()
            messages.success(request, 'Cart cleared')
    
    return redirect('marketplace:view_cart')


# Wishlist Views
@client_login_required
def view_wishlist(request):
    """View wishlist"""
    client = request.client
    wishlist, created = Wishlist.objects.get_or_create(client=client)
    items = wishlist.items.all().select_related('stock')
    
    context = {
        'wishlist': wishlist,
        'items': items,
    }
    
    return render(request, 'marketplace/wishlist.html', context)


@client_login_required
def add_to_wishlist(request, stock_id):
    """Add item to wishlist"""
    client = request.client
    stock = get_object_or_404(Stock, pk=stock_id, is_marketplace_visible=True)
    
    if request.method == 'POST':
        wishlist, created = Wishlist.objects.get_or_create(client=client)
        
        item, created = WishlistItem.objects.get_or_create(
            wishlist=wishlist,
            stock=stock
        )
        
        if created:
            messages.success(request, f'Added {stock.name} to wishlist')
        else:
            messages.info(request, f'{stock.name} is already in your wishlist')
        
        return redirect(request.META.get('HTTP_REFERER', 'marketplace:shop'))
    
    return redirect('marketplace:shop')


@client_login_required
def remove_from_wishlist(request, item_id):
    """Remove item from wishlist"""
    client = request.client
    item = get_object_or_404(WishlistItem, pk=item_id, wishlist__client=client)
    
    if request.method == 'POST':
        item_name = item.stock.name
        item.delete()
        messages.success(request, f'Removed {item_name} from wishlist')
    
    return redirect('marketplace:view_wishlist')


# Checkout & Orders
@client_login_required
def checkout(request):
    """Checkout process"""
    client = request.client
    cart = Cart.objects.filter(client=client).first()
    
    if not cart or not cart.items.exists():
        messages.warning(request, 'Your cart is empty')
        return redirect('marketplace:shop')

    cart_company = get_cart_company(cart)
    if not cart_company:
        messages.error(request, 'Unable to determine the company for this cart.')
        return redirect('marketplace:view_cart')

    mixed_company_items = cart.items.exclude(stock__company=cart_company)
    if mixed_company_items.exists():
        messages.error(
            request,
            'Your cart contains products from multiple companies. '
            'Please keep one company per order.'
        )
        return redirect('marketplace:view_cart')
    
    if request.method == 'POST':
        form = CheckoutForm(request.POST)
        if form.is_valid():
            try:
                with db_transaction.atomic():
                    # Create order
                    order = form.save(commit=False)
                    order.client = client
                    order.company = cart_company
                    order.subtotal = cart.total_price
                    order.tax = 0  # Add tax calculation if needed
                    order.shipping = 0  # Add shipping calculation if needed
                    order.total = order.subtotal + order.tax + order.shipping
                    order.order_number = f"ORD-{timezone.now().strftime('%Y%m%d%H%M%S')}-{client.id}"
                    order.save()
                    
                    # Create order items and update stock
                    for cart_item in cart.items.select_related('stock', 'stock__company'):
                        # Check stock availability again
                        if cart_item.stock.quantity < cart_item.quantity:
                            raise Exception(f'Insufficient stock for {cart_item.stock.name}')
                        
                        # Create order item
                        OrderItem.objects.create(
                            order=order,
                            stock=cart_item.stock,
                            item_name=cart_item.stock.name,
                            item_code=cart_item.stock.item_code,
                            quantity=cart_item.quantity,
                            unit_price=cart_item.stock.selling_price,
                            subtotal=cart_item.subtotal
                        )
                        
                        # Update stock quantity
                        stock = cart_item.stock
                        stock.quantity = F('quantity') - cart_item.quantity
                        stock.save()
                        
                        # Create stock transaction
                        StockTransaction.objects.create(
                            company=stock.company,
                            stock=stock,
                            transaction_type='out',
                            quantity=cart_item.quantity,
                            remarks=f'Order #{order.order_number} by {client.get_full_name()}',
                            user=None  # No user for client orders
                        )
                    
                    # Clear cart
                    cart.items.all().delete()
                    
                    # Notify company users of new order
                    try:
                        from notifications.utils import notify_users
                        from django.contrib.auth import get_user_model
                        UserModel = get_user_model()
                        company_users = UserModel.objects.filter(company=order.company, is_active=True)
                        notify_users(
                            users=company_users,
                            notification_type='system',
                            title=f"New Order #{order.order_number}",
                            message=f"New order #{order.order_number} (FCFA {order.total:,.0f}) placed by {client.get_full_name()}.",
                            related_object=order
                        )
                    except Exception as notif_err:
                        pass
                    
                    messages.success(request, f'Order placed successfully! Order number: {order.order_number}. Please proceed with payment.')
                    return redirect('marketplace:payment_gateway', pk=order.pk)
                    
            except Exception as e:
                messages.error(request, f'Error processing order: {str(e)}')
                return redirect('marketplace:checkout')
    else:
        # Pre-fill with client info
        form = CheckoutForm(initial={
            'shipping_address': client.address,
            'shipping_city': client.city,
            'shipping_country': client.country,
            'shipping_phone': client.phone,
        })
    
    context = {
        'form': form,
        'cart': cart,
    }
    
    return render(request, 'marketplace/checkout.html', context)


@client_login_required
def order_list(request):
    """List all client orders"""
    client = request.client
    orders = Order.objects.filter(client=client).order_by('-created_at')
    
    # Get order statistics
    total_orders = orders.count()
    pending_orders = orders.filter(status='pending').count()
    confirmed_orders = orders.filter(status='confirmed').count()
    shipped_orders = orders.filter(status='shipped').count()
    delivered_orders = orders.filter(status='delivered').count()
    
    # Recent orders (last 5)
    recent_orders = orders[:5]
    
    context = {
        'orders': orders,
        'total_orders': total_orders,
        'pending_orders': pending_orders,
        'confirmed_orders': confirmed_orders,
        'shipped_orders': shipped_orders,
        'delivered_orders': delivered_orders,
        'recent_orders': recent_orders,
    }
    
    return render(request, 'marketplace/order_list.html', context)


@client_login_required
def order_detail(request, pk):
    """View order details"""
    client = request.client
    order = get_object_or_404(Order, pk=pk, client=client)
    
    context = {
        'order': order,
    }
    
    return render(request, 'marketplace/order_detail.html', context)


@client_login_required
def cancel_order(request, pk):
    """Cancel an order"""
    client = request.client
    order = get_object_or_404(Order, pk=pk, client=client)
    
    if order.status != 'pending':
        messages.error(request, 'This order cannot be cancelled')
        return redirect('marketplace:order_detail', pk=pk)
    
    if request.method == 'POST':
        try:
            with db_transaction.atomic():
                restored_items = 0
                for item in order.items.select_related('stock'):
                    stock = item.stock
                    stock.quantity = F('quantity') + item.quantity
                    stock.save()

                    StockTransaction.objects.create(
                        company=stock.company,
                        stock=stock,
                        transaction_type='in',
                        quantity=item.quantity,
                        remarks=f'Order #{order.order_number} cancelled by customer - stock restored',
                        user=None,
                    )
                    restored_items += 1

                if restored_items > 0 and order.payment_status == 'paid' and order.finance_journal_entry_id:
                    reverse_order_payment_in_finance(
                        order,
                        user=None,
                        reason='order cancelled by customer',
                    )
                    order.payment_status = 'refunded'

                order.status = 'cancelled'
                order.save(update_fields=['status', 'payment_status', 'updated_at'])
                messages.success(request, 'Order cancelled successfully')
        except Exception as exc:
            messages.error(request, f'Unable to cancel this order: {exc}')
        return redirect('marketplace:order_detail', pk=pk)
    
    return redirect('marketplace:order_detail', pk=pk)


# Profile Views
@client_login_required
def client_profile(request):
    """View client profile"""
    client = request.client
    
    # Get order statistics
    total_orders = Order.objects.filter(client=client).count()
    pending_orders = Order.objects.filter(client=client, status='pending').count()
    
    context = {
        'client': client,
        'total_orders': total_orders,
        'pending_orders': pending_orders,
    }
    
    return render(request, 'marketplace/client_profile.html', context)


@client_login_required
def edit_client_profile(request):
    """Edit client profile"""
    client = request.client
    
    if request.method == 'POST':
        form = ClientProfileForm(request.POST, instance=client)
        if form.is_valid():
            form.save()
            messages.success(request, 'Profile updated successfully!')
            return redirect('marketplace:client_profile')
    else:
        form = ClientProfileForm(instance=client)
    
    context = {
        'form': form,
    }
    
    return render(request, 'marketplace/edit_client_profile.html', context)


@client_login_required
@require_http_methods(['GET', 'POST'])
def payment_gateway(request, pk):
    """Direct Merchant Payment Contact Gateway for Marketplace Orders."""
    client = request.client
    order = get_object_or_404(Order, pk=pk, client=client)

    if order.payment_status == 'paid':
        messages.warning(request, 'This order is already marked as paid.')
        return redirect('marketplace:order_list')

    payment_settings = CompanyPaymentSettings.objects.filter(company=order.company).first()

    if request.method == 'POST':
        messages.success(
            request,
            f'Thank you! Your payment notification for Order #{order.order_number} has been recorded. '
            'The merchant will verify your payment and update your order.'
        )
        return redirect('marketplace:order_list')

    return render(request, 'marketplace/payment_gateway.html', {
        'order': order,
        'client': client,
        'payment_settings': payment_settings,
    })


@client_login_required
def order_print(request, pk):
    """Render a print-ready B2C invoice receipt for a marketplace order."""
    client = request.client
    order = get_object_or_404(Order, pk=pk, client=client)
    items = order.items.all()
    return render(request, 'marketplace/order_print.html', {
        'order': order,
        'items': items,
        'company': order.company,
    })


@client_login_required
@require_http_methods(['POST'])
def add_product_review(request, stock_id):
    """Submit a customer rating and review for a marketplace product."""
    client = request.client
    stock = get_object_or_404(Stock, pk=stock_id, is_marketplace_visible=True)
    rating = request.POST.get('rating')
    comment = request.POST.get('comment', '').strip()

    if not rating or not rating.isdigit() or not (1 <= int(rating) <= 5):
        messages.error(request, 'Please provide a valid rating between 1 and 5.')
        return redirect('marketplace:product_detail', pk=stock_id)

    if not comment:
        messages.error(request, 'Please write a comment for your review.')
        return redirect('marketplace:product_detail', pk=stock_id)

    try:
        ProductReview.objects.update_or_create(
            stock=stock,
            client=client,
            defaults={
                'rating': int(rating),
                'comment': comment,
            }
        )
        messages.success(request, 'Thank you! Your product review has been submitted.')
    except Exception as e:
        messages.error(request, f'Unable to submit review: {e}')

    return redirect('marketplace:product_detail', pk=stock_id)


@client_login_required
@require_http_methods(['POST'])
def request_return(request, order_id):
    """Submit a return/refund request for a delivered marketplace order."""
    client = request.client
    order = get_object_or_404(Order, pk=order_id, client=client)

    if order.status != 'delivered':
        messages.error(request, 'Only delivered orders can be returned.')
        return redirect('marketplace:order_detail', pk=order.pk)

    # Check if a return request already exists
    if ReturnRequest.objects.filter(order=order).exists():
        messages.warning(request, 'A return request has already been submitted for this order.')
        return redirect('marketplace:order_detail', pk=order.pk)

    reason = request.POST.get('reason', '').strip()
    if not reason:
        messages.error(request, 'Please provide a reason for the return request.')
        return redirect('marketplace:order_detail', pk=order.pk)

    try:
        ReturnRequest.objects.create(
            order=order,
            client=client,
            reason=reason,
            status='pending'
        )
        messages.success(request, 'Your return request has been submitted successfully!')
    except Exception as e:
        messages.error(request, f'Unable to submit return request: {e}')

    return redirect('marketplace:order_detail', pk=order.pk)


# Stripe Helper Functions using urllib
import urllib.request
import urllib.parse
import json

def create_stripe_checkout_session(order, secret_key, success_url, cancel_url):
    """Create a Stripe Checkout Session using urllib.request."""
    url = "https://api.stripe.com/v1/checkout/sessions"
    currency = 'xof'  # Zero-decimal currency for West African CFA Franc
    
    params = [
        ('mode', 'payment'),
        ('success_url', success_url),
        ('cancel_url', cancel_url),
        ('payment_method_types[0]', 'card'),
        ('metadata[order_id]', str(order.pk)),
    ]
    
    index = 0
    for item in order.items.all():
        params.extend([
            (f'line_items[{index}][price_data][currency]', currency),
            (f'line_items[{index}][price_data][product_data][name]', item.item_name),
            (f'line_items[{index}][price_data][unit_amount]', str(int(item.unit_price))),
            (f'line_items[{index}][quantity]', str(item.quantity)),
        ])
        index += 1
        
    if order.shipping and order.shipping > 0:
        params.extend([
            (f'line_items[{index}][price_data][currency]', currency),
            (f'line_items[{index}][price_data][product_data][name]', 'Shipping & Handling'),
            (f'line_items[{index}][price_data][unit_amount]', str(int(order.shipping))),
            (f'line_items[{index}][quantity]', '1'),
        ])
        index += 1
        
    if order.tax and order.tax > 0:
        params.extend([
            (f'line_items[{index}][price_data][currency]', currency),
            (f'line_items[{index}][price_data][product_data][name]', 'Sales Tax'),
            (f'line_items[{index}][price_data][unit_amount]', str(int(order.tax))),
            (f'line_items[{index}][quantity]', '1'),
        ])
        index += 1

    data = urllib.parse.urlencode(params).encode('utf-8')
    
    req = urllib.request.Request(
        url,
        data=data,
        headers={
            'Authorization': f'Bearer {secret_key}',
            'Content-Type': 'application/x-www-form-urlencoded',
        },
        method='POST'
    )
    
    with urllib.request.urlopen(req) as response:
        return json.loads(response.read().decode('utf-8'))


def retrieve_stripe_checkout_session(session_id, secret_key):
    """Retrieve a Stripe Checkout Session status by ID."""
    url = f"https://api.stripe.com/v1/checkout/sessions/{session_id}"
    
    req = urllib.request.Request(
        url,
        headers={
            'Authorization': f'Bearer {secret_key}',
        },
        method='GET'
    )
    
    with urllib.request.urlopen(req) as response:
        return json.loads(response.read().decode('utf-8'))


@client_login_required
def payment_success(request, pk):
    """Handle successful Stripe Checkout redirects and verify payments."""
    client = request.client
    order = get_object_or_404(Order, pk=pk, client=client)
    session_id = request.GET.get('session_id')

    if not session_id:
        messages.error(request, 'Payment session ID missing.')
        return redirect('marketplace:payment_gateway', pk=order.pk)

    try:
        payment_settings, _ = CompanyPaymentSettings.objects.get_or_create(company=order.company)
        secret_key = payment_settings.stripe_secret_key or os.environ.get('STRIPE_SECRET_KEY', '')
        
        session = retrieve_stripe_checkout_session(session_id, secret_key)
        
        if session.get('payment_status') == 'paid':
            # Mark as paid and confirmed
            with db_transaction.atomic():
                order.payment_status = 'paid'
                order.status = 'confirmed'
                order.save(update_fields=['payment_status', 'status', 'updated_at'])
                
                try:
                    post_order_payment_to_finance(order, user=None)
                    messages.success(
                        request,
                        f'Stripe payment confirmed! Order #{order.order_number} has been processed.'
                    )
                except MarketplaceFinancePostingError as exc:
                    messages.warning(
                        request,
                        f'Stripe payment confirmed! Order #{order.order_number} is processed. Note: Finance ledger posting pending: {exc}'
                    )
            return redirect('marketplace:order_list')
        else:
            messages.error(request, 'Payment has not been completed yet.')
            return redirect('marketplace:payment_gateway', pk=order.pk)
            
    except Exception as e:
        messages.error(request, f'Verification error: {e}')
        return redirect('marketplace:payment_gateway', pk=order.pk)


@client_login_required
def payment_cancelled(request, pk):
    """Handle cancelled Stripe Checkout payments."""
    client = request.client
    order = get_object_or_404(Order, pk=pk, client=client)
    messages.info(request, 'Payment transaction cancelled. You can retry paying now.')
    return redirect('marketplace:payment_gateway', pk=order.pk)


def create_flutterwave_checkout_session(order, secret_key, redirect_url):
    """Create a Flutterwave Checkout Session using urllib.request."""
    url = "https://api.flutterwave.com/v3/payments"
    
    payload = {
        "tx_ref": f"ORD-{order.order_number}-{order.pk}",
        "amount": str(int(order.total)),
        "currency": "XAF",
        "redirect_url": redirect_url,
        "payment_options": "mobilemoneyfranco,card",
        "customer": {
            "email": order.client.email,
            "phonenumber": order.client.phone or "000000000",
            "name": order.client.get_full_name()
        },
        "customizations": {
            "title": order.company.name,
            "description": f"Payment for Order #{order.order_number}"
        }
    }
    
    data = json.dumps(payload).encode('utf-8')
    
    req = urllib.request.Request(
        url,
        data=data,
        headers={
            'Authorization': f'Bearer {secret_key}',
            'Content-Type': 'application/json',
        },
        method='POST'
    )
    
    with urllib.request.urlopen(req) as response:
        return json.loads(response.read().decode('utf-8'))


def verify_flutterwave_payment(transaction_id, secret_key):
    """Verify a Flutterwave transaction status."""
    url = f"https://api.flutterwave.com/v3/transactions/{transaction_id}/verify"
    
    req = urllib.request.Request(
        url,
        headers={
            'Authorization': f'Bearer {secret_key}',
            'Content-Type': 'application/json',
        },
        method='GET'
    )
    
    with urllib.request.urlopen(req) as response:
        return json.loads(response.read().decode('utf-8'))


@client_login_required
def flutterwave_verify(request, pk):
    """Verify Flutterwave Mobile Money transaction callback."""
    client = request.client
    order = get_object_or_404(Order, pk=pk, client=client)
    
    status = request.GET.get('status')
    tx_ref = request.GET.get('tx_ref')
    transaction_id = request.GET.get('transaction_id')

    if status != 'successful' or not transaction_id:
        messages.error(request, 'Mobile Money payment was not successful or was cancelled.')
        return redirect('marketplace:payment_gateway', pk=order.pk)

    try:
        payment_settings, _ = CompanyPaymentSettings.objects.get_or_create(company=order.company)
        secret_key = payment_settings.flutterwave_secret_key or os.environ.get('FLUTTERWAVE_SECRET_KEY', '')
        
        verification = verify_flutterwave_payment(transaction_id, secret_key)
        
        if (verification.get('status') == 'success' and 
            verification.get('data', {}).get('status') == 'successful' and 
            int(float(verification['data']['amount'])) >= int(order.total)):
            
            with db_transaction.atomic():
                order.payment_status = 'paid'
                order.status = 'confirmed'
                order.save(update_fields=['payment_status', 'status', 'updated_at'])
                
                try:
                    post_order_payment_to_finance(order, user=None)
                    messages.success(
                        request,
                        f'Mobile Money payment verified successfully via Flutterwave! Order #{order.order_number} is confirmed.'
                    )
                except MarketplaceFinancePostingError as exc:
                    messages.warning(
                        request,
                        f'Mobile Money payment verified! Order #{order.order_number} is confirmed. Note: Finance ledger posting pending: {exc}'
                    )
            return redirect('marketplace:order_list')
        else:
            messages.error(request, 'Payment verification failed at gateway.')
            return redirect('marketplace:payment_gateway', pk=order.pk)
            
    except Exception as e:
        messages.error(request, f'Verification error: {e}')
        return redirect('marketplace:payment_gateway', pk=order.pk)


def generate_order_pdf_bytes(order):
    """Generate a clean server-side PDF invoice for an order using ReportLab."""
    buffer = io.BytesIO()
    p = canvas.Canvas(buffer, pagesize=letter)
    width, height = letter

    # Header
    p.setFont("Helvetica-Bold", 18)
    p.drawString(50, height - 50, f"{order.company.name.upper()} - INVOICE")
    
    p.setFont("Helvetica", 10)
    p.drawString(50, height - 70, f"Order Number: #{order.order_number}")
    p.drawString(50, height - 85, f"Date: {order.created_at.strftime('%Y-%m-%d %H:%M')}")
    p.drawString(50, height - 100, f"Order Status: {order.get_status_display()}")
    p.drawString(50, height - 115, f"Payment Status: {order.get_payment_status_display()}")

    # Customer info
    p.setFont("Helvetica-Bold", 10)
    p.drawString(350, height - 50, "Billed To:")
    p.setFont("Helvetica", 10)
    p.drawString(350, height - 65, f"Client: {order.client.get_full_name()}")
    p.drawString(350, height - 80, f"Email: {order.client.email}")
    p.drawString(350, height - 95, f"Phone: {order.client.phone or 'N/A'}")
    if order.shipping_address:
        p.drawString(350, height - 110, f"Address: {order.shipping_address[:30]}")

    # Divider line
    p.setLineWidth(1)
    p.line(50, height - 135, width - 50, height - 135)

    # Table Headers
    y = height - 155
    p.setFont("Helvetica-Bold", 11)
    p.drawString(50, y, "Item Description")
    p.drawString(300, y, "Qty")
    p.drawString(370, y, "Unit Price")
    p.drawString(470, y, "Total")
    
    p.setLineWidth(0.5)
    p.line(50, y - 5, width - 50, y - 5)
    y -= 25

    p.setFont("Helvetica", 10)
    for item in order.items.all():
        if y < 100:
            p.showPage()
            y = height - 50
        p.drawString(50, y, str(item.item_name)[:35])
        p.drawString(300, y, str(item.quantity))
        p.drawString(370, y, f"FCFA {item.unit_price:,.0f}")
        p.drawString(470, y, f"FCFA {item.subtotal:,.0f}")
        y -= 20

    # Summary Line
    p.line(50, y - 5, width - 50, y - 5)
    y -= 25
    p.setFont("Helvetica-Bold", 12)
    p.drawString(370, y, "Total Payable:")
    p.drawString(470, y, f"FCFA {order.total:,.0f}")

    p.showPage()
    p.save()
    pdf_bytes = buffer.getvalue()
    buffer.close()
    return pdf_bytes


@client_login_required
def order_pdf(request, pk):
    """Download server-side generated PDF invoice for clients."""
    client = request.client
    order = get_object_or_404(Order, pk=pk, client=client)
    
    pdf_bytes = generate_order_pdf_bytes(order)
    response = HttpResponse(pdf_bytes, content_type='application/pdf')
    response['Content-Disposition'] = f'attachment; filename="Invoice_{order.order_number}.pdf"'
    return response


@login_required
def admin_order_pdf(request, pk):
    """Download server-side generated PDF invoice for staff/company admins."""
    company = request.user.company
    order = get_object_or_404(Order, pk=pk, company=company)
    
    pdf_bytes = generate_order_pdf_bytes(order)
    response = HttpResponse(pdf_bytes, content_type='application/pdf')
    response['Content-Disposition'] = f'attachment; filename="Invoice_{order.order_number}.pdf"'
    return response
