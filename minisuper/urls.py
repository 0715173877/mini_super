from django.contrib import admin
from django.urls import path, include
from django.shortcuts import redirect
from django.contrib.auth import views as auth_views
from . import views
from .reports import *


urlpatterns = [
    path('admin/', admin.site.urls),
    path('', views.dashboard, name='dashboard'),
    path('inventory/', include('inventory.urls')),
    path('sales/', include('sales.urls')),
    path('operations/', include('operations.urls')),
    
    # Authentication URLs - Using Django's built-in views with custom templates
    path('accounts/login/', auth_views.LoginView.as_view(
        template_name='registration/login.html',
        redirect_authenticated_user=True
    ), name='login'),
    
    path('accounts/logout/', auth_views.LogoutView.as_view(
        template_name='registration/logged_out.html'
    ), name='logout'),
    
    # Optional: Password reset URLs
    path('accounts/password_reset/', auth_views.PasswordResetView.as_view(
        template_name='registration/password_reset_form.html'
    ), name='password_reset'),
    
    path('accounts/password_reset/done/', auth_views.PasswordResetDoneView.as_view(
        template_name='registration/password_reset_done.html'
    ), name='password_reset_done'),
    
    path('accounts/reset/<uidb64>/<token>/', auth_views.PasswordResetConfirmView.as_view(
        template_name='registration/password_reset_confirm.html'
    ), name='password_reset_confirm'),
    
    path('accounts/reset/done/', auth_views.PasswordResetCompleteView.as_view(
        template_name='registration/password_reset_complete.html'
    ), name='password_reset_complete'),

    # Reports
    path('reports/sales/', views.SalesReportView.as_view(), name='sales_report_new'),
    path('reports/inventory/', views.InventoryReportView.as_view(), name='inventory_report'),
    path('reports/analytics/', views.AnalyticsView.as_view(), name='analytics'),
    # Export URLs
    path('reports/sales/export/<str:format_type>/', ExportSalesReportView.as_view(), name='export_sales_report'),
    path('reports/inventory/export/<str:format_type>/', ExportInventoryReportView.as_view(), name='export_inventory_report'),
    # path('reports/analytics/export/<str:format_type>/', ExportAnalyticsView.as_view(), name='export_analytics'),
]