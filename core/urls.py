from django.urls import path

from . import views

urlpatterns = [
    path('settings/', views.SiteSettingsUpdateView.as_view(), name='site-settings'),

    # Users & Roles — the owner hands out the roles here (there is no admin panel)
    path('settings/users/', views.UserListView.as_view(), name='user-list'),
    path('settings/users/add/', views.UserCreateView.as_view(), name='user-create'),
    path('settings/users/<int:pk>/edit/', views.UserUpdateView.as_view(), name='user-update'),

    # Notification bell (low stock / orders)
    path('notifications/', views.NotificationListView.as_view(), name='notifications'),
    path('notifications/open/', views.open_notification, name='notifications-open'),
    path(
        'notifications/mark-all-read/',
        views.mark_all_notifications_read,
        name='notifications-mark-all-read',
    ),
]
