"""Live alerts for the top-bar notification bell.

Nothing here is stored in the database: every alert is derived from the
*current* state of the inventory and the purchase orders, so an alert
disappears the moment the problem behind it is fixed (stock topped up,
order received, ...). That also means there is never a stale row to clean
up or a signal to forget to wire.

The only thing we do remember is which alerts the cashier has already
acknowledged ("read") — that lives in the session, see
:func:`acknowledge` / :func:`acknowledge_all`.

Alert sources live in :func:`product_alerts` (low / out of stock),
:func:`expiry_alerts` (expired / about to expire) and :func:`order_alerts`
(draft, due soon, overdue). To add a new kind of alert, append to one of those
lists — the bell, the full page and the badge render whatever they are given,
so no template change is needed.
"""

from datetime import timedelta

from django.db import OperationalError, ProgrammingError
from django.db.models import F, Q
from django.urls import reverse
from django.utils import timezone

from .formatting import format_number

# Safety valves so a mis-configured catalogue can never make the bell
# expensive to render.
MAX_PRODUCT_ALERTS = 200
MAX_ORDER_ALERTS = 200
MAX_EXPIRY_ALERTS = 200
# How many alerts the drop-down shows before "View all".
DROPDOWN_LIMIT = 8
# A delivery is "due soon" this many days (or less) before its date.
DUE_SOON_DAYS = 3
# Stock is "expiring soon" this many days (or less) before its use-by date.
EXPIRY_SOON_DAYS = 7

# Lower rank = shown first.
SEVERITY_RANK = {'danger': 0, 'warning': 1, 'info': 2, 'success': 3}
SEVERITIES = ('danger', 'warning', 'info', 'success')

SESSION_KEY = 'acknowledged_notifications'
MAX_ACKNOWLEDGED = 500  # keep the session row bounded

# Which alerts belong to which job. A seller (Sell) must not be nagged about
# shelving, and a stock clerk (Stock) must not be told about the takings — the
# permission a category needs is what decides who sees it.
CATEGORY_PERMISSIONS = {
    'stock': 'inventory.view_product',
    'expiry': 'inventory.view_product',
    'orders': 'inventory.view_purchaseorder',
}



def _quantity(value):
    """Stock levels are decimals (weighed goods) — print them tidily."""
    text = format_number(value, 3)
    if '.' in text:
        text = text.rstrip('0').rstrip('.')
    return text or '0'


def _order_reference(order):
    return f'PO-{order.pk:06d}'


def _days(count):
    """``'1 day'`` / ``'3 days'`` — keeps the alert titles grammatical."""
    return f'{count} day' if count == 1 else f'{count} days'


def _supplier_name(order):
    """Purchase orders may be raised for a walk-in / cash purchase."""
    return order.supplier.name if order.supplier_id else 'walk-in supplier'


# ----------------------------------------------------------------------
# Alert sources
# ----------------------------------------------------------------------
def product_alerts():
    """Products that are out of stock or at/below their minimum level."""
    from inventory.models import Product

    alerts = []
    products = (
        Product.objects.select_related('category', 'supplier')
        .filter(current_stock__lte=F('min_stock_level'))
        .order_by('current_stock', 'name')[:MAX_PRODUCT_ALERTS]
    )

    for product in products:
        out_of_stock = product.current_stock <= 0
        supplier = product.supplier.name if product.supplier_id else None

        if out_of_stock:
            detail = f'SKU {product.sku} — nothing left in stock.'
            if supplier:
                detail += f' Reorder from {supplier}.'
            alert = {
                'category': 'Stock',
                'category_slug': 'stock',
                'severity': 'danger',
                'icon': 'fa-times-circle',
                'badge': 'Out of stock',
                'title': f'{product.name} is out of stock',
                'detail': detail,
            }
        else:
            detail = (
                f'{_quantity(product.current_stock)} left, minimum is '
                f'{_quantity(product.min_stock_level)}.'
            )
            if supplier:
                detail += f' Supplier: {supplier}.'
            alert = {
                'category': 'Stock',
                'category_slug': 'stock',
                'severity': 'warning',
                'icon': 'fa-exclamation-triangle',
                'badge': 'Low stock',
                'title': f'{product.name} is running low',
                'detail': detail,
            }

        alert.update({
            'key': f"stock:{'out' if out_of_stock else 'low'}:{product.pk}",
            'kind': 'out_of_stock' if out_of_stock else 'low_stock',
            'url': reverse('product-detail', args=[product.pk]),
        })
        alerts.append(alert)

    return alerts


def expiry_alerts():
    """Products already past their use-by date, or about to pass it.

    Only products that still hold stock are reported: an expired date on an
    empty shelf is stale history, not something to act on. The date itself is
    never stored on the product — it is typed on the purchase order line when the
    delivery arrives, and ``Product.objects.with_expiry()`` reduces those lines to
    the date the shelf is actually heading for.
    """
    from inventory.models import Product

    today = timezone.now().date()
    cutoff = today + timedelta(days=EXPIRY_SOON_DAYS)
    alerts = []
    products = (
        Product.objects.with_expiry().select_related('category', 'supplier')
        .filter(
            current_stock__gt=0,
            effective_expiry_date__isnull=False,
            effective_expiry_date__lte=cutoff,
        )
        .order_by('effective_expiry_date', 'name')[:MAX_EXPIRY_ALERTS]
    )

    for product in products:
        days = (product.expiry_date - today).days
        supplier = product.supplier.name if product.supplier_id else None
        stock = _quantity(product.current_stock)

        if days < 0:
            severity, icon, badge = 'danger', 'fa-calendar-times', 'Expired'
            title = f'{product.name} has expired'
            detail = (
                f'Use-by date was {product.expiry_date:%d %b %Y} '
                f'({_days(abs(days))} ago) with {stock} still in stock — pull it from the shelf.'
            )
        else:
            severity, icon, badge = 'warning', 'fa-hourglass-half', 'Expiring soon'
            if days == 0:
                title = f'{product.name} expires today'
            else:
                title = f'{product.name} expires in {_days(days)}'
            detail = f'Use-by date {product.expiry_date:%d %b %Y} — {stock} in stock.'

        if supplier:
            detail += f' Supplier: {supplier}.'

        alerts.append({
            'key': f"expiry:{'expired' if days < 0 else 'soon'}:{product.pk}",
            'kind': 'expiry_expired' if days < 0 else 'expiry_soon',
            'category': 'Expiry',
            'category_slug': 'expiry',
            'severity': severity,
            'icon': icon,
            'badge': badge,
            'title': title,
            'detail': detail,
            'url': reverse('product-detail', args=[product.pk]),
        })

    return alerts


def order_alerts():
    """Open purchase orders: not placed yet, due soon or overdue."""
    from inventory.models import PurchaseOrder

    today = timezone.now().date()
    alerts = []
    orders = (
        PurchaseOrder.objects.select_related('supplier')
        .filter(status__in=['draft', 'ordered'])
        .order_by('expected_delivery', 'pk')[:MAX_ORDER_ALERTS]
    )

    for order in orders:
        reference = _order_reference(order)
        supplier = _supplier_name(order)
        expected = order.expected_delivery

        if order.status == 'draft':
            severity, icon, badge = 'info', 'fa-file-alt', 'Draft'
            title = f'{reference} is still a draft'
            detail = f'Not sent to {supplier} yet — place the order or delete it.'
        elif expected and expected < today:
            days = order.days_overdue
            severity, icon, badge = 'danger', 'fa-truck-loading', 'Overdue'
            title = f'{reference} is overdue by {days} day{"" if days == 1 else "s"}'
            detail = f'Was expected on {expected:%d %b %Y} from {supplier}.'
        elif expected and (expected - today).days <= DUE_SOON_DAYS:
            days = (expected - today).days
            severity, icon, badge = 'warning', 'fa-truck', 'Due soon'
            if days == 0:
                title = f'{reference} is expected today'
            else:
                title = f'{reference} arrives in {days} day{"" if days == 1 else "s"}'
            detail = f'From {supplier}, expected {expected:%d %b %Y}.'
        else:
            severity, icon, badge = 'info', 'fa-clock', 'Awaiting delivery'
            title = f'{reference} is awaiting delivery'
            detail = (
                f'Expected {expected:%d %b %Y} from {supplier}.'
                if expected else f'No delivery date set — ordered from {supplier}.'
            )

        alerts.append({
            'key': f'order:{order.status}:{order.pk}',
            'kind': f'order_{order.status}',
            'category': 'Orders',
            'category_slug': 'orders',
            'severity': severity,
            'icon': icon,
            'badge': badge,
            'title': title,
            'detail': detail,
            'url': reverse('purchase-order-detail', args=[order.pk]),
        })

    return alerts


# ----------------------------------------------------------------------
# Building / summarising
# ----------------------------------------------------------------------
def may(user, permission):
    """True when this user may see things guarded by `permission`.

    ``user=None`` means "no filtering requested" (used by the plain helper
    functions); a superuser may see everything.
    """
    if user is None:
        return True
    if not getattr(user, 'is_authenticated', False):
        return False
    if user.is_superuser:
        return True
    return user.has_perm(permission)


def visible_to(alerts, user):
    """Drop the alerts this user's role has no business showing."""
    if user is None:
        return list(alerts)
    seen = {}
    visible = []
    for alert in alerts:
        needed = CATEGORY_PERMISSIONS.get(alert.get('category_slug'))
        if needed is None:
            visible.append(alert)
            continue
        if needed not in seen:
            seen[needed] = may(user, needed)
        if seen[needed]:
            visible.append(alert)
    return visible


def build_notifications():
    """All current alerts, most urgent first (safe before migrations run)."""
    try:
        alerts = product_alerts() + expiry_alerts() + order_alerts()
    except (OperationalError, ProgrammingError):
        # Tables not created yet (e.g. during ``migrate``) — no alerts.
        return []

    alerts.sort(key=lambda a: (
        SEVERITY_RANK.get(a['severity'], len(SEVERITY_RANK)),
        a['category'],
        a['title'].lower(),
    ))
    return alerts


def alert_counts(user=None):
    """Sidebar counters: (low stock, open purchase orders, expiring stock).

    Counted in the database (not from ``build_notifications``) so the
    sidebar stays correct even when the alert list itself is capped. A counter
    the user's role does not cover stays at zero — the sidebar badge must never
    reveal what the page behind it would refuse to show.
    """
    from inventory.models import Product, PurchaseOrder

    cutoff = timezone.now().date() + timedelta(days=EXPIRY_SOON_DAYS)
    sees_shelf = may(user, CATEGORY_PERMISSIONS['stock'])
    sees_orders = may(user, CATEGORY_PERMISSIONS['orders'])
    try:
        stock = Product.objects.filter(current_stock__lte=F('min_stock_level')).count() if sees_shelf else 0
        orders = PurchaseOrder.objects.filter(status__in=['draft', 'ordered']).count() if sees_orders else 0
        expiring = Product.objects.with_expiry().filter(
            Q(current_stock__gt=0) & Q(effective_expiry_date__isnull=False)
            & Q(effective_expiry_date__lte=cutoff)
        ).count() if sees_shelf else 0
    except (OperationalError, ProgrammingError):
        return 0, 0, 0
    return stock, orders, expiring



def summarise(alerts):
    """``{'danger': 2, 'warning': 1, ...}`` for the given alerts."""
    counts = {severity: 0 for severity in SEVERITIES}
    for alert in alerts:
        counts[alert['severity']] = counts.get(alert['severity'], 0) + 1
    return counts


def group_by_severity(alerts):
    """Alerts bucketed by severity, most urgent bucket first."""
    groups = []
    for severity in ('danger', 'warning', 'info', 'success'):
        bucket = [a for a in alerts if a['severity'] == severity]
        if bucket:
            groups.append((severity, bucket))
    return groups


# ----------------------------------------------------------------------
# Acknowledged ("read") state — kept in the session, not the database
# ----------------------------------------------------------------------
def _session(request):
    return getattr(request, 'session', None)


def acknowledged_keys(request):
    session = _session(request)
    return set(session.get(SESSION_KEY, [])) if session is not None else set()


def acknowledge(request, keys):
    """Remember that `keys` have been read (the session list stays bounded)."""
    session = _session(request)
    if session is None:            # e.g. a bare RequestFactory request
        return
    acknowledged = list(session.get(SESSION_KEY, []))
    for key in keys:
        if key and key not in acknowledged:
            acknowledged.append(key)
    session[SESSION_KEY] = acknowledged[-MAX_ACKNOWLEDGED:]


def acknowledge_all(request):
    user = getattr(request, 'user', None)
    acknowledge(request, [
        alert['key'] for alert in visible_to(build_notifications(), user)
    ])


def mark_all_unread(request):
    """Forget every acknowledgement — mirrors "mark all as read"."""
    session = _session(request)
    if session is not None:
        session.pop(SESSION_KEY, None)


def attach_read_state(request, alerts):
    """Tag each alert with ``is_read`` based on the session."""
    acknowledged = acknowledged_keys(request)
    for alert in alerts:
        alert['is_read'] = alert['key'] in acknowledged
    return alerts


def unread(alerts):
    return [alert for alert in alerts if not alert.get('is_read')]


def context(request):
    """Everything the bell needs, as a template context dictionary."""
    empty = {
        'notifications': [],
        'notification_count': 0,
        'notification_total': 0,
        'notification_summary': summarise([]),
        'notification_severity': '',
        'low_stock_count': 0,
        'pending_order_count': 0,
        'expiring_count': 0,
    }

    user = getattr(request, 'user', None)
    if user is None or not user.is_authenticated:
        return empty
    # The Django admin has its own chrome — don't pay for alerts there.
    if request.path.startswith('/admin/'):
        return empty

    alerts = visible_to(attach_read_state(request, build_notifications()), user)
    unread_alerts = unread(alerts)
    worst = ''
    for severity in ('danger', 'warning', 'info', 'success'):
        if any(a['severity'] == severity for a in unread_alerts):
            worst = severity
            break

    low_stock_count, pending_order_count, expiring_count = alert_counts(user)
    return {
        'notifications': alerts[:DROPDOWN_LIMIT],
        'notification_count': len(unread_alerts),
        'notification_total': len(alerts),
        'notification_summary': summarise(alerts),
        'notification_severity': worst,
        'low_stock_count': low_stock_count,
        'pending_order_count': pending_order_count,
        'expiring_count': expiring_count,
    }
