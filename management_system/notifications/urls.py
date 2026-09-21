from django.urls import path
from . import views

app_name = 'notifications'

urlpatterns = [
    # Notification list and management
    path('', views.notification_list, name='notification_list'),
    path('<int:pk>/', views.notification_detail, name='notification_detail'),

    # Notification actions
    path('<int:pk>/read/', views.mark_as_read, name='mark_as_read'),
    path('<int:pk>/unread/', views.mark_as_unread, name='mark_as_unread'),
    path('<int:pk>/archive/', views.archive_notification, name='archive_notification'),
    path('<int:pk>/unarchive/', views.unarchive_notification, name='unarchive_notification'),
    path('<int:pk>/delete/', views.delete_notification, name='delete_notification'),

    # Bulk actions
    path('mark-all-read/', views.mark_all_read, name='mark_all_read'),

    # Preferences
    path('preferences/', views.notification_preferences, name='notification_preferences'),

    # AJAX endpoints
    path('api/unread-count/', views.get_unread_count, name='get_unread_count'),
]