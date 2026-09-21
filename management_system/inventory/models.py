from django.db import models
from django.conf import settings
from django.core.exceptions import ValidationError
from django.core.validators import MinValueValidator

class StockCategory(models.Model):
    """Stock category - scoped to company"""
    company = models.ForeignKey('accounts.Company', on_delete=models.CASCADE, related_name='stock_categories')
    name = models.CharField(max_length=100)
    description = models.TextField(blank=True)
    
    class Meta:
        unique_together = ['company', 'name']
        ordering = ['name']
        verbose_name_plural = 'Stock Categories'
    
    def __str__(self):
        return f"{self.name} ({self.company.name})"

class Stock(models.Model):
    UNIT_CHOICES = [
        ('pcs', 'Pieces'),
        ('kg', 'Kilograms'),
        ('ltr', 'Liters'),
        ('box', 'Boxes'),
        ('set', 'Sets'),
    ]
    
    company = models.ForeignKey('accounts.Company', on_delete=models.CASCADE, related_name='stocks')
    item_code = models.CharField(max_length=50)
    name = models.CharField(max_length=200)
    category = models.ForeignKey(StockCategory, on_delete=models.SET_NULL, null=True, related_name='items')
    description = models.TextField(blank=True)
    quantity = models.IntegerField(validators=[MinValueValidator(0)])
    unit = models.CharField(max_length=10, choices=UNIT_CHOICES, default='pcs')
    cost_price = models.DecimalField(max_digits=10, decimal_places=2, validators=[MinValueValidator(0)], help_text='Cost price for inventory')
    selling_price = models.DecimalField(max_digits=10, decimal_places=2, validators=[MinValueValidator(0)], help_text='Selling price for marketplace')
    reorder_level = models.IntegerField(validators=[MinValueValidator(0)])
    supplier_name = models.CharField(max_length=200)
    supplier_contact = models.CharField(max_length=100, blank=True)
    location = models.CharField(max_length=200, blank=True)
    is_marketplace_visible = models.BooleanField(default=True, help_text='Show this item on the marketplace')
    last_restocked = models.DateField(null=True, blank=True)
    created_by = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.SET_NULL, null=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    image = models.ImageField(upload_to='products/%Y/%m/', blank=True, null=True)
    
    def get_image_url(self):
        if self.image:
            return self.image.url
        return None

    class Meta:
        unique_together = ['company', 'item_code']
        ordering = ['-created_at']

    def clean(self):
        if self.category_id and self.category.company_id != self.company_id:
            raise ValidationError({'category': 'Category must belong to the same company as the stock.'})

    def save(self, *args, **kwargs):
        self.clean()
        return super().save(*args, **kwargs)
    
    @property
    def total_value(self):
        return self.quantity * self.cost_price
    
    @property
    def total_selling_value(self):
        return self.quantity * self.selling_price
    
    @property
    def needs_reorder(self):
        return self.quantity <= self.reorder_level
    
    def __str__(self):
        return f"{self.item_code} - {self.name} ({self.company.name})"

class StockTransaction(models.Model):
    TRANSACTION_TYPES = [
        ('in', 'Stock In'),
        ('out', 'Stock Out'),
        ('adjustment', 'Adjustment'),
    ]
    
    company = models.ForeignKey('accounts.Company', on_delete=models.CASCADE, related_name='stock_transactions')
    stock = models.ForeignKey(Stock, on_delete=models.CASCADE, related_name='transactions')
    transaction_type = models.CharField(max_length=20, choices=TRANSACTION_TYPES)
    quantity = models.IntegerField()
    remarks = models.TextField(blank=True)
    transaction_date = models.DateTimeField(auto_now_add=True)
    user = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.SET_NULL, null=True)
    
    class Meta:
        ordering = ['-transaction_date']
    
    def __str__(self):
        return f"{self.stock.item_code} - {self.transaction_type} - {self.quantity} ({self.company.name})"

    def clean(self):
        if self.stock_id and self.stock.company_id != self.company_id:
            raise ValidationError({'stock': 'Stock must belong to the same company as the transaction.'})

    def save(self, *args, **kwargs):
        self.clean()
        return super().save(*args, **kwargs)