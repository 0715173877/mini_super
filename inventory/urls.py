from django.urls import path
from . import views

urlpatterns = [
    # Product URLs
    path('', views.ProductListView.as_view(), name='product-list'),
    path('product/<int:pk>/', views.ProductDetailView.as_view(), name='product-detail'),
    path('product/add/', views.ProductCreateView.as_view(), name='product-create'),
    path('product/<int:pk>/edit/', views.ProductUpdateView.as_view(), name='product-update'),
    path('product/<int:pk>/delete/', views.ProductDeleteView.as_view(), name='product-delete'),
    path('low-stock/', views.LowStockView.as_view(), name='low-stock'),
    
    # Category URLs
    path('categories/', views.CategoryListView.as_view(), name='category-list'),
    path('category/add/', views.CategoryCreateView.as_view(), name='category-create'),
    path('category/<int:pk>/edit/', views.CategoryUpdateView.as_view(), name='category-update'),
    
    # Supplier URLs
    path('suppliers/', views.SupplierListView.as_view(), name='supplier-list'),
    path('supplier/add/', views.SupplierCreateView.as_view(), name='supplier-create'),
    path('supplier/<int:pk>/edit/', views.SupplierUpdateView.as_view(), name='supplier-update'),
    
    # Purchase Order URLs
    path('purchase-orders/', views.PurchaseOrderListView.as_view(), name='purchase-order-list'),
    path('purchase-order/add/', views.PurchaseOrderCreateView.as_view(), name='purchase-order-create'),
    path('purchase-order/<int:pk>/receive/', views.receive_purchase_order, name='purchase-order-receive'),
    
    # Stock Movement URLs
    path('stock-movements/', views.StockMovementListView.as_view(), name='stock-movement-list'),
    path('product/<int:product_id>/adjust-stock/', views.adjust_stock, name='adjust-stock'),

      # Purchase Order URLs
    path('purchase-orders/', views.PurchaseOrderListView.as_view(), name='purchase-order-list'),
    path('purchase-order/add/', views.PurchaseOrderCreateView.as_view(), name='purchase-order-create'),
    path('purchase-order/<int:pk>/', views.PurchaseOrderDetailView.as_view(), name='purchase-order-detail'),
    path('purchase-order/<int:pk>/edit/', views.PurchaseOrderUpdateView.as_view(), name='purchase-order-update'),
    path('purchase-order/<int:pk>/delete/', views.PurchaseOrderDeleteView.as_view(), name='purchase-order-delete'),
    path('purchase-order/<int:pk>/mark-ordered/', views.mark_as_ordered, name='purchase-order-mark-ordered'),
    path('purchase-order/<int:pk>/receive/', views.receive_purchase_order, name='purchase-order-receive'),
    path('purchase-order/<int:pk>/cancel/', views.cancel_purchase_order, name='purchase-order-cancel'),
]