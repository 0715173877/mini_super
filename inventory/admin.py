from django.contrib import admin
from django.utils.html import format_html
from django.urls import reverse
from django.db.models import Sum, Count
from .models import (
    Category, Supplier, Product, StockMovement, PurchaseOrder, PurchaseOrderItem,
    SupplierReturn, SupplierReturnItem,
)
from core.formatting import format_money

class ProductInline(admin.TabularInline):
    """Inline display of products for Category and Supplier"""
    model = Product
    fields = ['name', 'sku', 'current_stock', 'selling_price', 'stock_status_display']
    readonly_fields = ['stock_status_display']
    extra = 0
    can_delete = False
    show_change_link = True
    
    def stock_status_display(self, obj):
        if obj.current_stock <= 0:
            return format_html('<span style="color: red;">● Out of Stock</span>')
        elif obj.current_stock <= obj.min_stock_level:
            return format_html('<span style="color: orange;">● Low Stock</span>')
        else:
            return format_html('<span style="color: green;">● In Stock</span>')
    stock_status_display.short_description = 'Status'

@admin.register(Category)
class CategoryAdmin(admin.ModelAdmin):
    list_display = ['name', 'product_count', 'created_display']
    search_fields = ['name', 'description']
    list_per_page = 20
    
    def product_count(self, obj):
        return obj.product_set.count()
    product_count.short_description = 'Products'
    
    def created_display(self, obj):
        # This will show when we add auto created_ats
        return "—"
    created_display.short_description = 'Created'
    
    # Optional: Add inlines to see products in category
    inlines = [ProductInline]

@admin.register(Supplier)
class SupplierAdmin(admin.ModelAdmin):
    list_display = ['name', 'contact_person', 'email', 'phone', 'product_count', 'is_active_display']
    list_filter = []  # Add if you have is_active field later
    search_fields = ['name', 'contact_person', 'email', 'phone']
    list_per_page = 20
    
    def product_count(self, obj):
        return obj.product_set.count()
    product_count.short_description = 'Products'
    
    def is_active_display(self, obj):
        return "Yes"  # Add if you have is_active field later
    is_active_display.short_description = 'Active'
    
    # Optional: Add inlines to see products from supplier
    inlines = [ProductInline]

class StockMovementInline(admin.TabularInline):
    """Inline display of stock movements for Product"""
    model = StockMovement
    fields = ['movement_type', 'quantity', 'previous_stock', 'new_stock', 'reason_short', 'created_at', 'user']
    readonly_fields = ['previous_stock', 'new_stock', 'created_at', 'user', 'reason_short']
    extra = 0
    can_delete = False
    max_num = 10  # Show only last 10 movements
    
    def reason_short(self, obj):
        return obj.reason[:50] + "..." if len(obj.reason) > 50 else obj.reason
    reason_short.short_description = 'Reason'

class PurchaseOrderItemInline(admin.TabularInline):
    """Inline display of items for PurchaseOrder"""
    model = PurchaseOrderItem
    fields = ['product', 'quantity', 'unit_cost', 'expiry_date', 'total_cost_display']
    readonly_fields = ['total_cost_display']
    extra = 1
    
    def total_cost_display(self, obj):
        return format_money(obj.total_cost)
    total_cost_display.short_description = 'Total Cost'

@admin.register(Product)
class ProductAdmin(admin.ModelAdmin):
    list_display = [
        'name', 'sku', 'category', 'supplier', 'current_stock_display', 
        'min_stock_display', 'selling_price_display', 'stock_status_display',
        'profit_margin_display', 'is_high_risk_display'
    ]
    list_filter = ['category', 'supplier', 'product_type', 'requires_refrigeration', 'is_high_value', 'is_high_theft_risk']
    search_fields = ['name', 'sku', 'barcode', 'category__name', 'supplier__name']
    readonly_fields = [
        'profit_margin_display', 'stock_status_display', 'total_value_display',
        'expiry_display', 'created_display', 'updated_display'
    ]
    list_per_page = 50
    actions = ['mark_as_high_value', 'mark_as_high_risk']

    def get_queryset(self, request):
        """The shelf-life column is derived, so ask for it explicitly."""
        return super().get_queryset(request).with_expiry()
    
    fieldsets = (
        ('Basic Information', {
            'fields': (
                'name', 'sku', 'barcode', 
                ('category', 'supplier'), 
                'product_type'
            )
        }),
        ('Pricing', {
            'fields': (
                ('cost_price', 'selling_price'),
                'profit_margin_display'
            )
        }),
        ('Stock Management', {
            'fields': (
                ('current_stock', 'min_stock_level', 'max_stock_level'),
                'stock_status_display', 'total_value_display'
            )
        }),
        ('Product Details', {
            'fields': (
                'expiry_display',
                'requires_refrigeration',
                ('is_high_value', 'is_high_theft_risk')
            )
        }),
        ('Metadata', {
            'fields': ('created_display', 'updated_display'),
            'classes': ('collapse',)
        }),
    )
    
    # Add inline for stock movements
    inlines = [StockMovementInline]
    
    # Custom display methods for list view
    def current_stock_display(self, obj):
        color = "red" if obj.current_stock <= 0 else "orange" if obj.current_stock <= obj.min_stock_level else "green"
        return format_html('<span style="color: {};"><b>{}</b></span>', color, obj.current_stock)
    current_stock_display.short_description = 'Stock'
    current_stock_display.admin_order_field = 'current_stock'
    
    def min_stock_display(self, obj):
        return obj.min_stock_level
    min_stock_display.short_description = 'Min Stock'
    min_stock_display.admin_order_field = 'min_stock_level'
    
    def selling_price_display(self, obj):
        return format_money(obj.selling_price)
    selling_price_display.short_description = 'Price'
    selling_price_display.admin_order_field = 'selling_price'
    
    def stock_status_display(self, obj):
        status = obj.stock_status
        if status == 'out_of_stock':
            return format_html('<span class="badge" style="background-color: #dc3545;">Out of Stock</span>')
        elif status == 'low_stock':
            return format_html('<span class="badge" style="background-color: #ffc107; color: black;">Low Stock</span>')
        else:
            return format_html('<span class="badge" style="background-color: #198754;">In Stock</span>')
    stock_status_display.short_description = 'Status'
    
    def profit_margin_display(self, obj):
        margin = obj.profit_margin
        color = "green" if margin > 30 else "orange" if margin > 10 else "red"
        return format_html("<span style='color: {};'><b>{:.1f}%</b></span>", color, margin)
    profit_margin_display.short_description = 'Margin'
    
    def is_high_risk_display(self, obj):
        if obj.is_high_value or obj.is_high_theft_risk:
            badges = []
            if obj.is_high_value:
                badges.append('<span class="badge bg-warning">High Value</span>')
            if obj.is_high_theft_risk:
                badges.append('<span class="badge bg-danger">High Risk</span>')
            return format_html(' '.join(badges))
        return "—"
    is_high_risk_display.short_description = 'Flags'
    
    def total_value_display(self, obj):
        total_value = obj.current_stock * obj.cost_price
        return format_money(total_value)
    total_value_display.short_description = 'Total Value (Cost)'

    def expiry_display(self, obj):
        """Read-only: the date comes from the received purchase order lines."""
        if not obj.expiry_date:
            return "Not recorded — set it on the purchase order line"
        style = {
            'expired': 'color: #dc3545; font-weight: bold;',
            'expiring_soon': 'color: #fd7e14; font-weight: bold;',
        }.get(obj.expiry_status, '')
        days = obj.days_until_expiry
        if days < 0:
            note = f'expired {-days} day{"s" if -days != 1 else ""} ago'
        elif days == 0:
            note = 'expires today'
        else:
            note = f'{days} day{"s" if days != 1 else ""} left'
        return format_html(
            '<span style="{}">{}</span><br><small>{}</small>',
            style, obj.expiry_date, note,
        )
    expiry_display.short_description = 'Expiry (from deliveries)'

    
    def created_display(self, obj):
        return "—"  # Add when you have created_at field
    created_display.short_description = 'Created'
    
    def updated_display(self, obj):
        return "—"  # Add when you have updated_at field
    updated_display.short_description = 'Updated'
    
    # Custom actions
    def mark_as_high_value(self, request, queryset):
        updated = queryset.update(is_high_value=True)
        self.message_user(request, f'{updated} products marked as high value.')
    mark_as_high_value.short_description = "Mark selected products as high value"
    
    def mark_as_high_risk(self, request, queryset):
        updated = queryset.update(is_high_theft_risk=True)
        self.message_user(request, f'{updated} products marked as high theft risk.')
    mark_as_high_risk.short_description = "Mark selected products as high theft risk"

@admin.register(StockMovement)
class StockMovementAdmin(admin.ModelAdmin):
    list_display = [
        'product', 'movement_type_display', 'quantity', 'stock_change_display',
        'reason_short', 'user', 'created_at'
    ]
    list_filter = ['movement_type', 'created_at', 'user']
    search_fields = ['product__name', 'product__sku', 'reason', 'user__username']
    readonly_fields = ['previous_stock', 'new_stock', 'created_at', 'user']
    date_hierarchy = 'created_at'
    list_per_page = 50
    
    def movement_type_display(self, obj):
        type_colors = {
            'in': 'green',
            'out': 'red', 
            'adjustment': 'blue',
            'waste': 'orange'
        }
        color = type_colors.get(obj.movement_type, 'gray')
        return format_html(
            '<span style="color: {};"><b>{}</b></span>', 
            color, obj.get_movement_type_display()
        )
    movement_type_display.short_description = 'Type'
    
    def stock_change_display(self, obj):
        arrow = "↑" if obj.new_stock > obj.previous_stock else "↓" if obj.new_stock < obj.previous_stock else "→"
        color = "green" if obj.new_stock > obj.previous_stock else "red" if obj.new_stock < obj.previous_stock else "gray"
        return format_html(
            '{} <span style="color: {};">{} → {}</span>', 
            arrow, color, obj.previous_stock, obj.new_stock
        )
    stock_change_display.short_description = 'Stock Change'
    
    def reason_short(self, obj):
        return obj.reason[:75] + "..." if len(obj.reason) > 75 else obj.reason
    reason_short.short_description = 'Reason'

@admin.register(PurchaseOrder)
class PurchaseOrderAdmin(admin.ModelAdmin):
    list_display = [
        'order_number', 'supplier', 'order_date', 'expected_delivery', 
        'status_display', 'total_amount_display', 'item_count'
    ]
    list_filter = ['status', 'order_date', 'supplier']
    search_fields = ['supplier__name', 'id']
    readonly_fields = ['order_date', 'total_amount_display', 'item_count_display']
    date_hierarchy = 'order_date'
    list_per_page = 20
    actions = ['mark_as_received', 'mark_as_cancelled']
    
    inlines = [PurchaseOrderItemInline]
    
    fieldsets = (
        ('Order Information', {
            'fields': (
                'supplier',
                ('order_date', 'expected_delivery'),
                'status'
            )
        }),
        ('Order Summary', {
            'fields': (
                'total_amount_display',
                'item_count_display'
            )
        }),
    )
    
    def order_number(self, obj):
        return f"PO-{obj.id:06d}"
    order_number.short_description = 'Order #'
    order_number.admin_order_field = 'id'
    
    def status_display(self, obj):
        status_colors = {
            'draft': 'secondary',
            'ordered': 'info',
            'received': 'success', 
            'cancelled': 'danger'
        }
        color = status_colors.get(obj.status, 'secondary')
        return format_html(
            '<span class="badge bg-{}">{}</span>', 
            color, obj.get_status_display()
        )
    status_display.short_description = 'Status'
    
    def total_amount_display(self, obj):
        return format_money(obj.total_amount)
    total_amount_display.short_description = 'Total Amount'
    
    def item_count_display(self, obj):
        return obj.items.count()
    item_count_display.short_description = 'Items'
    
    def item_count(self, obj):
        return obj.items.count()
    item_count.short_description = 'Items'
    
    # Custom actions
    def mark_as_received(self, request, queryset):
        updated = queryset.update(status='received')
        self.message_user(request, f'{updated} purchase orders marked as received.')
    mark_as_received.short_description = "Mark selected orders as received"
    
    def mark_as_cancelled(self, request, queryset):
        updated = queryset.update(status='cancelled')
        self.message_user(request, f'{updated} purchase orders marked as cancelled.')
    mark_as_cancelled.short_description = "Mark selected orders as cancelled"

@admin.register(PurchaseOrderItem)
class PurchaseOrderItemAdmin(admin.ModelAdmin):
    list_display = [
        'purchase_order', 'product', 'quantity', 'unit_cost_display',
        'expiry_date', 'total_cost_display'
    ]
    list_filter = ['purchase_order__supplier', 'purchase_order__status']
    search_fields = ['product__name', 'purchase_order__id']
    list_per_page = 50
    
    def unit_cost_display(self, obj):
        return format_money(obj.unit_cost)
    unit_cost_display.short_description = 'Unit Cost'
    
    def total_cost_display(self, obj):
        return format_money(obj.total_cost)
    total_cost_display.short_description = 'Total Cost'

class SupplierReturnItemInline(admin.TabularInline):
    """Inline display of the items sent back to a supplier."""
    model = SupplierReturnItem
    fields = ['product', 'quantity', 'unit_cost', 'line_total_display']
    readonly_fields = ['line_total_display']
    extra = 1

    def line_total_display(self, obj):
        return format_money(obj.total_cost)
    line_total_display.short_description = 'Line Total'


@admin.register(SupplierReturn)
class SupplierReturnAdmin(admin.ModelAdmin):
    list_display = [
        'reference', 'created_at', 'supplier', 'purchase_order',
        'item_count', 'total_amount_display', 'processed_by',
    ]
    list_filter = ['created_at', 'supplier']
    search_fields = ['reference', 'supplier__name', 'purchase_order__id']
    readonly_fields = ['reference', 'total_amount', 'created_at', 'processed_by']
    date_hierarchy = 'created_at'
    list_per_page = 20

    inlines = [SupplierReturnItemInline]

    def item_count(self, obj):
        return obj.items.count()
    item_count.short_description = 'Items'

    def total_amount_display(self, obj):
        return format_money(obj.total_amount)
    total_amount_display.short_description = 'Value'


@admin.register(SupplierReturnItem)
class SupplierReturnItemAdmin(admin.ModelAdmin):
    list_display = ['supplier_return', 'product', 'quantity', 'unit_cost_display', 'line_total_display']
    list_filter = ['supplier_return__created_at', 'supplier_return__supplier']
    search_fields = ['product__name', 'supplier_return__reference']
    list_per_page = 50

    def unit_cost_display(self, obj):
        return format_money(obj.unit_cost)
    unit_cost_display.short_description = 'Unit Cost'

    def line_total_display(self, obj):
        return format_money(obj.total_cost)
    line_total_display.short_description = 'Line Total'


# Optional: Custom admin site header and title
admin.site.site_header = "MiniSuper Inventory Administration"
admin.site.site_title = "MiniSuper Admin"
admin.site.index_title = "Inventory Management"