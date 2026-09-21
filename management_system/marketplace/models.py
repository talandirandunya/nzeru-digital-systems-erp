from django.core.exceptions import ValidationError
from django.db import models
from django.conf import settings
from django.core.validators import MinValueValidator, MaxValueValidator
from accounts.models import Company
from inventory.models import Stock

class Client(models.Model):
    """Client model for marketplace customers - platform-wide registration"""
    email = models.EmailField(unique=True)
    password = models.CharField(max_length=128)  # Will be hashed
    first_name = models.CharField(max_length=100)
    last_name = models.CharField(max_length=100)
    phone = models.CharField(max_length=20, blank=True)
    address = models.TextField(blank=True)
    city = models.CharField(max_length=100, blank=True)
    country = models.CharField(max_length=100, blank=True)
    postal_code = models.CharField(max_length=20, blank=True)
    is_active = models.BooleanField(default=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    
    class Meta:
        ordering = ['-created_at']
    
    def __str__(self):
        return f"{self.first_name} {self.last_name} ({self.email})"
    
    def get_full_name(self):
        return f"{self.first_name} {self.last_name}"
    
    def set_password(self, raw_password):
        """Hash the password"""
        from django.contrib.auth.hashers import make_password
        self.password = make_password(raw_password)
    
    def check_password(self, raw_password):
        """Check if password matches"""
        from django.contrib.auth.hashers import check_password
        return check_password(raw_password, self.password)


class Cart(models.Model):
    """Shopping cart for clients"""
    client = models.OneToOneField(Client, on_delete=models.CASCADE, related_name='cart')
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    
    def __str__(self):
        return f"Cart for {self.client.get_full_name()}"
    
    @property
    def total_items(self):
        return sum(item.quantity for item in self.items.all())
    
    @property
    def total_price(self):
        return sum(item.subtotal for item in self.items.all())


class CartItem(models.Model):
    """Items in shopping cart"""
    cart = models.ForeignKey(Cart, on_delete=models.CASCADE, related_name='items')
    stock = models.ForeignKey(Stock, on_delete=models.CASCADE)
    quantity = models.IntegerField(validators=[MinValueValidator(1)])
    added_at = models.DateTimeField(auto_now_add=True)
    
    class Meta:
        unique_together = ['cart', 'stock']
    
    def __str__(self):
        return f"{self.quantity} x {self.stock.name}"
    
    @property
    def subtotal(self):
        return self.quantity * self.stock.selling_price


class Order(models.Model):
    """Customer orders"""
    STATUS_CHOICES = [
        ('pending', 'Pending'),
        ('confirmed', 'Confirmed'),
        ('processing', 'Processing'),
        ('shipped', 'Shipped'),
        ('delivered', 'Delivered'),
        ('cancelled', 'Cancelled'),
    ]
    
    PAYMENT_STATUS_CHOICES = [
        ('pending', 'Pending'),
        ('paid', 'Paid'),
        ('refunded', 'Refunded'),
        ('failed', 'Failed'),
    ]

    FINANCE_SYNC_STATUS_CHOICES = [
        ('pending', 'Pending'),
        ('posted', 'Posted'),
        ('reversed', 'Reversed'),
        ('failed', 'Failed'),
    ]
    
    order_number = models.CharField(max_length=50, unique=True)
    client = models.ForeignKey(Client, on_delete=models.CASCADE, related_name='orders')
    company = models.ForeignKey(Company, on_delete=models.CASCADE, related_name='marketplace_orders')
    status = models.CharField(max_length=20, choices=STATUS_CHOICES, default='pending')
    payment_status = models.CharField(max_length=20, choices=PAYMENT_STATUS_CHOICES, default='pending')
    finance_sync_status = models.CharField(
        max_length=20,
        choices=FINANCE_SYNC_STATUS_CHOICES,
        default='pending',
    )
    finance_journal_entry = models.ForeignKey(
        'finance.JournalEntry',
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='marketplace_orders',
    )
    finance_reversal_journal_entry = models.ForeignKey(
        'finance.JournalEntry',
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='marketplace_reversals',
    )
    finance_synced_at = models.DateTimeField(null=True, blank=True)
    finance_reversed_at = models.DateTimeField(null=True, blank=True)
    finance_sync_error = models.TextField(blank=True)
    
    # Totals
    subtotal = models.DecimalField(max_digits=10, decimal_places=2)
    tax = models.DecimalField(max_digits=10, decimal_places=2, default=0)
    shipping = models.DecimalField(max_digits=10, decimal_places=2, default=0)
    total = models.DecimalField(max_digits=10, decimal_places=2)
    
    # Shipping info
    shipping_address = models.TextField()
    shipping_city = models.CharField(max_length=100)
    shipping_country = models.CharField(max_length=100)
    shipping_phone = models.CharField(max_length=20)
    
    # Timestamps
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    confirmed_at = models.DateTimeField(null=True, blank=True)
    shipped_at = models.DateTimeField(null=True, blank=True)
    delivered_at = models.DateTimeField(null=True, blank=True)
    
    notes = models.TextField(blank=True)
    
    class Meta:
        ordering = ['-created_at']
    
    def __str__(self):
        return f"Order #{self.order_number} - {self.client.get_full_name()} ({self.company.name})"
    
    def generate_order_number(self):
        """Generate unique order number"""
        import datetime
        timestamp = datetime.datetime.now().strftime('%Y%m%d%H%M%S')
        return f"ORD-{timestamp}-{self.client.id}"

    @property
    def is_finance_posted(self):
        return self.finance_journal_entry_id is not None and self.finance_sync_status == 'posted'

    @property
    def is_finance_reversed(self):
        return self.finance_reversal_journal_entry_id is not None and self.finance_sync_status == 'reversed'


class OrderItem(models.Model):
    """Items in an order"""
    order = models.ForeignKey(Order, on_delete=models.CASCADE, related_name='items')
    stock = models.ForeignKey(Stock, on_delete=models.CASCADE)
    item_name = models.CharField(max_length=200)  # Store name at time of order
    item_code = models.CharField(max_length=50)
    quantity = models.IntegerField(validators=[MinValueValidator(1)])
    unit_price = models.DecimalField(max_digits=10, decimal_places=2)
    subtotal = models.DecimalField(max_digits=10, decimal_places=2)
    
    def __str__(self):
        return f"{self.quantity} x {self.item_name}"
    
    def clean(self):
        if self.order_id and self.stock_id and self.stock.company_id != self.order.company_id:
            raise ValidationError('Stock must belong to the order company.')

    def save(self, *args, **kwargs):
        self.subtotal = self.quantity * self.unit_price
        self.clean()
        return super().save(*args, **kwargs)


class Wishlist(models.Model):
    """Client wishlist"""
    client = models.OneToOneField(Client, on_delete=models.CASCADE, related_name='wishlist')
    created_at = models.DateTimeField(auto_now_add=True)
    
    def __str__(self):
        return f"Wishlist for {self.client.get_full_name()}"


class WishlistItem(models.Model):
    """Items in wishlist"""
    wishlist = models.ForeignKey(Wishlist, on_delete=models.CASCADE, related_name='items')
    stock = models.ForeignKey(Stock, on_delete=models.CASCADE)
    added_at = models.DateTimeField(auto_now_add=True)
    
    class Meta:
        unique_together = ['wishlist', 'stock']
    
    def __str__(self):
        return f"{self.stock.name} in {self.wishlist.client.get_full_name()}'s wishlist"

class ProductReview(models.Model):
    stock = models.ForeignKey(Stock, on_delete=models.CASCADE, related_name='reviews')
    client = models.ForeignKey(Client, on_delete=models.CASCADE, related_name='reviews')
    rating = models.PositiveIntegerField(validators=[MinValueValidator(1), MaxValueValidator(5)])
    comment = models.TextField()
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ['-created_at']
        unique_together = ['stock', 'client']

    def __str__(self):
        return f"Review by {self.client.get_full_name()} for {self.stock.name}"


class ReturnRequest(models.Model):
    STATUS_CHOICES = [
        ('pending', 'Pending'),
        ('approved', 'Approved'),
        ('rejected', 'Rejected'),
    ]
    order = models.ForeignKey('Order', on_delete=models.CASCADE, related_name='return_requests')
    client = models.ForeignKey(Client, on_delete=models.CASCADE, related_name='return_requests')
    reason = models.TextField()
    status = models.CharField(max_length=20, choices=STATUS_CHOICES, default='pending')
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ['-created_at']

    def __str__(self):
        return f"Return Request for Order #{self.order.order_number} ({self.status})"

    def clean(self):
        if self.order_id and self.client_id and self.order.client_id != self.client_id:
            raise ValidationError('Return requester must own the order.')

    def save(self, *args, **kwargs):
        self.clean()
        return super().save(*args, **kwargs)


class CompanyPaymentSettings(models.Model):
    company = models.OneToOneField(Company, on_delete=models.CASCADE, related_name='payment_settings')
    whatsapp_number = models.CharField(
        max_length=50,
        default='',
        blank=True,
        help_text='WhatsApp contact number for payments (e.g., +237690000000)'
    )
    orange_money_number = models.CharField(
        max_length=50,
        default='',
        blank=True,
        help_text='Orange Money transfer number'
    )
    mtn_momo_number = models.CharField(
        max_length=50,
        default='',
        blank=True,
        help_text='MTN Mobile Money transfer number'
    )
    payment_instructions = models.TextField(
        default='',
        blank=True,
        help_text='Payment instructions displayed to customers during checkout'
    )
    is_active = models.BooleanField(default=True)

    class Meta:
        verbose_name = 'Company Payment Settings'
        verbose_name_plural = 'Company Payment Settings'

    def __str__(self):
        return f"Payment Settings for {self.company.name}"
