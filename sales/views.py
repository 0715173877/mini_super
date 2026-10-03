import json
import uuid
from django.shortcuts import render, redirect, get_object_or_404
from django.urls import reverse_lazy
from django.views.generic import ListView, DetailView, CreateView
from django.contrib.auth.mixins import LoginRequiredMixin
from django.contrib.auth.decorators import login_required, permission_required
from django.db.models import Sum, Count, Q, F
from django.db import transaction
from django.utils import timezone
from django.http import JsonResponse
from django.contrib import messages
from datetime import datetime, timedelta
from .models import Sale, SaleItem, Customer, DailySummary, CustomerReturn, CustomerReturnItem
from .forms import CustomerReturnForm, CustomerReturnItemFormSet
from inventory.models import Product, StockMovement
from decimal import Decimal, InvalidOperation
from core.permissions import PermissionRequiredMixin

@login_required
@permission_required('sales.add_sale', raise_exception=True)
def point_of_sale(request):
    products = Product.objects.filter(current_stock__gt=0).select_related('category')
    customers = Customer.objects.filter(is_regular=True)
    
    if request.method == 'POST':
        return process_sale(request)
    
    return render(request, 'sales/point_of_sale.html', {
        'products': products,
        'customers': customers
    })

def process_sale(request):
    try:
        cart_data = json.loads(request.POST.get('cart_data', '[]'))
        payment_method = request.POST.get('payment_method')
        customer_id = request.POST.get('customer') or None
        
        if not cart_data:
            messages.error(request, 'No items in cart!')
            return redirect('point-of-sale')
        
        with transaction.atomic():
            # Create sale
            sale = Sale.objects.create(
                customer_id=customer_id,
                transaction_id=generate_transaction_id(),
                total_amount=Decimal('0.00'),
                tax_amount=Decimal('0.00'),
                payment_method=payment_method,
                cashier=request.user
            )
            
            total_amount = Decimal('0.00')
            
            # Process each cart item
            for item_data in cart_data:
                product = Product.objects.select_for_update().get(id=item_data['id'])
                
                # FIXED: Convert to Decimal instead of float
                quantity = Decimal(str(item_data['quantity']))
                unit_price = Decimal(str(item_data['price']))
                
                # Check stock availability
                if product.current_stock < quantity:
                    raise ValueError(f'Insufficient stock for {product.name}. Available: {product.current_stock}')
                
                # Create sale item
                sale_item = SaleItem.objects.create(
                    sale=sale,
                    product=product,
                    quantity=quantity,
                    unit_price=unit_price
                )
                
                # Update product stock - FIXED: Using Decimal operations
                old_stock = product.current_stock
                product.current_stock = old_stock - quantity
                product.save()
                
                # Record stock movement
                StockMovement.objects.create(
                    product=product,
                    movement_type='out',
                    quantity=quantity,
                    previous_stock=old_stock,
                    new_stock=product.current_stock,
                    reason=f'Sale #{sale.transaction_id}',
                    user=request.user
                )
                
                total_amount += sale_item.total_price
            
            # Calculate tax and update sale total - FIXED: Using Decimal
            tax_rate = Decimal('0.08')  # 8% tax
            tax_amount = total_amount * tax_rate
            sale.total_amount = total_amount + tax_amount
            sale.tax_amount = tax_amount
            sale.save()
            
            # Update daily summary
            update_daily_summary(sale.created_at.date())
            
            messages.success(request, f'Sale completed! Transaction ID: {sale.transaction_id}')
            return redirect('sale-detail', pk=sale.pk)
            
    except Exception as e:
        messages.error(request, f'Error processing sale: {str(e)}')
        return redirect('point-of-sale')

def generate_transaction_id():
    """Generate unique transaction ID"""
    from datetime import datetime
    return f"TX{datetime.now().strftime('%Y%m%d%H%M%S')}"

def update_daily_summary(date):
    """Update or create daily summary for the given date"""
    daily_sales = Sale.objects.filter(created_at__date=date)
    
    if daily_sales.exists():
        summary, created = DailySummary.objects.get_or_create(date=date)
        
        summary_data = daily_sales.aggregate(
            total_sales=Sum('total_amount'),
            total_customers=Count('customer', distinct=True),
            cash_sales=Sum('total_amount', filter=Q(payment_method='cash')),
            card_sales=Sum('total_amount', filter=Q(payment_method='card')),
            mobile_sales=Sum('total_amount', filter=Q(payment_method='mobile'))
        )
        
        summary.total_sales = summary_data['total_sales'] or 0
        summary.total_customers = summary_data['total_customers'] or 0
        summary.cash_sales = summary_data['cash_sales'] or 0
        summary.card_sales = summary_data['card_sales'] or 0
        summary.mobile_sales = summary_data['mobile_sales'] or 0
        summary.save()

class SaleListView(LoginRequiredMixin, PermissionRequiredMixin, ListView):
    permission_required = 'sales.view_sale'
    model = Sale
    template_name = 'sales/sale_list.html'
    context_object_name = 'sales'
    paginate_by = 20
    
    def get_queryset(self):
        queryset = Sale.objects.select_related('customer', 'cashier').order_by('-created_at')
        
        # Date filter
        date_filter = self.request.GET.get('date')
        if date_filter:
            try:
                filter_date = datetime.strptime(date_filter, '%Y-%m-%d').date()
                queryset = queryset.filter(created_at__date=filter_date)
            except ValueError:
                pass
        
        # Payment method filter
        payment_filter = self.request.GET.get('payment_method')
        if payment_filter:
            queryset = queryset.filter(payment_method=payment_filter)
        
        return queryset
    
    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        # Add filter values to context
        context['filter_date'] = self.request.GET.get('date', '')
        context['payment_method'] = self.request.GET.get('payment_method', '')
        return context

class SaleDetailView(LoginRequiredMixin, PermissionRequiredMixin, DetailView):
    permission_required = 'sales.view_sale'
    model = Sale
    template_name = 'sales/sale_detail.html'
    context_object_name = 'sale'
    
    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context['sale_items'] = self.object.items.select_related('product')
        return context

class DailyReportView(LoginRequiredMixin, PermissionRequiredMixin, ListView):
    permission_required = 'sales.view_dailysummary'
    template_name = 'sales/daily_reports.html'
    context_object_name = 'daily_summaries'
    
    def get_queryset(self):
        # Get last 30 days of summaries
        end_date = timezone.now().date()
        start_date = end_date - timedelta(days=30)
        
        return DailySummary.objects.filter(
            date__range=[start_date, end_date]
        ).order_by('-date')
    
    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        
        # Calculate metrics
        summaries = self.get_queryset()
        total_sales = sum(summary.total_sales for summary in summaries)
        avg_daily_sales = total_sales / len(summaries) if summaries else 0
        
        context.update({
            'total_sales': total_sales,
            'avg_daily_sales': avg_daily_sales,
            'total_customers': sum(summary.total_customers for summary in summaries),
        })
        
        return context

@login_required
@permission_required('sales.view_customer', raise_exception=True)
def customer_analytics(request):
    # Customer statistics
    total_customers = Customer.objects.count()
    regular_customers = Customer.objects.filter(is_regular=True).count()
    
    # Top customers by spending
    top_customers = Customer.objects.annotate(
        total_spent=Sum('sale__total_amount'),
        purchase_count=Count('sale')
    ).filter(total_spent__isnull=False).order_by('-total_spent')[:10]
    
    # Customer growth (last 30 days)
    thirty_days_ago = timezone.now() - timedelta(days=30)
    new_customers = Customer.objects.filter(
        sale__created_at__gte=thirty_days_ago
    ).distinct().count()
    
    context = {
        'total_customers': total_customers,
        'regular_customers': regular_customers,
        'top_customers': top_customers,
        'new_customers': new_customers,
    }
    
    return render(request, 'sales/customer_analytics.html', context)

@login_required
@permission_required('sales.view_sale', raise_exception=True)
def sales_api_data(request):
    """API endpoint for sales chart data"""
    days = int(request.GET.get('days', 7))
    end_date = timezone.now().date()
    start_date = end_date - timedelta(days=days-1)
    
    # Get daily sales data
    daily_data = []
    for i in range(days):
        date = start_date + timedelta(days=i)
        daily_sales = Sale.objects.filter(
            created_at__date=date
        ).aggregate(total=Sum('total_amount'))['total'] or 0
        
        daily_data.append({
            'date': date.strftime('%Y-%m-%d'),
            'sales': float(daily_sales)
        })
    
    return JsonResponse({'data': daily_data})


@login_required
@permission_required('sales.add_sale', raise_exception=True)
def barcode_lookup(request, code):
    """Resolve a scanned barcode (or SKU) to a product for the POS.

    Called by the Bluetooth / serial scanner integration in
    ``templates/sales/point_of_sale.html`` (Web Serial API). Returning JSON
    lets the POS push the product straight into the cart without a reload.
    """
    code = (code or '').strip()

    product = (
        Product.objects.filter(barcode=code).first()
        or Product.objects.filter(sku=code).first()
    )

    if product is None:
        return JsonResponse({
            'success': False,
            'error': f'No product matches barcode "{code}".',
        }, status=404)

    if product.current_stock <= 0:
        return JsonResponse({
            'success': False,
            'error': f'{product.name} is out of stock.',
        })

    return JsonResponse({
        'success': True,
        'product': {
            'id': product.id,
            'name': product.name,
            'price': str(product.selling_price),
            'stock': str(product.current_stock),
            'barcode': product.barcode,
            'sku': product.sku,
        },
    })


@login_required
@permission_required('sales.view_sale', raise_exception=True)
def sale_search_api(request):
    """Search past sales for the customer-return "Original Sale" picker.

    Matches on the receipt / transaction id, the customer name or phone,
    and an exact amount so a cashier can find the original receipt.
    """
    query = (request.GET.get('q') or '').strip()

    sales = Sale.objects.select_related('customer').order_by('-created_at')
    if query:
        filters = (
            Q(transaction_id__icontains=query)
            | Q(customer__name__icontains=query)
            | Q(customer__phone__icontains=query)
        )
        try:
            filters |= Q(total_amount=Decimal(query))
        except (InvalidOperation, ValueError):
            pass
        sales = sales.filter(filters)

    sales = sales[:15]

    results = [{
        'id': sale.id,
        'transaction_id': sale.transaction_id,
        'date': timezone.localtime(sale.created_at).strftime('%d %b %Y %H:%M'),
        'total': str(sale.total_amount),
        'customer_id': sale.customer_id,
        'customer_name': str(sale.customer) if sale.customer else 'Walk-in customer',
        'payment_method': sale.get_payment_method_display(),
    } for sale in sales]

    return JsonResponse({'success': True, 'results': results})


@login_required
@permission_required('sales.view_sale', raise_exception=True)
def sale_items_api(request, pk):
    """Return the line items of a sale for pre-filling a customer return.

    For each line we also report how much of it has already been returned
    against this same sale, so the form only offers what is still returnable.
    """
    sale = get_object_or_404(
        Sale.objects.select_related('customer').prefetch_related('items__product'),
        pk=pk,
    )

    already_returned = {
        row['product_id']: row['total']
        for row in CustomerReturnItem.objects.filter(
            customer_return__sale=sale
        ).values('product_id').annotate(total=Sum('quantity'))
    }

    items = []
    for item in sale.items.all():
        returned = already_returned.get(item.product_id, Decimal('0'))
        remaining = item.quantity - returned
        items.append({
            'product_id': item.product_id,
            'product_name': item.product.name,
            'sku': item.product.sku,
            'quantity': str(item.quantity),
            'already_returned': str(returned),
            'remaining': str(remaining if remaining > 0 else Decimal('0')),
            'unit_price': str(item.unit_price),
        })

    return JsonResponse({
        'success': True,
        'sale': {
            'id': sale.id,
            'transaction_id': sale.transaction_id,
            'date': timezone.localtime(sale.created_at).strftime('%d %b %Y %H:%M'),
            'total': str(sale.total_amount),
            'customer_id': sale.customer_id,
            'customer_name': str(sale.customer) if sale.customer else 'Walk-in customer',
        },
        'items': items,
    })


# ---------------------------------------------------------------------------
# Customer returns
#
# Goods a customer brings back re-enter the shop: recording a return adds the
# quantities to Product.current_stock and logs one StockMovement per line with
# movement_type='customer_return'. This is the mirror image of process_sale().
# ---------------------------------------------------------------------------

def generate_return_reference(prefix):
    """Build a unique reference such as ``CR20260930A1B2C3``."""
    stamp = timezone.now().strftime('%Y%m%d%H%M%S')
    return f"{prefix}{stamp}{uuid.uuid4().hex[:4].upper()}"


def add_customer_return_to_stock(customer_return, user):
    """Add every line of a customer return back to stock.

    Must be called inside ``transaction.atomic()``. Returns the number of
    lines applied.
    """
    lines = list(customer_return.items.select_related('product'))
    for item in lines:
        product = item.product
        previous_stock = product.current_stock
        product.current_stock = previous_stock + item.quantity
        product.save()

        StockMovement.objects.create(
            product=product,
            movement_type='customer_return',
            quantity=item.quantity,
            previous_stock=previous_stock,
            new_stock=product.current_stock,
            reason=f'Customer return {customer_return.reference}',
            user=user,
        )
    return len(lines)


class CustomerReturnListView(LoginRequiredMixin, PermissionRequiredMixin, ListView):
    permission_required = 'sales.view_customerreturn'
    model = CustomerReturn
    template_name = 'sales/customer_return_list.html'
    context_object_name = 'customer_returns'
    paginate_by = 20

    def get_queryset(self):
        return CustomerReturn.objects.select_related(
            'customer', 'sale', 'processed_by'
        ).prefetch_related('items').order_by('-created_at')


class CustomerReturnCreateView(LoginRequiredMixin, PermissionRequiredMixin, CreateView):
    permission_required = 'sales.add_customerreturn'
    model = CustomerReturn
    form_class = CustomerReturnForm
    template_name = 'sales/customer_return_form.html'

    def get_initial(self):
        initial = super().get_initial()
        # Allow the sale detail page to pre-select the sale: ?sale=<pk>
        sale_id = self.request.GET.get('sale')
        if sale_id:
            sale = Sale.objects.filter(pk=sale_id).first()
            if sale:
                initial['sale'] = sale
                initial['customer'] = sale.customer
        return initial

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        if self.request.POST:
            context['formset'] = CustomerReturnItemFormSet(self.request.POST, instance=self.object)
        else:
            context['formset'] = CustomerReturnItemFormSet(instance=self.object)
        context['products'] = Product.objects.select_related('category').order_by('name')

        # Info for the searchable "Original Sale" picker: pre-selected from
        # ?sale=<pk> (sale detail page) or restored after a failed submission.
        sale_id = self.request.POST.get('sale') or self.request.GET.get('sale')
        selected_sale = None
        if sale_id:
            try:
                selected_sale = Sale.objects.select_related('customer').filter(pk=sale_id).first()
            except (TypeError, ValueError):
                selected_sale = None
        context['selected_sale'] = selected_sale
        # Only auto-fill the item rows on a fresh GET so we never clobber a
        # submission that came back with validation errors.
        context['prefill_items'] = bool(selected_sale) and not self.request.POST
        return context

    def form_valid(self, form):
        context = self.get_context_data()
        formset = context['formset']

        if not formset.is_valid():
            return self.form_invalid(form)

        form.instance.processed_by = self.request.user
        form.instance.reference = generate_return_reference('CR')

        with transaction.atomic():
            response = super().form_valid(form)
            formset.instance = self.object
            formset.save()
            self.object.calculate_total_amount()
            lines = add_customer_return_to_stock(self.object, self.request.user)

        messages.success(
            self.request,
            f'Customer return {self.object.reference} recorded — '
            f'stock updated for {lines} item(s).'
        )
        return response

    def get_success_url(self):
        return reverse_lazy('customer-return-detail', kwargs={'pk': self.object.pk})


class CustomerReturnDetailView(LoginRequiredMixin, PermissionRequiredMixin, DetailView):
    permission_required = 'sales.view_customerreturn'
    model = CustomerReturn
    template_name = 'sales/customer_return_detail.html'
    context_object_name = 'customer_return'

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context['return_items'] = self.object.items.select_related('product')
        return context