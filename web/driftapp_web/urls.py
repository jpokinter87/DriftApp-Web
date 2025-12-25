"""
URL configuration for DriftApp Web.
"""
from django.contrib import admin
from django.http import HttpResponse
from django.urls import path, include
from django.views.generic import TemplateView

urlpatterns = [
    path('admin/', admin.site.urls),

    # API REST
    path('api/tracking/', include('tracking.urls')),
    path('api/hardware/', include('hardware.urls')),
    path('api/health/', include('health.urls')),

    # Interface web principale
    path('', TemplateView.as_view(template_name='dashboard.html'), name='dashboard'),

    # Favicon (évite les 404 dans les logs)
    path('favicon.ico', lambda r: HttpResponse(status=204)),
]
