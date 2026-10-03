from django.urls import path
from . import views

urlpatterns = [
    path('pos/', views.point_of_sale, name='point-of-sale'),
    path('sales/', views.SaleListView.as_view(), name='sale-list'),
    path('sales/<int:pk>/', views.SaleDetailView.as_view(), name='sale-detail'),
    path('daily-reports/', views.DailyReportView.as_view(), name='daily-reports'),
    path('customer-analytics/', views.customer_analytics, name='customer-analytics'),
    path('api/sales-data/', views.sales_api_data, name='sales-api-data'),
    path('api/barcode/<str:code>/', views.barcode_lookup, name='barcode-lookup'),
    path('api/sales/search/', views.sale_search_api, name='sale-search-api'),
    path('api/sales/<int:pk>/items/', views.sale_items_api, name='sale-items-api'),

    # Customer Return URLs
    path('returns/', views.CustomerReturnListView.as_view(), name='customer-return-list'),
    path('returns/new/', views.CustomerReturnCreateView.as_view(), name='customer-return-create'),
    path('returns/<int:pk>/', views.CustomerReturnDetailView.as_view(), name='customer-return-detail'),
]