from django.core.exceptions import ValidationError
from django.db import transaction
from django.db.models import Sum
from django.utils import timezone

from governance.models import AuditEvent
from inventory.models import Stock, StockTransaction

from .models import GoodsReceipt, GoodsReceiptLine, PurchaseOrder


@transaction.atomic
def receive_goods(*, order, received_by, receipt_number, quantities, notes=''):
    order = PurchaseOrder.objects.select_for_update().select_related('company').get(pk=order.pk)
    if order.status not in ('approved', 'partially_received'):
        raise ValidationError('Only approved purchase orders can receive goods.')
    receipt = GoodsReceipt.objects.create(order=order, received_by=received_by, receipt_number=receipt_number, notes=notes)
    total_ordered = 0
    total_received = 0
    for line in order.lines.select_for_update().select_related('stock'):
        quantity = int(quantities.get(str(line.pk), 0) or 0)
        already_received = line.receipt_lines.aggregate(total=Sum('quantity'))['total'] or 0
        if quantity < 0 or already_received + quantity > line.ordered_quantity:
            raise ValidationError(f'Receipt exceeds ordered quantity for {line.stock.name}.')
        total_ordered += line.ordered_quantity
        total_received += already_received + quantity
        if quantity:
            stock = Stock.objects.select_for_update().get(pk=line.stock_id, company=order.company)
            stock.quantity += quantity
            stock.last_restocked = timezone.localdate()
            stock.save(update_fields=['quantity', 'last_restocked', 'updated_at'])
            GoodsReceiptLine.objects.create(receipt=receipt, order_line=line, quantity=quantity)
            StockTransaction.objects.create(
                company=order.company, stock=stock, transaction_type='in', quantity=quantity,
                remarks=f'Goods receipt {receipt.receipt_number}', user=received_by,
            )
    if total_received == 0:
        raise ValidationError('At least one positive receipt quantity is required.')
    order.status = 'received' if total_received >= total_ordered else 'partially_received'
    order.save(update_fields=['status'])
    AuditEvent.record(actor=received_by, company=order.company, module='procurement', action='goods_received', obj=receipt, after={'status': order.status, 'quantity': total_received})
    return receipt
