"""URLs de l'app configuration."""

from django.urls import path

from . import views

urlpatterns = [
    path("", views.configuration_view, name="configuration-api"),
]
