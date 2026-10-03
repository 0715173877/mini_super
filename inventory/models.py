from django.db import models
from django.db.models import F, Max, Min, Q, Sum
from django.db.models.functions import Coalesce
from django.core.validators import MinValueValidator
from django.utils import timezone

class Category(models.Model):
    name = models.CharField(max_length=100)
    description = models.TextField(blank=True)
    
    def __str__(self):
        return self.name

class Supplier(models.Model):
    name = models.CharField(max_length=200)
    contact_person = models.CharField(max_length=100)
    email = models.EmailField()
    phone = models.CharField(max_length=20)
    address = models.TextField(blank=True, null=True)  # Add this field
    is_active = models.BooleanField(default=True)  # Add this field
    
    def __str__(self):
        return self.name
    
    def product_count(self):
        return self.product_set.count()

class ProductQuerySet(models.QuerySet):
    """Product queries that need the shelf life computed onto them.

    Expiry belongs to a *delivery*, not to the product: two deliveries of the
    same item can carry different use-by dates, so the only place a date is ever
    stored is :attr:`PurchaseOrderItem.expiry_date`. The bell and the product
    pages still need one answer per product, so it is derived here from the
    deliveries that product has actually received.
    """

    def with_expiry(self):
        """Annotate ``effective_expiry_date`` — when this shelf stock expires.

        The rule mirrors how the shop thinks about a shelf:

        * the **soonest** use-by date that has not passed yet — that is the
          delivery the shelf is about to lose; otherwise
        * the **latest** date already recorded — so a delivery that went past its
          date while still in stock keeps reporting as expired, instead of the
          alert quietly disappearing because nothing newer exists.

        A product with no received delivery carrying a date annotates to NULL,
        which is what ``Product.expiry_date`` reports as "not recorded".
        """
        today = timezone.now().date()
        received = Q(purchaseorderitem__purchase_order__status='received')
        return self.annotate(
            effective_expiry_date=Coalesce(
                Min(
                    'purchaseorderitem__expiry_date',
                    filter=received & Q(purchaseorderitem__expiry_date__gte=today),
                ),
                Max(
                    'purchaseorderitem__expiry_date',
                    filter=received & Q(purchaseorderitem__expiry_date__isnull=False),
                ),
                output_field=models.DateField(),
            )
        )


class Product(models.Model):
    PRODUCT_TYPES = [
        ('perishable', 'Perishable'),
        ('non_perishable', 'Non-Perishable'),
        ('frozen', 'Frozen'),
        ('non_food', 'Non-Food'),
    ]
    
    name = models.CharField(max_length=200)
    sku = models.CharField(max_length=50, unique=True)
    barcode = models.CharField(max_length=100, blank=True)
    category = models.ForeignKey(Category, on_delete=models.PROTECT)
    # Optional: a product may be stocked without a recorded supplier (walk-in / unknown vendor)
    supplier = models.ForeignKey(Supplier, on_delete=models.PROTECT, null=True, blank=True)
    product_type = models.CharField(max_length=20, choices=PRODUCT_TYPES)
    
    # Pricing
    cost_price = models.DecimalField(max_digits=10, decimal_places=2, validators=[MinValueValidator(0)])
    selling_price = models.DecimalField(max_digits=10, decimal_places=2, validators=[MinValueValidator(0)])
    
    # Stock tracking
    current_stock = models.DecimalField(max_digits=10, decimal_places=3, default=0)  # Decimal for weight-based items
    min_stock_level = models.DecimalField(max_digits=10, decimal_places=3, default=0)
    max_stock_level = models.DecimalField(max_digits=10, decimal_places=3, default=0)
    
    # Perishable goods specific.
    # NOTE: there is deliberately no expiry_date column here. A use-by date is a
    # fact about a delivery, so it is recorded on the purchase order line
    # (PurchaseOrderItem.expiry_date) and read back through the ``expiry_date``
    # property below. Use ``Product.objects.with_expiry()`` to have it computed
    # in the database.
    requires_refrigeration = models.BooleanField(default=False)
    
    # High-risk tracking
    is_high_value = models.BooleanField(default=False)
    is_high_theft_risk = models.BooleanField(default=False)
    profit_margin_display = models.PositiveIntegerField(default=0)
    
    objects = ProductQuerySet.as_manager()
    
    def __str__(self):
        return f"{self.name} ({self.sku})"
    
    @property
    def stock_status(self):
        if self.current_stock <= 0:
            return 'out_of_stock'
        elif self.current_stock <= self.min_stock_level:
            return 'low_stock'
        else:
            return 'in_stock'
    
    @property
    def profit_margin(self):
        if self.cost_price > 0:
            return ((self.selling_price - self.cost_price) / self.cost_price) * 100
        return 0

    @property
    def stock_value(self):
        """Value of the stock on hand, at cost price."""
        return self.current_stock * self.cost_price

    @property
    def expiry_date(self):
        """When this product's shelf stock expires — derived, never stored.

        The date is recorded per delivery (``PurchaseOrderItem.expiry_date``)
        and read back here, so editing a purchase order is the one place a
        use-by date is changed and nothing can drift out of sync.

        ``Product.objects.with_expiry()`` computes it in the database; on a
        product that was not fetched that way, the first access falls back to a
        single narrow query and caches the answer on the instance, so a template
        that renders the same product twice still asks the database once.
        """
        if not hasattr(self, 'effective_expiry_date'):
            self.effective_expiry_date = (
                Product.objects.with_expiry()
                .filter(pk=self.pk)
                .values_list('effective_expiry_date', flat=True)
                .first()
            )
        return self.effective_expiry_date

    @property
    def is_expired(self):
        """True when the recorded expiry date has already passed."""
        return bool(self.expiry_date and self.expiry_date < timezone.now().date())

    @property
    def days_until_expiry(self):
        """Signed days left before the expiry date (negative = already expired)."""
        if not self.expiry_date:
            return None
        return (self.expiry_date - timezone.now().date()).days

    @property
    def expiry_status(self):
        """``'expired'`` / ``'expiring_soon'`` / ``'ok'`` / ``''`` when no date is set.

        The 7-day horizon is kept in step with ``core.notifications.EXPIRY_SOON_DAYS``,
        which is what the bell and the sidebar badge count by.
        """
        days = self.days_until_expiry
        if days is None:
            return ''
        if days < 0:
            return 'expired'
        if days <= 7:
            return 'expiring_soon'
        return 'ok'

class StockMovement(models.Model):
    MOVEMENT_TYPES = [
        ('in', 'Stock In'),
        ('out', 'Stock Out'),
        ('adjustment', 'Adjustment'),
        ('waste', 'Waste'),
        # Goods a customer brings back — stock re-enters the shop.
        ('customer_return', 'Customer Return'),
        # Goods sent back to a supplier — stock leaves the shop.
        ('supplier_return', 'Supplier Return'),
    ]
    
    product = models.ForeignKey(Product, on_delete=models.CASCADE)
    movement_type = models.CharField(max_length=20, choices=MOVEMENT_TYPES)
    quantity = models.DecimalField(max_digits=10, decimal_places=3)
    previous_stock = models.DecimalField(max_digits=10, decimal_places=3)
    new_stock = models.DecimalField(max_digits=10, decimal_places=3)
    reason = models.TextField(blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    user = models.ForeignKey('auth.User', on_delete=models.PROTECT)
    
    class Meta:
        ordering = ['-created_at']

class PurchaseOrder(models.Model):
    ORDER_STATUS = [
        ('draft', 'Draft'),
        ('ordered', 'Ordered'),
        ('received', 'Received'),
        ('cancelled', 'Cancelled'),
    ]
    
    # Optional: an order may be raised for a walk-in / cash purchase with no recorded supplier
    supplier = models.ForeignKey(Supplier, on_delete=models.PROTECT, null=True, blank=True)
    order_date = models.DateTimeField(auto_now_add=True)
    expected_delivery = models.DateField()
    status = models.CharField(max_length=20, choices=ORDER_STATUS, default='draft')
    total_amount = models.DecimalField(max_digits=12, decimal_places=2, default=0)
    
    def calculate_total_amount(self):
        """Calculate total amount from order items"""
        total = self.items.aggregate(
            total=Sum(F('quantity') * F('unit_cost'))
        )['total'] or 0
        self.total_amount = total
        self.save()
        return total
    
    @property
    def is_overdue(self):
        """Check if the order is overdue"""
        if self.expected_delivery and self.status == 'ordered':
            return timezone.now().date() > self.expected_delivery
        return False
    
    @property
    def is_upcoming(self):
        """Check if delivery is within 3 days"""
        if self.expected_delivery and self.status == 'ordered':
            days_until = (self.expected_delivery - timezone.now().date()).days
            return 0 < days_until <= 3
        return False
    
    @property
    def days_until_delivery(self):
        """Days until expected delivery"""
        if self.expected_delivery and self.status == 'ordered':
            return (self.expected_delivery - timezone.now().date()).days
        return None
    
    @property
    def days_overdue(self):
        """Days overdue if delivery is late"""
        if self.expected_delivery and self.status == 'ordered' and self.is_overdue:
            return (timezone.now().date() - self.expected_delivery).days
        return 0

    # -- shelf life of what this order delivered -----------------------------
    # Read straight off the lines (they are the only place a use-by date lives),
    # so these stay cheap on a queryset that used prefetch_related('items').
    @property
    def line_expiry_dates(self):
        """Distinct use-by dates recorded on the order's lines, soonest first."""
        return sorted({item.expiry_date for item in self.items.all() if item.expiry_date})

    @property
    def earliest_expiry(self):
        """The soonest use-by date on the order's lines, or ``None`` if none was recorded.

        A single order can carry several dates (one per batch), so the order as a
        whole is only as fresh as its soonest line — that is the one worth showing
        in a list, and the one the product's shelf life is derived from.
        """
        dates = self.line_expiry_dates
        return dates[0] if dates else None

    @property
    def latest_expiry(self):
        """The furthest-out use-by date on the order's lines, or ``None``."""
        dates = self.line_expiry_dates
        return dates[-1] if dates else None

    @property
    def expiry_date_count(self):
        """How many distinct use-by dates the delivery carried."""
        return len(self.line_expiry_dates)

    @property
    def days_until_earliest_expiry(self):
        """Days left on the soonest line, ``None`` when no line recorded a date."""
        expiry = self.earliest_expiry
        if expiry is None:
            return None
        return (expiry - timezone.now().date()).days

    @property
    def expired_line_count(self):
        """Lines bought in whose use-by date has already passed."""
        return sum(1 for item in self.items.all() if item.is_expired)

    def __str__(self):
        return f"PO-{self.id:06d}"

class PurchaseOrderItem(models.Model):
    purchase_order = models.ForeignKey(PurchaseOrder, on_delete=models.CASCADE, related_name='items')
    product = models.ForeignKey(Product, on_delete=models.PROTECT)
    quantity = models.DecimalField(max_digits=10, decimal_places=3)
    unit_cost = models.DecimalField(max_digits=10, decimal_places=2)
    # Use-by date printed on the delivery, and the *only* place a shelf life is
    # recorded — the product row stores none. Purchasing the order changes stock
    # only; the product's expiry is derived from the lines of the orders it has
    # received (see Product.objects.with_expiry()). Keeping the single copy here
    # is what stops a product's date from drifting away from its delivery.
    expiry_date = models.DateField(
        null=True, blank=True,
        help_text='Optional. The use-by date printed on this delivery — the shelf life the shop reports for this product.',
    )

    @property
    def total_cost(self):
        return self.quantity * self.unit_cost

    @property
    def is_expired(self):
        return bool(self.expiry_date and self.expiry_date < timezone.now().date())

    @property
    def days_until_expiry(self):
        """Days left on this delivery; ``None`` when no date was recorded."""
        if not self.expiry_date:
            return None
        return (self.expiry_date - timezone.now().date()).days


class SupplierReturn(models.Model):
    """Goods sent back to a supplier.

    Creating one removes the returned quantities from stock (one
    ``StockMovement`` with type ``supplier_return`` per line).
    """
    # Optional: goods can go back to a walk-in / unknown vendor.
    supplier = models.ForeignKey(Supplier, on_delete=models.PROTECT, null=True, blank=True)
    # Optional link to the purchase order the goods originally came from.
    purchase_order = models.ForeignKey(
        PurchaseOrder, on_delete=models.SET_NULL, null=True, blank=True, related_name='returns'
    )
    reference = models.CharField(max_length=50, unique=True)
    total_amount = models.DecimalField(max_digits=12, decimal_places=2, default=0)
    reason = models.TextField(blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    processed_by = models.ForeignKey('auth.User', on_delete=models.PROTECT)

    class Meta:
        ordering = ['-created_at']

    def __str__(self):
        return f"SR-{self.id:06d}"

    def calculate_total_amount(self):
        """Total value of the returned goods, at cost price."""
        total = self.items.aggregate(
            total=Sum(F('quantity') * F('unit_cost'))
        )['total'] or 0
        self.total_amount = total
        self.save()
        return total


class SupplierReturnItem(models.Model):
    supplier_return = models.ForeignKey(SupplierReturn, on_delete=models.CASCADE, related_name='items')
    product = models.ForeignKey(Product, on_delete=models.PROTECT)
    quantity = models.DecimalField(max_digits=10, decimal_places=3)
    unit_cost = models.DecimalField(max_digits=10, decimal_places=2)

    @property
    def total_cost(self):
        return self.quantity * self.unit_cost