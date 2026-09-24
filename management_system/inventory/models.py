from datetime import timedelta

from django.db import models
from django.conf import settings
from django.contrib.auth import get_user_model
from django.core.exceptions import ValidationError
from django.core.validators import MinValueValidator
from django.db.models import Sum
from django.utils import timezone


class Warehouse(models.Model):
    """Physical storage location for stock items."""
    company = models.ForeignKey('accounts.Company', on_delete=models.CASCADE, related_name='warehouses')
    name = models.CharField(max_length=120)
    code = models.CharField(max_length=30, blank=True)
    location = models.CharField(max_length=200, blank=True)
    manager = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.SET_NULL, null=True, blank=True, related_name='managed_warehouses')
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        unique_together = ['company', 'name']
        ordering = ['name']

    def __str__(self):
        return f"{self.name} ({self.company.name})"


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
        if self.company_id and self.category_id and self.category.company_id != self.company_id:
            raise ValidationError({'category': 'Category must belong to the same company as the stock.'})

    def save(self, *args, **kwargs):
        self.clean()
        saved = super().save(*args, **kwargs)
        if self.company_id and self.quantity <= self.reorder_level:
            try:
                from .models import create_inventory_alerts
                create_inventory_alerts(self.company, stock=self)
            except Exception:
                pass
        return saved
    
    @property
    def total_value(self):
        return self.quantity * self.cost_price

    @property
    def total_selling_value(self):
        return self.quantity * self.selling_price

    @property
    def reserved_quantity(self):
        return self.reservations.filter(status__in=['reserved', 'allocated']).aggregate(total=Sum('quantity'))['total'] or 0

    @property
    def available_quantity(self):
        return max(self.quantity - self.reserved_quantity, 0)

    @property
    def needs_reorder(self):
        return self.quantity <= self.reorder_level

    @property
    def weighted_average_cost(self):
        total_qty = self.batches.aggregate(total=Sum('quantity'))['total'] or 0
        if not total_qty:
            return self.cost_price
        total_cost = self.batches.aggregate(total=models.Sum(models.F('quantity') * models.F('unit_cost')))['total'] or 0
        return total_cost / total_qty

    def reserve_quantity(self, *, quantity, warehouse=None, reference='', reserved_by=None, expires_at=None):
        if quantity <= 0:
            raise ValidationError('Reservation quantity must be positive.')
        if self.available_quantity < quantity:
            raise ValidationError('Not enough available stock to reserve this quantity.')
        return StockReservation.objects.create(
            company=self.company,
            stock=self,
            warehouse=warehouse,
            quantity=quantity,
            reference=reference,
            reserved_by=reserved_by,
            expires_at=expires_at or timezone.now() + timedelta(days=7),
        )

    def low_stock_alert(self, warehouse=None):
        threshold = self.reorder_level or 0
        quantity = warehouse.stock_movements.filter(stock=self).aggregate(total=models.Sum('quantity'))['total'] if warehouse else self.quantity
        return quantity <= threshold

    def __str__(self):
        return f"{self.item_code} - {self.name} ({self.company.name})"


class InventoryBatch(models.Model):
    """Stock lot record for batch and FIFO/weighted average costing."""
    company = models.ForeignKey('accounts.Company', on_delete=models.CASCADE, related_name='inventory_batches')
    stock = models.ForeignKey(Stock, on_delete=models.CASCADE, related_name='batches')
    batch_code = models.CharField(max_length=80)
    quantity = models.PositiveIntegerField(default=0)
    unit_cost = models.DecimalField(max_digits=12, decimal_places=2, default=0)
    supplier = models.ForeignKey('procurement.Supplier', on_delete=models.SET_NULL, null=True, blank=True, related_name='inventory_batches')
    received_at = models.DateTimeField(auto_now_add=True)
    expiry_date = models.DateField(null=True, blank=True)

    class Meta:
        unique_together = ['company', 'stock', 'batch_code']
        ordering = ['received_at']

    def clean(self):
        if self.stock_id and self.stock.company_id != self.company_id:
            raise ValidationError('Batch stock must belong to the same company.')
        if self.supplier_id and self.supplier.company_id != self.company_id:
            raise ValidationError('Supplier must belong to the same company.')
        if self.quantity < 0:
            raise ValidationError('Batch quantity cannot be negative.')

    def adjust_quantity(self, delta):
        if self.quantity + delta < 0:
            raise ValidationError('Batch quantity cannot fall below zero.')
        self.quantity += delta
        self.save(update_fields=['quantity'])

    def save(self, *args, **kwargs):
        self.clean()
        return super().save(*args, **kwargs)


class InventorySerial(models.Model):
    """Serial number tracking for tracked inventory items."""
    STATUS_CHOICES = [('available', 'Available'), ('reserved', 'Reserved'), ('issued', 'Issued'), ('sold', 'Sold')]
    company = models.ForeignKey('accounts.Company', on_delete=models.CASCADE, related_name='inventory_serials')
    stock = models.ForeignKey(Stock, on_delete=models.CASCADE, related_name='serials')
    batch = models.ForeignKey(InventoryBatch, on_delete=models.SET_NULL, null=True, blank=True, related_name='serials')
    serial_number = models.CharField(max_length=120)
    status = models.CharField(max_length=20, choices=STATUS_CHOICES, default='available', db_index=True)
    assigned_to = models.CharField(max_length=200, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        unique_together = ['company', 'serial_number']
        ordering = ['serial_number']

    def clean(self):
        if self.stock_id and self.stock.company_id != self.company_id:
            raise ValidationError('Serial stock must belong to the same company.')
        if self.batch_id and self.batch.company_id != self.company_id:
            raise ValidationError('Batch must belong to the same company.')

    def reserve(self, *, assigned_to=''):
        if self.status not in ('available',):
            raise ValidationError('Only available serials can be reserved.')
        self.status = 'reserved'
        self.assigned_to = assigned_to
        self.save(update_fields=['status', 'assigned_to'])

    def save(self, *args, **kwargs):
        self.clean()
        return super().save(*args, **kwargs)


class StockTransfer(models.Model):
    STATUS_CHOICES = [('pending', 'Pending'), ('completed', 'Completed'), ('cancelled', 'Cancelled')]
    company = models.ForeignKey('accounts.Company', on_delete=models.CASCADE, related_name='stock_transfers')
    stock = models.ForeignKey(Stock, on_delete=models.CASCADE, related_name='transfers')
    from_warehouse = models.ForeignKey(Warehouse, on_delete=models.PROTECT, related_name='outgoing_transfers')
    to_warehouse = models.ForeignKey(Warehouse, on_delete=models.PROTECT, related_name='incoming_transfers')
    quantity = models.PositiveIntegerField()
    transfer_date = models.DateField(default=timezone.now)
    reference = models.CharField(max_length=80, blank=True)
    notes = models.TextField(blank=True)
    moved_by = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.SET_NULL, null=True, blank=True, related_name='stock_transfers')
    status = models.CharField(max_length=20, choices=STATUS_CHOICES, default='pending', db_index=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ['-transfer_date', '-created_at']

    def clean(self):
        if self.stock_id and self.stock.company_id != self.company_id:
            raise ValidationError('Transfer stock must belong to the same company.')
        if self.from_warehouse_id and self.to_warehouse_id:
            if self.from_warehouse.company_id != self.company_id or self.to_warehouse.company_id != self.company_id:
                raise ValidationError('Transfer warehouses must belong to the same company.')
        if self.from_warehouse_id == self.to_warehouse_id:
            raise ValidationError('Transfer destination must differ from the source warehouse.')
        if self.quantity <= 0:
            raise ValidationError('Transfer quantity must be positive.')

    def complete(self, user=None):
        if self.status == 'completed':
            raise ValidationError('This transfer is already completed.')
        if self.stock.available_quantity < self.quantity:
            raise ValidationError('Not enough available stock for this transfer.')
        self.status = 'completed'
        self.moved_by = user or self.moved_by
        self.save(update_fields=['status', 'moved_by'])
        StockMovement.objects.create(
            company=self.company,
            stock=self.stock,
            warehouse=self.from_warehouse,
            movement_type='out',
            quantity=self.quantity,
            reference=self.reference or f'TR-{self.pk}',
            remarks=f'Transfer to {self.to_warehouse.name}',
            moved_by=user,
        )
        StockMovement.objects.create(
            company=self.company,
            stock=self.stock,
            warehouse=self.to_warehouse,
            movement_type='in',
            quantity=self.quantity,
            reference=self.reference or f'TR-{self.pk}',
            remarks=f'Receipt from {self.from_warehouse.name}',
            moved_by=user,
        )

    def save(self, *args, **kwargs):
        self.clean()
        return super().save(*args, **kwargs)


class StockReservation(models.Model):
    STATUS_CHOICES = [('reserved', 'Reserved'), ('allocated', 'Allocated'), ('fulfilled', 'Fulfilled'), ('released', 'Released')]
    company = models.ForeignKey('accounts.Company', on_delete=models.CASCADE, related_name='stock_reservations')
    stock = models.ForeignKey(Stock, on_delete=models.CASCADE, related_name='reservations')
    warehouse = models.ForeignKey(Warehouse, on_delete=models.SET_NULL, null=True, blank=True, related_name='reservations')
    quantity = models.PositiveIntegerField()
    reference = models.CharField(max_length=120, blank=True)
    reserved_by = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.SET_NULL, null=True, blank=True, related_name='stock_reservations')
    allocated_to = models.CharField(max_length=200, blank=True)
    expires_at = models.DateTimeField(null=True, blank=True)
    status = models.CharField(max_length=20, choices=STATUS_CHOICES, default='reserved', db_index=True)
    reserved_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ['-reserved_at']

    def clean(self):
        if self.stock_id and self.stock.company_id != self.company_id:
            raise ValidationError('Reservation stock must belong to the same company.')
        if self.warehouse_id and self.warehouse.company_id != self.company_id:
            raise ValidationError('Reservation warehouse must belong to the same company.')
        if self.quantity <= 0:
            raise ValidationError('Reservation quantity must be positive.')

    def allocate(self):
        if self.status == 'released':
            raise ValidationError('Released reservations cannot be allocated.')
        self.status = 'allocated'
        self.save(update_fields=['status'])

    def fulfill(self):
        if self.status == 'released':
            raise ValidationError('Released reservations cannot be fulfilled.')
        self.status = 'fulfilled'
        self.save(update_fields=['status'])

    def release(self):
        if self.status == 'fulfilled':
            raise ValidationError('Fulfilled reservations cannot be released.')
        self.status = 'released'
        self.save(update_fields=['status'])

    def save(self, *args, **kwargs):
        self.clean()
        return super().save(*args, **kwargs)


def warehouse_replenishment_alerts(company):
    """Return stock items near or below their reorder threshold for a company."""
    alerts = []
    for stock in Stock.objects.filter(company=company, quantity__lte=models.F('reorder_level')).select_related('category'):
        alerts.append({
            'stock': stock,
            'alert_type': 'low_stock',
            'quantity': stock.quantity,
            'reorder_level': stock.reorder_level,
            'available_quantity': stock.available_quantity,
        })
    return alerts


def create_inventory_alerts(company, *, stock=None):
    """Create low-stock and replenishment notifications for stock managers in the company."""
    from notifications.models import Notification
    from notifications.utils import create_notification

    User = get_user_model()
    recipients = User.objects.filter(company=company, role='stock_manager')
    queryset = Stock.objects.filter(company=company)
    if stock is not None:
        queryset = queryset.filter(pk=stock.pk)

    alerts = []
    for item in queryset.filter(quantity__lte=models.F('reorder_level')).select_related('category'):
        if not recipients.exists():
            continue
        alert_data = {
            'alert_type': 'low_stock',
            'quantity': item.quantity,
            'reorder_level': item.reorder_level,
            'available_quantity': item.available_quantity,
            'stock_id': item.pk,
        }
        for manager in recipients:
            existing_notification = Notification.objects.filter(
                user=manager,
                notification_type=Notification.INVENTORY_LOW,
                related_object_id=item.pk,
                created_at__date=timezone.now().date(),
            ).exists()
            if not existing_notification:
                create_notification(
                    user=manager,
                    notification_type=Notification.INVENTORY_LOW,
                    title=f'Low Stock Alert: {item.name}',
                    message=f'Stock item "{item.name}" (Code: {item.item_code}) is at {item.quantity} units against a reorder level of {item.reorder_level}.',
                    related_object=item,
                    data=alert_data,
                )
        alerts.append({
            'stock': item,
            'alert_type': 'low_stock',
            'quantity': item.quantity,
            'reorder_level': item.reorder_level,
            'available_quantity': item.available_quantity,
        })
    return alerts

class StockTransaction(models.Model):
    TRANSACTION_TYPES = [
        ('in', 'Stock In'),
        ('out', 'Stock Out'),
        ('adjustment', 'Adjustment'),
    ]

    company = models.ForeignKey('accounts.Company', on_delete=models.CASCADE, related_name='stock_transactions')
    stock = models.ForeignKey(Stock, on_delete=models.CASCADE, related_name='transactions')
    warehouse = models.ForeignKey(Warehouse, on_delete=models.SET_NULL, null=True, blank=True, related_name='transactions')
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
        if self.warehouse_id and self.warehouse.company_id != self.company_id:
            raise ValidationError({'warehouse': 'Warehouse must belong to the same company as the transaction.'})

    def save(self, *args, **kwargs):
        self.clean()
        return super().save(*args, **kwargs)


class StockMovement(models.Model):
    """Detailed stock movement event, including warehouse and reference tracking."""
    MOVE_TYPES = [
        ('in', 'Stock In'),
        ('out', 'Stock Out'),
        ('adjustment', 'Adjustment'),
    ]

    company = models.ForeignKey('accounts.Company', on_delete=models.CASCADE, related_name='stock_movements')
    stock = models.ForeignKey(Stock, on_delete=models.CASCADE, related_name='stock_movements')
    warehouse = models.ForeignKey(Warehouse, on_delete=models.SET_NULL, null=True, blank=True, related_name='stock_movements')
    movement_type = models.CharField(max_length=20, choices=MOVE_TYPES)
    quantity = models.PositiveIntegerField()
    reference = models.CharField(max_length=80, blank=True)
    remarks = models.TextField(blank=True)
    moved_by = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.SET_NULL, null=True, related_name='stock_movements')
    moved_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ['-moved_at']

    def __str__(self):
        return f"{self.stock.item_code} {self.movement_type} {self.quantity}"

    def clean(self):
        if self.stock_id and self.stock.company_id != self.company_id:
            raise ValidationError({'stock': 'Stock must belong to the same company as the movement.'})
        if self.warehouse_id and self.warehouse.company_id != self.company_id:
            raise ValidationError({'warehouse': 'Warehouse must belong to the same company as the movement.'})
        if self.quantity <= 0:
            raise ValidationError({'quantity': 'Movement quantity must be positive.'})

    def save(self, *args, **kwargs):
        self.clean()
        return super().save(*args, **kwargs)