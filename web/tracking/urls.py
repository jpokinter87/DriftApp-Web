"""
URLs pour l'API de suivi.
"""
from django.urls import path
from . import views

urlpatterns = [
    path('start/', views.TrackingStartView.as_view(), name='tracking-start'),
    path('stop/', views.TrackingStopView.as_view(), name='tracking-stop'),
    path('status/', views.TrackingStatusView.as_view(), name='tracking-status'),
    path('objects/', views.ObjectListView.as_view(), name='object-list'),
    path('search/', views.ObjectSearchView.as_view(), name='object-search'),
]
