from django.db import models
from django.db.models import Sum, F
from django.core.validators import MinValueValidator
from inventory.models import Product

class Customer(models.Model):
    name = models.CharField(max_length=200, blank=True)  # Optional for walk-in customers
    phone = models.CharField(max_length=20, blank=True)
    email = models.EmailField(blank=True)
    is_regular = models.BooleanField(default=False)
    
    def __str__(self):
        return self.name or f"Anonymous-{self.id}"

class Sale(models.Model):
    PAYMENT_METHODS = [
        ('cash', 'Cash'),
        ('card', 'Credit/Debit Card'),
        ('mobile', 'Mobile Wallet'),
        ('transfer', 'Bank Transfer'),
    ]
    
    customer = models.ForeignKey(Customer, on_delete=models.SET_NULL, null=True, blank=True)
    transaction_id = models.CharField(max_length=50, unique=True)
    total_amount = models.DecimalField(max_digits=12, decimal_places=2, validators=[MinValueValidator(0)])
    tax_amount = models.DecimalField(max_digits=12, decimal_places=2, default=0)
    payment_method = models.CharField(max_length=20, choices=PAYMENT_METHODS)
    created_at = models.DateTimeField(auto_now_add=True)
    cashier = models.ForeignKey('auth.User', on_delete=models.PROTECT)
    
    class Meta:
        ordering = ['-created_at']
    
    def __str__(self):
        return f"Sale-{self.transaction_id}"

class SaleItem(models.Model):
    sale = models.ForeignKey(Sale, on_delete=models.CASCADE, related_name='items')
    product = models.ForeignKey(Product, on_delete=models.CASCADE)
    quantity = models.DecimalField(max_digits=10, decimal_places=3)
    unit_price = models.DecimalField(max_digits=10, decimal_places=2)
    
    @property
    def total_price(self):
        return self.quantity * self.unit_price

class DailySummary(models.Model):
    date = models.DateField(unique=True)
    total_sales = models.DecimalField(max_digits=12, decimal_places=2, default=0)
    total_customers = models.PositiveIntegerField(default=0)
    cash_sales = models.DecimalField(max_digits=12, decimal_places=2, default=0)
    card_sales = models.DecimalField(max_digits=12, decimal_places=2, default=0)
    mobile_sales = models.DecimalField(max_digits=12, decimal_places=2, default=0)
    
    class Meta:
        ordering = ['-date']
    
    def __str__(self):
        return f"Summary-{self.date}"


class CustomerReturn(models.Model):
    """Goods a customer brings back.

    Creating one adds the returned quantities back into stock (one
    ``StockMovement`` with type ``customer_return`` per line).
    """
    customer = models.ForeignKey(Customer, on_delete=models.SET_NULL, null=True, blank=True)
    # Optional link to the original sale the goods were bought on.
    sale = models.ForeignKey(Sale, on_delete=models.SET_NULL, null=True, blank=True, related_name='returns')
    reference = models.CharField(max_length=50, unique=True)
    total_amount = models.DecimalField(max_digits=12, decimal_places=2, default=0)
    reason = models.TextField(blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    processed_by = models.ForeignKey('auth.User', on_delete=models.PROTECT)

    class Meta:
        ordering = ['-created_at']

    def __str__(self):
        return f"CR-{self.id:06d}"

    def calculate_total_amount(self):
        """Value refunded for the returned goods."""
        total = self.items.aggregate(
            total=Sum(F('quantity') * F('unit_price'))
        )['total'] or 0
        self.total_amount = total
        self.save()
        return total


class CustomerReturnItem(models.Model):
    customer_return = models.ForeignKey(CustomerReturn, on_delete=models.CASCADE, related_name='items')
    product = models.ForeignKey(Product, on_delete=models.CASCADE)
    quantity = models.DecimalField(max_digits=10, decimal_places=3)
    unit_price = models.DecimalField(max_digits=10, decimal_places=2)

    @property
    def total_price(self):
        return self.quantity * self.unit_price