from django.urls import path
from . import views

app_name = 'core'

urlpatterns = [
    path('dashboard/', views.dashboard, name='dashboard'),
    path('platform/', views.platform_dashboard, name='platform_dashboard'),
]