"""
URL configuration for DriftApp Web.
"""
from django.contrib import admin
from django.urls import path, include
from django.views.generic import TemplateView

urlpatterns = [
    path('admin/', admin.site.urls),

    # API REST
    path('api/tracking/', include('tracking.urls')),
    path('api/hardware/', include('hardware.urls')),

    # Interface web principale
    path('', TemplateView.as_view(template_name='dashboard.html'), name='dashboard'),
]
