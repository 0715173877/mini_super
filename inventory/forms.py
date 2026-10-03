from django import forms
from django.core.validators import EmailValidator, RegexValidator
from .models import *
from django.forms import inlineformset_factory

# NOTE: the purchase-order item formset lives further down this module (next to
# PurchaseOrderItemForm) so it can reuse that form class. Do not add a second
# definition here — a duplicate used to shadow the real one and silently
# swallowed the expiry_date field.

class CategoryForm(forms.ModelForm):
    class Meta:
        model = Category
        fields = ['name', 'description']
        widgets = {
            'name': forms.TextInput(attrs={
                'class': 'form-control',
                'placeholder': 'Enter category name...',
                'autofocus': True
            }),
            'description': forms.Textarea(attrs={
                'class': 'form-control',
                'placeholder': 'Enter category description (optional)...',
                'rows': 3
            }),
        }
        labels = {
            'name': 'Category Name',
            'description': 'Description'
        }
        help_texts = {
            'name': 'Enter a descriptive name for the product category.',
            'description': 'Optional description to help identify this category.'
        }

    def clean_name(self):
        name = self.cleaned_data.get('name')
        if name:
            # Check if category with this name already exists (excluding current instance)
            existing_categories = Category.objects.filter(name__iexact=name)
            if self.instance and self.instance.pk:
                existing_categories = existing_categories.exclude(pk=self.instance.pk)
            
            if existing_categories.exists():
                raise forms.ValidationError('A category with this name already exists.')
        
        return name

class SupplierForm(forms.ModelForm):
    phone_validator = RegexValidator(
        regex=r'^\+?1?\d{9,15}$',
        message="Phone number must be entered in the format: '+999999999'. Up to 15 digits allowed."
    )

    phone = forms.CharField(
        validators=[phone_validator],
        required=False,
        widget=forms.TextInput(attrs={
            'class': 'form-control',
            'placeholder': '+1-555-012-3456'
        })
    )

    class Meta:
        model = Supplier
        fields = ['name', 'contact_person', 'email', 'phone', 'address', 'is_active']
        widgets = {
            'name': forms.TextInput(attrs={
                'class': 'form-control',
                'placeholder': 'Enter supplier company name...',
                'autofocus': True
            }),
            'contact_person': forms.TextInput(attrs={
                'class': 'form-control',
                'placeholder': 'Enter contact person name...'
            }),
            'email': forms.EmailInput(attrs={
                'class': 'form-control',
                'placeholder': 'supplier@company.com'
            }),
            'address': forms.Textarea(attrs={
                'class': 'form-control',
                'placeholder': 'Enter supplier address...',
                'rows': 3
            }),
            'is_active': forms.CheckboxInput(attrs={
                'class': 'form-check-input'
            }),
        }
        labels = {
            'name': 'Supplier Name',
            'contact_person': 'Contact Person',
            'email': 'Email Address',
            'phone': 'Phone Number',
            'address': 'Address',
            'is_active': 'Active Supplier'
        }
        help_texts = {
            'name': 'The official name of the supplier company.',
            'contact_person': 'Primary contact person at the supplier.',
            'email': 'Primary email address for communication.',
            'phone': 'Contact phone number with country code.',
            'address': 'Physical address of the supplier.',
            'is_active': 'Uncheck to temporarily disable this supplier.'
        }

    def clean_email(self):
        email = self.cleaned_data.get('email')
        if email:
            # Check if supplier with this email already exists (excluding current instance)
            existing_suppliers = Supplier.objects.filter(email__iexact=email)
            if self.instance and self.instance.pk:
                existing_suppliers = existing_suppliers.exclude(pk=self.instance.pk)
            
            if existing_suppliers.exists():
                raise forms.ValidationError('A supplier with this email already exists.')
        
        return email

    def clean_name(self):
        name = self.cleaned_data.get('name')
        if name:
            # Check if supplier with this name already exists (excluding current instance)
            existing_suppliers = Supplier.objects.filter(name__iexact=name)
            if self.instance and self.instance.pk:
                existing_suppliers = existing_suppliers.exclude(pk=self.instance.pk)
            
            if existing_suppliers.exists():
                raise forms.ValidationError('A supplier with this name already exists.')
        
        return name

class ProductForm(forms.ModelForm):
    class Meta:
        model = Product
        # No expiry_date here on purpose: a use-by date is a fact about a
        # delivery, so it is captured per line on the purchase order form (see
        # PurchaseOrderItemForm below). Product.expiry_date is derived from those
        # lines and is read-only.
        fields = [
            'name', 'sku', 'barcode', 'category', 'supplier', 'product_type',
            'cost_price', 'selling_price', 'current_stock', 
            'min_stock_level', 'max_stock_level',
            'requires_refrigeration', 'is_high_value', 'is_high_theft_risk'
        ]
        widgets = {
            'name': forms.TextInput(attrs={
                'class': 'form-control',
                'placeholder': 'Enter product name...'
            }),
            'sku': forms.TextInput(attrs={
                'class': 'form-control',
                'placeholder': 'PROD-001'
            }),
            'barcode': forms.TextInput(attrs={
                'class': 'form-control',
                'placeholder': '1234567890123'
            }),
            'category': forms.Select(attrs={
                'class': 'form-select'
            }),
            'supplier': forms.Select(attrs={
                'class': 'form-select'
            }),
            'product_type': forms.Select(attrs={
                'class': 'form-select'
            }),
            'cost_price': forms.NumberInput(attrs={
                'class': 'form-control',
                'step': '0.01',
                'min': '0',
                'placeholder': '0.00'
            }),
            'selling_price': forms.NumberInput(attrs={
                'class': 'form-control',
                'step': '0.01',
                'min': '0',
                'placeholder': '0.00'
            }),
            'current_stock': forms.NumberInput(attrs={
                'class': 'form-control',
                'step': '0.001',
                'min': '0',
                'placeholder': '0'
            }),
            'min_stock_level': forms.NumberInput(attrs={
                'class': 'form-control',
                'step': '0.001',
                'min': '0',
                'placeholder': '0'
            }),
            'max_stock_level': forms.NumberInput(attrs={
                'class': 'form-control',
                'step': '0.001',
                'min': '0',
                'placeholder': '0'
            }),
            'requires_refrigeration': forms.CheckboxInput(attrs={
                'class': 'form-check-input'
            }),
            'is_high_value': forms.CheckboxInput(attrs={
                'class': 'form-check-input'
            }),
            'is_high_theft_risk': forms.CheckboxInput(attrs={
                'class': 'form-check-input'
            }),
        }
        labels = {
            'name': 'Product Name',
            'sku': 'SKU',
            'barcode': 'Barcode',
            'category': 'Category',
            'supplier': 'Supplier',
            'product_type': 'Product Type',
            'cost_price': 'Cost Price',
            'selling_price': 'Selling Price',
            'current_stock': 'Current Stock',
            'min_stock_level': 'Minimum Stock Level',
            'max_stock_level': 'Maximum Stock Level',
            'requires_refrigeration': 'Requires Refrigeration',
            'is_high_value': 'High Value Item',
            'is_high_theft_risk': 'High Theft Risk'
        }

    def clean_sku(self):
        sku = self.cleaned_data.get('sku')
        if sku:
            # Check if product with this SKU already exists (excluding current instance)
            existing_products = Product.objects.filter(sku__iexact=sku)
            if self.instance and self.instance.pk:
                existing_products = existing_products.exclude(pk=self.instance.pk)
            
            if existing_products.exists():
                raise forms.ValidationError('A product with this SKU already exists.')
        
        return sku

    def clean_selling_price(self):
        cost_price = self.cleaned_data.get('cost_price')
        selling_price = self.cleaned_data.get('selling_price')
        
        if cost_price and selling_price:
            if selling_price < cost_price:
                raise forms.ValidationError('Selling price cannot be less than cost price.')
        
        return selling_price

    def clean_max_stock_level(self):
        min_stock = self.cleaned_data.get('min_stock_level')
        max_stock = self.cleaned_data.get('max_stock_level')
        
        if min_stock and max_stock:
            if max_stock < min_stock:
                raise forms.ValidationError('Maximum stock level cannot be less than minimum stock level.')
        
        return max_stock

class PurchaseOrderForm(forms.ModelForm):
    class Meta:
        model = PurchaseOrder
        fields = ['supplier', 'expected_delivery']
        widgets = {
            'supplier': forms.Select(attrs={
                'class': 'form-select'
            }),
            'expected_delivery': forms.DateInput(attrs={
                'class': 'form-control',
                'type': 'date'
            }),
        }
        labels = {
            'supplier': 'Supplier',
            'expected_delivery': 'Expected Delivery Date'
        }

class PurchaseOrderItemForm(forms.ModelForm):
    class Meta:
        model = PurchaseOrderItem
        # expiry_date is the use-by date printed on the delivery — the only place
        # a shelf life is ever recorded. The product's expiry is derived from the
        # lines of the orders it has received, which is what the alerts read.
        fields = ['product', 'quantity', 'unit_cost', 'expiry_date']
        widgets = {
            'product': forms.Select(attrs={
                'class': 'form-select'
            }),
            'quantity': forms.NumberInput(attrs={
                'class': 'form-control',
                'step': '0.001',
                'min': '0.001'
            }),
            'unit_cost': forms.NumberInput(attrs={
                'class': 'form-control',
                'step': '0.01',
                'min': '0'
            }),
            'expiry_date': forms.DateInput(
                attrs={
                    'class': 'form-control',
                    'type': 'date',
                },
                format='%Y-%m-%d',
            ),
        }

class StockAdjustmentForm(forms.Form):
    ADJUSTMENT_TYPES = [
        ('add', 'Add Stock'),
        ('remove', 'Remove Stock'),
    ]
    
    adjustment_type = forms.ChoiceField(
        choices=ADJUSTMENT_TYPES,
        widget=forms.RadioSelect(attrs={
            'class': 'form-check-input'
        }),
        initial='add'
    )
    
    quantity = forms.DecimalField(
        max_digits=10,
        decimal_places=3,
        min_value=0.001,
        widget=forms.NumberInput(attrs={
            'class': 'form-control',
            'step': '0.001',
            'placeholder': '0.000'
        })
    )
    
    reason = forms.CharField(
        widget=forms.Textarea(attrs={
            'class': 'form-control',
            'rows': 3,
            'placeholder': 'Explain the reason for this stock adjustment...'
        }),
        required=True
    )

# Formset for purchase order items
PurchaseOrderItemFormSet = forms.inlineformset_factory(
    PurchaseOrder,
    PurchaseOrderItem,
    form=PurchaseOrderItemForm,
    extra=1,
    can_delete=True
)

class SupplierReturnForm(forms.ModelForm):
    class Meta:
        model = SupplierReturn
        fields = ['supplier', 'purchase_order', 'reason']
        widgets = {
            'supplier': forms.Select(attrs={'class': 'form-select'}),
            'purchase_order': forms.Select(attrs={'class': 'form-select'}),
            'reason': forms.Textarea(attrs={
                'class': 'form-control',
                'rows': 3,
                'placeholder': 'Why are these goods going back to the supplier?',
            }),
        }
        labels = {
            'supplier': 'Supplier',
            'purchase_order': 'Purchase Order',
            'reason': 'Reason',
        }
        help_texts = {
            'supplier': 'Optional — leave blank for a walk-in / unknown vendor.',
            'purchase_order': 'Optional — link this return to the original purchase order.',
            'reason': 'Optional note explaining the return.',
        }


class SupplierReturnItemForm(forms.ModelForm):
    class Meta:
        model = SupplierReturnItem
        fields = ('product', 'quantity', 'unit_cost')
        widgets = {
            'product': forms.Select(attrs={'class': 'form-select product-select'}),
            'quantity': forms.NumberInput(attrs={
                'class': 'form-control',
                'step': '0.001',
                'min': '0.001',
            }),
            'unit_cost': forms.NumberInput(attrs={
                'class': 'form-control',
                'step': '0.01',
                'min': '0',
            }),
        }


SupplierReturnItemFormSet = inlineformset_factory(
    SupplierReturn,
    SupplierReturnItem,
    form=SupplierReturnItemForm,
    extra=1,
    can_delete=True,
)


class CategoryFilterForm(forms.Form):
    name = forms.CharField(
        required=False,
        widget=forms.TextInput(attrs={
            'class': 'form-control',
            'placeholder': 'Search categories...'
        })
    )

class SupplierFilterForm(forms.Form):
    name = forms.CharField(
        required=False,
        widget=forms.TextInput(attrs={
            'class': 'form-control',
            'placeholder': 'Search suppliers...'
        })
    )
    
    is_active = forms.ChoiceField(
        choices=[
            ('', 'All Status'),
            ('active', 'Active Only'),
            ('inactive', 'Inactive Only'),
        ],
        required=False,
        widget=forms.Select(attrs={
            'class': 'form-select'
        })
    )

class ProductFilterForm(forms.Form):
    name = forms.CharField(
        required=False,
        widget=forms.TextInput(attrs={
            'class': 'form-control',
            'placeholder': 'Search products...'
        })
    )
    
    category = forms.ModelChoiceField(
        queryset=Category.objects.all(),
        required=False,
        widget=forms.Select(attrs={
            'class': 'form-select'
        }),
        empty_label="All Categories"
    )
    
    supplier = forms.ModelChoiceField(
        queryset=Supplier.objects.all(),
        required=False,
        widget=forms.Select(attrs={
            'class': 'form-select'
        }),
        empty_label="All Suppliers"
    )
    
    stock_status = forms.ChoiceField(
        choices=[
            ('', 'All Stock'),
            ('low', 'Low Stock'),
            ('out', 'Out of Stock'),
            ('healthy', 'Healthy Stock'),
        ],
        required=False,
        widget=forms.Select(attrs={
            'class': 'form-select'
        })
    )