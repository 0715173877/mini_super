from django import forms
from django.forms import inlineformset_factory

from .models import CustomerReturn, CustomerReturnItem


class CustomerReturnForm(forms.ModelForm):
    class Meta:
        model = CustomerReturn
        fields = ['customer', 'sale', 'reason']
        widgets = {
            'customer': forms.Select(attrs={'class': 'form-select'}),
            # Driven by the searchable "Original Sale" picker in the template,
            # which keeps this hidden input in sync with the chosen sale.
            'sale': forms.HiddenInput(),
            'reason': forms.Textarea(attrs={
                'class': 'form-control',
                'rows': 3,
                'placeholder': 'Why is the customer returning these items?',
            }),
        }
        labels = {
            'customer': 'Customer',
            'sale': 'Original Sale',
            'reason': 'Reason',
        }
        help_texts = {
            'customer': 'Optional — leave blank for a walk-in customer.',
            'sale': 'Optional — link this return to the original sale.',
            'reason': 'Optional note explaining the return.',
        }


class CustomerReturnItemForm(forms.ModelForm):
    class Meta:
        model = CustomerReturnItem
        fields = ('product', 'quantity', 'unit_price')
        widgets = {
            'product': forms.Select(attrs={'class': 'form-select product-select'}),
            'quantity': forms.NumberInput(attrs={
                'class': 'form-control',
                'step': '0.001',
                'min': '0.001',
            }),
            'unit_price': forms.NumberInput(attrs={
                'class': 'form-control',
                'step': '0.01',
                'min': '0',
            }),
        }


CustomerReturnItemFormSet = inlineformset_factory(
    CustomerReturn,
    CustomerReturnItem,
    form=CustomerReturnItemForm,
    extra=1,
    can_delete=True,
)
