"""Vues API REST pour le pilotage du cimier (v6.0 Phase 1).

Les vues écrivent des commandes dans /dev/shm/cimier_command.json (lu par
`services.cimier_service`) et lisent l'état publié dans
/dev/shm/cimier_status.json.

Pattern strict des vues `web/hardware/views.py`: réponse 200 sur succès,
503 si l'IPC est indisponible (cimier_service éteint, /dev/shm en lecture
seule, etc.).
"""

from rest_framework import status
from rest_framework.response import Response
from rest_framework.views import APIView

from web.common.cimier_client import cimier_client


def _send_action(action: str, success_message: str) -> Response:
    """Helper commun pour les 3 vues open/close/stop."""
    success = cimier_client.send_command(action)
    if success:
        return Response({"message": success_message, "action": action})
    return Response(
        {"error": "Impossible de communiquer avec Cimier Service"},
        status=status.HTTP_503_SERVICE_UNAVAILABLE,
    )


class OpenView(APIView):
    """POST /api/cimier/open/ — déclenche un cycle d'ouverture du cimier."""

    def post(self, request):
        return _send_action("open", "Ouverture cimier demandée")


class CloseView(APIView):
    """POST /api/cimier/close/ — déclenche un cycle de fermeture du cimier."""

    def post(self, request):
        return _send_action("close", "Fermeture cimier demandée")


class StopView(APIView):
    """POST /api/cimier/stop/ — interrompt un cycle en cours.

    Le cimier_service réagit en libérant la phase courante (boot_poll ou
    cycle_poll), passant en `power_off` puis `cooldown` (sécurité 220V).
    """

    def post(self, request):
        return _send_action("stop", "Arrêt cycle cimier demandé")


class StatusView(APIView):
    """GET /api/cimier/status/ — état courant publié par cimier_service.

    Retourne le payload brut de /dev/shm/cimier_status.json. Si le fichier
    n'existe pas (service éteint), retourne `{"state": "unknown",
    "error": "..."}` avec un statut HTTP 200 pour ne pas spammer la console
    front-end (cohérent avec EncoderView du module hardware).
    """

    def get(self, request):
        return Response(cimier_client.get_status())
