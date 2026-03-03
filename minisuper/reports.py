# views.py
import csv
import io
from datetime import datetime
from django.http import HttpResponse, JsonResponse
from django.views import View
from django.template.loader import render_to_string
from reportlab.pdfgen import canvas
from reportlab.lib.pagesizes import letter, A4
from reportlab.platypus import SimpleDocTemplate, Table, TableStyle, Paragraph
from reportlab.lib.styles import getSampleStyleSheet
from reportlab.lib import colors
import openpyxl
from openpyxl.styles import Font, Alignment
from inventory.models import *
from sales.models import *
from django.db.models import Sum, Count, Q, F
from django.utils import timezone

class ExportSalesReportView(View):
    
    def get(self, request, format_type):
        # Get filter parameters
        date_range = request.GET.get('date_range', 'month')
        start_date = request.GET.get('start_date')
        end_date = request.GET.get('end_date')
        
        # Your existing sales report logic here
        sales_data = self.get_sales_data(date_range, start_date, end_date)
        
        if format_type == 'pdf':
            return self.export_pdf(sales_data, date_range)
        elif format_type == 'excel':
            return self.export_excel(sales_data, date_range)
        elif format_type == 'csv':
            return self.export_csv(sales_data, date_range)
        else:
            return JsonResponse({'error': 'Invalid format'}, status=400)
    
    def get_sales_data(self, date_range, start_date, end_date):
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
        
        context = {
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
        }
        return context
        
    def export_pdf(self, sales_data, date_range):
        response = HttpResponse(content_type='application/pdf')
        filename = f"sales_report_{datetime.now().strftime('%Y%m%d')}.pdf"
        response['Content-Disposition'] = f'attachment; filename="{filename}"'
        
        doc = SimpleDocTemplate(response, pagesize=A4)
        elements = []
        
        # Title
        styles = getSampleStyleSheet()
        title = Paragraph(f"Sales Report - {date_range.title()}", styles['Title'])
        elements.append(title)
        
        # Summary Data
        summary_data = [
            ['Total Sales', f"{sales_data['total_sales']:,}"],
            ['Total Revenue', f"${sales_data['total_revenue']:,.2f}"],
            ['Items Sold', f"{sales_data['total_items_sold']:,}"],
            ['Average Sale', f"${sales_data['average_sale']:,.2f}"],
        ]
        
        summary_table = Table(summary_data, colWidths=[200, 100])
        summary_table.setStyle(TableStyle([
            ('BACKGROUND', (0, 0), (-1, 0), colors.grey),
            ('TEXTCOLOR', (0, 0), (-1, 0), colors.whitesmoke),
            ('ALIGN', (0, 0), (-1, -1), 'LEFT'),
            ('FONTNAME', (0, 0), (-1, 0), 'Helvetica-Bold'),
            ('FONTSIZE', (0, 0), (-1, -1), 10),
            ('BOTTOMPADDING', (0, 0), (-1, 0), 12),
            ('BACKGROUND', (0, 1), (-1, -1), colors.beige),
            ('GRID', (0, 0), (-1, -1), 1, colors.black)
        ]))
        elements.append(summary_table)
        
        # Sales Details Table
        if sales_data.get('daily_sales'):
            elements.append(Paragraph("Daily Sales", styles['Heading2']))
            
            table_data = [['Date', 'Transactions', 'Revenue']]
            for day in sales_data['daily_sales']:
                table_data.append([
                    day['date'],
                    str(day['daily_count']),
                    f"${day['daily_total']:,.2f}"
                ])
            
            sales_table = Table(table_data, colWidths=[150, 100, 100])
            sales_table.setStyle(TableStyle([
                ('BACKGROUND', (0, 0), (-1, 0), colors.grey),
                ('TEXTCOLOR', (0, 0), (-1, 0), colors.whitesmoke),
                ('ALIGN', (0, 0), (-1, -1), 'CENTER'),
                ('FONTNAME', (0, 0), (-1, 0), 'Helvetica-Bold'),
                ('FONTSIZE', (0, 0), (-1, -1), 8),
                ('BOTTOMPADDING', (0, 0), (-1, 0), 12),
                ('BACKGROUND', (0, 1), (-1, -1), colors.beige),
                ('GRID', (0, 0), (-1, -1), 1, colors.black)
            ]))
            elements.append(sales_table)
        
        doc.build(elements)
        return response
    
    def export_excel(self, sales_data, date_range):
        response = HttpResponse(content_type='application/vnd.openxmlformats-officedocument.spreadsheetml.sheet')
        filename = f"sales_report_{datetime.now().strftime('%Y%m%d')}.xlsx"
        response['Content-Disposition'] = f'attachment; filename="{filename}"'
        
        workbook = openpyxl.Workbook()
        worksheet = workbook.active
        worksheet.title = f"Sales Report {date_range.title()}"
        
        # Title
        worksheet.merge_cells('A1:D1')
        title_cell = worksheet['A1']
        title_cell.value = f"Sales Report - {date_range.title()}"
        title_cell.font = Font(size=16, bold=True)
        title_cell.alignment = Alignment(horizontal='center')
        
        # Summary Section
        worksheet['A3'] = 'Summary'
        worksheet['A3'].font = Font(bold=True)
        
        summary_data = [
            ['Total Sales', sales_data['total_sales']],
            ['Total Revenue', sales_data['total_revenue']],
            ['Items Sold', sales_data['total_items_sold']],
            ['Average Sale', sales_data['average_sale']],
        ]
        
        for i, (label, value) in enumerate(summary_data, start=4):
            worksheet[f'A{i}'] = label
            worksheet[f'B{i}'] = value
            if 'Revenue' in label or 'Sale' in label:
                worksheet[f'B{i}'].number_format = '"$"#,##0.00'
        
        # Daily Sales Data
        if sales_data.get('daily_sales'):
            worksheet['A9'] = 'Daily Sales'
            worksheet['A9'].font = Font(bold=True)
            
            headers = ['Date', 'Transactions', 'Revenue']
            for col, header in enumerate(headers, start=1):
                cell = worksheet.cell(row=10, column=col)
                cell.value = header
                cell.font = Font(bold=True)
            
            for row, day in enumerate(sales_data['daily_sales'], start=11):
                worksheet.cell(row=row, column=1).value = day['date']
                worksheet.cell(row=row, column=2).value = day['daily_count']
                worksheet.cell(row=row, column=3).value = day['daily_total']
                worksheet.cell(row=row, column=3).number_format = '"$"#,##0.00'
        
        # Auto-adjust column widths
        for column in worksheet.columns:
            max_length = 0
            column_letter = column[0].column_letter
            for cell in column:
                try:
                    if len(str(cell.value)) > max_length:
                        max_length = len(str(cell.value))
                except:
                    pass
            adjusted_width = (max_length + 2)
            worksheet.column_dimensions[column_letter].width = adjusted_width
        
        workbook.save(response)
        return response
    
    def export_csv(self, sales_data, date_range):
        response = HttpResponse(content_type='text/csv')
        filename = f"sales_report_{datetime.now().strftime('%Y%m%d')}.csv"
        response['Content-Disposition'] = f'attachment; filename="{filename}"'
        
        writer = csv.writer(response)
        
        # Header
        writer.writerow([f"Sales Report - {date_range.title()}"])
        writer.writerow([])
        
        # Summary
        writer.writerow(['Summary'])
        writer.writerow(['Total Sales', sales_data['total_sales']])
        writer.writerow(['Total Revenue', f"${sales_data['total_revenue']:,.2f}"])
        writer.writerow(['Items Sold', sales_data['total_items_sold']])
        writer.writerow(['Average Sale', f"${sales_data['average_sale']:,.2f}"])
        writer.writerow([])
        
        # Daily Sales
        if sales_data.get('daily_sales'):
            writer.writerow(['Daily Sales'])
            writer.writerow(['Date', 'Transactions', 'Revenue'])
            for day in sales_data['daily_sales']:
                writer.writerow([
                    day['date'],
                    day['daily_count'],
                    f"${day['daily_total']:,.2f}"
                ])
        
        return response

class ExportInventoryReportView(View):
    
    def get(self, request, format_type):
        # Get filter parameters
        stock_status = request.GET.get('stock_status')
        category = request.GET.get('category')
        
        # Your existing inventory data logic
        inventory_data = self.get_inventory_data(stock_status, category)
        
        if format_type == 'pdf':
            return self.export_pdf(inventory_data)
        elif format_type == 'excel':
            return self.export_excel(inventory_data)
        elif format_type == 'csv':
            return self.export_csv(inventory_data)
        else:
            return JsonResponse({'error': 'Invalid format'}, status=400)
    
    def get_inventory_data(self, stock_status, category):
        # Inventory summary
        products = Product.objects.all()
        total_products = Product.objects.count()
        total_value = Product.objects.aggregate(
            total=Sum(F('current_stock') * F('cost_price'))
        )['total'] or 0
        
        low_stock_count = Product.objects.filter(
            current_stock__lte=F('min_stock_level')
        ).count()
        
        out_of_stock_count = Product.objects.filter(current_stock=0).count()
        
        context = {
            'products':products,
            'categories': Category.objects.all(),
            'total_products': total_products,
            'total_value': total_value,
            'low_stock_count': low_stock_count,
            'out_of_stock_count': out_of_stock_count,
        }
        return context
    
    def export_pdf(self, inventory_data):
        response = HttpResponse(content_type='application/pdf')
        filename = f"inventory_report_{datetime.now().strftime('%Y%m%d')}.pdf"
        response['Content-Disposition'] = f'attachment; filename="{filename}"'
        
        doc = SimpleDocTemplate(response, pagesize=A4)
        elements = []
        
        styles = getSampleStyleSheet()
        title = Paragraph("Inventory Report", styles['Title'])
        elements.append(title)
        
        # Inventory Table
        table_data = [['SKU', 'Product Name', 'Category', 'Stock', 'Price', 'Status']]
        
        for product in inventory_data['products']:
            status = "In Stock"
            if product.current_stock == 0:
                status = "Out of Stock"
            elif product.current_stock <= product.min_stock_level:
                status = "Low Stock"
            
            table_data.append([
                product.sku,
                product.name,
                product.category.name,
                str(product.current_stock),
                f"${product.selling_price:.2f}",
                status
            ])
        
        inventory_table = Table(table_data, colWidths=[80, 150, 100, 60, 60, 80])
        inventory_table.setStyle(TableStyle([
            ('BACKGROUND', (0, 0), (-1, 0), colors.grey),
            ('TEXTCOLOR', (0, 0), (-1, 0), colors.whitesmoke),
            ('ALIGN', (0, 0), (-1, -1), 'CENTER'),
            ('FONTNAME', (0, 0), (-1, 0), 'Helvetica-Bold'),
            ('FONTSIZE', (0, 0), (-1, -1), 8),
            ('BOTTOMPADDING', (0, 0), (-1, 0), 12),
            ('BACKGROUND', (0, 1), (-1, -1), colors.beige),
            ('GRID', (0, 0), (-1, -1), 1, colors.black)
        ]))
        elements.append(inventory_table)
        
        doc.build(elements)
        return response
    
    def export_excel(self, inventory_data):
        response = HttpResponse(content_type='application/vnd.openxmlformats-officedocument.spreadsheetml.sheet')
        filename = f"inventory_report_{datetime.now().strftime('%Y%m%d')}.xlsx"
        response['Content-Disposition'] = f'attachment; filename="{filename}"'
        
        workbook = openpyxl.Workbook()
        worksheet = workbook.active
        worksheet.title = "Inventory Report"
        
        # Headers
        headers = ['SKU', 'Product Name', 'Category', 'Current Stock', 'Min Level', 
                  'Max Level', 'Cost Price', 'Selling Price', 'Status']
        
        for col, header in enumerate(headers, start=1):
            cell = worksheet.cell(row=1, column=col)
            cell.value = header
            cell.font = Font(bold=True)
        
        # Data
        for row, product in enumerate(inventory_data['products'], start=2):
            status = "In Stock"
            if product.current_stock == 0:
                status = "Out of Stock"
            elif product.current_stock <= product.min_stock_level:
                status = "Low Stock"
            
            worksheet.cell(row=row, column=1).value = product.sku
            worksheet.cell(row=row, column=2).value = product.name
            worksheet.cell(row=row, column=3).value = product.category.name
            worksheet.cell(row=row, column=4).value = product.current_stock
            worksheet.cell(row=row, column=5).value = product.min_stock_level
            worksheet.cell(row=row, column=6).value = product.max_stock_level
            worksheet.cell(row=row, column=7).value = float(product.cost_price)
            worksheet.cell(row=row, column=8).value = float(product.selling_price)
            worksheet.cell(row=row, column=9).value = status
            
            # Format currency columns
            worksheet.cell(row=row, column=7).number_format = '"$"#,##0.00'
            worksheet.cell(row=row, column=8).number_format = '"$"#,##0.00'
        
        # Auto-adjust column widths
        for column in worksheet.columns:
            max_length = 0
            column_letter = column[0].column_letter
            for cell in column:
                try:
                    if len(str(cell.value)) > max_length:
                        max_length = len(str(cell.value))
                except:
                    pass
            adjusted_width = (max_length + 2)
            worksheet.column_dimensions[column_letter].width = adjusted_width
        
        workbook.save(response)
        return response
    
    def export_csv(self, inventory_data):
        response = HttpResponse(content_type='text/csv')
        filename = f"inventory_report_{datetime.now().strftime('%Y%m%d')}.csv"
        response['Content-Disposition'] = f'attachment; filename="{filename}"'
        
        writer = csv.writer(response)
        
        # Headers
        writer.writerow(['SKU', 'Product Name', 'Category', 'Current Stock', 
                        'Min Level', 'Max Level', 'Cost Price', 'Selling Price', 'Status'])
        
        # Data
        for product in inventory_data['products']:
            status = "In Stock"
            if product.current_stock == 0:
                status = "Out of Stock"
            elif product.current_stock <= product.min_stock_level:
                status = "Low Stock"
            
            writer.writerow([
                product.sku,
                product.name,
                product.category.name,
                product.current_stock,
                product.min_stock_level,
                product.max_stock_level,
                f"${product.cost_price:.2f}",
                f"${product.selling_price:.2f}",
                status
            ])
        
        return response