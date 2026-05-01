"""URLs pour l'API cimier (v6.0 Phase 1).

Endpoints:
  POST /api/cimier/open/    -> écrit commande {action:"open"} dans IPC
  POST /api/cimier/close/   -> écrit commande {action:"close"} dans IPC
  POST /api/cimier/stop/    -> écrit commande {action:"stop"} dans IPC
  GET  /api/cimier/status/  -> lit l'état courant publié par cimier_service
"""

from django.urls import path

from . import views

urlpatterns = [
    path("open/", views.OpenView.as_view(), name="cimier-open"),
    path("close/", views.CloseView.as_view(), name="cimier-close"),
    path("stop/", views.StopView.as_view(), name="cimier-stop"),
    path("status/", views.StatusView.as_view(), name="cimier-status"),
]
