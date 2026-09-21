from django.urls import path
from . import views

app_name = 'crm'

urlpatterns = [
    path('', views.index, name='index'),
    path('contacts/', views.contact_list, name='contact_list'),
    path('contacts/new/', views.contact_create, name='contact_create'),
    path('contacts/<int:pk>/', views.contact_detail, name='contact_detail'),   # ← add this
    path('contacts/<int:pk>/edit/', views.contact_edit, name='contact_edit'),
    path('contacts/<int:pk>/delete/', views.contact_delete, name='contact_delete'),
    path('contacts/<int:pk>/notes/add/', views.note_add, name='note_add'),
    path('notes/<int:pk>/delete/', views.note_delete, name='note_delete'),
    path('opportunities/', views.opportunity_list, name='opportunity_list'),
    path('opportunities/new/', views.opportunity_create, name='opportunity_create'),
    path('opportunities/<int:pk>/edit/', views.opportunity_edit, name='opportunity_edit'),
    path('opportunities/<int:pk>/delete/', views.opportunity_delete, name='opportunity_delete'),
    path('opportunities/<int:pk>/advance/', views.opportunity_advance_stage, name='opportunity_advance'),
    path('opportunities/<int:pk>/mark-invoiced/', views.opportunity_mark_invoiced, name='opportunity_mark_invoiced'),
    path('opportunities/<int:pk>/mark-paid/', views.opportunity_mark_paid, name='opportunity_mark_paid'),
    path('pipeline/', views.pipeline, name='pipeline'),
]