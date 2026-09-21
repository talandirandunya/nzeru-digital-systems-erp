from django import forms

from .models import GoodsReceipt, PurchaseOrder, PurchaseRequisition, Supplier


class SupplierForm(forms.ModelForm):
    class Meta:
        model = Supplier
        fields = ['name', 'email', 'phone', 'address', 'is_active']


class PurchaseRequisitionForm(forms.ModelForm):
    class Meta:
        model = PurchaseRequisition
        fields = ['number']


class PurchaseOrderForm(forms.ModelForm):
    class Meta:
        model = PurchaseOrder
        fields = ['number', 'supplier']

    def __init__(self, *args, company=None, **kwargs):
        super().__init__(*args, **kwargs)
        if company:
            self.fields['supplier'].queryset = Supplier.objects.filter(company=company, is_active=True)


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
