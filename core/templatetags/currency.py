"""Template filters for money, honouring the configured currency.

Usage::

    {% load currency %}
    {{ product.selling_price|money }}        -> TZS 1,235   (or $1,234.56 / 1.234,56 €)
    {{ product.selling_price|money_code }}   -> TZS 1,235   (ISO code instead of symbol)
    {{ product.selling_price|money_plain }}  -> 1,235       (no symbol, for inputs)
"""

from django import template

from ..formatting import format_money, format_number

register = template.Library()


@register.filter(name='money')
def money(value):
    """Format `value` as money with the configured symbol."""
    return format_money(value)


@register.filter(name='money_code')
def money_code(value):
    """Format `value` as money using the ISO code (e.g. ``TZS 1,235``)."""
    return format_money(value, use_code=True)


@register.filter(name='money_plain')
def money_plain(value):
    """Format `value` without any symbol (still uses the configured layout)."""
    return format_money(value, include_symbol=False)


@register.filter(name='money_decimals')
def money_decimals(value):
    """Format `value` without grouping, always with the configured decimals."""
    from ..models import SiteSettings
    settings = SiteSettings.load()
    return format_number(value, settings.get_decimals(), '', settings.get_decimal_separator())
