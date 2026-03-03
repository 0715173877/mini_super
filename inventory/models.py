from django.db import models
from django.core.validators import MinValueValidator

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
    supplier = models.ForeignKey(Supplier, on_delete=models.PROTECT)
    product_type = models.CharField(max_length=20, choices=PRODUCT_TYPES)
    
    # Pricing
    cost_price = models.DecimalField(max_digits=10, decimal_places=2, validators=[MinValueValidator(0)])
    selling_price = models.DecimalField(max_digits=10, decimal_places=2, validators=[MinValueValidator(0)])
    
    # Stock tracking
    current_stock = models.DecimalField(max_digits=10, decimal_places=3, default=0)  # Decimal for weight-based items
    min_stock_level = models.DecimalField(max_digits=10, decimal_places=3, default=0)
    max_stock_level = models.DecimalField(max_digits=10, decimal_places=3, default=0)
    
    # Perishable goods specific
    expiry_date = models.DateField(null=True, blank=True)
    requires_refrigeration = models.BooleanField(default=False)
    
    # High-risk tracking
    is_high_value = models.BooleanField(default=False)
    is_high_theft_risk = models.BooleanField(default=False)
    profit_margin_display = models.PositiveIntegerField(default=0)
    
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

class StockMovement(models.Model):
    MOVEMENT_TYPES = [
        ('in', 'Stock In'),
        ('out', 'Stock Out'),
        ('adjustment', 'Adjustment'),
        ('waste', 'Waste'),
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
    
    supplier = models.ForeignKey(Supplier, on_delete=models.PROTECT)
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
    
    def __str__(self):
        return f"PO-{self.id:06d}"

class PurchaseOrderItem(models.Model):
    purchase_order = models.ForeignKey(PurchaseOrder, on_delete=models.CASCADE, related_name='items')
    product = models.ForeignKey(Product, on_delete=models.PROTECT)
    quantity = models.DecimalField(max_digits=10, decimal_places=3)
    unit_cost = models.DecimalField(max_digits=10, decimal_places=2)
    
    @property
    def total_cost(self):
        return self.quantity * self.unit_cost