"""
URL patterns pour l'app health.
"""

from django.urls import path

from . import views

urlpatterns = [
    path('', views.health_check, name='health_check'),
    path('motor/', views.motor_health, name='motor_health'),
    path('encoder/', views.encoder_health, name='encoder_health'),
    path('ipc/', views.ipc_status, name='ipc_status'),
]