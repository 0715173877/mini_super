from django.shortcuts import render
from django.utils import timezone
from django.db.models import Sum, Count, Q, F
from django.contrib.auth.decorators import login_required
from inventory.models import Product
from sales.models import Sale, SaleItem, DailySummary
from operations.models import WasteRecord
from datetime import datetime, timedelta
from django.contrib.auth import login, authenticate
from django.contrib.auth.forms import AuthenticationForm
from django.shortcuts import render, redirect

# views.py
from django.views.generic import TemplateView, ListView
from django.contrib.auth.mixins import LoginRequiredMixin
from django.db.models import Sum, Count, Avg, F, Q
from django.utils import timezone
from datetime import datetime, timedelta
from inventory.models import  Product, Category
# Roles: the sales report is a selling page, the inventory report a shelving one.
from core.permissions import PermissionRequiredMixin

class SalesReportView(LoginRequiredMixin, PermissionRequiredMixin, TemplateView):
    permission_required = 'sales.view_sale'
    template_name = 'reports/sales_report.html'
    
    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        
        # Date filtering
        date_range = self.request.GET.get('date_range', 'today')
        end_date = timezone.now()
        
        if date_range == 'today':
            start_date = end_date.replace(hour=0, minute=0, second=0, microsecond=0)
        elif date_range == 'yesterday':
            start_date = end_date.replace(hour=0, minute=0, second=0, microsecond=0) - timedelta(days=1)
            end_date = start_date + timedelta(days=1)
        elif date_range == 'week':
            start_date = end_date - timedelta(days=7)
        elif date_range == 'month':
            start_date = end_date - timedelta(days=30)
        elif date_range == 'custom':
            start_date_str = self.request.GET.get('start_date')
            end_date_str = self.request.GET.get('end_date')
            if start_date_str and end_date_str:
                start_date = timezone.make_aware(datetime.strptime(start_date_str, '%Y-%m-%d'))
                end_date = timezone.make_aware(datetime.strptime(end_date_str, '%Y-%m-%d'))
            else:
                start_date = end_date - timedelta(days=30)
        else:
            start_date = end_date - timedelta(days=30)
        
        # Sales data
        sales = Sale.objects.filter(created_at__range=[start_date, end_date])
        
        # Key metrics
        total_sales = sales.count()
        total_revenue = sales.aggregate(Sum('total_amount'))['total_amount__sum'] or 0
        total_items_sold = SaleItem.objects.filter(sale__in=sales).aggregate(Sum('quantity'))['quantity__sum'] or 0
        average_sale = total_revenue / total_sales if total_sales > 0 else 0
        
        # Payment method breakdown
        payment_methods = sales.values('payment_method').annotate(
            count=Count('id'),
            total=Sum('total_amount')
        )
        
        # Daily sales trend
        daily_sales = sales.extra(
            {'date': "date(created_at)"}
        ).values('date').annotate(
            daily_total=Sum('total_amount'),
            daily_count=Count('id')
        ).order_by('date')
        
        # Top products
        top_products = SaleItem.objects.filter(sale__in=sales).values(
            'product__name', 'product__sku'
        ).annotate(
            total_sold=Sum('quantity'),
            total_revenue=Sum('unit_price')
        ).order_by('-total_sold')[:10]
        
        context.update({
            'date_range': date_range,
            'start_date': start_date,
            'end_date': end_date,
            'total_sales': total_sales,
            'total_revenue': total_revenue,
            'total_items_sold': total_items_sold,
            'average_sale': average_sale,
            'payment_methods': payment_methods,
            'daily_sales': daily_sales,
            'top_products': top_products,
        })
        return context

class InventoryReportView(LoginRequiredMixin, PermissionRequiredMixin, ListView):
    permission_required = 'inventory.view_product'
    template_name = 'reports/inventory_report.html'
    context_object_name = 'products'
    paginate_by = 50
    
    def get_queryset(self):
        queryset = Product.objects.select_related('category', 'supplier')
        
        # Filters
        stock_status = self.request.GET.get('stock_status')
        category = self.request.GET.get('category')
        
        if stock_status == 'low_stock':
            queryset = queryset.filter(current_stock__lte=F('min_stock_level'))
        elif stock_status == 'out_of_stock':
            queryset = queryset.filter(current_stock=0)
        elif stock_status == 'over_stock':
            queryset = queryset.filter(current_stock__gt=F('max_stock_level'))
        
        if category:
            queryset = queryset.filter(category_id=category)
        
        return queryset.order_by('category__name', 'name')
    
    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        
        # Inventory summary
        total_products = Product.objects.count()
        total_value = Product.objects.aggregate(
            total=Sum(F('current_stock') * F('cost_price'))
        )['total'] or 0
        
        low_stock_count = Product.objects.filter(
            current_stock__lte=F('min_stock_level')
        ).count()
        
        out_of_stock_count = Product.objects.filter(current_stock=0).count()
        
        context.update({
            'categories': Category.objects.all(),
            'total_products': total_products,
            'total_value': total_value,
            'low_stock_count': low_stock_count,
            'out_of_stock_count': out_of_stock_count,
        })
        return context

class AnalyticsView(LoginRequiredMixin, PermissionRequiredMixin, TemplateView):
    permission_required = 'sales.view_sale'
    template_name = 'reports/analytics.html'
    
    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        
        # Time period
        period = self.request.GET.get('period', 'month')
        end_date = timezone.now()
        
        if period == 'week':
            start_date = end_date - timedelta(days=7)
        elif period == 'month':
            start_date = end_date - timedelta(days=30)
        elif period == 'quarter':
            start_date = end_date - timedelta(days=90)
        else:
            start_date = end_date - timedelta(days=30)
        
        # Sales analytics
        sales_data = Sale.objects.filter(created_at__range=[start_date, end_date])
        
        # Revenue trends
        revenue_trend = sales_data.extra({
            'date': "date(created_at)"
        }).values('date').annotate(
            revenue=Sum('total_amount'),
            transactions=Count('id')
        ).order_by('date')
        
        # Product performance
        product_performance = SaleItem.objects.filter(
            sale__created_at__range=[start_date, end_date]
        ).values(
            'product__name', 'product__category__name'
        ).annotate(
            units_sold=Sum('quantity'),
            revenue=Sum('unit_price'),
            profit=Sum(F('unit_price') - (F('quantity') * F('product__cost_price')))
        ).order_by('-revenue')[:15]
        
        # Category performance
        category_performance = SaleItem.objects.filter(
            sale__created_at__range=[start_date, end_date]
        ).values('product__category__name').annotate(
            revenue=Sum('unit_price'),
            units_sold=Sum('quantity')
        ).order_by('-revenue')
        
        # Customer analytics
        customer_analytics = Sale.objects.filter(
            created_at__range=[start_date, end_date]
        ).values('customer__name').annotate(
            total_spent=Sum('total_amount'),
            visit_count=Count('id'),
            avg_spent=Avg('total_amount')
        ).order_by('-total_spent')[:10]
        
        # Key metrics
        total_revenue = sales_data.aggregate(Sum('total_amount'))['total_amount__sum'] or 0
        total_transactions = sales_data.count()
        avg_transaction_value = total_revenue / total_transactions if total_transactions > 0 else 0
        
        context.update({
            'period': period,
            'revenue_trend': revenue_trend,
            'product_performance': product_performance,
            'category_performance': category_performance,
            'customer_analytics': customer_analytics,
            'total_revenue': total_revenue,
            'total_transactions': total_transactions,
            'avg_transaction_value': avg_transaction_value,
            'start_date': start_date,
            'end_date': end_date,
        })
        return context



def custom_login(request):
    """
    Custom login view to handle authentication
    """
    if request.user.is_authenticated:
        return redirect('dashboard')
    
    if request.method == 'POST':
        form = AuthenticationForm(request, data=request.POST)
        if form.is_valid():
            username = form.cleaned_data.get('username')
            password = form.cleaned_data.get('password')
            user = authenticate(username=username, password=password)
            if user is not None:
                login(request, user)
                messages.success(request, f'Welcome back, {username}!')
                
                # Redirect to next page or dashboard
                next_page = request.GET.get('next', 'dashboard')
                return redirect(next_page)
        else:
            messages.error(request, 'Invalid username or password.')
    else:
        form = AuthenticationForm()
    
    return render(request, 'registration/login.html', {'form': form})

@login_required
def dashboard(request):
    # Get date range for last 7 days
    end_date = timezone.now().date()
    start_date = end_date - timedelta(days=6)
    
    # Sales data for chart
    sales_data = []
    sales_labels = []
    
    for i in range(7):
        date = start_date + timedelta(days=i)
        daily_sales = Sale.objects.filter(
            created_at__date=date
        ).aggregate(total=Sum('total_amount'))['total'] or 0
        
        sales_data.append(float(daily_sales))
        sales_labels.append(date.strftime('%m/%d'))
    
    # Key metrics
    today_sales = Sale.objects.filter(
        created_at__date=end_date
    ).aggregate(total=Sum('total_amount'))['total'] or 0
    
    # FIXED: Added models import, so F() works now
    low_stock_count = Product.objects.filter(
        current_stock__lte=F('min_stock_level')
    ).count()
    
    today_customers = Sale.objects.filter(
        created_at__date=end_date
    ).values('customer').distinct().count()
    
    monthly_waste = WasteRecord.objects.filter(
        created_at__month=end_date.month,
        created_at__year=end_date.year
    ).aggregate(total=Sum('cost_value'))['total'] or 0
    
    # Recent sales
    recent_sales = Sale.objects.select_related('cashier', 'customer').order_by('-created_at')[:10]
    
    # Low stock items - FIXED: using F() with proper import
    low_stock_items = Product.objects.filter(
        current_stock__lte=F('min_stock_level')
    )[:5]
    
    context = {
        'today_sales': today_sales,
        'low_stock_count': low_stock_count,
        'today_customers': today_customers,
        'monthly_waste': monthly_waste,
        'recent_sales': recent_sales,
        'low_stock_items': low_stock_items,
        'sales_data': sales_data,
        'sales_labels': sales_labels,
        'current_date': end_date.strftime('%B %d, %Y'),
    }
    
    return render(request, 'dashboard.html', context)