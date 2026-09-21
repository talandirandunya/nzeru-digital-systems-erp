from django.conf import settings
from django.core.exceptions import ValidationError
from django.db import models
from django.db.models import Sum
from django.utils import timezone


class Supplier(models.Model):
    company = models.ForeignKey('accounts.Company', on_delete=models.CASCADE, related_name='suppliers')
    name = models.CharField(max_length=200)
    email = models.EmailField(blank=True)
    phone = models.CharField(max_length=40, blank=True)
    address = models.TextField(blank=True)
    is_active = models.BooleanField(default=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        constraints = [models.UniqueConstraint(fields=('company', 'name'), name='unique_supplier_company_name')]
        ordering = ('name',)


class PurchaseRequisition(models.Model):
    STATUS_CHOICES = [('draft', 'Draft'), ('submitted', 'Submitted'), ('returned', 'Returned for correction'), ('approved', 'Approved'), ('rejected', 'Rejected'), ('converted', 'Converted')]
    company = models.ForeignKey('accounts.Company', on_delete=models.CASCADE, related_name='purchase_requisitions')
    requested_by = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.PROTECT, related_name='purchase_requisitions')
    number = models.CharField(max_length=40)
    status = models.CharField(max_length=20, choices=STATUS_CHOICES, default='draft', db_index=True)
    decision_by = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.SET_NULL, null=True, blank=True, related_name='decided_requisitions')
    decision_reason = models.TextField(blank=True)
    decided_at = models.DateTimeField(null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        constraints = [models.UniqueConstraint(fields=('company', 'number'), name='unique_requisition_company_number')]
        ordering = ('-created_at',)

    def submit(self):
        if self.status not in ('draft', 'returned') or not self.lines.exists():
            raise ValidationError('Only a draft or returned requisition with lines can be submitted.')
        self.status = 'submitted'
        self.save(update_fields=['status'])

    def apply_approval_decision(self, decision):
        if decision == 'approved':
            self.status = 'approved'
        elif decision == 'rejected':
            self.status = 'rejected'
        elif decision == 'returned':
            self.status = 'returned'
        self.save(update_fields=['status'])

    def decide(self, *, approver, approved, reason=''):
        if self.status != 'submitted':
            raise ValidationError('Only submitted requisitions can be decided.')
        if approver == self.requested_by:
            raise ValidationError('The requester cannot approve their own requisition.')
        if not approved and not reason.strip():
            raise ValidationError('A rejection reason is required.')
        self.status = 'approved' if approved else 'rejected'
        self.decision_by = approver
        self.decision_reason = reason
        self.decided_at = timezone.now()
        self.save(update_fields=['status', 'decision_by', 'decision_reason', 'decided_at'])


class PurchaseRequisitionLine(models.Model):
    requisition = models.ForeignKey(PurchaseRequisition, on_delete=models.CASCADE, related_name='lines')
    stock = models.ForeignKey('inventory.Stock', on_delete=models.PROTECT)
    quantity = models.PositiveIntegerField()
    notes = models.CharField(max_length=200, blank=True)

    def clean(self):
        if self.stock_id and self.requisition_id and self.stock.company_id != self.requisition.company_id:
            raise ValidationError('Stock must belong to the requisition company.')
        if self.quantity <= 0:
            raise ValidationError('Quantity must be positive.')


class PurchaseOrder(models.Model):
    STATUS_CHOICES = [('draft', 'Draft'), ('submitted', 'Submitted'), ('returned', 'Returned for correction'), ('approved', 'Approved'), ('rejected', 'Rejected'), ('partially_received', 'Partially received'), ('received', 'Received'), ('cancelled', 'Cancelled')]
    company = models.ForeignKey('accounts.Company', on_delete=models.CASCADE, related_name='purchase_orders')
    requisition = models.OneToOneField(PurchaseRequisition, on_delete=models.PROTECT, related_name='purchase_order')
    supplier = models.ForeignKey(Supplier, on_delete=models.PROTECT, related_name='purchase_orders')
    number = models.CharField(max_length=40)
    status = models.CharField(max_length=25, choices=STATUS_CHOICES, default='draft', db_index=True)
    approved_by = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.SET_NULL, null=True, blank=True, related_name='approved_purchase_orders')
    approved_at = models.DateTimeField(null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        constraints = [models.UniqueConstraint(fields=('company', 'number'), name='unique_po_company_number')]
        ordering = ('-created_at',)

    def clean(self):
        if self.requisition_id and self.requisition.company_id != self.company_id:
            raise ValidationError('Requisition must belong to the purchase order company.')
        if self.supplier_id and self.supplier.company_id != self.company_id:
            raise ValidationError('Supplier must belong to the purchase order company.')

    def approve(self, approver):
        if self.status != 'submitted':
            raise ValidationError('Only submitted purchase orders can be approved.')
        if approver == self.requisition.requested_by:
            raise ValidationError('The requisition requester cannot approve the purchase order.')
        self.status = 'approved'
        self.approved_by = approver
        self.approved_at = timezone.now()
        self.save(update_fields=['status', 'approved_by', 'approved_at'])

    def submit(self):
        if self.status not in ('draft', 'returned') or not self.lines.exists():
            raise ValidationError('Only a draft or returned purchase order with lines can be submitted.')
        self.status = 'submitted'
        self.save(update_fields=['status'])

    def apply_approval_decision(self, decision):
        if decision == 'approved':
            self.status = 'approved'
        elif decision == 'rejected':
            self.status = 'rejected'
        elif decision == 'returned':
            self.status = 'returned'
        self.save(update_fields=['status'])


class PurchaseOrderLine(models.Model):
    order = models.ForeignKey(PurchaseOrder, on_delete=models.CASCADE, related_name='lines')
    stock = models.ForeignKey('inventory.Stock', on_delete=models.PROTECT)
    ordered_quantity = models.PositiveIntegerField()
    unit_cost = models.DecimalField(max_digits=12, decimal_places=2, default=0)

    def clean(self):
        if self.order_id and self.stock_id and self.stock.company_id != self.order.company_id:
            raise ValidationError('Stock must belong to the purchase order company.')
        if self.ordered_quantity <= 0:
            raise ValidationError('Ordered quantity must be positive.')

    def save(self, *args, **kwargs):
        self.clean()
        return super().save(*args, **kwargs)


class GoodsReceipt(models.Model):
    order = models.ForeignKey(PurchaseOrder, on_delete=models.PROTECT, related_name='receipts')
    received_by = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.PROTECT)
    receipt_number = models.CharField(max_length=40)
    received_at = models.DateTimeField(default=timezone.now)
    notes = models.TextField(blank=True)

    class Meta:
        constraints = [models.UniqueConstraint(fields=('order', 'receipt_number'), name='unique_receipt_order_number')]
        ordering = ('-received_at',)

    @property
    def total_quantity(self):
        return self.lines.aggregate(total=Sum('quantity'))['total'] or 0


class GoodsReceiptLine(models.Model):
    receipt = models.ForeignKey(GoodsReceipt, on_delete=models.CASCADE, related_name='lines')
    order_line = models.ForeignKey(PurchaseOrderLine, on_delete=models.PROTECT, related_name='receipt_lines')
    quantity = models.PositiveIntegerField()

    def clean(self):
        if self.quantity <= 0:
            raise ValidationError('Received quantity must be positive.')
        if self.receipt_id and self.order_line_id:
            if self.receipt.order_id != self.order_line.order_id:
                raise ValidationError('Receipt line must belong to the receipt order.')
            if self.order_line.stock.company_id != self.receipt.order.company_id:
                raise ValidationError('Order stock must belong to the receipt company.')

    def save(self, *args, **kwargs):
        self.clean()
        return super().save(*args, **kwargs)
