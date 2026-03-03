from django.urls import path
from . import views

urlpatterns = [
    path('waste-tracking/', views.waste_tracking, name='waste-tracking'),
    path('staff-scheduling/', views.StaffSchedulingView.as_view(), name='staff-scheduling'),
    path('add-shift/', views.add_shift, name='add-shift'),
    path('performance-metrics/', views.PerformanceMetricsView.as_view(), name='performance-metrics'),
    path('supplier-performance/', views.SupplierPerformanceView.as_view(), name='supplier-performance'),
    path('evaluate-supplier/', views.evaluate_supplier, name='evaluate-supplier'),
    path('track-peak-hours/', views.track_peak_hours, name='track-peak-hours'),
]