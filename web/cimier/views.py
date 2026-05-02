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
import time
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

    GET : retourne `{mode, service_mode, mode_apply_pending, service_running,
           next_open_at, next_close_at}`.
        - `mode` : choix utilisateur **persistant** lu directement dans
          data/config.json (source de vérité du choix UI). C'est le champ
          consommé par le sélecteur dashboard et la carte page Système.
        - `service_mode` : ce que le `cimier_service` a actuellement chargé
          en mémoire (publié dans cimier_status.json).
        - `service_running` : True si cimier_service est vivant
          (cimier_status.json présent ET last_update < 90 s). Permet à l'UI de
          masquer l'indicateur « application en cours » quand le service est
          juste arrêté (typiquement dev avec cimier.enabled=false).
        - `mode_apply_pending` : True si `mode != service_mode` ET le service
          est vivant. Si le service est down, ce champ est False (rien à
          attendre, le hot-reload ne se fera jamais).
        - `next_open_at` / `next_close_at` : prochains triggers calculés par
          le scheduler du service (en mémoire), lus du status.

    POST : persiste `mode` ∈ {manual, semi, full} dans data/config.json.
    Le `cimier_service` rechargera ce mode au prochain tick scheduler
    (max 60s) sans nécessiter de redémarrage.
    """

    # Seuil au-delà duquel cimier_status.json est considéré stale → service
    # probablement arrêté (typiquement dev avec cimier.enabled=false, ou crash).
    _SERVICE_STALE_THRESHOLD_SECONDS = 90

    def get(self, request):
        # Source de vérité utilisateur : data/config.json.
        configured_mode = self._read_configured_mode()
        # Vue runtime du service (peut différer si pas encore propagé par tick).
        status_payload = cimier_client.get_status()
        service_mode = status_payload.get("mode", "manual")
        service_running = self._is_service_running(status_payload)
        # `mode_apply_pending` n'a de sens que si le service est vivant
        # (sinon le hot-reload ne se fera jamais → ne pas afficher le hint).
        apply_pending = service_running and (configured_mode != service_mode)

        # Triggers : priorité au status (calculé live par cimier_service),
        # fallback sur calcul Django on-demand si le service n'est pas vivant
        # (typiquement dev avec cimier.enabled=false). Permet de vérifier la
        # cohérence avec les éphémérides solaires sans avoir cimier_service.
        next_open_iso = status_payload.get("next_open_at")
        next_close_iso = status_payload.get("next_close_at")
        if not service_running:
            fallback = self._compute_next_triggers_fallback(configured_mode)
            if fallback is not None:
                next_open_iso, next_close_iso = fallback

        response = Response(
            {
                "mode": configured_mode,
                "service_mode": service_mode,
                "service_running": service_running,
                "mode_apply_pending": apply_pending,
                "next_open_at": next_open_iso,
                "next_close_at": next_close_iso,
            }
        )
        # Empêche le cache HTTP : la fraîcheur du calcul change toutes les minutes
        # (cache backend interne TTL 60s) — on veut que le navigateur re-questionne
        # à chaque refresh sans intercepter sa réponse précédente.
        response["Cache-Control"] = "no-store, must-revalidate"
        return response

    # Cache module-level pour le fallback compute_next_triggers (TTL 60s).
    # Évite le coût astropy de ~30s à chaque refresh UI 2s côté Système.
    # Clé : mode courant. Valeur : (timestamp_calc, (open_iso, close_iso)).
    _trigger_cache_ttl_s = 60
    _trigger_cache: dict = {}

    @classmethod
    def _compute_next_triggers_fallback(cls, mode: str):
        """Calcule next_open_at / next_close_at directement depuis la config Django,
        sans dépendre de cimier_service. Utilisé en dev (service arrêté).

        Returns:
            (open_iso, close_iso) ou None si calcul impossible.
        """
        from datetime import datetime, timezone
        import time as _time

        # Cache hit (TTL 60s) ?
        cached = cls._trigger_cache.get(mode)
        if cached is not None:
            cached_ts, cached_value = cached
            if (_time.time() - cached_ts) < cls._trigger_cache_ttl_s:
                return cached_value

        try:
            from core.config.config_loader import load_config
            from core.hardware.weather_provider import NoopWeatherProvider
            from services.cimier_scheduler import CimierScheduler

            cfg = load_config(Path(settings.DRIFTAPP_CONFIG))
            # Surcharge le mode in-memory pour refléter le choix UI courant
            # (et pas le mode persisté qui peut être différent).
            cfg.cimier.automation.mode = mode

            # Stubs minimaux : compute_next_triggers n'utilise ni cimier_ipc ni motor_ipc.
            class _NoopIpc:
                def write_command(self, *a, **kw): pass
                def send_goto(self, *a, **kw): return True
                def send_jog(self, *a, **kw): return True
                def send_tracking_stop(self, *a, **kw): return True
                def send_stop(self, *a, **kw): return True

            scheduler = CimierScheduler(
                automation_config=cfg.cimier.automation,
                site_config=cfg.site,
                weather_provider=NoopWeatherProvider(),
                cimier_ipc=_NoopIpc(),
                motor_ipc=_NoopIpc(),
            )
            next_open, next_close = scheduler.compute_next_triggers(
                datetime.now(timezone.utc)
            )
            value = (
                next_open.isoformat() if next_open else None,
                next_close.isoformat() if next_close else None,
            )
            cls._trigger_cache[mode] = (_time.time(), value)
            return value
        except Exception as exc:
            # Log discret, pas critique (l'UI affichera juste '--').
            import logging
            logging.getLogger(__name__).warning(
                "compute_next_triggers_fallback failed: %s", exc
            )
            return None

    @classmethod
    def _is_service_running(cls, status_payload: dict) -> bool:
        """Détecte si cimier_service est vivant via la fraîcheur de last_update.

        Critère : `last_update` ISO 8601 présent ET écart < 90 s. Si absent ou
        trop vieux, le service est considéré arrêté.

        Important : les services écrivent `last_update = datetime.now().isoformat()`
        donc en HEURE LOCALE naive (cf. cimier_ipc_manager.py:118 et
        motor_service.py:393). On compare donc naive vs naive (heure locale)
        pour éviter une dérive de la timezone (ex: CEST UTC+2 inverserait
        artificiellement le signe de la diff et le check < 90 s passerait
        toujours, fix bug 2026-05-02 21:30).
        """
        last_update_iso = status_payload.get("last_update")
        if not last_update_iso:
            return False
        try:
            from datetime import datetime
            dt = datetime.fromisoformat(last_update_iso)
            # Si le timestamp est tz-aware (cas atypique), on le convertit en
            # naive local pour comparer cohéremment avec datetime.now() naive.
            if dt.tzinfo is not None:
                dt = dt.astimezone().replace(tzinfo=None)
            now = datetime.now()
            elapsed = (now - dt).total_seconds()
            return 0 <= elapsed < cls._SERVICE_STALE_THRESHOLD_SECONDS
        except (ValueError, TypeError):
            return False

    @staticmethod
    def _read_configured_mode() -> str:
        """Lit `cimier.automation.mode` depuis data/config.json, fallback `manual`.

        Gère la rétro-compat lecture-seule de la clé legacy `enabled` (true → full,
        false/absent → manual), cohérent avec config_loader._resolve_automation_mode
        livré en 04-01.
        """
        config_path = Path(settings.DRIFTAPP_CONFIG)
        try:
            with open(config_path, "r") as f:
                cfg = json.load(f)
        except (IOError, json.JSONDecodeError):
            return "manual"
        automation = cfg.get("cimier", {}).get("automation", {})
        explicit = automation.get("mode")
        if explicit in VALID_AUTOMATION_MODES:
            return explicit
        # Rétro-compat lecture : `enabled` legacy.
        legacy_enabled = automation.get("enabled")
        if legacy_enabled is True:
            return "full"
        return "manual"

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

    # Délai entre les writes IPC successifs vers motor_command.json (un seul slot,
    # commandes consommées 1×/tick à 20 Hz). Sans cette pause, send_tracking_stop()
    # est immédiatement écrasé par send_goto() dans le même fichier et motor_service
    # ne consomme que la dernière commande, laissant le tracking actif à GOTO ignoré.
    # Fix smoke 2026-05-02 (parking restant à 215° au lieu d'aller à 45°).
    # 0.2 s = 4 ticks motor_service → marge confortable pour consommer + agir.
    _MOTOR_IPC_INTER_COMMAND_DELAY_S = 0.2

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
        # Étape 1 : tracking_stop. Laisse motor_service consommer + couper le
        # thread tracking avant la prochaine commande.
        tracking_stopped = motor_writer.send_tracking_stop()
        time.sleep(self._MOTOR_IPC_INTER_COMMAND_DELAY_S)
        # Étape 2 : GOTO parking. Va passer motor en initializing/idle puis
        # rejoindre la cible (45° par défaut, configurable).
        goto_45_sent = motor_writer.send_goto(parking_deg)
        time.sleep(self._MOTOR_IPC_INTER_COMMAND_DELAY_S)
        # Étape 3 : close cimier. IPC séparé (cimier_command.json), pas de
        # collision avec motor.
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
