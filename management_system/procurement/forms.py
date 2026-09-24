from django import forms

from .models import (
    GoodsReceipt, PurchaseOrder, PurchaseRequisition, RequestForQuotation,
    Supplier, SupplierContract, SupplierInvoiceMatch, SupplierQuotation,
    SupplierRisk, QualityInspection,
)


class SupplierForm(forms.ModelForm):
    class Meta:
        model = Supplier
        fields = ['name', 'email', 'phone', 'address', 'tax_id', 'category', 'is_active']


class PurchaseRequisitionForm(forms.ModelForm):
    class Meta:
        model = PurchaseRequisition
        fields = ['number', 'budget_amount']


class PurchaseOrderForm(forms.ModelForm):
    class Meta:
        model = PurchaseOrder
        fields = ['number', 'supplier', 'quotation', 'requested_delivery_date']

    def __init__(self, *args, company=None, **kwargs):
        super().__init__(*args, **kwargs)
        if company:
            self.fields['supplier'].queryset = Supplier.objects.filter(company=company, is_active=True)
            self.fields['quotation'].queryset = SupplierQuotation.objects.filter(rfq__company=company, status__in=('received', 'shortlisted', 'accepted')).select_related('supplier')


class RequestForQuotationForm(forms.ModelForm):
    class Meta:
        model = RequestForQuotation
        fields = ['requisition', 'number', 'deadline', 'status', 'notes']

    def __init__(self, *args, company=None, **kwargs):
        super().__init__(*args, **kwargs)
        if company:
            self.fields['requisition'].queryset = PurchaseRequisition.objects.filter(company=company, status='approved')


class SupplierQuotationForm(forms.ModelForm):
    class Meta:
        model = SupplierQuotation
        fields = ['rfq', 'supplier', 'quote_number', 'quoted_total', 'lead_time_days', 'valid_until', 'status', 'notes']

    def __init__(self, *args, company=None, **kwargs):
        super().__init__(*args, **kwargs)
        if company:
            self.fields['rfq'].queryset = RequestForQuotation.objects.filter(company=company, status__in=('open', 'closed'))
            self.fields['supplier'].queryset = Supplier.objects.filter(company=company, is_active=True)


class SupplierContractForm(forms.ModelForm):
    class Meta:
        model = SupplierContract
        fields = ['supplier', 'number', 'start_date', 'end_date', 'value', 'status', 'terms']

    def __init__(self, *args, company=None, owner=None, **kwargs):
        super().__init__(*args, **kwargs)
        if company:
            self.fields['supplier'].queryset = Supplier.objects.filter(company=company, is_active=True)


class SupplierRiskForm(forms.ModelForm):
    class Meta:
        model = SupplierRisk
        fields = ['supplier', 'title', 'description', 'level', 'status', 'mitigation']

    def __init__(self, *args, company=None, **kwargs):
        super().__init__(*args, **kwargs)
        if company:
            self.fields['supplier'].queryset = Supplier.objects.filter(company=company)


class QualityInspectionForm(forms.ModelForm):
    class Meta:
        model = QualityInspection
        fields = ['result', 'criteria', 'findings']


class SupplierInvoiceMatchForm(forms.ModelForm):
    class Meta:
        model = SupplierInvoiceMatch
        fields = ['order', 'invoice_number', 'invoice_date', 'due_date', 'invoice_total', 'exception_reason']

    def __init__(self, *args, company=None, **kwargs):
        super().__init__(*args, **kwargs)
        if company:
            self.fields['order'].queryset = PurchaseOrder.objects.filter(company=company, status__in=('approved', 'partially_received', 'received')).select_related('supplier')


class GoodsReceiptForm(forms.Form):
    receipt_number = forms.CharField(max_length=40)
    notes = forms.CharField(required=False, widget=forms.Textarea)

    def __init__(self, *args, order=None, **kwargs):
        self.order = order
        super().__init__(*args, **kwargs)
        for line in order.lines.select_related('stock'):
            self.fields[f'quantity_{line.pk}'] = forms.IntegerField(min_value=0, required=False, label=f'{line.stock.name} (ordered: {line.ordered_quantity})')

    def quantities(self):
        return {str(line.pk): self.cleaned_data.get(f'quantity_{line.pk}', 0) for line in self.order.lines.all()}
