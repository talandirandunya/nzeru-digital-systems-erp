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
    tax_id = models.CharField(max_length=80, blank=True)
    category = models.CharField(max_length=120, blank=True)
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
    budget_amount = models.DecimalField(max_digits=14, decimal_places=2, default=0)
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


class RequestForQuotation(models.Model):
    STATUS_CHOICES = [('draft', 'Draft'), ('open', 'Open'), ('closed', 'Closed'), ('awarded', 'Awarded')]
    company = models.ForeignKey('accounts.Company', on_delete=models.CASCADE, related_name='procurement_rfqs')
    requisition = models.ForeignKey(PurchaseRequisition, on_delete=models.PROTECT, related_name='rfqs')
    number = models.CharField(max_length=40)
    deadline = models.DateField(null=True, blank=True)
    status = models.CharField(max_length=20, choices=STATUS_CHOICES, default='draft', db_index=True)
    notes = models.TextField(blank=True)
    created_by = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.PROTECT, related_name='created_procurement_rfqs')
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        constraints = [models.UniqueConstraint(fields=('company', 'number'), name='unique_rfq_company_number')]
        ordering = ('-created_at',)


class SupplierQuotation(models.Model):
    STATUS_CHOICES = [('received', 'Received'), ('shortlisted', 'Shortlisted'), ('accepted', 'Accepted'), ('rejected', 'Rejected')]
    rfq = models.ForeignKey(RequestForQuotation, on_delete=models.CASCADE, related_name='quotations')
    supplier = models.ForeignKey(Supplier, on_delete=models.PROTECT, related_name='quotations')
    quote_number = models.CharField(max_length=80)
    quoted_total = models.DecimalField(max_digits=14, decimal_places=2)
    lead_time_days = models.PositiveIntegerField(default=0)
    valid_until = models.DateField(null=True, blank=True)
    status = models.CharField(max_length=20, choices=STATUS_CHOICES, default='received', db_index=True)
    notes = models.TextField(blank=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        constraints = [models.UniqueConstraint(fields=('rfq', 'supplier'), name='unique_rfq_supplier_quote')]

    def clean(self):
        if self.supplier_id and self.rfq_id and self.supplier.company_id != self.rfq.company_id:
            raise ValidationError('Supplier must belong to the RFQ company.')
        if self.quoted_total < 0:
            raise ValidationError('Quoted total cannot be negative.')


class PurchaseOrder(models.Model):
    STATUS_CHOICES = [('draft', 'Draft'), ('submitted', 'Submitted'), ('returned', 'Returned for correction'), ('approved', 'Approved'), ('rejected', 'Rejected'), ('partially_received', 'Partially received'), ('received', 'Received'), ('cancelled', 'Cancelled')]
    company = models.ForeignKey('accounts.Company', on_delete=models.CASCADE, related_name='purchase_orders')
    requisition = models.OneToOneField(PurchaseRequisition, on_delete=models.PROTECT, related_name='purchase_order')
    supplier = models.ForeignKey(Supplier, on_delete=models.PROTECT, related_name='purchase_orders')
    quotation = models.ForeignKey(SupplierQuotation, on_delete=models.SET_NULL, null=True, blank=True, related_name='purchase_orders')
    number = models.CharField(max_length=40)
    requested_delivery_date = models.DateField(null=True, blank=True)
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
        if self.quotation_id and self.quotation.rfq.company_id != self.company_id:
            raise ValidationError('Quotation must belong to the purchase order company.')

    @property
    def total_amount(self):
        return sum((line.line_total for line in self.lines.all()), 0)

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

    @property
    def line_total(self):
        return self.ordered_quantity * self.unit_cost


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


class QualityInspection(models.Model):
    RESULT_CHOICES = [('pending', 'Pending'), ('passed', 'Passed'), ('failed', 'Failed'), ('conditional', 'Conditional')]
    receipt = models.OneToOneField(GoodsReceipt, on_delete=models.CASCADE, related_name='inspection')
    inspected_by = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.PROTECT, related_name='procurement_inspections')
    result = models.CharField(max_length=20, choices=RESULT_CHOICES, default='pending')
    criteria = models.TextField(blank=True)
    findings = models.TextField(blank=True)
    inspected_at = models.DateTimeField(default=timezone.now)


class SupplierContract(models.Model):
    STATUS_CHOICES = [('draft', 'Draft'), ('active', 'Active'), ('expired', 'Expired'), ('terminated', 'Terminated')]
    company = models.ForeignKey('accounts.Company', on_delete=models.CASCADE, related_name='supplier_contracts')
    supplier = models.ForeignKey(Supplier, on_delete=models.PROTECT, related_name='contracts')
    number = models.CharField(max_length=80)
    start_date = models.DateField()
    end_date = models.DateField()
    value = models.DecimalField(max_digits=14, decimal_places=2, default=0)
    status = models.CharField(max_length=20, choices=STATUS_CHOICES, default='draft', db_index=True)
    terms = models.TextField(blank=True)
    owner = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.PROTECT, related_name='owned_supplier_contracts')

    class Meta:
        constraints = [models.UniqueConstraint(fields=('company', 'number'), name='unique_contract_company_number')]

    def clean(self):
        if self.supplier_id and self.supplier.company_id != self.company_id:
            raise ValidationError('Supplier must belong to the contract company.')
        if self.end_date < self.start_date:
            raise ValidationError('Contract end date must be after its start date.')


class SupplierRisk(models.Model):
    LEVEL_CHOICES = [('low', 'Low'), ('medium', 'Medium'), ('high', 'High'), ('critical', 'Critical')]
    STATUS_CHOICES = [('open', 'Open'), ('mitigated', 'Mitigated'), ('accepted', 'Accepted')]
    company = models.ForeignKey('accounts.Company', on_delete=models.CASCADE, related_name='supplier_risks')
    supplier = models.ForeignKey(Supplier, on_delete=models.PROTECT, related_name='risks')
    title = models.CharField(max_length=160)
    description = models.TextField(blank=True)
    level = models.CharField(max_length=20, choices=LEVEL_CHOICES, default='medium', db_index=True)
    status = models.CharField(max_length=20, choices=STATUS_CHOICES, default='open', db_index=True)
    mitigation = models.TextField(blank=True)
    owner = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.PROTECT, related_name='owned_supplier_risks')
    created_at = models.DateTimeField(auto_now_add=True)

    def clean(self):
        if self.supplier_id and self.supplier.company_id != self.company_id:
            raise ValidationError('Supplier must belong to the risk company.')


class SupplierInvoiceMatch(models.Model):
    STATUS_CHOICES = [('draft', 'Draft'), ('matched', 'Matched'), ('exception', 'Exception'), ('approved', 'Approved'), ('paid', 'Paid')]
    company = models.ForeignKey('accounts.Company', on_delete=models.CASCADE, related_name='supplier_invoice_matches')
    order = models.ForeignKey(PurchaseOrder, on_delete=models.PROTECT, related_name='invoice_matches')
    supplier = models.ForeignKey(Supplier, on_delete=models.PROTECT, related_name='invoice_matches')
    invoice_number = models.CharField(max_length=80)
    invoice_date = models.DateField()
    due_date = models.DateField(null=True, blank=True)
    invoice_total = models.DecimalField(max_digits=14, decimal_places=2)
    status = models.CharField(max_length=20, choices=STATUS_CHOICES, default='draft', db_index=True)
    exception_reason = models.TextField(blank=True)
    approved_by = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.SET_NULL, null=True, blank=True, related_name='approved_supplier_invoice_matches')
    paid_at = models.DateTimeField(null=True, blank=True)
    created_by = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.PROTECT, related_name='created_supplier_invoice_matches')
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        constraints = [models.UniqueConstraint(fields=('company', 'invoice_number'), name='unique_supplier_invoice_match')]

    @property
    def order_total(self):
        return self.order.total_amount

    def evaluate(self):
        self.status = 'matched' if self.invoice_total == self.order_total else 'exception'
        if self.status == 'matched':
            self.exception_reason = ''
        elif not self.exception_reason:
            self.exception_reason = 'Invoice total does not match the purchase order total.'
        return self.status


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
