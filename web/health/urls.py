"""
URL patterns pour l'app health.
"""

from django.urls import path
from django.views.generic import TemplateView

from . import views

urlpatterns = [
    # API endpoints
    path('', views.health_check, name='health_check'),
    path('motor/', views.motor_health, name='motor_health'),
    path('encoder/', views.encoder_health, name='encoder_health'),
    path('ipc/', views.ipc_status, name='ipc_status'),
    path('diagnostic/', views.diagnostic, name='diagnostic_api'),

    # Endpoints de mise à jour
    path('update/check/', views.check_update, name='update_check'),
    path('update/apply/', views.apply_update, name='update_apply'),

    # Page HTML de diagnostic système
    path('system/', TemplateView.as_view(template_name='system.html'), name='system_page'),
]