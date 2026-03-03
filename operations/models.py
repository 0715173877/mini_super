from django.db import models
from django.core.validators import MinValueValidator
from inventory.models import Product

class Staff(models.Model):
    user = models.OneToOneField('auth.User', on_delete=models.CASCADE)
    employee_id = models.CharField(max_length=20, unique=True)
    position = models.CharField(max_length=100)
    phone = models.CharField(max_length=20)
    hire_date = models.DateField()
    
    def __str__(self):
        return f"{self.user.get_full_name()} ({self.employee_id})"

class Shift(models.Model):
    staff = models.ForeignKey(Staff, on_delete=models.CASCADE)
    shift_date = models.DateField()
    start_time = models.TimeField()
    end_time = models.TimeField()
    hours_worked = models.DecimalField(max_digits=4, decimal_places=2, validators=[MinValueValidator(0)])
    
    class Meta:
        ordering = ['-shift_date', 'staff']

class WasteRecord(models.Model):
    WASTE_CATEGORIES = [
        ('spoilage', 'Spoilage'),
        ('damage', 'Damage'),
        ('expired', 'Expired'),
        ('other', 'Other'),
    ]
    
    product = models.ForeignKey(Product, on_delete=models.CASCADE)
    quantity = models.DecimalField(max_digits=10, decimal_places=3)
    category = models.CharField(max_length=20, choices=WASTE_CATEGORIES)
    cost_value = models.DecimalField(max_digits=10, decimal_places=2)  # Cost of wasted goods
    reason = models.TextField()
    recorded_by = models.ForeignKey('auth.User', on_delete=models.PROTECT)
    created_at = models.DateTimeField(auto_now_add=True)
    
    class Meta:
        ordering = ['-created_at']

class PeakHour(models.Model):
    date = models.DateField()
    hour = models.PositiveIntegerField()  # 0-23
    customer_count = models.PositiveIntegerField()
    total_sales = models.DecimalField(max_digits=10, decimal_places=2)
    
    class Meta:
        ordering = ['-date', 'hour']
        unique_together = ['date', 'hour']

class SupplierPerformance(models.Model):
    supplier = models.ForeignKey('inventory.Supplier', on_delete=models.CASCADE)
    evaluation_date = models.DateField()
    on_time_delivery_rate = models.DecimalField(max_digits=5, decimal_places=2)  # Percentage
    order_accuracy = models.DecimalField(max_digits=5, decimal_places=2)  # Percentage
    product_quality_score = models.DecimalField(max_digits=3, decimal_places=1)  # 1-5 scale
    notes = models.TextField(blank=True)
    
    class Meta:
        ordering = ['-evaluation_date']