import json
from django.shortcuts import render, redirect, get_object_or_404
from django.urls import reverse_lazy
from django.views.generic import ListView, DetailView, CreateView
from django.contrib.auth.mixins import LoginRequiredMixin
from django.contrib.auth.decorators import login_required
from django.db.models import Sum, Count, Q, F
from django.db import transaction
from django.utils import timezone
from django.http import JsonResponse
from django.contrib import messages
from datetime import datetime, timedelta
from .models import Sale, SaleItem, Customer, DailySummary
from inventory.models import Product, StockMovement
from decimal import Decimal

@login_required
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

class SaleListView(LoginRequiredMixin, ListView):
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

class SaleDetailView(LoginRequiredMixin, DetailView):
    model = Sale
    template_name = 'sales/sale_detail.html'
    context_object_name = 'sale'
    
    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context['sale_items'] = self.object.items.select_related('product')
        return context

class DailyReportView(LoginRequiredMixin, ListView):
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