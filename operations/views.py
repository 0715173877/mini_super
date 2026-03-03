from django.shortcuts import render, redirect, get_object_or_404
from django.urls import reverse_lazy
from django.views.generic import ListView, CreateView, TemplateView, UpdateView, DeleteView
from django.contrib.auth.mixins import LoginRequiredMixin
from django.contrib.auth.decorators import login_required
from django.db.models import Sum, Count, Avg, Q, F
from django.utils import timezone
from django.contrib import messages
from django.http import JsonResponse
from datetime import datetime, timedelta
from decimal import Decimal
import json

from .models import WasteRecord, Staff, Shift, PeakHour, SupplierPerformance
from inventory.models import Product, Supplier, StockMovement
from sales.models import Sale, DailySummary

@login_required
def waste_tracking(request):
    """
    Main view for waste tracking - handles both display and form submission
    """
    if request.method == 'POST':
        return record_waste(request)
    
    # Get filter parameters
    waste_category = request.GET.get('category', '')
    start_date = request.GET.get('start_date', '')
    end_date = request.GET.get('end_date', '')
    
    # Base queryset
    waste_records = WasteRecord.objects.select_related('product', 'recorded_by').order_by('-created_at')
    
    # Apply filters
    if waste_category:
        waste_records = waste_records.filter(category=waste_category)
    
    if start_date:
        try:
            start_date_obj = datetime.strptime(start_date, '%Y-%m-%d').date()
            waste_records = waste_records.filter(created_at__date__gte=start_date_obj)
        except ValueError:
            pass
    
    if end_date:
        try:
            end_date_obj = datetime.strptime(end_date, '%Y-%m-%d').date()
            waste_records = waste_records.filter(created_at__date__lte=end_date_obj)
        except ValueError:
            pass
    
    # Waste statistics
    current_month = timezone.now().month
    current_year = timezone.now().year
    
    monthly_waste_total = WasteRecord.objects.filter(
        created_at__month=current_month,
        created_at__year=current_year
    ).aggregate(total=Sum('cost_value'))['total'] or 0
    
    spoilage_count = WasteRecord.objects.filter(
        category='spoilage',
        created_at__month=current_month
    ).count()
    
    # Waste by category for current month
    waste_by_category = WasteRecord.objects.filter(
        created_at__month=current_month,
        created_at__year=current_year
    ).values('category').annotate(
        total_cost=Sum('cost_value'),
        total_quantity=Sum('quantity'),
        record_count=Count('id')
    ).order_by('-total_cost')
    
    # Top wasted products
    top_wasted_products = WasteRecord.objects.filter(
        created_at__month=current_month
    ).values('product__name', 'product__sku').annotate(
        total_cost=Sum('cost_value'),
        total_quantity=Sum('quantity')
    ).order_by('-total_cost')[:10]
    
    products = Product.objects.filter(current_stock__gt=0).order_by('name')
    
    context = {
        'waste_records': waste_records,
        'monthly_waste_total': monthly_waste_total,
        'spoilage_count': spoilage_count,
        'waste_by_category': waste_by_category,
        'top_wasted_products': top_wasted_products,
        'products': products,
        'current_filters': {
            'category': waste_category,
            'start_date': start_date,
            'end_date': end_date,
        }
    }
    
    return render(request, 'operations/waste_tracking.html', context)

def record_waste(request):
    """
    Process waste recording form submission
    """
    try:
        product_id = request.POST.get('product')
        quantity = Decimal(request.POST.get('quantity', 0))
        category = request.POST.get('category')
        cost_value = Decimal(request.POST.get('cost_value', 0))
        reason = request.POST.get('reason', '').strip()
        
        if not product_id or quantity <= 0 or cost_value < 0:
            messages.error(request, 'Please fill all required fields with valid values.')
            return redirect('waste-tracking')
        
        product = Product.objects.get(id=product_id)
        
        # Validate that we're not wasting more than available stock
        if quantity > product.current_stock:
            messages.error(request, 
                         f'Cannot waste {quantity} units. Only {product.current_stock} units available.')
            return redirect('waste-tracking')
        
        # Create waste record
        waste_record = WasteRecord.objects.create(
            product=product,
            quantity=quantity,
            category=category,
            cost_value=cost_value,
            reason=reason,
            recorded_by=request.user
        )
        
        # Update product stock
        old_stock = product.current_stock
        product.current_stock = max(0, product.current_stock - quantity)
        product.save()
        
        # Record stock movement
        StockMovement.objects.create(
            product=product,
            movement_type='waste',
            quantity=quantity,
            previous_stock=old_stock,
            new_stock=product.current_stock,
            reason=f'Waste ({category}): {reason}',
            user=request.user
        )
        
        messages.success(request, 
                        f'Waste recorded for {product.name}. {quantity} units wasted. Cost: ${cost_value:.2f}')
        
    except Product.DoesNotExist:
        messages.error(request, 'Selected product not found.')
    except Exception as e:
        messages.error(request, f'Error recording waste: {str(e)}')
    
    return redirect('waste-tracking')

@login_required
def delete_waste_record(request, record_id):
    """
    Delete a waste record and restore stock
    """
    try:
        waste_record = get_object_or_404(WasteRecord, id=record_id)
        product = waste_record.product
        
        # Restore stock
        product.current_stock += waste_record.quantity
        product.save()
        
        # Record the reversal as a stock movement
        StockMovement.objects.create(
            product=product,
            movement_type='in',
            quantity=waste_record.quantity,
            previous_stock=product.current_stock - waste_record.quantity,
            new_stock=product.current_stock,
            reason=f'Waste record deletion - restored stock',
            user=request.user
        )
        
        # Delete the waste record
        product_name = waste_record.product.name
        waste_record.delete()
        
        messages.success(request, f'Waste record for {product_name} deleted and stock restored.')
        
    except Exception as e:
        messages.error(request, f'Error deleting waste record: {str(e)}')
    
    return redirect('waste-tracking')

class StaffSchedulingView(LoginRequiredMixin, ListView):
    """
    View for staff scheduling and shift management
    """
    model = Shift
    template_name = 'operations/staff_scheduling.html'
    context_object_name = 'shifts'
    
    def get_queryset(self):
        # Get date range from request or default to current week
        date_filter = self.request.GET.get('date', '')
        
        if date_filter:
            try:
                filter_date = datetime.strptime(date_filter, '%Y-%m-%d').date()
                start_of_week = filter_date - timedelta(days=filter_date.weekday())
                end_of_week = start_of_week + timedelta(days=6)
            except ValueError:
                start_of_week = timezone.now().date() - timedelta(days=timezone.now().weekday())
                end_of_week = start_of_week + timedelta(days=6)
        else:
            start_of_week = timezone.now().date() - timedelta(days=timezone.now().weekday())
            end_of_week = start_of_week + timedelta(days=6)
        
        return Shift.objects.filter(
            shift_date__range=[start_of_week, end_of_week]
        ).select_related('staff__user').order_by('shift_date', 'start_time')
    
    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context['staff_members'] = Staff.objects.select_related('user').order_by('user__first_name')
        
        # Calculate week range for display
        date_filter = self.request.GET.get('date', '')
        if date_filter:
            try:
                filter_date = datetime.strptime(date_filter, '%Y-%m-%d').date()
                week_start = filter_date - timedelta(days=filter_date.weekday())
            except ValueError:
                week_start = timezone.now().date() - timedelta(days=timezone.now().weekday())
        else:
            week_start = timezone.now().date() - timedelta(days=timezone.now().weekday())
        
        context['week_start'] = week_start
        context['week_days'] = [week_start + timedelta(days=i) for i in range(7)]
        
        # Calculate total hours per staff for the week
        shifts = self.get_queryset()
        staff_hours = {}
        for shift in shifts:
            if shift.staff.id not in staff_hours:
                staff_hours[shift.staff.id] = 0
            staff_hours[shift.staff.id] += float(shift.hours_worked)
        
        context['staff_hours'] = staff_hours
        
        return context

@login_required
def add_shift(request):
    """
    Add a new shift for staff
    """
    if request.method == 'POST':
        staff_id = request.POST.get('staff')
        shift_date = request.POST.get('shift_date')
        start_time = request.POST.get('start_time')
        end_time = request.POST.get('end_time')
        notes = request.POST.get('notes', '')
        
        try:
            if not all([staff_id, shift_date, start_time, end_time]):
                messages.error(request, 'Please fill all required fields.')
                return redirect('staff-scheduling')
            
            staff = Staff.objects.get(id=staff_id)
            
            # Calculate hours worked
            start_dt = datetime.strptime(f"{shift_date} {start_time}", "%Y-%m-%d %H:%M")
            end_dt = datetime.strptime(f"{shift_date} {end_time}", "%Y-%m-%d %H:%M")
            
            if end_dt <= start_dt:
                messages.error(request, 'End time must be after start time.')
                return redirect('staff-scheduling')
            
            hours_worked = (end_dt - start_dt).total_seconds() / 3600
            
            # Check for overlapping shifts
            overlapping_shifts = Shift.objects.filter(
                staff=staff,
                shift_date=shift_date
            ).filter(
                Q(start_time__lt=end_time, end_time__gt=start_time)
            )
            
            if overlapping_shifts.exists():
                messages.warning(request, 
                               f'Warning: This shift overlaps with existing shifts for {staff.user.get_full_name()}.')
            
            Shift.objects.create(
                staff=staff,
                shift_date=shift_date,
                start_time=start_time,
                end_time=end_time,
                hours_worked=hours_worked,
                notes=notes
            )
            
            messages.success(request, f'Shift added successfully for {staff.user.get_full_name()}!')
            
        except Staff.DoesNotExist:
            messages.error(request, 'Selected staff member not found.')
        except ValueError as e:
            messages.error(request, f'Invalid date or time format: {str(e)}')
        except Exception as e:
            messages.error(request, f'Error adding shift: {str(e)}')
    
    return redirect('staff-scheduling')

@login_required
def delete_shift(request, shift_id):
    """
    Delete a shift
    """
    try:
        shift = get_object_or_404(Shift, id=shift_id)
        staff_name = shift.staff.user.get_full_name()
        shift_date = shift.shift_date
        
        shift.delete()
        
        messages.success(request, f'Shift for {staff_name} on {shift_date} deleted successfully.')
        
    except Exception as e:
        messages.error(request, f'Error deleting shift: {str(e)}')
    
    return redirect('staff-scheduling')

class PerformanceMetricsView(LoginRequiredMixin, TemplateView):
    """
    View for overall performance metrics and KPIs
    """
    template_name = 'operations/performance_metrics.html'
    
    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        
        today = timezone.now().date()
        current_month = today.month
        current_year = today.year
        
        # Sales performance metrics
        current_week_start = today - timedelta(days=today.weekday())
        previous_week_start = current_week_start - timedelta(days=7)
        
        # Current week sales
        current_week_sales = Sale.objects.filter(
            created_at__date__gte=current_week_start
        ).aggregate(total=Sum('total_amount'))['total'] or 0
        
        # Previous week sales
        previous_week_sales = Sale.objects.filter(
            created_at__date__range=[previous_week_start, current_week_start - timedelta(days=1)]
        ).aggregate(total=Sum('total_amount'))['total'] or 0
        
        # Sales growth calculation
        sales_growth = 0
        if previous_week_sales > 0:
            sales_growth = ((current_week_sales - previous_week_sales) / previous_week_sales) * 100
        
        # Inventory metrics
        total_products = Product.objects.count()
        out_of_stock = Product.objects.filter(current_stock=0).count()
        low_stock = Product.objects.filter(current_stock__lte=F('min_stock_level')).exclude(current_stock=0).count()
        
        stock_health = 0
        if total_products > 0:
            healthy_stock = total_products - out_of_stock - low_stock
            stock_health = (healthy_stock / total_products) * 100
        
        # Waste metrics
        monthly_waste = WasteRecord.objects.filter(
            created_at__month=current_month,
            created_at__year=current_year
        ).aggregate(total=Sum('cost_value'))['total'] or 0
        
        # Customer metrics
        total_customers_today = Sale.objects.filter(
            created_at__date=today
        ).values('customer').distinct().count()
        
        avg_transaction_value = Sale.objects.filter(
            created_at__date=today
        ).aggregate(avg=Avg('total_amount'))['avg'] or 0
        
        # Staff productivity
        total_staff_hours_today = Shift.objects.filter(
            shift_date=today
        ).aggregate(total_hours=Sum('hours_worked'))['total_hours'] or 0
        
        staff_productivity = 0
        if total_staff_hours_today > 0 and current_week_sales > 0:
            # Sales per staff hour
            staff_productivity = current_week_sales / total_staff_hours_today
        
        # Peak hours analysis
        peak_hours = PeakHour.objects.filter(
            date__gte=today - timedelta(days=7)
        ).order_by('-customer_count')[:5]
        
        context.update({
            'current_week_sales': current_week_sales,
            'previous_week_sales': previous_week_sales,
            'sales_growth': sales_growth,
            'total_products': total_products,
            'out_of_stock': out_of_stock,
            'low_stock': low_stock,
            'stock_health': stock_health,
            'monthly_waste': monthly_waste,
            'total_customers_today': total_customers_today,
            'avg_transaction_value': avg_transaction_value,
            'total_staff_hours_today': total_staff_hours_today,
            'staff_productivity': staff_productivity,
            'peak_hours': peak_hours,
            'today': today,
        })
        
        return context

class SupplierPerformanceView(LoginRequiredMixin, ListView):
    """
    View for supplier performance evaluation and tracking
    """
    model = SupplierPerformance
    template_name = 'operations/supplier_performance.html'
    context_object_name = 'supplier_performances'
    paginate_by = 10
    
    def get_queryset(self):
        return SupplierPerformance.objects.select_related('supplier').order_by('-evaluation_date')
    
    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context['suppliers'] = Supplier.objects.all().order_by('name')
        
        # Calculate average performance metrics for each supplier
        suppliers_with_performance = []
        for supplier in context['suppliers']:
            performances = SupplierPerformance.objects.filter(supplier=supplier)
            
            if performances.exists():
                avg_performance = performances.aggregate(
                    avg_on_time=Avg('on_time_delivery_rate'),
                    avg_accuracy=Avg('order_accuracy'),
                    avg_quality=Avg('product_quality_score'),
                    evaluation_count=Count('id')
                )
                
                suppliers_with_performance.append({
                    'supplier': supplier,
                    'avg_on_time': avg_performance['avg_on_time'],
                    'avg_accuracy': avg_performance['avg_accuracy'],
                    'avg_quality': avg_performance['avg_quality'],
                    'evaluation_count': avg_performance['evaluation_count'],
                    'overall_score': (
                        avg_performance['avg_on_time'] + 
                        avg_performance['avg_accuracy'] + 
                        (avg_performance['avg_quality'] * 20)  # Convert 1-5 scale to percentage
                    ) / 3 if avg_performance['avg_quality'] else 0
                })
        
        context['suppliers_with_performance'] = sorted(
            suppliers_with_performance, 
            key=lambda x: x['overall_score'] if x['overall_score'] else 0, 
            reverse=True
        )
        
        return context

@login_required
def evaluate_supplier(request):
    """
    Process supplier evaluation form submission
    """
    if request.method == 'POST':
        supplier_id = request.POST.get('supplier')
        on_time_rate = Decimal(request.POST.get('on_time_delivery_rate', 0))
        order_accuracy = Decimal(request.POST.get('order_accuracy', 0))
        quality_score = Decimal(request.POST.get('product_quality_score', 0))
        notes = request.POST.get('notes', '').strip()
        
        try:
            if not supplier_id or on_time_rate < 0 or on_time_rate > 100:
                messages.error(request, 'Please provide valid evaluation data.')
                return redirect('supplier-performance')
            
            supplier = Supplier.objects.get(id=supplier_id)
            
            # Validate scores
            if order_accuracy < 0 or order_accuracy > 100:
                messages.error(request, 'Order accuracy must be between 0 and 100.')
                return redirect('supplier-performance')
            
            if quality_score < 1 or quality_score > 5:
                messages.error(request, 'Quality score must be between 1 and 5.')
                return redirect('supplier-performance')
            
            SupplierPerformance.objects.create(
                supplier=supplier,
                evaluation_date=timezone.now().date(),
                on_time_delivery_rate=on_time_rate,
                order_accuracy=order_accuracy,
                product_quality_score=quality_score,
                notes=notes
            )
            
            messages.success(request, f'Performance evaluation recorded for {supplier.name}')
            
        except Supplier.DoesNotExist:
            messages.error(request, 'Selected supplier not found.')
        except Exception as e:
            messages.error(request, f'Error recording evaluation: {str(e)}')
    
    return redirect('supplier-performance')

@login_required
def track_peak_hours(request):
    """
    Automatically track peak hours based on sales data for the past week
    """
    try:
        start_date = timezone.now().date() - timedelta(days=7)
        end_date = timezone.now().date()
        
        current_date = start_date
        while current_date <= end_date:
            # Analyze sales by hour for each day
            for hour in range(24):
                hour_start = timezone.make_aware(datetime(
                    current_date.year, current_date.month, current_date.day, hour
                ))
                hour_end = hour_start + timedelta(hours=1)
                
                hour_sales = Sale.objects.filter(
                    created_at__range=[hour_start, hour_end]
                ).aggregate(
                    total_sales=Sum('total_amount'),
                    customer_count=Count('id')
                )
                
                if hour_sales['customer_count'] > 0:
                    PeakHour.objects.update_or_create(
                        date=current_date,
                        hour=hour,
                        defaults={
                            'customer_count': hour_sales['customer_count'],
                            'total_sales': hour_sales['total_sales'] or 0
                        }
                    )
                else:
                    # Remove peak hour record if no sales in that hour
                    PeakHour.objects.filter(date=current_date, hour=hour).delete()
            
            current_date += timedelta(days=1)
        
        messages.success(request, 'Peak hours analysis completed for the past week!')
        
    except Exception as e:
        messages.error(request, f'Error analyzing peak hours: {str(e)}')
    
    return redirect('performance-metrics')

@login_required
def operations_dashboard_data(request):
    """
    API endpoint for operations dashboard charts and metrics
    """
    try:
        days = int(request.GET.get('days', 7))
        end_date = timezone.now().date()
        start_date = end_date - timedelta(days=days-1)
        
        # Waste data by day
        waste_data = []
        waste_categories = ['spoilage', 'damage', 'expired', 'other']
        
        for i in range(days):
            date = start_date + timedelta(days=i)
            daily_waste = WasteRecord.objects.filter(
                created_at__date=date
            ).aggregate(total_cost=Sum('cost_value'))['total_cost'] or 0
            
            waste_data.append({
                'date': date.strftime('%Y-%m-%d'),
                'cost': float(daily_waste)
            })
        
        # Waste by category
        category_data = []
        for category in waste_categories:
            category_waste = WasteRecord.objects.filter(
                category=category,
                created_at__date__range=[start_date, end_date]
            ).aggregate(total_cost=Sum('cost_value'))['total_cost'] or 0
            
            category_data.append({
                'category': category,
                'cost': float(category_waste)
            })
        
        return JsonResponse({
            'waste_trend': waste_data,
            'waste_by_category': category_data,
            'status': 'success'
        })
        
    except Exception as e:
        return JsonResponse({
            'status': 'error',
            'message': str(e)
        }, status=500)

@login_required
def staff_productivity_report(request):
    """
    Generate staff productivity report
    """
    start_date = request.GET.get('start_date', '')
    end_date = request.GET.get('end_date', '')
    
    try:
        if start_date:
            start_date_obj = datetime.strptime(start_date, '%Y-%m-%d').date()
        else:
            start_date_obj = timezone.now().date() - timedelta(days=30)
        
        if end_date:
            end_date_obj = datetime.strptime(end_date, '%Y-%m-%d').date()
        else:
            end_date_obj = timezone.now().date()
        
        # Get shifts in date range
        shifts = Shift.objects.filter(
            shift_date__range=[start_date_obj, end_date_obj]
        ).select_related('staff__user')
        
        # Calculate productivity metrics per staff
        staff_metrics = {}
        for shift in shifts:
            staff_id = shift.staff.id
            if staff_id not in staff_metrics:
                staff_metrics[staff_id] = {
                    'staff': shift.staff,
                    'total_hours': 0,
                    'shift_count': 0,
                    'sales_processed': 0
                }
            
            staff_metrics[staff_id]['total_hours'] += float(shift.hours_worked)
            staff_metrics[staff_id]['shift_count'] += 1
        
        # Get sales processed by each staff (assuming cashier field in Sale model)
        sales_by_staff = Sale.objects.filter(
            created_at__date__range=[start_date_obj, end_date_obj],
            cashier__isnull=False
        ).values('cashier').annotate(
            sales_count=Count('id'),
            total_sales=Sum('total_amount')
        )
        
        for sale_data in sales_by_staff:
            try:
                staff = Staff.objects.get(user=sale_data['cashier'])
                if staff.id in staff_metrics:
                    staff_metrics[staff.id]['sales_processed'] = sale_data['sales_count']
                    staff_metrics[staff.id]['sales_amount'] = sale_data['total_sales']
            except Staff.DoesNotExist:
                continue
        
        # Calculate productivity score
        for metrics in staff_metrics.values():
            if metrics['total_hours'] > 0:
                metrics['sales_per_hour'] = metrics.get('sales_amount', 0) / metrics['total_hours']
            else:
                metrics['sales_per_hour'] = 0
        
        context = {
            'staff_metrics': sorted(
                staff_metrics.values(), 
                key=lambda x: x.get('sales_per_hour', 0), 
                reverse=True
            ),
            'start_date': start_date_obj,
            'end_date': end_date_obj,
        }
        
        return render(request, 'operations/staff_productivity_report.html', context)
        
    except Exception as e:
        messages.error(request, f'Error generating productivity report: {str(e)}')
        return redirect('performance-metrics')
        