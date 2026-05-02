"""Vues API REST pour le pilotage du cimier (v6.0 Phase 1 + Phase 4).

Les vues écrivent des commandes dans /dev/shm/cimier_command.json (lu par
`services.cimier_service`) et lisent l'état publié dans
/dev/shm/cimier_status.json.

Pattern strict des vues `web/hardware/views.py`: réponse 200 sur succès,
503 si l'IPC est indisponible (cimier_service éteint, /dev/shm en lecture
seule, etc.).

Phase 4 (sub-plan v6.0-04-01) ajoute :
- `AutomationView` : GET retourne le mode courant + next_open_at + next_close_at
  (depuis cimier_status.json). POST persiste un nouveau mode dans data/config.json
  (atomique). `restart_required` indique que cimier_service doit être redémarré
  pour prise en compte (lecture config au boot uniquement, pas de hot-reload).
- `ParkingSessionView` : POST atomique = `tracking_stop` motor IPC + GOTO
  `parking_target_azimuth_deg` + `close` cimier IPC. Best-effort (les
  3 commandes sont émises même si l'une échoue, priorité protection).
"""

import json
import os
import tempfile
from pathlib import Path

from django.conf import settings
from rest_framework import status
from rest_framework.response import Response
from rest_framework.views import APIView

from web.common.cimier_client import cimier_client


VALID_AUTOMATION_MODES = ("manual", "semi", "full")


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


class AutomationView(APIView):
    """v6.0 Phase 4 — GET/POST `cimier.automation.mode`.

    GET : retourne `{mode, next_open_at, next_close_at}` extraits de
    cimier_status.json (publié par cimier_service tick scheduler).
    POST : persiste `mode` ∈ {manual, semi, full} dans data/config.json.
    """

    def get(self, request):
        status_payload = cimier_client.get_status()
        return Response(
            {
                "mode": status_payload.get("mode", "manual"),
                "next_open_at": status_payload.get("next_open_at"),
                "next_close_at": status_payload.get("next_close_at"),
            }
        )

    def post(self, request):
        mode = request.data.get("mode")
        if mode not in VALID_AUTOMATION_MODES:
            return Response(
                {"error": "mode invalide", "valid": list(VALID_AUTOMATION_MODES)},
                status=status.HTTP_400_BAD_REQUEST,
            )
        config_path = Path(settings.DRIFTAPP_CONFIG)
        try:
            with open(config_path, "r") as f:
                cfg = json.load(f)
        except (IOError, json.JSONDecodeError) as exc:
            return Response(
                {"error": f"Lecture config.json impossible : {exc}"},
                status=status.HTTP_503_SERVICE_UNAVAILABLE,
            )
        cimier_section = cfg.setdefault("cimier", {})
        automation_section = cimier_section.setdefault("automation", {})
        automation_section["mode"] = mode
        # Nettoyage : on retire la clé legacy `enabled` si présente — `mode`
        # est désormais la source de vérité (la rétro-compat reste côté lecture
        # parser, mais on évite de la perpétuer en écriture).
        automation_section.pop("enabled", None)
        try:
            self._write_atomic(config_path, cfg)
        except OSError as exc:
            return Response(
                {"error": f"Écriture config.json impossible : {exc}"},
                status=status.HTTP_503_SERVICE_UNAVAILABLE,
            )
        return Response(
            {"mode": mode, "applied": True, "restart_required": True}
        )

    @staticmethod
    def _write_atomic(target: Path, data: dict) -> None:
        """Écrit `data` JSON dans `target` de manière atomique (tmp+rename)."""
        target = Path(target)
        target.parent.mkdir(parents=True, exist_ok=True)
        # NamedTemporaryFile dans le même dir → os.replace atomique sur POSIX.
        with tempfile.NamedTemporaryFile(
            mode="w", dir=str(target.parent), delete=False, suffix=".tmp", encoding="utf-8"
        ) as tmp:
            json.dump(data, tmp, indent=2, ensure_ascii=False)
            tmp.flush()
            os.fsync(tmp.fileno())
            tmp_path = Path(tmp.name)
        os.replace(tmp_path, target)


class ParkingSessionView(APIView):
    """v6.0 Phase 4 — POST séquence parking session manuelle (1-clic).

    Émet 3 commandes IPC séquentielles (best-effort, pas de rollback) :
      1. tracking_stop motor
      2. goto parking_target_azimuth_deg motor (lit data/config.json,
         défaut 45° si absent)
      3. close cimier

    Retourne 200 si tout OK, 503 si la commande cimier (la plus critique
    pour la protection) a échoué. Les commandes motor sont always-best-effort.
    """

    def post(self, request):
        from core.config.config_loader import load_config
        from services.motor_ipc_writer import MotorIpcWriter

        try:
            cfg = load_config(Path(settings.DRIFTAPP_CONFIG))
            parking_deg = cfg.cimier.automation.parking_target_azimuth_deg
        except (IOError, OSError, ValueError):
            parking_deg = 45.0

        motor_writer = MotorIpcWriter(
            command_file=Path(settings.MOTOR_SERVICE_IPC["COMMAND_FILE"])
        )
        tracking_stopped = motor_writer.send_tracking_stop()
        goto_45_sent = motor_writer.send_goto(parking_deg)
        cimier_close_sent = cimier_client.send_command("close")

        all_ok = tracking_stopped and goto_45_sent and cimier_close_sent
        body = {
            "applied": all_ok,
            "tracking_stopped": tracking_stopped,
            "goto_45_sent": goto_45_sent,
            "cimier_close_sent": cimier_close_sent,
            "parking_target_deg": parking_deg,
        }
        if all_ok:
            return Response(body)
        body["error"] = "Une ou plusieurs commandes IPC ont échoué"
        return Response(body, status=status.HTTP_503_SERVICE_UNAVAILABLE)
