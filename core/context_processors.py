"""Expose the configured currency, the alerts, and the caller's role to templates."""

from . import notifications as notification_alerts
from .models import SiteSettings
from .permissions import group_names, has_role, role_label


def currency(request):
    settings = SiteSettings.load()
    return {
        'site_settings': settings,
        'currency_code': settings.get_code(),
        'currency_symbol': settings.get_symbol(),
        'currency_name': settings.currency_name(),
        'currency_decimals': settings.get_decimals(),
        'currency_position': settings.get_symbol_position(),
        'currency_thousands': settings.get_thousands_separator(),
        'currency_decimal': settings.get_decimal_separator(),
    }


def notifications(request):
    """Low-stock / order alerts shown in the top-bar bell.

    Only the alerts this user's role actually covers are counted and listed: a
    seller is not nagged about shelving, a stock clerk not about the takings.
    """
    return notification_alerts.context(request)


def roles(request):
    """Which role(s) the caller holds — drives the top bar and the sidebar links."""
    user = getattr(request, 'user', None)
    return {
        'user_role': role_label(user),
        'user_groups': group_names(user),
        'user_has_role': has_role(user),
    }


