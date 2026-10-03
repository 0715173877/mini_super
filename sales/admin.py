from django.contrib import admin
from django.utils.html import format_html

from .models import CustomerReturn, CustomerReturnItem
from core.formatting import format_money


class CustomerReturnItemInline(admin.TabularInline):
    """Inline display of the items a customer brought back."""
    model = CustomerReturnItem
    fields = ['product', 'quantity', 'unit_price', 'line_total_display']
    readonly_fields = ['line_total_display']
    extra = 1

    def line_total_display(self, obj):
        return format_money(obj.total_price)
    line_total_display.short_description = 'Line Total'


@admin.register(CustomerReturn)
class CustomerReturnAdmin(admin.ModelAdmin):
    list_display = [
        'reference', 'created_at', 'customer', 'sale',
        'item_count', 'total_amount_display', 'processed_by',
    ]
    list_filter = ['created_at']
    search_fields = ['reference', 'customer__name', 'sale__transaction_id']
    readonly_fields = ['reference', 'total_amount', 'created_at', 'processed_by']
    date_hierarchy = 'created_at'
    list_per_page = 20

    inlines = [CustomerReturnItemInline]

    def item_count(self, obj):
        return obj.items.count()
    item_count.short_description = 'Items'

    def total_amount_display(self, obj):
        return format_money(obj.total_amount)
    total_amount_display.short_description = 'Refund'


@admin.register(CustomerReturnItem)
class CustomerReturnItemAdmin(admin.ModelAdmin):
    list_display = ['customer_return', 'product', 'quantity', 'unit_price_display', 'line_total_display']
    list_filter = ['customer_return__created_at']
    search_fields = ['product__name', 'customer_return__reference']
    list_per_page = 50

    def unit_price_display(self, obj):
        return format_money(obj.unit_price)
    unit_price_display.short_description = 'Unit Price'

    def line_total_display(self, obj):
        return format_money(obj.total_price)
    line_total_display.short_description = 'Line Total'
