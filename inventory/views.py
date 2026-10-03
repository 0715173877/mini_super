import uuid
from datetime import datetime, timedelta
from django.shortcuts import render, get_object_or_404, redirect
from django.urls import reverse_lazy
from django.views.generic import ListView, DetailView, CreateView, UpdateView, DeleteView
from django.contrib.auth.mixins import LoginRequiredMixin
from django.db import transaction
from django.db.models import Q, F, ExpressionWrapper, DecimalField, Count, Sum
from django.contrib import messages
from django.contrib.auth.decorators import login_required, permission_required
from django.utils import timezone
from django.views.decorators.http import require_POST
from .models import (
    Category, Supplier, Product, StockMovement, PurchaseOrder, PurchaseOrderItem,
    SupplierReturn, SupplierReturnItem,
)
from .forms import (
    CategoryForm, SupplierForm, ProductForm, PurchaseOrderForm, StockAdjustmentForm,
    PurchaseOrderItemFormSet, SupplierReturnForm, SupplierReturnItemFormSet,
)
# Single source of truth for "expiring soon" — shared with the notification bell.
from core.notifications import EXPIRY_SOON_DAYS
# Roles: every page here belongs to the Stock role (and the owner).
from core.permissions import PermissionRequiredMixin

# Category Views
class CategoryListView(LoginRequiredMixin, PermissionRequiredMixin, ListView):
    permission_required = 'inventory.view_category'
    model = Category
    template_name = 'inventory/category_list.html'
    context_object_name = 'categories'
    
    def get_queryset(self):
        queryset = Category.objects.annotate(
            product_count=Count('product')
        ).order_by('name')
        
        # Filter by search
        search_query = self.request.GET.get('search')
        if search_query:
            queryset = queryset.filter(
                Q(name__icontains=search_query) |
                Q(description__icontains=search_query)
            )
        
        return queryset
    
    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context['search_query'] = self.request.GET.get('search', '')
        return context

class CategoryCreateView(LoginRequiredMixin, PermissionRequiredMixin, CreateView):
    permission_required = 'inventory.add_category'
    model = Category
    form_class = CategoryForm  # Use the form class
    template_name = 'inventory/category_form.html'
    success_url = reverse_lazy('category-list')
    
    def form_valid(self, form):
        messages.success(self.request, f'Category "{form.instance.name}" created successfully!')
        return super().form_valid(form)

class CategoryUpdateView(LoginRequiredMixin, PermissionRequiredMixin, UpdateView):
    permission_required = 'inventory.change_category'
    model = Category
    form_class = CategoryForm  # Use the form class
    template_name = 'inventory/category_form.html'
    success_url = reverse_lazy('category-list')
    
    def form_valid(self, form):
        messages.success(self.request, f'Category "{form.instance.name}" updated successfully!')
        return super().form_valid(form)

# Supplier Views
class SupplierListView(LoginRequiredMixin, PermissionRequiredMixin, ListView):
    permission_required = 'inventory.view_supplier'
    model = Supplier
    template_name = 'inventory/supplier_list.html'
    context_object_name = 'suppliers'
    
    def get_queryset(self):
        queryset = Supplier.objects.annotate(
            product_count=Count('product')
        ).order_by('name')
        
        # Filter by search
        search_query = self.request.GET.get('search')
        if search_query:
            queryset = queryset.filter(
                Q(name__icontains=search_query) |
                Q(contact_person__icontains=search_query) |
                Q(email__icontains=search_query)
            )
        
        # Filter by status
        status_filter = self.request.GET.get('status')
        if status_filter == 'active':
            queryset = queryset.filter(is_active=True)
        elif status_filter == 'inactive':
            queryset = queryset.filter(is_active=False)
        
        return queryset
    
    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context['search_query'] = self.request.GET.get('search', '')
        context['status_filter'] = self.request.GET.get('status', '')
        return context

class SupplierCreateView(LoginRequiredMixin, PermissionRequiredMixin, CreateView):
    permission_required = 'inventory.add_supplier'
    model = Supplier
    form_class = SupplierForm  # Use the form class
    template_name = 'inventory/supplier_form.html'
    success_url = reverse_lazy('supplier-list')
    
    def form_valid(self, form):
        messages.success(self.request, f'Supplier "{form.instance.name}" created successfully!')
        return super().form_valid(form)

class SupplierUpdateView(LoginRequiredMixin, PermissionRequiredMixin, UpdateView):
    permission_required = 'inventory.change_supplier'
    model = Supplier
    form_class = SupplierForm  # Use the form class
    template_name = 'inventory/supplier_form.html'
    success_url = reverse_lazy('supplier-list')
    
    def form_valid(self, form):
        messages.success(self.request, f'Supplier "{form.instance.name}" updated successfully!')
        return super().form_valid(form)


class ProductListView(LoginRequiredMixin, PermissionRequiredMixin, ListView):
    permission_required = 'inventory.view_product'
    model = Product
    template_name = 'inventory/product_list.html'
    context_object_name = 'products'
    paginate_by = 20
    
    def get_queryset(self):
        # with_expiry() annotates the shelf life derived from the received
        # purchase order lines — the product row itself stores no date.
        queryset = (
            Product.objects.with_expiry()
            .select_related('category', 'supplier').order_by('name')
        )
        
        # Filter by category
        category_id = self.request.GET.get('category')
        if category_id:
            queryset = queryset.filter(category_id=category_id)
        
        # Filter by stock status
        stock_filter = self.request.GET.get('stock')
        if stock_filter == 'low':
            queryset = queryset.filter(current_stock__lte=F('min_stock_level'))
        elif stock_filter == 'out':
            queryset = queryset.filter(current_stock=0)

        # Filter by shelf life — only stock actually on hand is worth listing.
        expiry_filter = self.request.GET.get('expiry')
        today = timezone.now().date()
        if expiry_filter == 'expired':
            queryset = queryset.filter(
                current_stock__gt=0, effective_expiry_date__lt=today
            )
        elif expiry_filter == 'soon':
            queryset = queryset.filter(
                current_stock__gt=0,
                effective_expiry_date__isnull=False,
                effective_expiry_date__lte=today + timedelta(days=EXPIRY_SOON_DAYS),
            )
        
        # Search
        search_query = self.request.GET.get('search')
        if search_query:
            queryset = queryset.filter(
                Q(name__icontains=search_query) |
                Q(sku__icontains=search_query) |
                Q(category__name__icontains=search_query)
            )
        
        return queryset
    
    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context['categories'] = Category.objects.all()
        # Remembered so the filter drop-down shows the sidebar link's choice.
        context['expiry_filter'] = self.request.GET.get('expiry', '')
        return context

class ProductDetailView(LoginRequiredMixin, PermissionRequiredMixin, DetailView):
    permission_required = 'inventory.view_product'
    model = Product
    template_name = 'inventory/product_detail.html'
    context_object_name = 'product'

    def get_queryset(self):
        # The shelf life shown here is derived from the purchase order lines.
        return Product.objects.with_expiry()

    
    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context['stock_movements'] = StockMovement.objects.filter(
            product=self.object
        ).order_by('-created_at')[:10]
        return context

class ProductCreateView(LoginRequiredMixin, PermissionRequiredMixin, CreateView):
    permission_required = 'inventory.add_product'
    model = Product
    form_class = ProductForm
    template_name = 'inventory/product_form.html'
    success_url = reverse_lazy('product-list')
    
    def form_valid(self, form):
        messages.success(self.request, f'Product "{form.instance.name}" created successfully!')
        return super().form_valid(form)

class ProductUpdateView(LoginRequiredMixin, PermissionRequiredMixin, UpdateView):
    permission_required = 'inventory.change_product'
    model = Product
    form_class = ProductForm
    template_name = 'inventory/product_form.html'
    
    def get_success_url(self):
        return reverse_lazy('product-detail', kwargs={'pk': self.object.pk})
    
    def form_valid(self, form):
        messages.success(self.request, f'Product "{form.instance.name}" updated successfully!')
        return super().form_valid(form)

class ProductDeleteView(LoginRequiredMixin, PermissionRequiredMixin, DeleteView):
    permission_required = 'inventory.delete_product'
    model = Product
    template_name = 'inventory/product_confirm_delete.html'
    success_url = reverse_lazy('product-list')
    
    def delete(self, request, *args, **kwargs):
        product = self.get_object()
        messages.success(request, f'Product "{product.name}" deleted successfully!')
        return super().delete(request, *args, **kwargs)

class LowStockView(LoginRequiredMixin, PermissionRequiredMixin, ListView):
    permission_required = 'inventory.view_product'
    model = Product
    template_name = 'inventory/low_stock.html'
    context_object_name = 'low_stock_products'
    
    def get_queryset(self):
        return Product.objects.filter(
            current_stock__lte=F('min_stock_level')
        ).select_related('category', 'supplier').order_by('current_stock')
    
    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        # Calculate stock percentage for display
        for product in context['low_stock_products']:
            if product.min_stock_level > 0:
                product.stock_percentage = (product.current_stock / product.min_stock_level) * 100
            else:
                product.stock_percentage = 0
        return context

from .forms import PurchaseOrderForm, PurchaseOrderItemFormSet

# ---------------------------------------------------------------------------
# Purchase order straight flow
#
# In this shop the supplier usually supplies on the spot, so a purchase order is
# never parked as a draft: it is created already placed ('ordered') and the only
# action left is the purchase itself, which adds the quantities to stock. The
# 'draft' status is kept in the model so orders created before this change (and
# the filter on the list page) keep working, and a leftover draft can still be
# purchased directly.
# ---------------------------------------------------------------------------

#: An order in one of these states has already finished its life cycle.
CLOSED_ORDER_STATUSES = ('received', 'cancelled')


def add_purchase_order_to_stock(order, user):
    """Add every line of `order` to product stock, logging one movement per line.

    Must be called inside ``transaction.atomic()`` so a failure halfway through
    cannot leave stock half-updated. Returns the number of lines applied.

    When a line carries the use-by date printed on the delivery, that date is
    *not* copied anywhere: it stays on the line where it was typed, and the
    product's expiry is derived from the lines of the orders it has received
    (``Product.objects.with_expiry()``). Keeping the single copy on the order
    line is what stops a product's date from drifting away from its delivery.
    The movement log still records the date so the stock history explains itself.
    """
    lines = list(order.items.select_related('product'))
    for item in lines:
        product = item.product
        previous_stock = product.current_stock
        product.current_stock = previous_stock + item.quantity
        product.save()

        expiry = item.expiry_date
        expiry_note = f' (expires {expiry:%d %b %Y})' if expiry else ''

        StockMovement.objects.create(
            product=product,
            movement_type='in',
            quantity=item.quantity,
            previous_stock=previous_stock,
            new_stock=product.current_stock,
            reason=f'Purchase order #{order.id} purchased{expiry_note}',
            user=user,
        )
    return len(lines)


def purchase_order_into_stock(order, user):
    """Purchase `order` in one atomic step: place it if still a draft, then stock it."""
    with transaction.atomic():
        if order.status == 'draft':
            order.status = 'ordered'
        lines = add_purchase_order_to_stock(order, user)
        order.status = 'received'
        order.save()
        return lines


def order_items_present(formset):
    """True when a validated item formset still carries at least one product line."""
    deleted = set(formset.deleted_forms)
    for form in formset.forms:
        if form in deleted:
            continue
        if form.cleaned_data.get('product'):
            return True
    return False


class PurchaseOrderListView(LoginRequiredMixin, PermissionRequiredMixin, ListView):
    permission_required = 'inventory.view_purchaseorder'
    model = PurchaseOrder
    template_name = 'inventory/purchaseorder_list.html'
    context_object_name = 'purchase_orders'
    paginate_by = 20
    
    def get_queryset(self):
        queryset = PurchaseOrder.objects.select_related('supplier').prefetch_related('items').order_by('-order_date')
        queryset = self.apply_filters(queryset)

        # The status filter is applied last, and the wider queryset kept on the
        # instance, so the status tabs can still count every status while the
        # table below shows only the selected one.
        self.base_queryset = queryset
        status_filter = self.request.GET.get('status')
        if status_filter:
            queryset = queryset.filter(status=status_filter)

        return queryset

    def apply_filters(self, queryset):
        """Everything the filter card can narrow, except the status tab itself."""
        # Supplier filter
        supplier_filter = self.request.GET.get('supplier')
        if supplier_filter:
            queryset = queryset.filter(supplier_id=supplier_filter)

        # Date range filter
        date_from = self.request.GET.get('date_from')
        date_to = self.request.GET.get('date_to')

        if date_from:
            try:
                date_from_obj = datetime.strptime(date_from, '%Y-%m-%d').date()
                queryset = queryset.filter(order_date__date__gte=date_from_obj)
            except ValueError:
                pass

        if date_to:
            try:
                date_to_obj = datetime.strptime(date_to, '%Y-%m-%d').date()
                queryset = queryset.filter(order_date__date__lte=date_to_obj)
            except ValueError:
                pass

        # Search filter
        search_query = self.request.GET.get('search')
        if search_query:
            queryset = queryset.filter(
                Q(supplier__name__icontains=search_query) |
                Q(id__icontains=search_query)
            )

        return queryset

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        
        # Add filter values to context
        context['status_filter'] = self.request.GET.get('status', '')
        context['selected_supplier'] = self.request.GET.get('supplier', '')
        context['date_from'] = self.request.GET.get('date_from', '')
        context['date_to'] = self.request.GET.get('date_to', '')
        context['search_query'] = self.request.GET.get('search', '')
        
        # Add suppliers for filter dropdown
        context['suppliers'] = Supplier.objects.filter(is_active=True).order_by('name')

        # Threshold the status words in the table use — same constant as the bell.
        context['expiry_soon_days'] = EXPIRY_SOON_DAYS

        # Statistics describe the current supplier / date / search scope (not the
        # selected tab), so the cards and the tabs always agree with each other.
        queryset = self.base_queryset
        context['total_orders'] = queryset.count()
        context['draft_orders'] = queryset.filter(status='draft').count()
        context['ordered_orders'] = queryset.filter(status='ordered').count()
        context['received_orders'] = queryset.filter(status='received').count()
        context['cancelled_orders'] = queryset.filter(status='cancelled').count()

        # One entry per status tab: value, label, count, icon.
        context['status_tabs'] = [
            ('', 'All orders', context['total_orders'], 'fa-layer-group'),
            ('draft', 'Not placed', context['draft_orders'], 'fa-edit'),
            ('ordered', 'Placed', context['ordered_orders'], 'fa-paper-plane'),
            ('received', 'Purchased', context['received_orders'], 'fa-check'),
            ('cancelled', 'Cancelled', context['cancelled_orders'], 'fa-ban'),
        ]
        
        # Calculate total order value
        total_value = queryset.aggregate(total=Sum('total_amount'))['total'] or 0
        context['total_order_value'] = total_value
        
        return context

class ReceivedPurchaseListView(LoginRequiredMixin, PermissionRequiredMixin, ListView):
    permission_required = 'inventory.view_purchaseorder'
    """What actually arrived: purchased orders, one block per order.

    The purchase order list deliberately mixes open and closed orders. Once an
    order has been purchased it is no longer something to chase — it is a
    delivery, and the interesting thing about it is the shelf life its lines
    recorded. This page separates those deliveries and reads the use-by dates
    back per line.
    """

    model = PurchaseOrder
    template_name = 'inventory/received_purchases.html'
    context_object_name = 'purchase_orders'
    paginate_by = 10

    def get_queryset(self):
        queryset = (
            PurchaseOrder.objects.filter(status='received')
            .select_related('supplier')
            .prefetch_related('items', 'items__product')
            .order_by('-order_date', '-id')
        )
        return self.apply_filters(queryset)

    def apply_filters(self, queryset):
        supplier_filter = self.request.GET.get('supplier')
        if supplier_filter:
            queryset = queryset.filter(supplier_id=supplier_filter)

        date_from = self.request.GET.get('date_from')
        if date_from:
            try:
                queryset = queryset.filter(
                    order_date__date__gte=datetime.strptime(date_from, '%Y-%m-%d').date()
                )
            except ValueError:
                pass

        date_to = self.request.GET.get('date_to')
        if date_to:
            try:
                queryset = queryset.filter(
                    order_date__date__lte=datetime.strptime(date_to, '%Y-%m-%d').date()
                )
            except ValueError:
                pass

        search_query = self.request.GET.get('search')
        if search_query:
            queryset = queryset.filter(
                Q(supplier__name__icontains=search_query) |
                Q(id__icontains=search_query) |
                Q(items__product__name__icontains=search_query) |
                Q(items__product__sku__icontains=search_query)
            ).distinct()

        # Narrow to deliveries carrying a shelf life in a given state; the wording
        # matches the product list filters (`?expiry=expired` / `soon`).
        expiry_filter = self.request.GET.get('expiry')
        today = timezone.now().date()
        if expiry_filter == 'expired':
            queryset = queryset.filter(items__expiry_date__lt=today).distinct()
        elif expiry_filter == 'soon':
            queryset = queryset.filter(
                items__expiry_date__gte=today,
                items__expiry_date__lte=today + timedelta(days=EXPIRY_SOON_DAYS),
            ).distinct()
        elif expiry_filter == 'none':
            # Nothing on this delivery reached the shop with a date recorded.
            queryset = queryset.filter(items__expiry_date__isnull=True).distinct()

        return queryset

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context['selected_supplier'] = self.request.GET.get('supplier', '')
        context['date_from'] = self.request.GET.get('date_from', '')
        context['date_to'] = self.request.GET.get('date_to', '')
        context['search_query'] = self.request.GET.get('search', '')
        context['expiry_filter'] = self.request.GET.get('expiry', '')
        context['expiry_soon_days'] = EXPIRY_SOON_DAYS
        context['suppliers'] = Supplier.objects.filter(is_active=True).order_by('name')

        # Statistics describe the whole filtered history, not just the visible page.
        deliveries = self.get_queryset()
        lines = PurchaseOrderItem.objects.filter(purchase_order__in=deliveries)
        today = timezone.now().date()
        soon = today + timedelta(days=EXPIRY_SOON_DAYS)

        context['delivery_count'] = deliveries.count()
        context['delivered_line_count'] = lines.count()
        context['delivered_quantity'] = lines.aggregate(total=Sum('quantity'))['total'] or 0
        context['delivered_value'] = deliveries.aggregate(
            total=Sum('total_amount')
        )['total'] or 0
        context['expired_batch_count'] = lines.filter(expiry_date__lt=today).count()
        context['expiring_batch_count'] = lines.filter(
            expiry_date__gte=today, expiry_date__lte=soon
        ).count()

        return context


class PurchaseOrderCreateView(LoginRequiredMixin, PermissionRequiredMixin, CreateView):
    permission_required = 'inventory.add_purchaseorder'
    model = PurchaseOrder
    form_class = PurchaseOrderForm
    template_name = 'inventory/purchase_order_form.html'
    
    def get_initial(self):
        initial = super().get_initial()
        # Suppliers here usually deliver on the spot, so pre-fill today. The column
        # is not nullable, so the field must always end up with a real date.
        initial['expected_delivery'] = timezone.now().date()
        return initial

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        if self.request.POST:
            context['formset'] = PurchaseOrderItemFormSet(self.request.POST)
        else:
            context['formset'] = PurchaseOrderItemFormSet()
        
        # Add products and suppliers for the form
        context['products'] = Product.objects.select_related('category', 'supplier').order_by('name')
        context['suppliers'] = Supplier.objects.filter(is_active=True).order_by('name')
        return context
    
    def form_valid(self, form):
        context = self.get_context_data()
        formset = context['formset']
        
        if formset.is_valid() and not order_items_present(formset):
            # Nothing usable was submitted — re-render with a clear message instead of
            # quietly saving an order with no lines.
            form.add_error(None, 'Add at least one product line to the order.')
            return self.form_invalid(form)

        if formset.is_valid():
            # Straight flow: there is no draft step — an order is created already placed.
            form.instance.order_date = timezone.now()
            form.instance.status = 'ordered'
            
            response = super().form_valid(form)
            
            # Save the formset instances
            formset.instance = self.object
            formset.save()
            
            # Calculate and save total amount
            self.object.calculate_total_amount()
            
            if 'purchase_now' in self.request.POST:
                # "Create & Purchase Now" — place and add to stock in the same click.
                self.purchase_now()
            else:
                messages.success(
                    self.request,
                    f'Purchase Order #{self.object.id} created and placed. '
                    'Use Purchase when the goods arrive to add them to stock.'
                )
            
            return response
        else:
            return self.form_invalid(form)
    
    def purchase_now(self):
        """Purchase the order that was just created, without touching a placed order twice."""
        try:
            lines = purchase_order_into_stock(self.object, self.request.user)
        except Exception as e:
            messages.error(
                self.request,
                f'Purchase Order #{self.object.id} was placed, but purchasing it failed: {e}'
            )
        else:
            messages.success(
                self.request,
                f'Purchase Order #{self.object.id} created and purchased — '
                f'stock updated for {lines} item(s).'
            )
    
    def get_success_url(self):
        return reverse_lazy('purchase-order-detail', kwargs={'pk': self.object.pk})

class PurchaseOrderDetailView(LoginRequiredMixin, PermissionRequiredMixin, DetailView):
    permission_required = 'inventory.view_purchaseorder'
    model = PurchaseOrder
    template_name = 'inventory/purchaseorder_detail.html'
    context_object_name = 'order'
    
    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context['order_items'] = self.object.items.select_related('product')
        return context

class PurchaseOrderUpdateView(LoginRequiredMixin, PermissionRequiredMixin, UpdateView):
    permission_required = 'inventory.change_purchaseorder'
    model = PurchaseOrder
    form_class = PurchaseOrderForm
    template_name = 'inventory/purchase_order_form.html'
    
    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        if self.request.POST:
            context['formset'] = PurchaseOrderItemFormSet(self.request.POST, instance=self.object)
        else:
            context['formset'] = PurchaseOrderItemFormSet(instance=self.object)
        
        context['products'] = Product.objects.select_related('category', 'supplier').order_by('name')
        context['suppliers'] = Supplier.objects.filter(is_active=True).order_by('name')
        return context
    
    def form_valid(self, form):
        context = self.get_context_data()
        formset = context['formset']
        
        if formset.is_valid() and not order_items_present(formset):
            form.add_error(None, 'Keep at least one product line on the order.')
            return self.form_invalid(form)

        if formset.is_valid():
            response = super().form_valid(form)
            formset.instance = self.object
            formset.save()
            
            # Recalculate total amount
            self.object.calculate_total_amount()
            
            # A leftover draft (created before the straight flow) can be placed or
            # purchased straight from the edit page.
            if 'purchase_now' in self.request.POST:
                self.purchase_from_edit_page()
            elif 'place_order' in self.request.POST and self.object.status == 'draft':
                self.object.status = 'ordered'
                self.object.save()
                messages.success(self.request, f'Purchase Order #{self.object.id} updated and placed successfully!')
            else:
                messages.success(self.request, f'Purchase Order #{self.object.id} updated successfully!')
            
            return response
        else:
            return self.form_invalid(form)
    
    def purchase_from_edit_page(self):
        """Purchase the order being edited — same rules as receive_purchase_order()."""
        if self.object.status in CLOSED_ORDER_STATUSES:
            messages.warning(
                self.request,
                f'Purchase Order #{self.object.id} is already '
                f'{self.object.get_status_display().lower()} — stock was not changed again.'
            )
            return
        
        try:
            lines = purchase_order_into_stock(self.object, self.request.user)
        except Exception as e:
            messages.error(
                self.request,
                f'Order #{self.object.id} was saved, but purchasing it failed: {e}'
            )
        else:
            messages.success(
                self.request,
                f'Purchase Order #{self.object.id} purchased — stock updated for {lines} item(s).'
            )
    
    def get_success_url(self):
        return reverse_lazy('purchase-order-detail', kwargs={'pk': self.object.pk})

class PurchaseOrderDeleteView(LoginRequiredMixin, PermissionRequiredMixin, DeleteView):
    permission_required = 'inventory.delete_purchaseorder'
    model = PurchaseOrder
    template_name = 'inventory/purchaseorder_confirm_delete.html'
    success_url = reverse_lazy('purchase-order-list')
    
    def delete(self, request, *args, **kwargs):
        order = self.get_object()
        messages.success(request, f'Purchase Order #{order.id} deleted successfully!')
        return super().delete(request, *args, **kwargs)


@login_required
@require_POST
@permission_required('inventory.change_purchaseorder', raise_exception=True)
def mark_as_ordered(request, pk):
    """Place a leftover draft order — new orders are created already placed."""
    order = get_object_or_404(PurchaseOrder, pk=pk)
    
    if order.status == 'draft':
        order.status = 'ordered'
        order.save()
        messages.success(request, f'Purchase Order #{order.id} placed!')
    else:
        messages.error(request, 'Only draft orders can be placed.')
    
    return redirect('purchase-order-detail', pk=order.pk)


@login_required
@require_POST
@permission_required('inventory.change_purchaseorder', raise_exception=True)
def receive_purchase_order(request, pk):
    """Purchase: add every line of the order to stock, then mark the order received.
    
    This is the only state-changing action left in the straight flow. It refuses to
    run twice: purchasing an already received order would add the same quantities
    to stock again. (There used to be two definitions of this view in this file —
    the second one, with no status check and no transaction, was the live one.)
    """
    order = get_object_or_404(PurchaseOrder, pk=pk)
    
    if order.status == 'received':
        messages.warning(
            request,
            f'Purchase Order #{order.id} was already purchased — stock was not changed again.'
        )
        return redirect('purchase-order-detail', pk=order.pk)
    
    if order.status == 'cancelled':
        messages.error(request, 'Cancelled orders cannot be purchased.')
        return redirect('purchase-order-detail', pk=order.pk)
    
    try:
        lines = purchase_order_into_stock(order, request.user)
    except Exception as e:
        messages.error(request, f'Error purchasing order: {e}')
    else:
        messages.success(
            request,
            f'Purchase Order #{order.id} purchased — stock updated for {lines} item(s).'
        )
    
    return redirect('purchase-order-detail', pk=order.pk)


@login_required
@require_POST
@permission_required('inventory.change_purchaseorder', raise_exception=True)
def cancel_purchase_order(request, pk):
    """Cancel an order. Without a migration there is no undo, so the status is kept."""
    order = get_object_or_404(PurchaseOrder, pk=pk)
    
    if order.status in ['draft', 'ordered']:
        order.status = 'cancelled'
        order.save()
        messages.success(request, f'Purchase Order #{order.id} cancelled!')
    else:
        messages.error(
            request,
            f'A {order.get_status_display().lower()} order cannot be cancelled.'
        )
    
    return redirect('purchase-order-detail', pk=order.pk)

class StockMovementListView(LoginRequiredMixin, PermissionRequiredMixin, ListView):
    permission_required = 'inventory.view_stockmovement'
    model = StockMovement
    template_name = 'inventory/stock_movements.html'
    context_object_name = 'stock_movements'
    paginate_by = 20
    
    def get_queryset(self):
        return StockMovement.objects.select_related('product', 'user').order_by('-created_at')

@login_required
@permission_required('inventory.add_stockmovement', raise_exception=True)
def adjust_stock(request, product_id):
    product = get_object_or_404(Product, id=product_id)
    
    if request.method == 'POST':
        form = StockAdjustmentForm(request.POST)
        if form.is_valid():
            adjustment_type = form.cleaned_data['adjustment_type']
            quantity = form.cleaned_data['quantity']
            reason = form.cleaned_data['reason']
            
            old_stock = product.current_stock
            
            if adjustment_type == 'add':
                product.current_stock += quantity
                movement_type = 'in'
            else:  # remove
                product.current_stock = max(0, product.current_stock - quantity)
                movement_type = 'out'
            
            product.save()
            
            # Record stock movement
            StockMovement.objects.create(
                product=product,
                movement_type=movement_type,
                quantity=quantity,
                previous_stock=old_stock,
                new_stock=product.current_stock,
                reason=reason,
                user=request.user
            )
            
            messages.success(request, f'Stock adjusted for {product.name}. New stock: {product.current_stock}')
            return redirect('product-detail', pk=product.id)
    else:
        form = StockAdjustmentForm()
    
    return render(request, 'inventory/stock_adjustment.html', {
        'product': product,
        'form': form
    })


# ---------------------------------------------------------------------------
# Supplier returns
#
# Goods sent back to a supplier leave the shop: recording a return subtracts
# the quantities from Product.current_stock and logs one StockMovement per line
# with movement_type='supplier_return'. This is the mirror image of the
# purchase-order receive flow (add_purchase_order_to_stock).
# ---------------------------------------------------------------------------

def generate_supplier_return_reference():
    """Build a unique reference such as ``SR20260930A1B2C3``."""
    stamp = timezone.now().strftime('%Y%m%d%H%M%S')
    return f"SR{stamp}{uuid.uuid4().hex[:4].upper()}"


def remove_supplier_return_from_stock(supplier_return, user):
    """Subtract every line of a supplier return from stock.

    Must be called inside ``transaction.atomic()``. Returns the number of
    lines applied. Callers validate that there is enough stock first, so this
    never drives ``current_stock`` below zero.
    """
    lines = list(supplier_return.items.select_related('product'))
    for item in lines:
        product = item.product
        previous_stock = product.current_stock
        product.current_stock = previous_stock - item.quantity
        product.save()

        StockMovement.objects.create(
            product=product,
            movement_type='supplier_return',
            quantity=item.quantity,
            previous_stock=previous_stock,
            new_stock=product.current_stock,
            reason=f'Supplier return {supplier_return.reference}',
            user=user,
        )
    return len(lines)


class SupplierReturnListView(LoginRequiredMixin, PermissionRequiredMixin, ListView):
    permission_required = 'inventory.view_supplierreturn'
    model = SupplierReturn
    template_name = 'inventory/supplier_return_list.html'
    context_object_name = 'supplier_returns'
    paginate_by = 20

    def get_queryset(self):
        return SupplierReturn.objects.select_related(
            'supplier', 'purchase_order', 'processed_by'
        ).prefetch_related('items').order_by('-created_at')


class SupplierReturnCreateView(LoginRequiredMixin, PermissionRequiredMixin, CreateView):
    permission_required = 'inventory.add_supplierreturn'
    model = SupplierReturn
    form_class = SupplierReturnForm
    template_name = 'inventory/supplier_return_form.html'

    def get_initial(self):
        initial = super().get_initial()
        # Allow the purchase-order detail page to pre-select the order: ?purchase_order=<pk>
        order_id = self.request.GET.get('purchase_order')
        if order_id:
            order = PurchaseOrder.objects.filter(pk=order_id).first()
            if order:
                initial['purchase_order'] = order
                initial['supplier'] = order.supplier
        return initial

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        if self.request.POST:
            context['formset'] = SupplierReturnItemFormSet(self.request.POST, instance=self.object)
        else:
            context['formset'] = SupplierReturnItemFormSet(instance=self.object)
        context['products'] = Product.objects.select_related('category', 'supplier').order_by('name')
        context['suppliers'] = Supplier.objects.filter(is_active=True).order_by('name')
        return context

    def form_valid(self, form):
        context = self.get_context_data()
        formset = context['formset']

        if not formset.is_valid():
            return self.form_invalid(form)

        # Never let a return drive stock below zero.
        stock_errors = []
        for item_form in formset:
            data = item_form.cleaned_data
            if not data or data.get('DELETE'):
                continue
            product = data.get('product')
            quantity = data.get('quantity')
            if product and quantity and quantity > product.current_stock:
                stock_errors.append(
                    f'{product.name}: cannot return {quantity} — '
                    f'only {product.current_stock} in stock.'
                )

        if stock_errors:
            for error in stock_errors:
                messages.error(self.request, error)
            return self.form_invalid(form)

        form.instance.processed_by = self.request.user
        form.instance.reference = generate_supplier_return_reference()

        with transaction.atomic():
            response = super().form_valid(form)
            formset.instance = self.object
            formset.save()
            self.object.calculate_total_amount()
            lines = remove_supplier_return_from_stock(self.object, self.request.user)

        messages.success(
            self.request,
            f'Supplier return {self.object.reference} recorded — '
            f'stock reduced for {lines} item(s).'
        )
        return response

    def get_success_url(self):
        return reverse_lazy('supplier-return-detail', kwargs={'pk': self.object.pk})


class SupplierReturnDetailView(LoginRequiredMixin, PermissionRequiredMixin, DetailView):
    permission_required = 'inventory.view_supplierreturn'
    model = SupplierReturn
    template_name = 'inventory/supplier_return_detail.html'
    context_object_name = 'supplier_return'

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context['return_items'] = self.object.items.select_related('product')
        return context



