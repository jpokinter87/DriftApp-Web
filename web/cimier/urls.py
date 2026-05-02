"""URLs pour l'API cimier (v6.0 Phase 1 + Phase 4).

Endpoints:
  POST /api/cimier/open/             -> écrit commande {action:"open"} dans IPC
  POST /api/cimier/close/            -> écrit commande {action:"close"} dans IPC
  POST /api/cimier/stop/             -> écrit commande {action:"stop"} dans IPC
  GET  /api/cimier/status/           -> lit l'état courant publié par cimier_service
  GET  /api/cimier/automation/       -> mode + next_open_at + next_close_at (Phase 4)
  POST /api/cimier/automation/       -> persiste le mode dans data/config.json (Phase 4)
  POST /api/cimier/parking-session/  -> séquence atomique tracking_stop + GOTO + close (Phase 4)
"""

from django.urls import path

from . import views

urlpatterns = [
    path("open/", views.OpenView.as_view(), name="cimier-open"),
    path("close/", views.CloseView.as_view(), name="cimier-close"),
    path("stop/", views.StopView.as_view(), name="cimier-stop"),
    path("status/", views.StatusView.as_view(), name="cimier-status"),
    path("automation/", views.AutomationView.as_view(), name="cimier-automation"),
    path("parking-session/", views.ParkingSessionView.as_view(), name="cimier-parking-session"),
]
