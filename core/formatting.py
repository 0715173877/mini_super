"""Money formatting helpers.

These functions are deliberately free of model imports at module level so they
can be used from models, admin, views, reports and template tags alike. When no
settings object is passed, the store's :class:`core.models.SiteSettings` is used.
"""

from decimal import Decimal, InvalidOperation, ROUND_HALF_UP

# Use characters that never appear in a formatted number as intermediate
# markers while swapping thousands/decimal separators around.
_GROUP_MARKER = '\x00'
_DECIMAL_MARKER = '\x01'


def to_decimal(value):
    """Best-effort conversion of `value` to :class:`~decimal.Decimal`."""
    if value is None or value == '':
        return Decimal('0')
    if isinstance(value, Decimal):
        return value
    try:
        return Decimal(str(value).strip())
    except (InvalidOperation, ValueError, TypeError):
        return Decimal('0')


def quantize(value, decimals):
    """Round `value` to `decimals` decimal places (half up, like prices)."""
    decimals = int(decimals or 0)
    exponent = Decimal(1).scaleb(-decimals)
    return to_decimal(value).quantize(exponent, rounding=ROUND_HALF_UP)


def format_number(value, decimals=2, thousands=',', decimal='.'):
    """Format a number using the given separators, e.g. ``1,234.56``."""
    decimals = int(decimals or 0)
    text = f'{quantize(value, decimals):,.{decimals}f}'

    thousands = ',' if thousands is None else thousands
    decimal = '.' if decimal is None else decimal

    if thousands != ',':
        text = text.replace(',', _GROUP_MARKER)
    if decimal != '.':
        text = text.replace('.', decimal)
    if thousands != ',':
        text = text.replace(_GROUP_MARKER, thousands)
    return text


def _load_settings(settings=None):
    if settings is not None:
        return settings
    from .models import SiteSettings
    return SiteSettings.load()


def format_money(value, settings=None, include_symbol=True, use_code=False):
    """Format `value` as money for the store's configured currency.

    ``format_money(1234.5)`` -> ``'TZS 1,235'`` (default store configuration).
    """
    settings = _load_settings(settings)
    text = format_number(
        value,
        settings.get_decimals(),
        settings.get_thousands_separator(),
        settings.get_decimal_separator(),
    )

    symbol = settings.get_code() if use_code else settings.get_symbol()
    if not include_symbol or not symbol:
        return text

    if settings.get_symbol_position() == 'after':
        return f'{text} {symbol}'
    # Letter symbols (TZS, KSh, ...) read better with a space; currency signs
    # ($, €, £, ...) are written straight against the amount.
    spacer = ' ' if symbol[-1].isalnum() else ''
    return f'{symbol}{spacer}{text}'
