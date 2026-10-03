"""Tests for the configurable currency settings (core app)."""

from decimal import Decimal
from html.parser import HTMLParser

from django.contrib.auth import get_user_model
from django.contrib.auth.models import Group, Permission
from django.core.management import call_command
from django.core.management.base import CommandError
from django.template import Context, Template
from django.test import Client, TestCase
from django.urls import reverse
from django.utils import timezone

from .formatting import format_money, format_number
from .models import SiteSettings
from .currencies import CUSTOM_CURRENCY
from .permissions import (
    GROUP_ORDER, GROUP_OWNER, GROUP_SELL, GROUP_SELLER_STOCK, GROUP_STOCK,
    assign_role, declared_permissions, group_names, has_role, role_label, sync_groups,
)


class MoneyFormattingTests(TestCase):
    """core.formatting must honour the store currency."""

    def setUp(self):
        SiteSettings.reset_cache()
        SiteSettings.objects.all().delete()

    def test_default_currency_is_tzs(self):
        settings = SiteSettings.load()
        self.assertEqual(settings.get_code(), 'TZS')
        self.assertEqual(settings.get_decimals(), 0)          # shilling has no cents
        self.assertEqual(settings.format_money(1234.5), 'TZS 1,235')

    def test_usd_uses_dollar_and_two_decimals(self):
        settings = SiteSettings.load()
        settings.currency = 'USD'
        settings.save()
        self.assertEqual(settings.format_money(1234.5), '$1,234.50')
        self.assertEqual(settings.format_money(0), '$0.00')

    def test_euro_layout_can_be_overridden(self):
        settings = SiteSettings.load()
        settings.currency = 'EUR'
        settings.symbol_position = 'after'
        settings.decimal_places = '1'
        settings.thousands_separator = 'dot'
        settings.decimal_separator = 'comma'
        settings.save()
        self.assertEqual(settings.format_money(1234.5), '1.234,5 €')

    def test_custom_symbol_override(self):
        settings = SiteSettings.load()
        settings.currency = 'TZS'
        settings.symbol_override = 'TSh'
        settings.decimal_places = '2'
        settings.save()
        self.assertEqual(settings.format_money(50), 'TSh 50.00')

    def test_symbol_can_be_left_out(self):
        settings = SiteSettings.load()
        settings.currency = 'USD'
        settings.save()
        self.assertEqual(settings.format_money(12.3, include_symbol=False), '12.30')
        self.assertEqual(settings.format_money(12.3, use_code=True), 'USD 12.30')

    def test_settings_always_stay_on_the_single_row(self):
        first = SiteSettings.load()
        self.assertEqual(first.pk, 1)
        first.currency = 'USD'
        first.save()

        second = SiteSettings(currency='EUR')
        second.save()
        self.assertEqual(second.pk, 1)
        self.assertEqual(SiteSettings.objects.count(), 1)
        self.assertEqual(SiteSettings.load().get_code(), 'EUR')

    def test_format_number_has_no_symbol(self):
        self.assertEqual(format_number(1234.5, 2), '1,234.50')
        self.assertEqual(format_number(1234.5, 0), '1,235')
        self.assertEqual(format_number(Decimal('0.1'), 2, '', '.'), '0.10')

    def test_format_money_accepts_a_settings_instance(self):
        settings = SiteSettings(currency='JPY')
        self.assertEqual(format_money(1234, settings=settings), '¥1,234')


class MoneyTemplateTests(TestCase):
    """The |money filters and the template context processor."""

    def setUp(self):
        SiteSettings.reset_cache()
        SiteSettings.objects.all().delete()

    def render(self, source, context=None):
        return Template('{% load currency %}' + source).render(Context(context or {}))

    def test_money_filter_uses_configured_currency(self):
        SiteSettings.objects.create(pk=1, currency='USD')
        SiteSettings.reset_cache()
        self.assertEqual(self.render('{{ 1234.5|money }}'), '$1,234.50')
        self.assertEqual(self.render('{{ 1234.5|money_code }}'), 'USD 1,234.50')
        self.assertEqual(self.render('{{ 1234.5|money_plain }}'), '1,234.50')

    def test_context_processor_exposes_symbol(self):
        SiteSettings.objects.create(pk=1, currency='TZS')
        SiteSettings.reset_cache()
        user = get_user_model().objects.create_user(
            username='viewer', password='secret-pass-123',
        )
        self.client.force_login(user)
        response = self.client.get(reverse('dashboard'))
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.context['currency_symbol'], 'TZS')
        self.assertEqual(response.context['currency_code'], 'TZS')


class SiteSettingsViewTests(TestCase):
    """The Currency & Settings page drives what the whole system displays."""

    def setUp(self):
        SiteSettings.reset_cache()
        SiteSettings.objects.all().delete()
        user = get_user_model().objects.create_user(
            username='manager', password='secret-pass-123',
            is_staff=True, is_superuser=True,
        )
        self.client.force_login(user)

    def test_page_requires_login(self):
        self.client.logout()
        response = self.client.get(reverse('site-settings'))
        self.assertEqual(response.status_code, 302)
        self.assertIn('/accounts/login/', response['Location'])

    def test_page_renders_current_currency(self):
        response = self.client.get(reverse('site-settings'))
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, 'TZS')

    def test_page_exposes_the_field_ids_the_preview_script_uses(self):
        html = self.client.get(reverse('site-settings')).content.decode()
        for field_id in ('id_currency', 'id_symbol_override', 'id_symbol_position',
                         'id_decimal_places', 'id_thousands_separator', 'id_decimal_separator'):
            self.assertIn(field_id, html)
        self.assertIn('currencyPresets', html)
        self.assertIn('previewRows', html)

    def test_post_changes_currency_everywhere(self):
        response = self.client.post(reverse('site-settings'), {
            'currency': 'USD',
            'symbol_override': '',
            'symbol_position': 'auto',
            'decimal_places': 'auto',
            'thousands_separator': 'auto',
            'decimal_separator': 'auto',
        })
        self.assertEqual(response.status_code, 302)

        settings = SiteSettings.load()
        self.assertEqual(settings.get_code(), 'USD')
        self.assertEqual(settings.format_money(9.5), '$9.50')

        dashboard = self.client.get(reverse('dashboard'))
        self.assertEqual(dashboard.context['currency_symbol'], '$')

    def test_custom_currency_needs_a_symbol(self):
        response = self.client.post(reverse('site-settings'), {
            'currency': 'CUSTOM',
            'symbol_override': '',
            'symbol_position': 'auto',
            'decimal_places': 'auto',
            'thousands_separator': 'auto',
            'decimal_separator': 'auto',
        })
        self.assertEqual(response.status_code, 200)
        self.assertTrue(response.context['form'].errors.get('symbol_override'))

    def test_custom_currency_is_formatted(self):
        settings = SiteSettings.load()
        settings.currency = CUSTOM_CURRENCY
        settings.symbol_override = 'FCFA'
        settings.decimal_places = '0'
        settings.save()
        self.assertEqual(settings.format_money(250000), 'FCFA 250,000')
        self.assertEqual(settings.get_symbol_position(), 'before')


class EveryTemplateStillCompilesTests(TestCase):
    """Guard against broken template tags/filters after the currency rollout."""

    def test_all_templates_compile(self):
        from pathlib import Path

        from django.conf import settings
        from django.template.loader import get_template

        root = Path(settings.BASE_DIR) / 'templates'
        failures = []
        for path in sorted(root.rglob('*.html')):
            name = path.relative_to(root).as_posix()
            if 'copy' in name:
                continue
            try:
                get_template(name)
            except Exception as exc:  # noqa: BLE001 - report whatever happened
                failures.append(f'{name}: {exc}')
        self.assertEqual(failures, [])


class MoneyPageSmokeTests(TestCase):
    """Every money-bearing page must render with the configured currency."""

    PAGES = [
        'dashboard',
        'product-list', 'product-create', 'category-list', 'supplier-list',
        'low-stock', 'stock-movement-list',
        'purchase-order-list', 'purchase-order-create',
        'supplier-return-list', 'supplier-return-create',
        'point-of-sale', 'sale-list', 'daily-reports', 'customer-analytics',
        'customer-return-list', 'customer-return-create',
        'waste-tracking', 'staff-scheduling', 'performance-metrics', 'supplier-performance',
        'sales_report_new', 'inventory_report', 'analytics',
    ]

    def setUp(self):
        SiteSettings.reset_cache()
        SiteSettings.objects.all().delete()
        user = get_user_model().objects.create_user(
            username='boss', password='secret-pass-123',
            is_staff=True, is_superuser=True,
        )
        self.client.force_login(user)

    def test_pages_render_in_tzs(self):
        for name in self.PAGES:
            with self.subTest(page=name):
                response = self.client.get(reverse(name))
                self.assertEqual(response.status_code, 200, f'{name} returned {response.status_code}')

    def test_pages_render_in_usd(self):
        settings = SiteSettings.load()
        settings.currency = 'USD'
        settings.save()
        for name in self.PAGES:
            with self.subTest(page=name):
                response = self.client.get(reverse(name))
                self.assertEqual(response.status_code, 200, f'{name} returned {response.status_code}')

    def test_dashboard_shows_the_configured_symbol(self):
        settings = SiteSettings.load()
        settings.currency = 'USD'
        settings.save()
        self.assertContains(self.client.get(reverse('dashboard')), '$0.00')

    def test_template_exposes_currency_to_javascript(self):
        html = self.client.get(reverse('dashboard')).content.decode()
        self.assertIn("symbol: 'TZS'", html)
        self.assertIn('decimals: 0,', html)


class NotificationTests(TestCase):
    """The top-bar bell must reflect real low-stock and order alerts."""

    def setUp(self):
        from datetime import timedelta

        from inventory.models import Category, Product, Supplier

        SiteSettings.reset_cache()
        SiteSettings.objects.all().delete()

        self.user = get_user_model().objects.create_user(
            username='manager', password='secret-pass-123',
        )
        # The bell is role-aware: a manager who does both jobs sees the lot.
        assign_role(self.user, GROUP_SELLER_STOCK)
        self.client.force_login(self.user)

        self.category = Category.objects.create(name='Drinks')
        self.supplier = Supplier.objects.create(
            name='Acme Ltd', contact_person='Ann', email='ann@acme.test', phone='0700',
        )
        self.healthy = Product.objects.create(
            name='Healthy Juice', sku='OK-1', category=self.category,
            product_type='non_perishable', cost_price=1, selling_price=2,
            current_stock=50, min_stock_level=10, max_stock_level=200,
        )
        self.low = Product.objects.create(
            name='Low Cola', sku='LOW-1', category=self.category, supplier=self.supplier,
            product_type='non_perishable', cost_price=1, selling_price=2,
            current_stock=3, min_stock_level=10, max_stock_level=200,
        )
        self.out = Product.objects.create(
            name='Empty Water', sku='OUT-1', category=self.category,
            product_type='non_perishable', cost_price=1, selling_price=2,
            current_stock=0, min_stock_level=5, max_stock_level=100,
        )
        self.today = timezone.now().date()
        self._timedelta = timedelta

    def make_order(self, status, days_from_today):
        from inventory.models import PurchaseOrder

        return PurchaseOrder.objects.create(
            supplier=self.supplier,
            expected_delivery=self.today + self._timedelta(days=days_from_today),
            status=status,
        )

    # -- the alert sources ------------------------------------------------
    def test_healthy_stock_produces_no_alerts(self):
        from . import notifications

        titles = [a['title'] for a in notifications.product_alerts()]
        self.assertNotIn('Healthy Juice is running low', titles)
        self.assertNotIn('Healthy Juice is out of stock', titles)

    def test_below_minimum_is_a_warning(self):
        from . import notifications

        alerts = {a['key']: a for a in notifications.product_alerts()}
        self.assertIn(f'stock:low:{self.low.pk}', alerts)
        self.assertEqual(alerts[f'stock:low:{self.low.pk}']['severity'], 'warning')
        self.assertIn('3 left', alerts[f'stock:low:{self.low.pk}']['detail'])

    def test_empty_stock_is_critical(self):
        from . import notifications

        alerts = {a['key']: a for a in notifications.product_alerts()}
        self.assertIn(f'stock:out:{self.out.pk}', alerts)
        self.assertEqual(alerts[f'stock:out:{self.out.pk}']['severity'], 'danger')

    def test_draft_order_alert(self):
        from . import notifications

        order = self.make_order('draft', 5)
        alerts = {a['key']: a for a in notifications.order_alerts()}
        self.assertIn(f'order:draft:{order.pk}', alerts)
        self.assertEqual(alerts[f'order:draft:{order.pk}']['severity'], 'info')

    def test_overdue_order_is_critical(self):
        from . import notifications

        order = self.make_order('ordered', -2)
        alerts = {a['key']: a for a in notifications.order_alerts()}
        self.assertEqual(alerts[f'order:ordered:{order.pk}']['severity'], 'danger')
        self.assertIn('overdue by 2 days', alerts[f'order:ordered:{order.pk}']['title'])

    def test_order_arriving_soon_is_a_warning(self):
        from . import notifications

        order = self.make_order('ordered', 1)
        alerts = {a['key']: a for a in notifications.order_alerts()}
        self.assertEqual(alerts[f'order:ordered:{order.pk}']['severity'], 'warning')

    def test_received_orders_drop_off_the_list(self):
        from . import notifications

        order = self.make_order('received', -9)
        keys = {a['key'] for a in notifications.order_alerts()}
        self.assertNotIn(f'order:received:{order.pk}', keys)

    # -- expiry -----------------------------------------------------------
    def make_perishable(self, name, sku, days_from_today, stock=5):
        """A product whose last delivery carries a use-by date, or no delivery.

        Expiry belongs to the delivery, so the date is recorded the way the shop
        records it: on the line of a purchase order that has been received. The
        bell derives the product's shelf life from exactly that. Passing
        ``days_from_today=None`` leaves the product with no dated delivery at all.
        """
        from inventory.models import Product, PurchaseOrder, PurchaseOrderItem

        product = Product.objects.create(
            name=name, sku=sku, category=self.category, supplier=self.supplier,
            product_type='perishable', cost_price=1, selling_price=2,
            current_stock=stock, min_stock_level=1, max_stock_level=50,
        )
        if days_from_today is not None:
            order = PurchaseOrder.objects.create(
                supplier=self.supplier, status='received',
                expected_delivery=self.today,
            )
            PurchaseOrderItem.objects.create(
                purchase_order=order, product=product,
                quantity=stock or 1, unit_cost=1,
                expiry_date=self.today + self._timedelta(days=days_from_today),
            )
        return product

    def test_the_product_table_holds_no_expiry_date(self):
        """A use-by date is a fact about a delivery, so it is not a product column."""
        from inventory.models import Product

        self.assertNotIn('expiry_date', {f.name for f in Product._meta.get_fields()})

    def test_correcting_the_delivery_moves_the_alert(self):
        """There is one copy of the date — on the order line — so nothing drifts."""
        from inventory.models import PurchaseOrderItem

        from . import notifications

        product = self.make_perishable('Soon Yoghurt', 'EXP-1', 3)
        keys = {a['key'] for a in notifications.expiry_alerts()}
        self.assertIn(f'expiry:soon:{product.pk}', keys)

        item = PurchaseOrderItem.objects.get(product=product)   # the date was mis-keyed
        item.expiry_date = self.today + self._timedelta(days=90)
        item.save()

        self.assertEqual(notifications.expiry_alerts(), [])

    def test_expiring_soon_is_a_warning(self):
        from . import notifications

        soon = self.make_perishable('Soon Yoghurt', 'EXP-1', 3)
        alerts = {a['key']: a for a in notifications.expiry_alerts()}
        self.assertIn(f'expiry:soon:{soon.pk}', alerts)
        self.assertEqual(alerts[f'expiry:soon:{soon.pk}']['severity'], 'warning')
        self.assertIn('expires in 3 days', alerts[f'expiry:soon:{soon.pk}']['title'])

    def test_expires_today_is_a_warning_too(self):
        from . import notifications

        today = self.make_perishable('Today Bread', 'EXP-0', 0)
        keys = [a['key'] for a in notifications.expiry_alerts()]
        self.assertIn(f'expiry:soon:{today.pk}', keys)

    def test_expired_stock_is_critical(self):
        from . import notifications

        old = self.make_perishable('Old Cheese', 'EXP-2', -2)
        alerts = {a['key']: a for a in notifications.expiry_alerts()}
        self.assertIn(f'expiry:expired:{old.pk}', alerts)
        self.assertEqual(alerts[f'expiry:expired:{old.pk}']['severity'], 'danger')
        self.assertIn('has expired', alerts[f'expiry:expired:{old.pk}']['title'])
        self.assertIn('2 days ago', alerts[f'expiry:expired:{old.pk}']['detail'])

    def test_a_comfortable_expiry_produces_no_alert(self):
        from . import notifications

        self.make_perishable('Long Life Juice', 'EXP-3', 30)
        keys = [a['key'] for a in notifications.expiry_alerts()]
        self.assertEqual(keys, [])

    def test_a_product_without_a_date_is_ignored(self):
        from . import notifications

        self.make_perishable('Undated Flour', 'EXP-4', None)
        self.assertEqual(notifications.expiry_alerts(), [])

    def test_expired_stock_that_is_finished_is_not_reported(self):
        """Once the shelf is empty the old date is just stale history."""
        from . import notifications

        self.make_perishable('Gone Yoghurt', 'EXP-5', -1, stock=0)
        self.assertEqual(notifications.expiry_alerts(), [])

    def test_the_bell_lists_expiry_alerts(self):
        self.make_perishable('Soon Yoghurt', 'EXP-1', 2)
        self.make_perishable('Old Cheese', 'EXP-2', -1)
        html = self.client.get(reverse('dashboard')).content.decode()
        self.assertIn('Soon Yoghurt expires in 2 days', html)
        self.assertIn('Old Cheese has expired', html)

    def test_the_sidebar_expiry_counter_and_filter_link(self):
        self.make_perishable('Soon Yoghurt', 'EXP-1', 2)
        self.make_perishable('Old Cheese', 'EXP-2', -1)   # expired counts as well
        self.make_perishable('Long Life Juice', 'EXP-3', 30)
        html = self.client.get(reverse('dashboard')).content.decode()
        self.assertIn('id="expiringCount">2<', html)
        self.assertIn(f"{reverse('product-list')}?expiry=soon", html)

    def test_the_product_list_filters_by_shelf_life(self):
        soon = self.make_perishable('Soon Yoghurt', 'EXP-1', 2)
        old = self.make_perishable('Old Cheese', 'EXP-2', -1)
        far = self.make_perishable('Long Life Juice', 'EXP-3', 30)
        self.make_perishable('Undated Flour', 'EXP-4', None)

        response = self.client.get(reverse('product-list'), {'expiry': 'soon'})
        names = [p.name for p in response.context['products']]
        self.assertIn(soon.name, names)
        self.assertIn(old.name, names)
        self.assertNotIn(far.name, names)

        response = self.client.get(reverse('product-list'), {'expiry': 'expired'})
        names = [p.name for p in response.context['products']]
        self.assertEqual(names, [old.name])

    def test_the_product_list_shows_the_shelf_life_column(self):
        self.make_perishable('Soon Yoghurt', 'EXP-1', 2)
        self.make_perishable('Old Cheese', 'EXP-2', -3)
        html = self.client.get(reverse('product-list')).content.decode()
        self.assertIn('<th>Expiry</th>', html)
        self.assertIn('2 days left', html)
        self.assertIn('Expired 3 days ago', html)

    # -- the bell ---------------------------------------------------------
    def test_bell_badge_counts_every_alert(self):
        html = self.client.get(reverse('dashboard')).content.decode()
        self.assertIn('class="notification-badge', html)
        self.assertIn('2 new', html)          # Empty Water + Low Cola, no orders yet

    def test_bell_lists_low_stock_and_orders_together(self):
        self.make_order('ordered', -1)
        html = self.client.get(reverse('dashboard')).content.decode()
        self.assertIn('Empty Water is out of stock', html)
        self.assertIn('Low Cola is running low', html)
        self.assertIn('is overdue by 1 day', html)

    def test_bell_is_empty_when_all_is_well(self):
        from inventory.models import Product

        Product.objects.update(current_stock=100)
        html = self.client.get(reverse('dashboard')).content.decode()
        self.assertIn("You're all caught up!", html)
        self.assertNotIn('class="notification-badge', html)

    def test_mark_all_read_clears_the_badge(self):
        response = self.client.post(reverse('notifications-mark-all-read'), {'next': '/'})
        self.assertRedirects(response, '/')
        html = self.client.get(reverse('dashboard')).content.decode()
        self.assertNotIn('class="notification-badge', html)
        self.assertIn('Empty Water is out of stock', html)   # still listed, just read

    def test_opening_a_notification_marks_it_read_and_redirects(self):
        from . import notifications

        alert = notifications.build_notifications()[0]
        response = self.client.post(
            reverse('notifications-open'), {'key': alert['key'], 'next': alert['url']},
        )
        self.assertRedirects(response, alert['url'])
        # One of the two alerts is now acknowledged, so the badge drops to 1.
        html = self.client.get(reverse('dashboard')).content.decode()
        self.assertIn('1 new', html)

    def test_opening_a_notification_refuses_a_foreign_redirect(self):
        response = self.client.post(
            reverse('notifications-open'), {'key': 'x', 'next': 'https://evil.example.com/'},
        )
        self.assertRedirects(response, reverse('notifications'))

    def test_notifications_page_lists_the_alerts(self):
        response = self.client.get(reverse('notifications'))
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, 'Empty Water is out of stock')
        self.assertContains(response, 'Low Cola is running low')

    def test_notifications_page_is_empty_by_default(self):
        from inventory.models import Product

        Product.objects.update(current_stock=100)
        response = self.client.get(reverse('notifications'))
        self.assertContains(response, "You're all caught up")

    def test_notifications_require_login(self):
        self.client.logout()
        response = self.client.get(reverse('notifications'))
        self.assertEqual(response.status_code, 302)
        self.assertIn(reverse('login'), response['Location'])
        self.assertEqual(
            self.client.post(reverse('notifications-open'), {'key': 'x'}).status_code, 302,
        )

    def test_anonymous_visitors_get_no_alert_context(self):
        from django.contrib.auth.models import AnonymousUser
        from django.test import RequestFactory

        from .context_processors import notifications as notification_processor

        request = RequestFactory().get('/')
        request.user = AnonymousUser()
        context = notification_processor(request)
        self.assertEqual(context['notification_count'], 0)
        self.assertEqual(context['low_stock_count'], 0)
        self.assertEqual(context['notifications'], [])

    # -- the sidebar counters ---------------------------------------------
    def test_sidebar_counters_use_real_numbers(self):
        self.make_order('ordered', 4)
        self.make_order('received', 4)      # received orders must not be counted
        html = self.client.get(reverse('dashboard')).content.decode()
        self.assertIn('id="lowStockCount">2<', html)      # Low Cola + Empty Water
        self.assertIn('id="pendingOrdersCount">1<', html)
        self.assertNotIn('Math.random', html)

    def test_money_pages_are_unchanged_by_the_bell(self):
        """The bell must not break the pages the currency rollout covered."""
        for name in ('point-of-sale', 'low-stock', 'purchase-order-list'):
            with self.subTest(page=name):
                self.assertEqual(self.client.get(reverse(name)).status_code, 200)


class LoginPageTests(TestCase):
    """The standalone login template must show messages and keep ?next=."""

    def test_next_is_preserved_in_the_form(self):
        html = self.client.get(f"{reverse('login')}?next=/inventory/").content.decode()
        self.assertIn('name="next" value="/inventory/"', html)

    def test_messages_are_rendered(self):
        """An error message must come out as a styled Bootstrap alert."""
        from django.contrib.auth.forms import AuthenticationForm
        from django.contrib.messages import constants
        from django.contrib.messages.storage.base import Message
        from django.template.loader import render_to_string

        html = render_to_string('registration/login.html', {
            'messages': [Message(constants.ERROR, 'You have been logged out.')],
            'form': AuthenticationForm(),
        })
        self.assertIn('You have been logged out.', html)
        self.assertIn('alert-danger', html)
        self.assertNotIn('alert-error', html)

    def test_base_page_renders_error_messages_as_danger_alerts(self):
        from django.contrib.messages import constants
        from django.contrib.messages.storage.base import Message
        from django.template.loader import render_to_string

        user = get_user_model().objects.create_user('x', password='secret-pass-123')
        self.client.force_login(user)
        response = self.client.get(reverse('dashboard'))
        html = render_to_string('base.html', {
            'messages': [Message(constants.ERROR, 'Stock update failed.')],
        }, request=response.wsgi_request)
        self.assertIn('alert-danger', html)
        self.assertIn('Stock update failed.', html)



# ----------------------------------------------------------------------
# Roles: Owner / Sell / Stock / SellerStock
# ----------------------------------------------------------------------
# Every page, grouped the way the roles group them. Listing them here means a
# new page that nobody thought about fails these tests instead of leaking.
SHELF_PAGES = [
    'product-list', 'product-create', 'category-list', 'category-create',
    'supplier-list', 'supplier-create', 'purchase-order-list',
    'purchase-order-create', 'received-purchases', 'low-stock',
    'stock-movement-list', 'supplier-return-list', 'supplier-return-create',
    'inventory_report',
]

TILL_PAGES = [
    'point-of-sale', 'sale-list', 'daily-reports', 'customer-analytics',
    'customer-return-list', 'customer-return-create', 'sales_report_new',
    'analytics',
]

OPERATIONS_PAGES = [
    'waste-tracking', 'staff-scheduling', 'performance-metrics',
    'supplier-performance',
]

OWNER_PAGES = ['site-settings', 'user-list', 'user-create']

# Pages everybody who is signed in may open, whatever their role.
OPEN_PAGES = ['dashboard', 'notifications']


def role_permissions(name):
    """``{'app.codename', ...}`` held by a role group."""
    group = Group.objects.get(name=name)
    return {
        f'{app}.{codename}'
        for app, codename in group.permissions.values_list(
            'content_type__app_label', 'codename'
        )
    }


class RoleGroupTests(TestCase):
    """The roles themselves: what each group is allowed to do."""

    def test_the_roles_exist_after_migrate(self):
        """`migrate` (and therefore the test runner) creates them — no manual step."""
        self.assertEqual(
            sorted(Group.objects.filter(name__in=GROUP_ORDER).values_list('name', flat=True)),
            sorted(GROUP_ORDER),
        )

    def test_every_declared_permission_exists(self):
        """A typo in a spec would silently hand out nothing — catch it here."""
        known = {
            f'{p.content_type.app_label}.{p.codename}'
            for p in Permission.objects.select_related('content_type')
        }
        self.assertEqual(sorted(declared_permissions() - known), [])

    def test_owner_gets_both_jobs_plus_the_settings(self):
        owner = role_permissions(GROUP_OWNER)
        self.assertLessEqual(role_permissions(GROUP_SELL), owner)
        self.assertLessEqual(role_permissions(GROUP_STOCK), owner)
        self.assertIn('core.change_sitesettings', owner)
        self.assertIn('auth.view_user', owner)

    def test_seller_stock_is_the_union_of_the_two_jobs(self):
        self.assertEqual(
            role_permissions(GROUP_SELLER_STOCK),
            role_permissions(GROUP_SELL) | role_permissions(GROUP_STOCK),
        )

    def test_selling_cannot_touch_the_shelf(self):
        sell = role_permissions(GROUP_SELL)
        self.assertIn('sales.add_sale', sell)
        self.assertNotIn('inventory.view_product', sell)
        self.assertNotIn('operations.view_wasterecord', sell)

    def test_stock_keeping_cannot_touch_the_till(self):
        stock = role_permissions(GROUP_STOCK)
        self.assertIn('inventory.view_product', stock)
        self.assertNotIn('sales.view_sale', stock)
        self.assertNotIn('sales.add_sale', stock)

    def test_none_of_the_roles_grants_the_django_admin(self):
        for name in GROUP_ORDER:
            with self.subTest(role=name):
                self.assertNotIn('auth.add_group', role_permissions(name))

    def test_syncing_twice_changes_nothing(self):
        first = sync_groups(verbosity=0)
        second = sync_groups(verbosity=0)
        self.assertEqual(first, second)
        self.assertEqual(Group.objects.filter(name__in=GROUP_ORDER).count(), 4)

    def test_syncing_takes_back_a_permission_that_no_longer_belongs(self):
        stray = Permission.objects.get(codename='add_user')
        Group.objects.get(name=GROUP_STOCK).permissions.add(stray)
        sync_groups(verbosity=0)
        self.assertNotIn('auth.add_user', role_permissions(GROUP_STOCK))

    def test_group_names_follow_the_role_order(self):
        user = get_user_model().objects.create_user('multi', password='secret-pass-123')
        assign_role(user, GROUP_STOCK, GROUP_SELL)
        self.assertEqual(group_names(user), [GROUP_SELL, GROUP_STOCK])
        self.assertEqual(role_label(user), 'Seller + Stock')

    def test_labels(self):
        seller = get_user_model().objects.create_user('s', password='secret-pass-123')
        assign_role(seller, GROUP_SELL)
        self.assertEqual(role_label(seller), 'Seller')

        nobody = get_user_model().objects.create_user('n', password='secret-pass-123')
        self.assertEqual(role_label(nobody), 'No role')
        self.assertEqual(group_names(nobody), [])
        self.assertFalse(has_role(nobody))

        boss = get_user_model().objects.create_user(
            'root', password='secret-pass-123', is_superuser=True,
        )
        self.assertEqual(role_label(boss), 'Administrator')
        self.assertTrue(has_role(boss, GROUP_OWNER))
        self.assertTrue(has_role(boss))



class RoleAccessTests(TestCase):
    """Every role gets exactly its own pages, and a 403 (not a login loop) for the rest."""

    def sign_in(self, *roles, username=None):
        user = get_user_model().objects.create_user(
            username=username or ('user' + str(len(roles))),
            password='secret-pass-123',
        )
        if roles:
            assign_role(user, *roles)
        self.client.force_login(user)
        return user

    def open(self, page):
        return self.client.get(reverse(page))

    def assert_pages_open(self, pages):
        for page in pages:
            with self.subTest(page=page):
                self.assertEqual(
                    self.open(page).status_code, 200,
                    f'{page} should be open to this role',
                )

    def assert_pages_blocked(self, pages):
        for page in pages:
            with self.subTest(page=page):
                response = self.open(page)
                self.assertEqual(
                    response.status_code, 403,
                    f'{page} should be closed to this role',
                )
                self.assertContains(response, 'not part of your role', status_code=403)

    # -- the seller -------------------------------------------------------
    def test_a_seller_gets_the_till_and_nothing_else(self):
        self.sign_in(GROUP_SELL)
        self.assert_pages_open(TILL_PAGES + OPEN_PAGES)
        self.assert_pages_blocked(SHELF_PAGES + OPERATIONS_PAGES + OWNER_PAGES)

    # -- the stock keeper -------------------------------------------------
    def test_a_stock_keeper_gets_the_shelf_and_nothing_else(self):
        self.sign_in(GROUP_STOCK)
        self.assert_pages_open(SHELF_PAGES + OPERATIONS_PAGES + OPEN_PAGES)
        self.assert_pages_blocked(TILL_PAGES + OWNER_PAGES)

    # -- the person who does both -----------------------------------------
    def test_seller_stock_gets_both_halves(self):
        self.sign_in(GROUP_SELLER_STOCK)
        self.assert_pages_open(
            TILL_PAGES + SHELF_PAGES + OPERATIONS_PAGES + OPEN_PAGES
        )
        self.assert_pages_blocked(OWNER_PAGES)

    # -- the owner --------------------------------------------------------
    def test_an_owner_reaches_every_page(self):
        self.sign_in(GROUP_OWNER)
        self.assert_pages_open(
            TILL_PAGES + SHELF_PAGES + OPERATIONS_PAGES + OWNER_PAGES + OPEN_PAGES
        )

    def test_an_owner_has_no_django_admin(self):
        user = self.sign_in(GROUP_OWNER)
        self.assertFalse(user.is_staff)
        response = self.client.get('/admin/')
        self.assertEqual(response.status_code, 302)
        self.assertIn('/admin/login/', response['Location'])

    # -- somebody with no role at all --------------------------------------
    def test_a_login_with_no_role_sees_the_friendly_dashboard(self):
        self.sign_in()
        response = self.open('dashboard')
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, 'no role yet')
        self.assert_pages_blocked(TILL_PAGES + SHELF_PAGES + OPERATIONS_PAGES + OWNER_PAGES)

    # -- the sidebar ------------------------------------------------------
    def test_the_sidebar_only_lists_the_pages_of_that_role(self):
        self.sign_in(GROUP_SELL)
        html = self.open('dashboard').content.decode()
        self.assertIn(reverse('point-of-sale'), html)
        self.assertIn(reverse('sale-list'), html)
        self.assertNotIn(reverse('product-list'), html)
        self.assertNotIn(reverse('purchase-order-list'), html)
        self.assertNotIn(reverse('waste-tracking'), html)
        self.assertNotIn(reverse('site-settings'), html)
        self.assertNotIn('Admin Panel', html)

    def test_the_stock_sidebar_hides_the_till(self):
        self.sign_in(GROUP_STOCK)
        html = self.open('dashboard').content.decode()
        self.assertIn(reverse('product-list'), html)
        self.assertIn(reverse('purchase-order-list'), html)
        self.assertIn(reverse('waste-tracking'), html)
        self.assertIn(reverse('inventory_report'), html)
        self.assertNotIn(reverse('point-of-sale'), html)
        self.assertNotIn(reverse('sale-list'), html)
        self.assertNotIn(reverse('site-settings'), html)
        self.assertNotIn('Admin Panel', html)

    def test_the_owner_sidebar_has_the_settings_and_users_but_not_the_admin_panel(self):
        self.sign_in(GROUP_OWNER)
        html = self.open('dashboard').content.decode()
        self.assertIn(reverse('site-settings'), html)
        self.assertIn(reverse('user-list'), html)
        self.assertNotIn(reverse('admin:index'), html)
        self.assertNotIn('Admin Panel', html)

    def test_the_top_bar_names_the_role(self):
        self.sign_in(GROUP_SELLER_STOCK)
        self.assertContains(self.open('dashboard'), 'Seller + Stock')

    def test_the_dashboard_only_shows_the_cards_of_that_role(self):
        self.sign_in(GROUP_SELL)
        html = self.open('dashboard').content.decode()
        self.assertIn("Today's Sales", html)
        # The Low Stock (green) and Waste (amber) cards belong to other roles.
        self.assertNotIn('border-left-success', html)
        self.assertNotIn('border-left-warning', html)



class UsersAndRolesPageTests(TestCase):
    """The owner's replacement for the Django admin: who signs in, as what."""

    def setUp(self):
        self.owner = get_user_model().objects.create_user(
            username='owner', password='secret-pass-123',
        )
        assign_role(self.owner, GROUP_OWNER)
        self.client.force_login(self.owner)

    def add_user(self, username='till1', roles=(GROUP_SELL,)):
        user = get_user_model().objects.create_user(
            username=username, password='secret-pass-123',
        )
        return assign_role(user, *roles) if roles else user

    def post_new_user(self, **overrides):
        data = {
            'username': 'newbie',
            'first_name': 'New',
            'last_name': 'Person',
            'email': 'newbie@example.test',
            'is_active': 'on',
            'groups': [str(Group.objects.get(name=GROUP_SELL).pk)],
            'password1': 'a-good-password',
            'password2': 'a-good-password',
        }
        data.update(overrides)
        if data.get('groups') is None:
            data.pop('groups', None)
        return self.client.post(reverse('user-create'), data)

    def test_the_page_lists_every_login_with_its_role(self):
        self.add_user('till1', (GROUP_SELL,))
        self.add_user('shelf1', (GROUP_STOCK,))
        response = self.client.get(reverse('user-list'))
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, 'till1')
        self.assertContains(response, 'shelf1')
        self.assertContains(response, GROUP_SELL)
        self.assertContains(response, GROUP_STOCK)

    def test_the_legend_counts_the_logins_per_role(self):
        self.add_user('till1', (GROUP_SELL,))
        html = self.client.get(reverse('user-list')).content.decode()
        self.assertIn('1 login', html)        # the owner's own role, and till1's
        self.assertIn('0 logins', html)       # nobody keeps the shelf (or does both)

    def test_the_owner_is_the_only_role_that_may_open_it(self):
        for role, username in ((GROUP_SELL, 'seller'), (GROUP_STOCK, 'stock')):
            with self.subTest(role=role):
                self.client.force_login(
                    assign_role(
                        get_user_model().objects.create_user(
                            username=username, password='secret-pass-123',
                        ),
                        role,
                    )
                )
                self.assertEqual(self.client.get(reverse('user-list')).status_code, 403)
                self.assertEqual(self.client.get(reverse('user-create')).status_code, 403)
                self.assertEqual(self.client.post(reverse('user-create'), {}).status_code, 403)

    def test_the_page_needs_a_login(self):
        self.client.logout()
        response = self.client.get(reverse('user-list'))
        self.assertEqual(response.status_code, 302)
        self.assertIn(reverse('login'), response['Location'])

    def test_the_owner_can_add_a_login_with_a_role(self):
        response = self.post_new_user()
        self.assertEqual(response.status_code, 302, response.content.decode()[:2000])

        user = get_user_model().objects.get(username='newbie')
        self.assertEqual(role_label(user), 'Seller')
        self.assertTrue(user.check_password('a-good-password'))
        self.assertTrue(user.is_active)
        self.assertFalse(user.is_staff)

    def test_a_new_login_must_carry_a_role(self):
        response = self.post_new_user(groups=None)
        self.assertEqual(response.status_code, 200)
        self.assertTrue(response.context['form'].errors.get('groups'))
        self.assertFalse(get_user_model().objects.filter(username='newbie').exists())

    def test_a_short_password_is_refused(self):
        response = self.post_new_user(password1='short', password2='short')
        self.assertEqual(response.status_code, 200)
        self.assertTrue(response.context['form'].errors.get('password1'))

    def test_mismatched_passwords_are_refused(self):
        response = self.post_new_user(password2='a-different-password')
        self.assertEqual(response.status_code, 200)
        self.assertTrue(response.context['form'].errors.get('password2'))

    def test_the_form_only_offers_the_four_shop_roles(self):
        html = self.client.get(reverse('user-create')).content.decode()
        for name in GROUP_ORDER:
            self.assertIn(name, html)
        # The role legend explains each role on the same page.
        self.assertIn('but not the Django admin panel', html)


    def test_the_owner_can_move_someone_to_another_role(self):
        user = self.add_user('till1', (GROUP_SELL,))
        response = self.client.post(reverse('user-update', args=[user.pk]), {
            'username': 'till1',
            'first_name': '',
            'last_name': '',
            'email': '',
            'is_active': 'on',
            'groups': [str(Group.objects.get(name=GROUP_STOCK).pk)],
            'password1': '',
            'password2': '',
        })
        self.assertEqual(response.status_code, 302, response.content.decode()[:2000])
        user.refresh_from_db()
        self.assertEqual(group_names(user), [GROUP_STOCK])
        self.assertTrue(user.check_password('secret-pass-123'))   # blank keeps the old one

    def test_the_owner_can_set_a_new_password(self):
        user = self.add_user('till1', (GROUP_SELL,))
        self.client.post(reverse('user-update', args=[user.pk]), {
            'username': 'till1', 'first_name': '', 'last_name': '', 'email': '',
            'is_active': 'on',
            'groups': [str(Group.objects.get(name=GROUP_SELL).pk)],
            'password1': 'another-good-password',
            'password2': 'another-good-password',
        })
        user.refresh_from_db()
        self.assertTrue(user.check_password('another-good-password'))

    def test_the_owner_can_block_someone(self):
        user = self.add_user('till1', (GROUP_SELL,))
        self.client.post(reverse('user-update', args=[user.pk]), {
            'username': 'till1', 'first_name': '', 'last_name': '', 'email': '',
            'groups': [str(Group.objects.get(name=GROUP_SELL).pk)],
            'password1': '', 'password2': '',
        })
        user.refresh_from_db()
        self.assertFalse(user.is_active)

    def test_a_role_change_reaches_the_sidebar_on_the_next_page_load(self):
        """The person's own session needs nothing more than a refresh."""
        till = self.add_user('till1', (GROUP_SELL,))
        till_client = Client()
        till_client.force_login(till)

        html = till_client.get(reverse('dashboard')).content.decode()
        self.assertIn(reverse('point-of-sale'), html)
        self.assertNotIn(reverse('waste-tracking'), html)

        # The owner moves them onto the shelf team...
        till.groups.set([Group.objects.get(name=GROUP_STOCK)])

        # ...and the very next page load re-filters the links.
        html = till_client.get(reverse('dashboard')).content.decode()
        self.assertNotIn(reverse('point-of-sale'), html)
        self.assertIn(reverse('waste-tracking'), html)

    def test_an_owner_may_hand_their_own_role_over_when_another_owner_remains(self):
        """A second Owner means stepping down is safe, so the ticked role sticks."""
        self.add_user('owner2', (GROUP_OWNER,))
        response = self.client.post(
            reverse('user-update', args=[self.owner.pk]),
            {
                'username': 'owner', 'first_name': '', 'last_name': '', 'email': '',
                'is_active': 'on',
                'groups': [str(Group.objects.get(name=GROUP_SELL).pk)],
                'password1': '', 'password2': '',
            },
            follow=True,
        )
        self.assertEqual(response.status_code, 200, response.content.decode()[:2000])

        self.owner.refresh_from_db()
        self.assertEqual(group_names(self.owner), [GROUP_SELL])
        html = response.content.decode()
        self.assertIn(reverse('point-of-sale'), html)
        self.assertNotIn(reverse('user-list'), html)      # the owner pages are gone

    def test_the_last_owner_cannot_lock_themselves_out(self):
        response = self.client.post(reverse('user-update', args=[self.owner.pk]), {
            'username': 'owner', 'first_name': '', 'last_name': '', 'email': '',
            'groups': [],   # tries to drop every role
            'password1': '', 'password2': '',
        })
        self.assertEqual(response.status_code, 302, response.content.decode()[:2000])
        self.owner.refresh_from_db()
        self.assertTrue(self.owner.is_active)
        self.assertEqual(group_names(self.owner), [GROUP_OWNER])

    def test_editing_yourself_warns_about_the_role_you_keep(self):
        response = self.client.post(
            reverse('user-update', args=[self.owner.pk]),
            {
                'username': 'owner', 'first_name': '', 'last_name': '', 'email': '',
                'groups': [], 'password1': '', 'password2': '',
            },
            follow=True,
        )
        self.assertContains(response, 'locking yourself out')


class RoleAwareNotificationTests(TestCase):
    """The bell only mentions the alerts a role can act on."""

    def setUp(self):
        from inventory.models import Category, Product

        self.category = Category.objects.create(name='Drinks')
        Product.objects.create(
            name='Low Cola', sku='LOW-1', category=self.category,
            product_type='non_perishable', cost_price=1, selling_price=2,
            current_stock=1, min_stock_level=10, max_stock_level=100,
        )

    def sign_in(self, *roles):
        user = get_user_model().objects.create_user(
            username='-'.join(roles) or 'nobody', password='secret-pass-123',
        )
        if roles:
            assign_role(user, *roles)
        self.client.force_login(user)
        return user

    def test_a_seller_is_not_nagged_about_the_shelf(self):
        self.sign_in(GROUP_SELL)
        html = self.client.get(reverse('dashboard')).content.decode()
        self.assertNotIn('Low Cola is running low', html)
        self.assertNotIn('class="notification-badge', html)
        self.assertContains(self.client.get(reverse('notifications')), "You're all caught up")

    def test_a_stock_keeper_is_told_about_the_shelf(self):
        self.sign_in(GROUP_STOCK)
        html = self.client.get(reverse('dashboard')).content.decode()
        self.assertIn('Low Cola is running low', html)
        self.assertIn('class="notification-badge', html)

    def test_the_sidebar_counters_stay_zero_for_a_role_that_cannot_use_them(self):
        self.sign_in(GROUP_SELL)
        html = self.client.get(reverse('dashboard')).content.decode()
        self.assertNotIn('id="lowStockCount"', html)


class SetupGroupsCommandTests(TestCase):
    """`python manage.py setup_groups` — the visible half of the same job."""

    def test_it_reports_the_four_roles(self):
        from io import StringIO

        out = StringIO()
        call_command('setup_groups', stdout=out)
        text = out.getvalue()
        for name in GROUP_ORDER:
            self.assertIn(name, text)

    def test_it_can_be_quiet(self):
        from io import StringIO

        out = StringIO()
        call_command('setup_groups', verbosity=0, stdout=out)
        self.assertEqual(out.getvalue(), '')

    def test_a_verbose_run_lists_what_each_role_can_do(self):
        from io import StringIO

        out = StringIO()
        call_command('setup_groups', verbosity=2, stdout=out)
        text = out.getvalue()
        self.assertIn('permissions', text)
        self.assertIn('Owner', text)

    def test_it_can_hand_the_owner_role_to_the_first_person(self):
        from io import StringIO

        user = get_user_model().objects.create_user('carl', password='secret-pass-123')
        call_command('setup_groups', owner=['carl'], stdout=StringIO())
        self.assertEqual(group_names(user), [GROUP_OWNER])

    def test_it_refuses_an_unknown_user(self):
        from io import StringIO

        with self.assertRaises(CommandError):
            call_command('setup_groups', owner=['nobody-here'], stdout=StringIO())



def named_urls():
    """Every URL in the project that can be reversed without arguments."""
    from django.urls import NoReverseMatch, get_resolver

    def walk(patterns):
        for pattern in patterns:
            if hasattr(pattern, 'url_patterns'):        # an include() — dig in
                yield from walk(pattern.url_patterns)
            elif getattr(pattern, 'name', None):
                yield pattern.name

    names = set()
    for name in walk(get_resolver().url_patterns):
        try:
            reverse(name)
        except NoReverseMatch:
            continue          # needs arguments (a pk, a format, ...) — skip it
        names.add(name)
    return sorted(names)


class EveryPageIsGuardedTests(TestCase):
    """A login with no role may only see the dashboard and the bell.

    This walks the project's own URLconf, so a page added later without a role
    fails here instead of quietly becoming public.
    """

    #: Pages that are open to any signed-in user, or that are not page views.
    OPEN = {
        'dashboard', 'notifications',
        'login', 'logout', 'admin:index',
        'password_reset', 'password_reset_done',
        'password_reset_confirm', 'password_reset_complete',
        # POST-only endpoints (they are exercised elsewhere).
        'notifications-open', 'notifications-mark-all-read',
    }

    def setUp(self):
        user = get_user_model().objects.create_user(
            username='norole', password='secret-pass-123',
        )
        self.client.force_login(user)

    def test_no_role_no_access(self):
        checked = 0
        for name in named_urls():
            if name in self.OPEN:
                continue
            with self.subTest(page=name):
                self.assertEqual(
                    self.client.get(reverse(name)).status_code, 403,
                    f'{name} is not guarded by a role',
                )
                checked += 1
        # Guard against the resolver silently returning nothing.
        self.assertGreater(checked, 25)

    #: Endpoints that answer a GET with a redirect because they expect a form POST.
    POST_ONLY = {'add-shift', 'evaluate-supplier', 'track-peak-hours'}

    def test_an_owner_can_open_every_one_of_them(self):
        owner = get_user_model().objects.create_user(
            username='owner', password='secret-pass-123',
        )
        assign_role(owner, GROUP_OWNER)
        self.client.force_login(owner)

        checked = 0
        for name in named_urls():
            if name in self.OPEN or name == 'sales-api-data':
                continue
            with self.subTest(page=name):
                status = self.client.get(reverse(name)).status_code
                if name in self.POST_ONLY:
                    self.assertIn(status, (200, 302, 405))
                else:
                    self.assertEqual(status, 200, f'{name} should open for an owner')
                checked += 1
        self.assertGreater(checked, 25)



class _TagBalance(HTMLParser):
    """Collects the tags a page leaves open (void elements ignored)."""

    VOID = {
        'area', 'base', 'br', 'col', 'embed', 'hr', 'img', 'input', 'link',
        'meta', 'param', 'source', 'track', 'wbr',
    }

    def __init__(self):
        super().__init__(convert_charrefs=True)
        self.stack = []
        self.errors = []

    def handle_starttag(self, tag, attrs):
        if tag not in self.VOID:
            self.stack.append((tag, self.getpos()[0]))

    def handle_endtag(self, tag):
        if tag in self.VOID:
            return
        if not self.stack:
            self.errors.append(f'stray </{tag}> at line {self.getpos()[0]}')
            return
        opened, line = self.stack.pop()
        if opened != tag:
            self.errors.append(
                f'</{tag}> at line {self.getpos()[0]} closes <{opened}> from line {line}'
            )


class PageStructureTests(TestCase):
    """Every page must keep the sidebar inside its own ``<nav>``.

    A stray ``</div>`` in the sidebar closed it early, which dropped the rest of
    the page out of the main column and pushed the content down as soon as you
    scrolled. Checking that each rendered page balances its tags catches that
    whole family of mistakes — and it runs for every role, so a link only one
    role can see cannot hide one.
    """

    def test_every_page_balances_its_tags(self):
        checked = 0
        for role in (GROUP_OWNER, GROUP_SELL, GROUP_STOCK):
            user = get_user_model().objects.create_user(
                username='layout-' + role, password='secret-pass-123',
            )
            assign_role(user, role)
            self.client.force_login(user)
            for name in named_urls():
                if name in EveryPageIsGuardedTests.OPEN or name == 'sales-api-data':
                    continue
                response = self.client.get(reverse(name))
                if response.status_code not in (200, 403):
                    continue
                with self.subTest(role=role, page=name, status=response.status_code):
                    parser = _TagBalance()
                    parser.feed(response.content.decode())
                    self.assertEqual(parser.errors, [])
                    self.assertEqual(
                        parser.stack, [],
                        f'{name} leaves {[tag for tag, _ in parser.stack]} open',
                    )
                checked += 1
        self.assertGreater(checked, 25)

