from decimal import Decimal

from django.contrib import messages
from django.core.exceptions import ValidationError
from django.db import transaction
from django.db.models import Count, Q, Sum
from django.shortcuts import get_object_or_404, redirect, render
from django.utils import timezone
from django.views.decorators.http import require_POST

from governance.decorators import capability_required
from governance.models import AuditEvent
from governance.services import decide_approval, latest_approval_for, submit_for_approval
from inventory.models import Stock

from .forms import (
    GoodsReceiptForm, PurchaseOrderForm, PurchaseRequisitionForm, QualityInspectionForm,
    RequestForQuotationForm, SupplierContractForm, SupplierForm, SupplierInvoiceMatchForm,
    SupplierQuotationForm, SupplierRiskForm,
)
from .models import (
    GoodsReceipt, PurchaseOrder, PurchaseOrderLine, PurchaseRequisition,
    PurchaseRequisitionLine, QualityInspection, RequestForQuotation, Supplier,
    SupplierContract, SupplierInvoiceMatch, SupplierQuotation, SupplierRisk,
)
from .services import receive_goods


@capability_required('procurement.view')
def dashboard(request):
    company = request.user.company
    orders = PurchaseOrder.objects.filter(company=company)
    suppliers = Supplier.objects.filter(company=company).annotate(
        order_count=Count('purchase_orders', distinct=True),
        received_count=Count('purchase_orders', filter=Q(purchase_orders__status='received'), distinct=True),
        risk_count=Count('risks', filter=Q(risks__status='open'), distinct=True),
    )
    context = {
        'requisition_counts': PurchaseRequisition.objects.filter(company=company).values('status').annotate(total=Count('id')),
        'order_counts': orders.values('status').annotate(total=Count('id')),
        'open_requisitions': PurchaseRequisition.objects.filter(company=company, status__in=('submitted', 'approved')).count(),
        'orders_pending_approval': orders.filter(status='submitted').count(),
        'open_rfqs': RequestForQuotation.objects.filter(company=company, status='open').count(),
        'active_contracts': SupplierContract.objects.filter(company=company, status='active').count(),
        'open_risks': SupplierRisk.objects.filter(company=company, status='open').count(),
        'invoice_exceptions': SupplierInvoiceMatch.objects.filter(company=company, status='exception').count(),
        'committed_spend': sum((order.total_amount for order in orders.exclude(status='cancelled').prefetch_related('lines')), 0),
        'suppliers': suppliers.order_by('-risk_count', 'name')[:10],
    }
    return render(request, 'procurement/dashboard.html', context)


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
def rfq_create(request):
    form = RequestForQuotationForm(request.POST or None, company=request.user.company)
    if request.method == 'POST' and form.is_valid():
        rfq = form.save(commit=False)
        rfq.company = request.user.company
        rfq.created_by = request.user
        rfq.save()
        AuditEvent.record(actor=request.user, company=rfq.company, module='procurement', action='rfq_created', obj=rfq, request=request)
        return redirect('procurement:rfq_list')
    return render(request, 'procurement/form.html', {'form': form, 'title': 'New request for quotation'})


@capability_required('procurement.view')
def rfq_list(request):
    rfqs = RequestForQuotation.objects.filter(company=request.user.company).select_related('requisition').prefetch_related('quotations__supplier')
    return render(request, 'procurement/rfq_list.html', {'rfqs': rfqs})


@capability_required('procurement.manage')
def quotation_create(request):
    form = SupplierQuotationForm(request.POST or None, company=request.user.company)
    if request.method == 'POST' and form.is_valid():
        quote = form.save()
        AuditEvent.record(actor=request.user, company=request.user.company, module='procurement', action='quotation_created', obj=quote, request=request)
        return redirect('procurement:quotation_list')
    return render(request, 'procurement/form.html', {'form': form, 'title': 'Record supplier quotation'})


@capability_required('procurement.view')
def quotation_list(request):
    quotations = SupplierQuotation.objects.filter(rfq__company=request.user.company).select_related('rfq', 'supplier')
    return render(request, 'procurement/quotation_list.html', {'quotations': quotations})


@capability_required('procurement.manage')
def contract_create(request):
    form = SupplierContractForm(request.POST or None, company=request.user.company)
    if request.method == 'POST' and form.is_valid():
        contract = form.save(commit=False)
        contract.company = request.user.company
        contract.owner = request.user
        contract.save()
        return redirect('procurement:contract_list')
    return render(request, 'procurement/form.html', {'form': form, 'title': 'New supplier contract'})


@capability_required('procurement.view')
def contract_list(request):
    contracts = SupplierContract.objects.filter(company=request.user.company).select_related('supplier', 'owner')
    return render(request, 'procurement/contract_list.html', {'contracts': contracts})


@capability_required('procurement.manage')
def risk_create(request):
    form = SupplierRiskForm(request.POST or None, company=request.user.company)
    if request.method == 'POST' and form.is_valid():
        risk = form.save(commit=False)
        risk.company = request.user.company
        risk.owner = request.user
        risk.save()
        return redirect('procurement:risk_list')
    return render(request, 'procurement/form.html', {'form': form, 'title': 'Record supplier risk'})


@capability_required('procurement.view')
def risk_list(request):
    risks = SupplierRisk.objects.filter(company=request.user.company).select_related('supplier', 'owner')
    return render(request, 'procurement/risk_list.html', {'risks': risks})


@capability_required('procurement.manage')
def requisition_create(request):
    company = request.user.company
    form = PurchaseRequisitionForm(request.POST or None)
    if request.method == 'POST' and form.is_valid():
        stock_ids = request.POST.getlist('stock_id')
        quantities = request.POST.getlist('quantity')
        line_budgets = request.POST.getlist('line_budget')

        if not stock_ids:
            form.add_error(None, 'Add at least one stock line.')
        else:
            selected_lines = {}
            for stock_id, quantity, line_budget in zip(stock_ids, quantities, line_budgets + ['0'] * max(0, len(stock_ids) - len(line_budgets))):
                if not stock_id or not quantity:
                    continue
                stock = get_object_or_404(Stock, pk=stock_id, company=company)
                qty = int(quantity)
                if qty <= 0:
                    continue
                budget = Decimal(line_budget or '0') if line_budget else Decimal(str(stock.selling_price)) * qty
                if stock.pk in selected_lines:
                    selected_lines[stock.pk]['quantity'] += qty
                    selected_lines[stock.pk]['budget'] += budget
                else:
                    selected_lines[stock.pk] = {'stock': stock, 'quantity': qty, 'budget': budget}

            if not selected_lines:
                form.add_error(None, 'Select at least one valid item and enter a quantity.')
            else:
                with transaction.atomic():
                    requisition = form.save(commit=False)
                    requisition.company = company
                    requisition.requested_by = request.user
                    requisition.budget_amount = sum((entry['budget'] for entry in selected_lines.values()), Decimal('0'))
                    requisition.save()

                    for entry in selected_lines.values():
                        PurchaseRequisitionLine.objects.create(
                            requisition=requisition,
                            stock=entry['stock'],
                            quantity=entry['quantity'],
                        )
                AuditEvent.record(actor=request.user, company=company, module='procurement', action='requisition_created', obj=requisition, request=request)
                return redirect('procurement:requisition_list')
    stocks = Stock.objects.filter(company=company).order_by('name')
    stock_catalog = list(stocks.values('id', 'item_code', 'name', 'unit', 'quantity', 'selling_price', 'category__name'))
    return render(request, 'procurement/requisition_form.html', {'form': form, 'stocks': stocks, 'stock_catalog': stock_catalog})


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
                PurchaseOrderLine.objects.create(order=order, stock=line.stock, ordered_quantity=line.quantity, unit_cost=line.stock.cost_price)
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


@capability_required('procurement.manage')
def inspection_create(request, receipt_pk):
    receipt = get_object_or_404(GoodsReceipt, pk=receipt_pk, order__company=request.user.company)
    inspection = getattr(receipt, 'inspection', None)
    form = QualityInspectionForm(request.POST or None, instance=inspection)
    if request.method == 'POST' and form.is_valid():
        inspection = form.save(commit=False)
        inspection.receipt = receipt
        inspection.inspected_by = request.user
        inspection.save()
        return redirect('procurement:order_list')
    return render(request, 'procurement/form.html', {'form': form, 'title': f'Quality inspection for {receipt.receipt_number}'})


@capability_required('procurement.manage')
def invoice_match_create(request):
    form = SupplierInvoiceMatchForm(request.POST or None, company=request.user.company)
    if request.method == 'POST' and form.is_valid():
        invoice = form.save(commit=False)
        invoice.company = request.user.company
        invoice.supplier = invoice.order.supplier
        invoice.created_by = request.user
        invoice.evaluate()
        invoice.save()
        return redirect('procurement:invoice_match_list')
    return render(request, 'procurement/form.html', {'form': form, 'title': 'Verify supplier invoice'})


@capability_required('procurement.view')
def invoice_match_list(request):
    invoices = SupplierInvoiceMatch.objects.filter(company=request.user.company).select_related('order', 'supplier', 'approved_by')
    return render(request, 'procurement/invoice_match_list.html', {'invoices': invoices})


@capability_required('procurement.approve')
@require_POST
def invoice_match_approve(request, pk):
    invoice = get_object_or_404(SupplierInvoiceMatch, pk=pk, company=request.user.company)
    if invoice.status == 'matched':
        invoice.status = 'approved'
        invoice.approved_by = request.user
        invoice.save(update_fields=['status', 'approved_by'])
        messages.success(request, 'Invoice matched and approved.')
    else:
        messages.error(request, 'Only an exactly matched invoice can be approved.')
    return redirect('procurement:invoice_match_list')


@capability_required('procurement.manage')
@require_POST
def invoice_match_paid(request, pk):
    invoice = get_object_or_404(SupplierInvoiceMatch, pk=pk, company=request.user.company)
    if invoice.status != 'approved':
        messages.error(request, 'Only approved invoices can be marked paid.')
    else:
        invoice.status = 'paid'
        invoice.paid_at = timezone.now()
        invoice.save(update_fields=['status', 'paid_at'])
        messages.success(request, 'Invoice marked as paid.')
    return redirect('procurement:invoice_match_list')
