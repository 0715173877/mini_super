from django.shortcuts import render, get_object_or_404, redirect
from django.urls import reverse_lazy
from django.views.generic import ListView, DetailView, CreateView, UpdateView, DeleteView
from django.contrib.auth.mixins import LoginRequiredMixin
from django.db.models import Q, F, ExpressionWrapper, DecimalField, Count, Sum
from django.contrib import messages
from django.utils import timezone
from django.utils import timezone
from .models import Category, Supplier, Product, StockMovement, PurchaseOrder, PurchaseOrderItem
from .forms import CategoryForm, SupplierForm, ProductForm, PurchaseOrderForm, StockAdjustmentForm, PurchaseOrderItemFormSet
from datetime import datetime
# Category Views
class CategoryListView(LoginRequiredMixin, ListView):
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

class CategoryCreateView(LoginRequiredMixin, CreateView):
    model = Category
    form_class = CategoryForm  # Use the form class
    template_name = 'inventory/category_form.html'
    success_url = reverse_lazy('category-list')
    
    def form_valid(self, form):
        messages.success(self.request, f'Category "{form.instance.name}" created successfully!')
        return super().form_valid(form)

class CategoryUpdateView(LoginRequiredMixin, UpdateView):
    model = Category
    form_class = CategoryForm  # Use the form class
    template_name = 'inventory/category_form.html'
    success_url = reverse_lazy('category-list')
    
    def form_valid(self, form):
        messages.success(self.request, f'Category "{form.instance.name}" updated successfully!')
        return super().form_valid(form)

# Supplier Views
class SupplierListView(LoginRequiredMixin, ListView):
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

class SupplierCreateView(LoginRequiredMixin, CreateView):
    model = Supplier
    form_class = SupplierForm  # Use the form class
    template_name = 'inventory/supplier_form.html'
    success_url = reverse_lazy('supplier-list')
    
    def form_valid(self, form):
        messages.success(self.request, f'Supplier "{form.instance.name}" created successfully!')
        return super().form_valid(form)

class SupplierUpdateView(LoginRequiredMixin, UpdateView):
    model = Supplier
    form_class = SupplierForm  # Use the form class
    template_name = 'inventory/supplier_form.html'
    success_url = reverse_lazy('supplier-list')
    
    def form_valid(self, form):
        messages.success(self.request, f'Supplier "{form.instance.name}" updated successfully!')
        return super().form_valid(form)


class ProductListView(LoginRequiredMixin, ListView):
    model = Product
    template_name = 'inventory/product_list.html'
    context_object_name = 'products'
    paginate_by = 20
    
    def get_queryset(self):
        queryset = Product.objects.select_related('category', 'supplier').order_by('name')
        
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
        return context

class ProductDetailView(LoginRequiredMixin, DetailView):
    model = Product
    template_name = 'inventory/product_detail.html'
    context_object_name = 'product'
    
    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context['stock_movements'] = StockMovement.objects.filter(
            product=self.object
        ).order_by('-timestamp')[:10]
        return context

class ProductCreateView(LoginRequiredMixin, CreateView):
    model = Product
    form_class = ProductForm
    template_name = 'inventory/product_form.html'
    success_url = reverse_lazy('product-list')
    
    def form_valid(self, form):
        messages.success(self.request, f'Product "{form.instance.name}" created successfully!')
        return super().form_valid(form)

class ProductUpdateView(LoginRequiredMixin, UpdateView):
    model = Product
    form_class = ProductForm
    template_name = 'inventory/product_form.html'
    
    def get_success_url(self):
        return reverse_lazy('product-detail', kwargs={'pk': self.object.pk})
    
    def form_valid(self, form):
        messages.success(self.request, f'Product "{form.instance.name}" updated successfully!')
        return super().form_valid(form)

class ProductDeleteView(LoginRequiredMixin, DeleteView):
    model = Product
    template_name = 'inventory/product_confirm_delete.html'
    success_url = reverse_lazy('product-list')
    
    def delete(self, request, *args, **kwargs):
        product = self.get_object()
        messages.success(request, f'Product "{product.name}" deleted successfully!')
        return super().delete(request, *args, **kwargs)

class LowStockView(LoginRequiredMixin, ListView):
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

class PurchaseOrderListView(LoginRequiredMixin, ListView):
    model = PurchaseOrder
    template_name = 'inventory/purchaseorder_list.html'
    context_object_name = 'purchase_orders'
    paginate_by = 20
    
    def get_queryset(self):
        queryset = PurchaseOrder.objects.select_related('supplier').prefetch_related('items').order_by('-order_date')
        
        # Status filter
        status_filter = self.request.GET.get('status')
        if status_filter:
            queryset = queryset.filter(status=status_filter)
        
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
        
        # Calculate statistics
        queryset = self.get_queryset()
        context['total_orders'] = queryset.count()
        context['draft_orders'] = queryset.filter(status='draft').count()
        context['ordered_orders'] = queryset.filter(status='ordered').count()
        context['received_orders'] = queryset.filter(status='received').count()
        context['cancelled_orders'] = queryset.filter(status='cancelled').count()
        
        # Calculate total order value
        total_value = queryset.aggregate(total=Sum('total_amount'))['total'] or 0
        context['total_order_value'] = total_value
        
        return context

class PurchaseOrderCreateView(LoginRequiredMixin, CreateView):
    model = PurchaseOrder
    form_class = PurchaseOrderForm
    template_name = 'inventory/purchase_order_form.html'
    
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
        
        if formset.is_valid():
            # Set the order date and initial status
            form.instance.order_date = timezone.now()
            
            # Calculate total amount from items
            response = super().form_valid(form)
            
            # Save the formset instances
            formset.instance = self.object
            formset.save()
            
            # Calculate and save total amount
            self.object.calculate_total_amount()
            
            # Check if the order should be placed immediately
            if 'place_order' in self.request.POST:
                self.object.status = 'ordered'
                self.object.save()
                messages.success(self.request, f'Purchase Order #{self.object.id} created and placed successfully!')
            else:
                messages.success(self.request, f'Purchase Order #{self.object.id} saved as draft!')
            
            return response
        else:
            return self.form_invalid(form)
    
    def get_success_url(self):
        return reverse_lazy('purchase-order-detail', kwargs={'pk': self.object.pk})

class PurchaseOrderDetailView(LoginRequiredMixin, DetailView):
    model = PurchaseOrder
    template_name = 'inventory/purchaseorder_detail.html'
    context_object_name = 'order'
    
    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context['order_items'] = self.object.items.select_related('product')
        return context

class PurchaseOrderUpdateView(LoginRequiredMixin, UpdateView):
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
        
        if formset.is_valid():
            response = super().form_valid(form)
            formset.instance = self.object
            formset.save()
            
            # Recalculate total amount
            self.object.calculate_total_amount()
            
            # Check if the order should be placed
            if 'place_order' in self.request.POST and self.object.status == 'draft':
                self.object.status = 'ordered'
                self.object.save()
                messages.success(self.request, f'Purchase Order #{self.object.id} updated and placed successfully!')
            else:
                messages.success(self.request, f'Purchase Order #{self.object.id} updated successfully!')
            
            return response
        else:
            return self.form_invalid(form)
    
    def get_success_url(self):
        return reverse_lazy('purchase-order-detail', kwargs={'pk': self.object.pk})

class PurchaseOrderDeleteView(LoginRequiredMixin, DeleteView):
    model = PurchaseOrder
    template_name = 'inventory/purchaseorder_confirm_delete.html'
    success_url = reverse_lazy('purchase-order-list')
    
    def delete(self, request, *args, **kwargs):
        order = self.get_object()
        messages.success(request, f'Purchase Order #{order.id} deleted successfully!')
        return super().delete(request, *args, **kwargs)


def mark_as_ordered(request, pk):
    order = get_object_or_404(PurchaseOrder, pk=pk)
    
    if order.status == 'draft':
        order.status = 'ordered'
        order.save()
        messages.success(request, f'Purchase Order #{order.id} marked as ordered!')
    else:
        messages.error(request, 'Only draft orders can be marked as ordered.')
    
    return redirect('purchase-order-list')


def receive_purchase_order(request, pk):
    order = get_object_or_404(PurchaseOrder, pk=pk)
    
    if order.status == 'ordered':
        try:
            with transaction.atomic():
                # Update stock for each item
                for item in order.items.all():
                    product = item.product
                    old_stock = product.current_stock
                    product.current_stock += item.quantity
                    product.save()
                    
                    # Record stock movement
                    StockMovement.objects.create(
                        product=product,
                        movement_type='in',
                        quantity=item.quantity,
                        previous_stock=old_stock,
                        new_stock=product.current_stock,
                        reason=f'Purchase order #{order.id} received',
                        user=request.user
                    )
                
                # Update order status
                order.status = 'received'
                order.save()
                
                messages.success(request, f'Purchase Order #{order.id} received and stock updated!')
                
        except Exception as e:
            messages.error(request, f'Error receiving order: {str(e)}')
    else:
        messages.error(request, 'Only ordered orders can be received.')
    
    return redirect('purchase-order-list')

def cancel_purchase_order(request, pk):
    order = get_object_or_404(PurchaseOrder, pk=pk)
    
    if order.status in ['draft', 'ordered']:
        order.status = 'cancelled'
        order.save()
        messages.success(request, f'Purchase Order #{order.id} cancelled!')
    else:
        messages.error(request, 'Only draft or ordered orders can be cancelled.')
    
    return redirect('purchase-order-list')

def receive_purchase_order(request, pk):
    purchase_order = get_object_or_404(PurchaseOrder, pk=pk)
    
    if request.method == 'POST':
        # Update stock for each item in the purchase order
        for item in purchase_order.items.all():
            # Update product stock
            product = item.product
            old_stock = product.current_stock
            product.current_stock += item.quantity
            product.save()
            
            # Record stock movement
            StockMovement.objects.create(
                product=product,
                movement_type='in',
                quantity=item.quantity,
                previous_stock=old_stock,
                new_stock=product.current_stock,
                reason=f'Purchase order #{purchase_order.id} received',
                user=request.user
            )
        
        # Update purchase order status
        purchase_order.status = 'received'
        purchase_order.save()
        
        messages.success(request, f'Purchase order #{purchase_order.id} received and stock updated!')
    
    return redirect('purchase-order-list')

class StockMovementListView(LoginRequiredMixin, ListView):
    model = StockMovement
    template_name = 'inventory/stock_movements.html'
    context_object_name = 'stock_movements'
    paginate_by = 20
    
    def get_queryset(self):
        return StockMovement.objects.select_related('product', 'user').order_by('-timestamp')

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



