from django import forms
from django.core.exceptions import ValidationError
from .models import Client, Order
from accounts.models import Company
from inventory.models import Stock

class ClientRegistrationForm(forms.ModelForm):
    password = forms.CharField(widget=forms.PasswordInput)
    confirm_password = forms.CharField(widget=forms.PasswordInput, label="Confirm Password")

    class Meta:
        model = Client
        fields = ['first_name', 'last_name', 'email', 'phone', 'address', 'city', 'country', 'postal_code']
        widgets = {
            'address': forms.Textarea(attrs={'rows': 3}),
        }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        for field_name, field in self.fields.items():
            field.widget.attrs['class'] = 'form-control'

    def clean(self):
        cleaned_data = super().clean()
        password = cleaned_data.get('password')
        confirm_password = cleaned_data.get('confirm_password')

        # Check passwords match
        if password and confirm_password and password != confirm_password:
            self.add_error('confirm_password', 'Passwords do not match.')

        # Check if email already exists platform-wide
        email = cleaned_data.get('email')
        if email and Client.objects.filter(email=email).exists():
            self.add_error('email', 'An account with this email already exists.')

        return cleaned_data

    def save(self, commit=True):
        client = super().save(commit=False)
        client.set_password(self.cleaned_data['password'])

        if commit:
            client.save()
            # Create cart and wishlist for client
            from .models import Cart, Wishlist
            Cart.objects.create(client=client)
            Wishlist.objects.create(client=client)

        return client


class ClientLoginForm(forms.Form):
    email = forms.EmailField()
    password = forms.CharField(widget=forms.PasswordInput)

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        for field_name, field in self.fields.items():
            field.widget.attrs['class'] = 'form-control'

    def clean(self):
        cleaned_data = super().clean()
        email = cleaned_data.get('email')
        password = cleaned_data.get('password')

        if email and password:
            try:
                client = Client.objects.get(email=email, is_active=True)
                if not client.check_password(password):
                    raise ValidationError('Invalid email or password.')
                cleaned_data['client'] = client
            except Client.DoesNotExist:
                raise ValidationError('No account found with these credentials.')

        return cleaned_data


class ClientProfileForm(forms.ModelForm):
    class Meta:
        model = Client
        fields = ['first_name', 'last_name', 'phone', 'address', 'city', 'country', 'postal_code']
        widgets = {
            'address': forms.Textarea(attrs={'rows': 3}),
        }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        for field_name, field in self.fields.items():
            field.widget.attrs['class'] = 'form-control'


class CheckoutForm(forms.ModelForm):
    class Meta:
        model = Order
        fields = ['shipping_address', 'shipping_city', 'shipping_country', 'shipping_phone', 'notes']
        widgets = {
            'shipping_address': forms.Textarea(attrs={'rows': 3, 'class': 'form-control'}),
            'shipping_city': forms.TextInput(attrs={'class': 'form-control'}),
            'shipping_country': forms.TextInput(attrs={'class': 'form-control'}),
            'shipping_phone': forms.TextInput(attrs={'class': 'form-control', 'type': 'tel'}),
            'notes': forms.Textarea(attrs={'rows': 2, 'class': 'form-control', 'placeholder': 'Any special instructions?'}),
        }


class AddToCartForm(forms.Form):
    quantity = forms.IntegerField(min_value=1, initial=1)


class QuickOrderForm(forms.Form):
    PAYMENT_METHOD_CHOICES = [
        ('cash', 'Cash'),
        ('card', 'Card'),
        ('mobile', 'Mobile Money'),
        ('other', 'Other'),
    ]

    client = forms.ModelChoiceField(
        queryset=Client.objects.none(),
        required=False,
        empty_label='Walk-in customer',
        label='Existing Client',
    )
    first_name = forms.CharField(required=False, max_length=100)
    last_name = forms.CharField(required=False, max_length=100)
    email = forms.EmailField(required=False)
    phone = forms.CharField(required=False, max_length=20)
    payment_method = forms.ChoiceField(choices=PAYMENT_METHOD_CHOICES, required=False, initial='cash')
    payment_notes = forms.CharField(
        required=False,
        widget=forms.Textarea(attrs={'rows': 2, 'class': 'form-control'}),
        label='Order Notes',
    )

    def __init__(self, company=None, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.company = company
        if company is not None:
            self.fields['client'].queryset = Client.objects.filter(is_active=True).order_by('first_name', 'last_name')
            self.stock_queryset = Stock.objects.filter(
                company=company,
                quantity__gt=0,
            ).order_by('name')
        else:
            self.stock_queryset = Stock.objects.none()

        for field_name, field in self.fields.items():
            if field_name not in ['payment_notes']:
                field.widget.attrs['class'] = 'form-control'

    def clean(self):
        cleaned_data = super().clean()
        client = cleaned_data.get('client')
        first_name = cleaned_data.get('first_name')
        phone = cleaned_data.get('phone')

        if not client:
            if not first_name or not phone:
                raise ValidationError('Please select an existing client or provide at least a name and phone number for walk-in customer.')

        # Parse dynamic product_id and quantity fields from submitted POST data
        post_data = self.data
        product_ids = post_data.getlist('product_id') or post_data.getlist('product_id[]')
        quantities = post_data.getlist('quantity') or post_data.getlist('quantity[]')

        # Fallback for key-value pair submissions (e.g. stock_1, stock_2)
        if not product_ids:
            product_ids = []
            quantities = []
            for key in post_data.keys():
                if key.startswith('stock_') and post_data.get(key):
                    num = key.split('_')[1]
                    product_ids.append(post_data.get(key))
                    quantities.append(post_data.get(f'quantity_{num}', '1'))

        item_rows = []
        for pid, qty_str in zip(product_ids, quantities):
            if not pid:
                continue
            try:
                stock = self.stock_queryset.get(pk=pid)
                qty = int(qty_str)
                if qty < 1:
                    qty = 1
                if stock.quantity < qty:
                    self.add_error(None, f'Only {stock.quantity} units available for "{stock.name}".')
                item_rows.append({'stock': stock, 'quantity': qty})
            except (Stock.DoesNotExist, ValueError):
                continue

        if not item_rows:
            raise ValidationError('Please select at least one product with a valid quantity.')

        cleaned_data['items'] = item_rows
        return cleaned_data