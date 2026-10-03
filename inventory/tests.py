"""Purchase-order shelf life.

A delivery carries a use-by date. Without it, purchasing an order tops up
stock with no expiry information at all, and the notification bell has
nothing to warn about — which is exactly the gap these tests lock down.
"""

import re
from datetime import timedelta

from django.contrib.auth import get_user_model
from django.test import TestCase
from django.urls import reverse
from django.utils import timezone

from .models import (
    Category, Product, PurchaseOrder, PurchaseOrderItem, StockMovement, Supplier,
)
from .views import purchase_order_into_stock
from core.permissions import GROUP_STOCK, assign_role


class PurchaseOrderExpiryTests(TestCase):
    def setUp(self):
        self.user = get_user_model().objects.create_user(
            username='manager', password='secret-pass-123',
        )
        # These are shelving pages: the Stock role is enough.
        assign_role(self.user, GROUP_STOCK)
        self.today = timezone.now().date()
        self.category = Category.objects.create(name='Dairy')
        self.supplier = Supplier.objects.create(
            name='Fresh Co', contact_person='Mary', email='mary@fresh.test', phone='0755',
        )
        self.product = Product.objects.create(
            name='Fresh Milk', sku='MILK-1', category=self.category,
            supplier=self.supplier, product_type='perishable',
            cost_price=1, selling_price=2,
            current_stock=5, min_stock_level=2, max_stock_level=100,
        )
        self.order = PurchaseOrder.objects.create(
            supplier=self.supplier, status='ordered',
            expected_delivery=self.today,
        )

    def add_line(self, expiry, quantity=10):
        return PurchaseOrderItem.objects.create(
            purchase_order=self.order, product=self.product,
            quantity=quantity, unit_cost=1, expiry_date=expiry,
        )

    def days(self, count):
        return self.today + timedelta(days=count)

    # -- the field itself ---------------------------------------------------
    def test_a_line_can_record_its_use_by_date(self):
        item = self.add_line(self.days(10))
        item.refresh_from_db()
        self.assertEqual(item.expiry_date, self.days(10))
        self.assertFalse(item.is_expired)

    def test_the_date_is_optional(self):
        item = self.add_line(None)
        self.assertIsNone(item.expiry_date)
        self.assertEqual(item.total_cost, 10)

    def test_a_past_date_is_reported_as_expired(self):
        self.assertTrue(self.add_line(self.days(-1)).is_expired)

    def received_line(self, expiry, quantity=10):
        """A delivery that has already been bought in (its order is `received`)."""
        order = PurchaseOrder.objects.create(
            supplier=self.supplier, status='received',
            expected_delivery=self.today,
        )
        return PurchaseOrderItem.objects.create(
            purchase_order=order, product=self.product,
            quantity=quantity, unit_cost=1, expiry_date=expiry,
        )

    def product_expiry(self):
        """The shelf life the views and the bell read, computed in the database."""
        return (
            Product.objects.with_expiry()
            .filter(pk=self.product.pk)
            .values_list('effective_expiry_date', flat=True)
            .get()
        )

    # -- what the shop is told the shelf life is ----------------------------
    def test_the_product_row_carries_no_expiry_date(self):
        """A use-by date is a fact about a delivery, not about the product."""
        self.assertNotIn('expiry_date', {f.name for f in Product._meta.get_fields()})

    def test_purchasing_dates_the_product_from_the_delivery(self):
        self.add_line(self.days(10))
        purchase_order_into_stock(self.order, self.user)

        self.product.refresh_from_db()
        self.assertEqual(self.product_expiry(), self.days(10))
        self.assertEqual(self.product.current_stock, 15)

    def test_the_soonest_future_date_wins(self):
        """Old shelf stock still expires first — a later delivery must not hide it."""
        self.received_line(self.days(3))
        self.add_line(self.days(30))

        purchase_order_into_stock(self.order, self.user)

        self.assertEqual(self.product_expiry(), self.days(3))

    def test_a_delivery_that_has_passed_gives_way_to_the_fresh_one(self):
        """Otherwise a batch sold out long ago would pin the product to a dead date."""
        self.received_line(self.days(-5))
        self.add_line(self.days(20))

        purchase_order_into_stock(self.order, self.user)

        self.product.refresh_from_db()
        self.assertEqual(self.product_expiry(), self.days(20))
        self.assertFalse(self.product.is_expired)

    def test_a_lapsed_delivery_still_reports_as_expired(self):
        """A delivery that went past its date on the shelf must not vanish."""
        self.received_line(self.days(-4))
        self.product.current_stock = 10
        self.product.save()

        self.assertEqual(self.product_expiry(), self.days(-4))
        self.product.refresh_from_db()
        self.assertTrue(self.product.is_expired)

    def test_a_line_without_a_date_leaves_the_product_alone(self):
        self.received_line(self.days(9))
        self.add_line(None)

        purchase_order_into_stock(self.order, self.user)

        self.assertEqual(self.product_expiry(), self.days(9))

    def test_an_order_that_has_only_been_placed_dates_nothing(self):
        """Expiry describes goods in the shop, so an ordered-but-undelivered line is silent."""
        self.add_line(self.days(5))

        self.assertIsNone(self.product_expiry())

    def test_correcting_the_line_corrects_the_product(self):
        """One copy of the date — editing the order is enough, nothing to re-save."""
        item = self.add_line(self.days(10))
        purchase_order_into_stock(self.order, self.user)
        self.assertEqual(self.product_expiry(), self.days(10))

        item.expiry_date = self.days(45)
        item.save()

        self.assertEqual(self.product_expiry(), self.days(45))

    def test_the_movement_log_mentions_the_expiry(self):
        self.add_line(self.days(7))
        purchase_order_into_stock(self.order, self.user)

        movement = StockMovement.objects.get(product=self.product)
        self.assertIn('purchased', movement.reason)
        self.assertIn(self.days(7).strftime('%d %b %Y'), movement.reason)

    # -- ordering through the web form --------------------------------------
    def post_order(self, expiry):
        self.client.force_login(self.user)
        return self.client.post(reverse('purchase-order-create'), {
            'supplier': self.supplier.pk,
            'expected_delivery': self.days(2).strftime('%Y-%m-%d'),
            'items-TOTAL_FORMS': '1',
            'items-INITIAL_FORMS': '0',
            'items-MIN_NUM_FORMS': '0',
            'items-MAX_NUM_FORMS': '1000',
            'items-0-product': self.product.pk,
            'items-0-quantity': '4',
            'items-0-unit_cost': '1.50',
            'items-0-expiry_date': expiry,
        })

    def test_the_order_form_saves_the_expiry_date(self):
        response = self.post_order(self.days(14).strftime('%Y-%m-%d'))
        self.assertEqual(response.status_code, 302, response.content.decode()[:2000])

        item = PurchaseOrderItem.objects.get(purchase_order__supplier=self.supplier)
        self.assertEqual(item.expiry_date, self.days(14))

    def test_the_order_form_still_saves_a_line_without_an_expiry(self):
        response = self.post_order('')
        self.assertEqual(response.status_code, 302, response.content.decode()[:2000])

        item = PurchaseOrderItem.objects.get(purchase_order__supplier=self.supplier)
        self.assertIsNone(item.expiry_date)

    def test_the_edit_page_pre_fills_an_iso_date(self):
        """An <input type="date"> only understands YYYY-MM-DD.

        Rendering `{{ field.value }}` verbatim hands the browser a localized
        date ("Oct. 7, 2026"), which the input then silently discards — so the
        saved date looked lost every time the order was reopened.
        """
        self.add_line(self.days(14))
        self.client.force_login(self.user)

        html = self.client.get(
            reverse('purchase-order-update', args=[self.order.pk])
        ).content.decode()

        match = re.search(r'name="items-0-expiry_date"[^>]*value="([^"]*)"', html)
        self.assertIsNotNone(match, 'no expiry input on the edit page')
        self.assertEqual(match.group(1), self.days(14).strftime('%Y-%m-%d'))


class DeliverySummaryTests(TestCase):
    """What a *delivery* reports about its shelf life.

    One order can hold several use-by dates (one per batch), so the order as a
    whole is only as fresh as its soonest line. The list pages read those
    summaries, so they are worth pinning down on their own.
    """

    def setUp(self):
        self.today = timezone.now().date()
        self.category = Category.objects.create(name='Dairy')
        self.supplier = Supplier.objects.create(
            name='Fresh Co', contact_person='Mary', email='mary@fresh.test', phone='0755',
        )
        self.milk = Product.objects.create(
            name='Fresh Milk', sku='MILK-1', category=self.category,
            supplier=self.supplier, product_type='perishable',
            cost_price=1, selling_price=2,
            current_stock=5, min_stock_level=2, max_stock_level=100,
        )
        self.cheese = Product.objects.create(
            name='Cheddar', sku='CHS-1', category=self.category,
            supplier=self.supplier, product_type='perishable',
            cost_price=3, selling_price=5,
            current_stock=4, min_stock_level=1, max_stock_level=50,
        )
        self.order = PurchaseOrder.objects.create(
            supplier=self.supplier, status='received', expected_delivery=self.today,
        )

    def days(self, count):
        return self.today + timedelta(days=count)

    def add_line(self, expiry, product=None):
        return PurchaseOrderItem.objects.create(
            purchase_order=self.order, product=product or self.milk,
            quantity=10, unit_cost=1, expiry_date=expiry,
        )

    def test_an_order_without_lines_reports_no_expiry(self):
        self.assertIsNone(self.order.earliest_expiry)
        self.assertIsNone(self.order.days_until_earliest_expiry)
        self.assertEqual(self.order.expiry_date_count, 0)

    def test_the_soonest_date_is_the_one_the_order_reports(self):
        """The freshest line does not hide a line that is about to lapse."""
        self.add_line(self.days(40), product=self.cheese)
        self.add_line(self.days(3))

        self.assertEqual(self.order.earliest_expiry, self.days(3))
        self.assertEqual(self.order.latest_expiry, self.days(40))
        self.assertEqual(self.order.days_until_earliest_expiry, 3)

    def test_the_number_of_distinct_dates_is_counted_once_each(self):
        self.add_line(self.days(3))
        self.add_line(self.days(3), product=self.cheese)
        self.add_line(self.days(9), product=self.cheese)

        self.assertEqual(self.order.expiry_date_count, 2)

    def test_lines_without_a_date_do_not_count(self):
        self.add_line(None)
        self.add_line(self.days(6))

        self.assertEqual(self.order.expiry_date_count, 1)
        self.assertEqual(self.order.earliest_expiry, self.days(6))

    def test_lapsed_lines_are_counted(self):
        self.add_line(self.days(-2))
        self.add_line(self.days(5), product=self.cheese)

        self.assertEqual(self.order.expired_line_count, 1)
        self.assertEqual(self.order.earliest_expiry, self.days(-2))
        self.assertEqual(self.order.days_until_earliest_expiry, -2)

    def test_a_line_reports_its_own_days_left(self):
        item = self.add_line(self.days(4))
        self.assertEqual(item.days_until_expiry, 4)

    def test_a_line_without_a_date_has_no_days_left(self):
        self.assertIsNone(self.add_line(None).days_until_expiry)



class ReceivedPurchasesPageTests(TestCase):
    """The deliveries page: purchased orders, separated one block per order.

    The purchase order list mixes open and closed orders together; this page is
    the other half of the split, showing the deliveries that were actually
    bought in along with the shelf life their lines recorded.
    """

    def setUp(self):
        self.user = get_user_model().objects.create_user(
            username='manager', password='secret-pass-123',
        )
        assign_role(self.user, GROUP_STOCK)
        self.today = timezone.now().date()
        self.category = Category.objects.create(name='Dairy')
        self.supplier = Supplier.objects.create(
            name='Fresh Co', contact_person='Mary', email='mary@fresh.test', phone='0755',
        )
        self.other_supplier = Supplier.objects.create(
            name='Corner Store', contact_person='Ali', email='ali@corner.test', phone='0756',
        )
        self.milk = Product.objects.create(
            name='Fresh Milk', sku='MILK-1', category=self.category,
            supplier=self.supplier, product_type='perishable',
            cost_price=1, selling_price=2,
            current_stock=5, min_stock_level=2, max_stock_level=100,
        )
        self.cheese = Product.objects.create(
            name='Cheddar', sku='CHS-1', category=self.category,
            supplier=self.supplier, product_type='perishable',
            cost_price=3, selling_price=5,
            current_stock=4, min_stock_level=1, max_stock_level=50,
        )

    def days(self, count):
        return self.today + timedelta(days=count)

    def delivery(self, expiry, product=None, supplier=None, status='received', quantity=10):
        """A purchase order with a single line, ready to be read as a delivery."""
        order = PurchaseOrder.objects.create(
            supplier=supplier or self.supplier, status=status,
            expected_delivery=self.today,
        )
        PurchaseOrderItem.objects.create(
            purchase_order=order, product=product or self.milk,
            quantity=quantity, unit_cost=1, expiry_date=expiry,
        )
        order.calculate_total_amount()
        return order

    def open_page(self, **params):
        self.client.force_login(self.user)
        return self.client.get(reverse('received-purchases'), params)

    def page_html(self, **params):
        return self.open_page(**params).content.decode()

    def deliveries_html(self, html):
        """Only the delivery blocks.

        The notification bell in the sidebar names pending orders too, so a
        page-wide search for an order number proves nothing about this list.
        """
        marker = '<!-- One block per delivery -->'
        self.assertIn(marker, html)
        return html.split(marker, 1)[1]

    def delivery_blocks(self, **params):
        """The delivery blocks for one request, without the sidebar around them."""
        return self.deliveries_html(self.page_html(**params))

    # -- what is on the page -------------------------------------------------
    def test_only_purchased_orders_are_shown(self):
        """An order that was never bought in is not a delivery."""
        bought = self.delivery(self.days(5))
        placed = self.delivery(self.days(5), status='ordered')
        dropped = self.delivery(self.days(5), status='cancelled')
        drafted = self.delivery(self.days(5), status='draft')

        response = self.open_page()
        listed = {order.pk for order in response.context['purchase_orders']}
        html = self.deliveries_html(response.content.decode())

        self.assertEqual(listed, {bought.pk})
        self.assertIn(f'PO-{bought.pk:06d}', html)
        for order in (placed, dropped, drafted):
            self.assertNotIn(f'PO-{order.pk:06d}', html)

    def test_each_delivery_carries_its_own_lines_and_dates(self):
        first = self.delivery(self.days(4))
        PurchaseOrderItem.objects.create(
            purchase_order=first, product=self.cheese, quantity=2, unit_cost=3,
            expiry_date=self.days(30),
        )
        second = self.delivery(self.days(60), product=self.cheese, supplier=self.other_supplier)

        html = self.delivery_blocks()

        self.assertIn(f'PO-{first.pk:06d}', html)
        self.assertIn(f'PO-{second.pk:06d}', html)
        # Both lines of the first delivery, each with its own use-by date.
        self.assertIn(self.days(4).strftime('%b %d, %Y'), html)
        self.assertIn(self.days(30).strftime('%b %d, %Y'), html)
        self.assertIn(self.days(60).strftime('%b %d, %Y'), html)

    def test_a_delivery_with_several_dates_is_summarised_by_its_soonest(self):
        order = self.delivery(self.days(50))
        PurchaseOrderItem.objects.create(
            purchase_order=order, product=self.cheese, quantity=2, unit_cost=3,
            expiry_date=self.days(2),
        )

        html = self.delivery_blocks()

        self.assertIn('Use-by', html)
        self.assertIn('2 dates on this order', html)
        # The soonest of the two is what the block reports.
        self.assertIn(f'Use-by {self.days(2).strftime("%b %d, %Y")}', html)
        # ...while the far date is still readable on its own line.
        self.assertIn(self.days(50).strftime('%b %d, %Y'), html)

    def test_a_delivery_without_any_date_says_so(self):
        self.delivery(None)

        html = self.delivery_blocks()

        self.assertIn('No expiry recorded on this delivery', html)
        self.assertIn('Not recorded', html)

    def test_a_lapsed_delivery_is_flagged(self):
        self.delivery(self.days(-3))

        html = self.delivery_blocks()

        self.assertIn('Expired 3 days ago', html)
        self.assertIn('table-danger', html)


    # -- narrowing the list --------------------------------------------------
    def test_the_shelf_life_filter_keeps_only_lapsed_deliveries(self):
        lapsed = self.delivery(self.days(-1))
        fresh = self.delivery(self.days(10))

        html = self.delivery_blocks(expiry='expired')

        self.assertIn(f'PO-{lapsed.pk:06d}', html)
        self.assertNotIn(f'PO-{fresh.pk:06d}', html)

    def test_the_shelf_life_filter_finds_soon_to_lapse_deliveries(self):
        soon = self.delivery(self.days(2))
        far = self.delivery(self.days(90))

        html = self.delivery_blocks(expiry='soon')

        self.assertIn(f'PO-{soon.pk:06d}', html)
        self.assertNotIn(f'PO-{far.pk:06d}', html)

    def test_the_shelf_life_filter_finds_deliveries_with_no_date(self):
        dateless = self.delivery(None)
        dated = self.delivery(self.days(10))

        html = self.delivery_blocks(expiry='none')

        self.assertIn(f'PO-{dateless.pk:06d}', html)
        self.assertNotIn(f'PO-{dated.pk:06d}', html)

    def test_a_delivery_is_findable_by_the_product_it_brought(self):
        milk_order = self.delivery(self.days(10))
        cheese_order = self.delivery(self.days(10), product=self.cheese)

        html = self.delivery_blocks(search='Cheddar')

        self.assertIn(f'PO-{cheese_order.pk:06d}', html)
        self.assertNotIn(f'PO-{milk_order.pk:06d}', html)

    def test_a_delivery_is_findable_by_its_supplier(self):
        mine = self.delivery(self.days(10))
        theirs = self.delivery(self.days(10), supplier=self.other_supplier)

        html = self.delivery_blocks(supplier=self.supplier.pk)

        self.assertIn(f'PO-{mine.pk:06d}', html)
        self.assertNotIn(f'PO-{theirs.pk:06d}', html)

    # -- the numbers above the list ------------------------------------------
    def test_the_statistics_describe_every_delivery_in_scope(self):
        self.delivery(self.days(-1))
        self.delivery(self.days(2), product=self.cheese)
        self.delivery(self.days(90), supplier=self.other_supplier, status='ordered')

        response = self.open_page()
        context = response.context

        self.assertEqual(context['delivery_count'], 2)
        self.assertEqual(context['delivered_line_count'], 2)
        self.assertEqual(context['expired_batch_count'], 1)
        self.assertEqual(context['expiring_batch_count'], 1)
        self.assertEqual(context['delivered_value'], 20)

    def test_the_page_needs_a_login(self):
        response = self.client.get(reverse('received-purchases'))
        self.assertEqual(response.status_code, 302)
        self.assertIn('/login/', response['Location'])

    def test_pagination_keeps_the_filters(self):
        """`purchase_orders` is the page's QuerySet, so the controls need page_obj."""
        for _ in range(11):
            self.delivery(self.days(2))

        html = self.page_html(expiry='soon')

        self.assertIn('page=2', html)
        self.assertIn('expiry=soon', html)
        self.assertEqual(self.open_page(page=2, expiry='soon').status_code, 200)

    def test_the_page_is_linked_from_the_sidebar(self):
        html = self.page_html()
        self.assertIn(reverse('received-purchases'), html)


class PurchaseOrderListExpiryTests(TestCase):
    """The order list has to show the shelf life too, not just the detail page."""

    def setUp(self):
        self.user = get_user_model().objects.create_user(
            username='manager', password='secret-pass-123',
        )
        self.client.force_login(self.user)
        assign_role(self.user, GROUP_STOCK)
        self.today = timezone.now().date()
        self.category = Category.objects.create(name='Dairy')
        self.supplier = Supplier.objects.create(
            name='Fresh Co', contact_person='Mary', email='mary@fresh.test', phone='0755',
        )
        self.product = Product.objects.create(
            name='Fresh Milk', sku='MILK-1', category=self.category,
            supplier=self.supplier, product_type='perishable',
            cost_price=1, selling_price=2,
            current_stock=5, min_stock_level=2, max_stock_level=100,
        )

    def days(self, count):
        return self.today + timedelta(days=count)

    def order(self, expiry, status='received'):
        order = PurchaseOrder.objects.create(
            supplier=self.supplier, status=status, expected_delivery=self.today,
        )
        if expiry != 'skip':
            PurchaseOrderItem.objects.create(
                purchase_order=order, product=self.product,
                quantity=10, unit_cost=1, expiry_date=expiry,
            )
        order.calculate_total_amount()
        return order

    def page_html(self, **params):
        return self.client.get(reverse('purchase-order-list'), params).content.decode()

    def table_html(self, **params):
        """Only the rows of the orders table.

        The notification bell in the sidebar names pending orders too, so a
        page-wide match on an order number proves nothing about this list.
        """
        html = self.page_html(**params)
        self.assertIn('<tbody>', html)
        return html.split('<tbody>', 1)[1].split('</tbody>', 1)[0]

    def test_the_table_has_an_expiry_column(self):
        self.assertIn('<th width="14%">Expiry</th>', self.page_html())

    def test_pagination_shows_up_once_the_list_is_longer_than_a_page(self):
        """The controls were dead: they read `purchase_orders`, the page's QuerySet."""
        for _ in range(21):
            PurchaseOrder.objects.create(
                supplier=self.supplier, status='received',
                expected_delivery=self.days(3),
            )

        html = self.page_html()

        self.assertIn('page=2', html)
        self.assertIn('total orders', html)
        self.assertEqual(
            self.client.get(reverse('purchase-order-list'), {'page': 2}).status_code, 200,
        )

    def test_a_purchased_order_shows_the_use_by_date_of_its_line(self):
        self.order(self.days(6))

        html = self.table_html()

        self.assertIn(self.days(6).strftime('%b %d, %Y'), html)
        self.assertIn('6 days left', html)

    def test_a_purchased_order_without_dates_says_not_recorded(self):
        self.order('skip')

        self.assertIn('Not recorded', self.table_html())

    def test_a_lapsed_line_is_flagged_on_the_order_row(self):
        self.order(self.days(-1))

        html = self.table_html()

        self.assertIn('Expired &middot; 1 line past', html)


    # -- received purchases kept apart from the orders still open -------------
    def test_the_status_tabs_name_every_status(self):
        html = self.page_html()

        for label in ('All orders', 'Not placed', 'Placed', 'Purchased', 'Cancelled'):
            self.assertIn(label, html)

    def test_the_purchased_tab_shows_only_received_orders(self):
        bought = self.order(self.days(4), status='received')
        planned = self.order(self.days(4), status='ordered')

        html = self.table_html(status='received')

        self.assertIn(f'PO-{bought.pk:06d}', html)
        self.assertNotIn(f'PO-{planned.pk:06d}', html)

    def test_the_tabs_keep_counting_the_status_you_are_not_looking_at(self):
        """Switching to the purchased tab must not zero the other counters."""
        self.order(self.days(4), status='received')
        self.order(self.days(4), status='ordered')
        self.order(self.days(4), status='cancelled')

        response = self.client.get(reverse('purchase-order-list'), {'status': 'received'})
        counts = {value: count for value, _, count, _ in response.context['status_tabs']}

        self.assertEqual(counts[''], 3)
        self.assertEqual(counts['received'], 1)
        self.assertEqual(counts['ordered'], 1)
        self.assertEqual(counts['cancelled'], 1)

    def test_the_tab_keeps_the_other_filters(self):
        """A tab is a link, so the supplier / search narrowing has to survive."""
        mine = self.order(self.days(4), status='received')
        planned = self.order(self.days(4), status='ordered')

        rows = self.table_html(status='received', supplier=self.supplier.pk)

        self.assertIn(f'PO-{mine.pk:06d}', rows)
        self.assertNotIn(f'PO-{planned.pk:06d}', rows)
        # The tab links carry the narrowing with them instead of dropping it.
        self.assertIn(
            f'supplier={self.supplier.pk}',
            self.page_html(status='received', supplier=self.supplier.pk),
        )

