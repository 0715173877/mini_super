from django.db import models, OperationalError, ProgrammingError

from .currencies import (
    AUTO,
    CURRENCIES,
    CURRENCY_CHOICES,
    DECIMAL_PLACES_CHOICES,
    DECIMAL_SEPARATOR_CHOICES,
    DEFAULT_CURRENCY,
    SEPARATOR_CHARS,
    SYMBOL_POSITION_CHOICES,
    THOUSANDS_SEPARATOR_CHOICES,
    currency_config,
)
from .formatting import format_money as _format_money

# Simple in-process cache so every page/report row does not hit the database.
_CACHE = {'instance': None}


class SiteSettings(models.Model):
    """Store-wide settings (currently the currency). Single row, pk=1."""

    currency = models.CharField(
        max_length=10,
        choices=CURRENCY_CHOICES,
        default=DEFAULT_CURRENCY,
        help_text='Currency used everywhere in the system.',
    )
    symbol_override = models.CharField(
        max_length=8,
        blank=True,
        help_text='Optional. Replaces the currency symbol above, e.g. "TSh", "FCFA", "د.إ".',
    )
    symbol_position = models.CharField(
        max_length=6,
        choices=SYMBOL_POSITION_CHOICES,
        default=AUTO,
    )
    decimal_places = models.CharField(
        max_length=4,
        choices=DECIMAL_PLACES_CHOICES,
        default=AUTO,
    )
    thousands_separator = models.CharField(
        max_length=5,
        choices=THOUSANDS_SEPARATOR_CHOICES,
        default=AUTO,
    )
    decimal_separator = models.CharField(
        max_length=5,
        choices=DECIMAL_SEPARATOR_CHOICES,
        default=AUTO,
    )
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        verbose_name = 'System Settings'
        verbose_name_plural = 'System Settings'

    def __str__(self):
        return f'System Settings ({self.get_code()})'

    def save(self, *args, **kwargs):
        # Enforce a single settings row.
        self.pk = 1
        super().save(*args, **kwargs)
        _CACHE['instance'] = self

    # ------------------------------------------------------------------
    # Accessors — every one of them falls back to the currency preset when
    # the store left the field on "Automatic".
    # ------------------------------------------------------------------
    def _preset(self, key):
        return currency_config(self.currency).get(key)

    def get_code(self):
        return self.currency

    def get_symbol(self):
        override = (self.symbol_override or '').strip()
        if override:
            return override
        return self._preset('symbol') or self.currency

    def get_symbol_position(self):
        if self.symbol_position and self.symbol_position != AUTO:
            return self.symbol_position
        return self._preset('position') or 'before'

    def get_decimals(self):
        if self.decimal_places and self.decimal_places != AUTO:
            try:
                return int(self.decimal_places)
            except (TypeError, ValueError):
                pass
        return int(self._preset('decimals') or 0)

    def get_thousands_separator(self):
        if self.thousands_separator and self.thousands_separator != AUTO:
            return SEPARATOR_CHARS.get(self.thousands_separator, ',')
        return SEPARATOR_CHARS.get(self._preset('thousands'), ',')

    def get_decimal_separator(self):
        if self.decimal_separator and self.decimal_separator != AUTO:
            return SEPARATOR_CHARS.get(self.decimal_separator, '.')
        return SEPARATOR_CHARS.get(self._preset('decimal'), '.')

    def currency_name(self):
        return CURRENCIES.get(self.currency, {}).get('name', self.currency)

    # ------------------------------------------------------------------
    def format_money(self, value, include_symbol=True, use_code=False):
        """Format `value` using this configuration."""
        return _format_money(value, settings=self, include_symbol=include_symbol, use_code=use_code)

    # ------------------------------------------------------------------
    @classmethod
    def load(cls):
        """Return the (cached) settings row, creating it on first use."""
        if _CACHE['instance'] is not None:
            return _CACHE['instance']
        try:
            instance = cls.objects.filter(pk=1).first()
            if instance is None:
                instance = cls.objects.create(pk=1)
        except (OperationalError, ProgrammingError):
            # Table not created yet (e.g. during migrate) — serve defaults.
            instance = cls()
        _CACHE['instance'] = instance
        return instance

    @classmethod
    def reset_cache(cls):
        _CACHE['instance'] = None
