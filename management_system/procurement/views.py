from django.contrib import messages
from django.core.exceptions import ValidationError
from django.db import transaction
from django.shortcuts import get_object_or_404, redirect, render
from django.utils import timezone
from django.views.decorators.http import require_POST

from governance.decorators import capability_required
from governance.models import AuditEvent
from governance.services import decide_approval, latest_approval_for, submit_for_approval
from inventory.models import Stock

from .forms import GoodsReceiptForm, PurchaseOrderForm, PurchaseRequisitionForm, SupplierForm
from .models import PurchaseOrder, PurchaseOrderLine, PurchaseRequisition, PurchaseRequisitionLine, Supplier
from .services import receive_goods


@capability_required('procurement.view')
def supplier_list(request):
    return render(request, 'procurement/supplier_list.html', {'suppliers': Supplier.objects.filter(company=request.user.company)})


@capability_required('procurement.manage')
def supplier_create(request):
    form = SupplierForm(request.POST or None)
    if request.method == 'POST' and form.is_valid():
        supplier = form.save(commit=False)
        supplier.company = request.user.company
        supplier.save()
        AuditEvent.record(actor=request.user, module='procurement', action='supplier_created', obj=supplier, request=request)
        return redirect('procurement:supplier_list')
    return render(request, 'procurement/form.html', {'form': form, 'title': 'New supplier'})


@capability_required('procurement.manage')
def requisition_create(request):
    company = request.user.company
    form = PurchaseRequisitionForm(request.POST or None)
    line_forms = []
    if request.method == 'POST' and form.is_valid():
        stock_ids = request.POST.getlist('stock_id')
        quantities = request.POST.getlist('quantity')
        if not stock_ids or len(stock_ids) != len(quantities):
            form.add_error(None, 'Add at least one stock line.')
        else:
            with transaction.atomic():
                requisition = form.save(commit=False)
                requisition.company = company
                requisition.requested_by = request.user
                requisition.save()
                for stock_id, quantity in zip(stock_ids, quantities):
                    stock = get_object_or_404(Stock, pk=stock_id, company=company)
                    PurchaseRequisitionLine.objects.create(requisition=requisition, stock=stock, quantity=quantity)
            AuditEvent.record(actor=request.user, company=company, module='procurement', action='requisition_created', obj=requisition, request=request)
            return redirect('procurement:requisition_list')
    stocks = Stock.objects.filter(company=company).order_by('name')
    return render(request, 'procurement/requisition_form.html', {'form': form, 'stocks': stocks})


@capability_required('procurement.view')
def requisition_list(request):
    requisitions = PurchaseRequisition.objects.filter(company=request.user.company).select_related('requested_by').prefetch_related('lines__stock')
    return render(request, 'procurement/requisition_list.html', {'requisitions': requisitions})


@capability_required('procurement.approve')
@require_POST
def requisition_decide(request, pk):
    requisition = get_object_or_404(PurchaseRequisition, pk=pk, company=request.user.company)
    decision = {'approve': 'approved', 'reject': 'rejected', 'return': 'returned'}.get(request.POST.get('decision'), 'rejected')
    try:
        approval = latest_approval_for(requisition)
        if approval is None:
            raise ValidationError('No approval request exists for this requisition.')
        decide_approval(approval=approval, actor=request.user, decision=decision, reason=request.POST.get('reason', ''), request=request)
        requisition.decision_by = request.user
        requisition.decision_reason = request.POST.get('reason', '')
        requisition.decided_at = timezone.now()
        requisition.save(update_fields=['decision_by', 'decision_reason', 'decided_at'])
        messages.success(request, 'Requisition decision saved.')
    except Exception as exc:
        messages.error(request, str(exc))
    return redirect('procurement:requisition_list')


@capability_required('procurement.manage')
@require_POST
def requisition_submit(request, pk):
    requisition = get_object_or_404(PurchaseRequisition, pk=pk, company=request.user.company)
    try:
        with transaction.atomic():
            requisition.submit()
            submit_for_approval(target=requisition, requester=request.user, transaction_type='purchase_requisition', request=request)
        messages.success(request, 'Requisition submitted for approval.')
    except Exception as exc:
        messages.error(request, str(exc))
    return redirect('procurement:requisition_list')


@capability_required('procurement.manage')
def purchase_order_create(request, requisition_pk):
    requisition = get_object_or_404(PurchaseRequisition, pk=requisition_pk, company=request.user.company, status='approved')
    form = PurchaseOrderForm(request.POST or None, company=request.user.company)
    if request.method == 'POST' and form.is_valid():
        with transaction.atomic():
            order = form.save(commit=False)
            order.company = request.user.company
            order.requisition = requisition
            order.save()
            for line in requisition.lines.all():
                PurchaseOrderLine.objects.create(order=order, stock=line.stock, ordered_quantity=line.quantity)
            requisition.status = 'converted'
            requisition.save(update_fields=['status'])
        AuditEvent.record(actor=request.user, company=request.user.company, module='procurement', action='purchase_order_created', obj=order, request=request)
        return redirect('procurement:order_list')
    return render(request, 'procurement/form.html', {'form': form, 'title': 'New purchase order'})


@capability_required('procurement.view')
def order_list(request):
    orders = PurchaseOrder.objects.filter(company=request.user.company).select_related('supplier', 'requisition')
    return render(request, 'procurement/order_list.html', {'orders': orders})


@capability_required('procurement.manage')
@require_POST
def order_submit(request, pk):
    order = get_object_or_404(PurchaseOrder, pk=pk, company=request.user.company)
    try:
        with transaction.atomic():
            order.submit()
            submit_for_approval(target=order, requester=request.user, transaction_type='purchase_order', request=request)
        messages.success(request, 'Purchase order submitted for approval.')
    except Exception as exc:
        messages.error(request, str(exc))
    return redirect('procurement:order_list')


@capability_required('procurement.approve')
@require_POST
def order_approve(request, pk):
    order = get_object_or_404(PurchaseOrder, pk=pk, company=request.user.company)
    try:
        approval = latest_approval_for(order)
        if approval is None:
            raise ValidationError('No approval request exists for this purchase order.')
        decide_approval(approval=approval, actor=request.user, decision='approved', request=request)
        if approval.status == 'approved':
            order.status = 'approved'
            order.approved_by = request.user
            order.approved_at = timezone.now()
            order.save(update_fields=['status', 'approved_by', 'approved_at'])
        messages.success(request, 'Purchase order approved.')
    except Exception as exc:
        messages.error(request, str(exc))
    return redirect('procurement:order_list')


@capability_required('procurement.manage')
def goods_receipt_create(request, order_pk):
    order = get_object_or_404(PurchaseOrder, pk=order_pk, company=request.user.company)
    form = GoodsReceiptForm(request.POST or None, order=order)
    if request.method == 'POST' and form.is_valid():
        try:
            quantities = {str(line.pk): form.cleaned_data.get(f'quantity_{line.pk}', 0) for line in order.lines.all()}
            receive_goods(order=order, received_by=request.user, receipt_number=form.cleaned_data['receipt_number'], quantities=quantities, notes=form.cleaned_data['notes'])
            messages.success(request, 'Goods receipt posted and stock updated.')
            return redirect('procurement:order_list')
        except Exception as exc:
            form.add_error(None, str(exc))
    return render(request, 'procurement/goods_receipt_form.html', {'form': form, 'order': order})
