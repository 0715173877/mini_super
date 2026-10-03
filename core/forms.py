from django import forms
from django.contrib.auth import get_user_model
from django.contrib.auth.models import Group
from django.contrib.auth.password_validation import validate_password
from django.core.exceptions import ValidationError

from .currencies import CUSTOM_CURRENCY
from .models import SiteSettings
from .permissions import GROUP_ORDER

#: The floor we ask of a new login, whatever AUTH_PASSWORD_VALIDATORS says.
MIN_PASSWORD_LENGTH = 8


class SiteSettingsForm(forms.ModelForm):
    class Meta:
        model = SiteSettings
        fields = [
            'currency',
            'symbol_override',
            'symbol_position',
            'decimal_places',
            'thousands_separator',
            'decimal_separator',
        ]
        widgets = {
            'currency': forms.Select(attrs={'class': 'form-select'}),
            'symbol_override': forms.TextInput(attrs={
                'class': 'form-control',
                'placeholder': 'e.g. TSh, FCFA, د.إ, Rp',
                'maxlength': 8,
                'autocomplete': 'off',
            }),
            'symbol_position': forms.Select(attrs={'class': 'form-select'}),
            'decimal_places': forms.Select(attrs={'class': 'form-select'}),
            'thousands_separator': forms.Select(attrs={'class': 'form-select'}),
            'decimal_separator': forms.Select(attrs={'class': 'form-select'}),
        }
        help_texts = {
            'symbol_override': 'Optional — overrides the symbol of the selected currency.',
            'decimal_places': 'Leave on automatic for the usual number of decimals of that currency.',
            'thousands_separator': 'Leave on automatic unless your customers expect a different layout.',
            'decimal_separator': 'Leave on automatic unless your customers expect a different layout.',
        }

    def clean(self):
        cleaned = super().clean()
        if cleaned.get('currency') == CUSTOM_CURRENCY and not (cleaned.get('symbol_override') or '').strip():
            self.add_error('symbol_override', 'Enter a symbol when using a custom currency.')


class StaffUserForm(forms.ModelForm):
    """Create a login and hand it one or more roles (Owner / Sell / Stock / SellerStock)."""

    password1 = forms.CharField(
        label='Password',
        strip=False,
        widget=forms.PasswordInput(attrs={'class': 'form-control', 'autocomplete': 'new-password'}),
        help_text='At least 8 characters.',
    )
    password2 = forms.CharField(
        label='Confirm password',
        strip=False,
        widget=forms.PasswordInput(attrs={'class': 'form-control', 'autocomplete': 'new-password'}),
    )

    class Meta:
        model = get_user_model()
        fields = ['username', 'first_name', 'last_name', 'email', 'is_active', 'groups']
        labels = {'is_active': 'Can sign in', 'groups': 'Roles'}
        widgets = {
            'username': forms.TextInput(attrs={'class': 'form-control', 'autocomplete': 'off'}),
            'first_name': forms.TextInput(attrs={'class': 'form-control'}),
            'last_name': forms.TextInput(attrs={'class': 'form-control'}),
            'email': forms.EmailInput(attrs={'class': 'form-control'}),
            'is_active': forms.CheckboxInput(attrs={'class': 'form-check-input'}),
            'groups': forms.CheckboxSelectMultiple(attrs={'class': 'form-check-input'}),
        }
        help_texts = {
            'username': 'The name used on the login screen.',
            'is_active': 'Un-tick to block this person from signing in.',
            'groups': 'A role decides which parts of the system this person sees.',
        }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        # Only the shop's own roles — the Django admin groups are none of our business.
        self.fields['groups'].queryset = Group.objects.filter(name__in=GROUP_ORDER)
        self.fields['groups'].required = True

    def clean(self):
        cleaned = super().clean()
        password = cleaned.get('password1')
        if password:
            if len(password) < MIN_PASSWORD_LENGTH:
                self.add_error('password1', f'Use at least {MIN_PASSWORD_LENGTH} characters.')
            else:
                validate_password(password)
        return cleaned

    def clean_password2(self):
        password1 = self.cleaned_data.get('password1')
        password2 = self.cleaned_data.get('password2')
        if password1 and password2 and password1 != password2:
            raise ValidationError('The two passwords do not match.')
        return password2

    def save(self, commit=True):
        user = super().save(commit=False)
        password = self.cleaned_data.get('password1')
        if password:
            user.set_password(password)
        if commit:
            user.save()
            self.save_m2m()
        return user


class StaffUserUpdateForm(StaffUserForm):
    """Edit a login. The password fields are optional here — blank keeps the old one.

    ``editor`` is the person doing the editing: when they are editing themselves
    the role tick-boxes may be left empty, and the view only puts the Owner role
    back if that would otherwise leave the shop with no Owner at all.
    """

    password1 = forms.CharField(
        label='New password',
        required=False,
        strip=False,
        widget=forms.PasswordInput(attrs={'class': 'form-control', 'autocomplete': 'new-password'}),
        help_text='Leave blank to keep the current password.',
    )
    password2 = forms.CharField(
        label='Confirm new password',
        required=False,
        strip=False,
        widget=forms.PasswordInput(attrs={'class': 'form-control', 'autocomplete': 'new-password'}),
    )

    def __init__(self, *args, editor=None, **kwargs):
        super().__init__(*args, **kwargs)
        self.editing_self = bool(
            editor is not None
            and getattr(editor, 'pk', None) is not None
            and self.instance.pk == editor.pk
        )
        if self.editing_self:
            self.fields['groups'].required = False
            self.fields['groups'].help_text = (
                'Leave blank (or untick everything) to stay an Owner.'
            )

    def clean_password2(self):
        password1 = self.cleaned_data.get('password1') or ''
        password2 = self.cleaned_data.get('password2') or ''
        if password1 or password2:
            if password1 != password2:
                raise ValidationError('The two passwords do not match.')
        return password2

        return cleaned
