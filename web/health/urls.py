"""
URL patterns pour l'app health.
"""

from django.urls import path

from . import views

urlpatterns = [
    path('', views.health_check, name='health_check'),
    path('update/check/', views.check_update, name='update_check'),
    path('update/apply/', views.apply_update, name='update_apply'),
]
