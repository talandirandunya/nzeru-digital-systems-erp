from django.contrib import admin
from .models import Client, Cart, CartItem, Order, OrderItem, Wishlist, WishlistItem


@admin.register(Client)
class ClientAdmin(admin.ModelAdmin):
    list_display = ['email', 'first_name', 'last_name', 'is_active', 'created_at']
    list_filter = ['is_active', 'created_at']
    search_fields = ['email', 'first_name', 'last_name']
    readonly_fields = ['created_at', 'updated_at']
    
    fieldsets = (
        ('Account Info', {
            'fields': ('email', 'is_active')
        }),
        ('Personal Info', {
            'fields': ('first_name', 'last_name', 'phone')
        }),
        ('Address', {
            'fields': ('address', 'city', 'country', 'postal_code')
        }),
        ('Timestamps', {
            'fields': ('created_at', 'updated_at'),
            'classes': ('collapse',)
        }),
    )


class OrderItemInline(admin.TabularInline):
    model = OrderItem
    extra = 0
    readonly_fields = ['subtotal']


@admin.register(Order)
class OrderAdmin(admin.ModelAdmin):
    list_display = ['order_number', 'client', 'company', 'status', 'payment_status', 'finance_sync_status', 'total', 'created_at']
    list_filter = ['company', 'status', 'payment_status', 'finance_sync_status', 'created_at']
    search_fields = ['order_number', 'client__email', 'client__first_name', 'client__last_name']
    readonly_fields = [
        'order_number', 'created_at', 'updated_at', 'confirmed_at', 'shipped_at',
        'delivered_at', 'finance_journal_entry', 'finance_reversal_journal_entry',
        'finance_synced_at', 'finance_reversed_at'
    ]
    inlines = [OrderItemInline]
    
    fieldsets = (
        ('Order Info', {
            'fields': ('order_number', 'client', 'company', 'status', 'payment_status', 'finance_sync_status')
        }),
        ('Pricing', {
            'fields': ('subtotal', 'tax', 'shipping', 'total')
        }),
        ('Shipping Address', {
            'fields': ('shipping_address', 'shipping_city', 'shipping_country', 'shipping_phone')
        }),
        ('Additional Info', {
            'fields': (
                'notes', 'finance_journal_entry', 'finance_reversal_journal_entry',
                'finance_synced_at', 'finance_reversed_at', 'finance_sync_error'
            )
        }),
        ('Timestamps', {
            'fields': ('created_at', 'updated_at', 'confirmed_at', 'shipped_at', 'delivered_at'),
            'classes': ('collapse',)
        }),
    )
    
    actions = ['mark_as_confirmed', 'mark_as_shipped', 'mark_as_delivered']
    
    def mark_as_confirmed(self, request, queryset):
        from django.utils import timezone
        queryset.update(status='confirmed', confirmed_at=timezone.now())
    mark_as_confirmed.short_description = "Mark selected orders as confirmed"
    
    def mark_as_shipped(self, request, queryset):
        from django.utils import timezone
        queryset.update(status='shipped', shipped_at=timezone.now())
    mark_as_shipped.short_description = "Mark selected orders as shipped"
    
    def mark_as_delivered(self, request, queryset):
        from django.utils import timezone
        queryset.update(status='delivered', delivered_at=timezone.now())
    mark_as_delivered.short_description = "Mark selected orders as delivered"


class CartItemInline(admin.TabularInline):
    model = CartItem
    extra = 0


@admin.register(Cart)
class CartAdmin(admin.ModelAdmin):
    list_display = ['client', 'total_items', 'total_price', 'updated_at']
    search_fields = ['client__email', 'client__first_name', 'client__last_name']
    inlines = [CartItemInline]


class WishlistItemInline(admin.TabularInline):
    model = WishlistItem
    extra = 0


@admin.register(Wishlist)
class WishlistAdmin(admin.ModelAdmin):
    list_display = ['client', 'created_at']
    search_fields = ['client__email', 'client__first_name', 'client__last_name']
    inlines = [WishlistItemInline]
