from django import forms
from .models import Stock, StockTransaction, StockCategory
from django.core.exceptions import ValidationError

class StockForm(forms.ModelForm):
    class Meta:
        model = Stock
        fields = ['item_code', 'name', 'category', 'description','image', 'quantity', 
                  'unit', 'cost_price', 'selling_price', 'reorder_level', 'supplier_name', 
                  'supplier_contact', 'location', 'is_marketplace_visible', 'last_restocked']
        widgets = {
            'last_restocked': forms.DateInput(attrs={'type': 'date'}),
            'description': forms.Textarea(attrs={'rows': 3}),
             'image': forms.FileInput(attrs={'class': 'form-control', 'accept': 'image/*'}),
             'is_marketplace_visible': forms.CheckboxInput(attrs={'class': 'form-check-input'}),
        }
    
    def __init__(self, *args, **kwargs):
        self.company = kwargs.pop('company', None)
        super().__init__(*args, **kwargs)
        
        if self.company:
            # Filter categories to only those in the company
            self.fields['category'].queryset = StockCategory.objects.filter(company=self.company)
        
        # Make category and supplier_name non-required fields
        self.fields['category'].required = False
        self.fields['supplier_name'].required = False

class StockTransactionForm(forms.ModelForm):
    class Meta:
        model = StockTransaction
        fields = ['transaction_type', 'quantity', 'remarks']
        widgets = {
            'remarks': forms.Textarea(attrs={'rows': 3}),
        }
    
class StockCategoryForm(forms.ModelForm):
    class Meta:
        model = StockCategory
        fields = ['name', 'description']
        widgets = {
            'description': forms.Textarea(attrs={'rows': 3, 'class': 'form-control'}),
            'name': forms.TextInput(attrs={'class': 'form-control', 'placeholder': 'Category name'}),
        }
    
    def __init__(self, *args, **kwargs):
        self.company = kwargs.pop('company', None)
        super().__init__(*args, **kwargs)
    
    def clean_name(self):
        name = self.cleaned_data['name'].strip()
        if self.company:
            queryset = StockCategory.objects.filter(company=self.company, name=name)
            if self.instance and self.instance.pk:
                queryset = queryset.exclude(pk=self.instance.pk)
            if queryset.exists():
                raise ValidationError(f'Category "{name}" already exists in your company.')
        
        return name
    
    def save(self, commit=True):
        category = super().save(commit=False)
        if self.company:
            category.company = self.company
        
        if commit:
            category.save()
        
        return category  