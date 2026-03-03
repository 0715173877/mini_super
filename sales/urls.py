from django.urls import path
from . import views

urlpatterns = [
    path('pos/', views.point_of_sale, name='point-of-sale'),
    path('sales/', views.SaleListView.as_view(), name='sale-list'),
    path('sales/<int:pk>/', views.SaleDetailView.as_view(), name='sale-detail'),
    path('daily-reports/', views.DailyReportView.as_view(), name='daily-reports'),
    path('customer-analytics/', views.customer_analytics, name='customer-analytics'),
    path('api/sales-data/', views.sales_api_data, name='sales-api-data'),
]