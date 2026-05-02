"""
Cimier Service — orchestre un cycle complet du cimier (v6.0 Phase 1).

Flow d'un cycle (commande "open" ou "close") :
  1. power_on    : `power_switch.turn_on()` (Shelly 220V)
  2. boot_poll   : poll GET <pico>/status jusqu'à 200 OK ou boot_poll_timeout_s
  3. push_config : POST <pico>/config {invert_direction:true} si non-défaut
                   (l'invert est perdu à chaque coupure Shelly → re-push obligatoire)
  4. command_pico: POST <pico>/<action>
  5. cycle_poll  : poll GET <pico>/status jusqu'à pico_state cible (open|closed|error)
                   ou cycle_timeout_s. Surveille aussi une commande "stop" entrante.
  6. power_off   : `power_switch.turn_off()` — TOUJOURS appelé (sécurité 220V).
  7. cooldown    : attente post_off_quiet_s avant d'accepter une nouvelle commande
                   (anti-bounce hardware ; le 12V coupe ~10 s plus tard via heartbeat).

Bus : commande-driven via /dev/shm/cimier_command.json (pas de scheduler
éphémérides — c'est Phase 3).

Le service est testable sans hardware : NoopPowerSwitch + CimierSimulator
suffisent pour reproduire le contrat REST du firmware Pico W.
"""

from __future__ import annotations

import json
import logging
import signal
import time
import urllib.error
import urllib.request
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Callable, Dict, Optional, Tuple

from core.config.config_loader import (
    CimierConfig,
    ConfigLoader,
    PowerSwitchConfig,
    SiteConfig,
    load_config,
)
from core.hardware.power_switch import (
    NoopPowerSwitch,
    PowerSwitchError,
    ShellyPowerSwitch,
)
from core.hardware.weather_provider import (
    NoopWeatherProvider,
    WeatherProvider,
    make_weather_provider,
)
from services.cimier_ipc_manager import CimierIpcManager
from services.cimier_scheduler import (
    CIMIER_STATE_CLOSED,
    CIMIER_STATE_COOLDOWN,
    CIMIER_STATE_CYCLE,
    CIMIER_STATE_ERROR,
    CIMIER_STATE_OPEN,
    CimierScheduler,
)
from services.motor_ipc_writer import MotorIpcWriter

logger = logging.getLogger(__name__)


# Phases publiées dans cimier_status.json["phase"]
PHASE_IDLE = "idle"
PHASE_POWER_ON = "power_on"
PHASE_BOOT_POLL = "boot_poll"
PHASE_PUSH_CONFIG = "push_config"
PHASE_COMMAND_PICO = "command_pico"
PHASE_CYCLE_POLL = "cycle_poll"
PHASE_POWER_OFF = "power_off"
PHASE_COOLDOWN = "cooldown"

# États de haut niveau publiés dans cimier_status.json["state"]
STATE_IDLE = "idle"
STATE_CYCLE = "cycle"          # un cycle est en cours (phase = sous-état)
STATE_COOLDOWN = "cooldown"
STATE_ERROR = "error"
STATE_DISABLED = "disabled"

# Actions valides
ACTION_OPEN = "open"
ACTION_CLOSE = "close"
ACTION_STOP = "stop"
_VALID_CYCLE_ACTIONS = (ACTION_OPEN, ACTION_CLOSE)

# Polling intervals par défaut (overridables par constructeur pour tests rapides)
DEFAULT_BOOT_POLL_INTERVAL_S = 0.5
DEFAULT_CYCLE_POLL_INTERVAL_S = 0.5
DEFAULT_RUN_LOOP_INTERVAL_S = 0.5
DEFAULT_HTTP_TIMEOUT_S = 3.0


class HttpClient:
    """Client HTTP minimal autour de urllib.request, injectable pour tests."""

    def __init__(
        self,
        timeout_s: float = DEFAULT_HTTP_TIMEOUT_S,
        urlopen: Optional[Callable[..., Any]] = None,
    ):
        self._timeout = float(timeout_s)
        self._urlopen = urlopen or urllib.request.urlopen

    def request(
        self,
        method: str,
        url: str,
        body: Optional[Dict[str, Any]] = None,
    ) -> Tuple[int, Dict[str, Any]]:
        """Émet une requête HTTP. Retourne (status_code, payload_json_dict).

        Lève urllib.error.URLError / OSError sur erreur réseau, propagés
        jusqu'à la logique cycle qui les transforme en state=error.
        """
        data = None
        headers = {}
        if body is not None:
            data = json.dumps(body).encode("utf-8")
            headers["Content-Type"] = "application/json"
        req = urllib.request.Request(url, data=data, method=method, headers=headers)

        with self._urlopen(req, timeout=self._timeout) as resp:
            status = getattr(resp, "status", 200)
            raw = resp.read()

        if not raw:
            return status, {}
        try:
            return status, json.loads(raw.decode("utf-8"))
        except (ValueError, UnicodeDecodeError):
            return status, {}


PowerSwitchProtocol = Any  # duck-typed : turn_on() / turn_off()


def make_power_switch(cfg: PowerSwitchConfig) -> PowerSwitchProtocol:
    """Factory : instancie le power_switch d'après la config.

    type ∈ {noop, shelly_gen2, shelly_gen1}.
    """
    t = (cfg.type or "noop").lower()
    if t == "noop":
        return NoopPowerSwitch()
    if t == "shelly_gen2":
        if not cfg.host:
            raise ValueError("PowerSwitchConfig.host vide pour shelly_gen2")
        return ShellyPowerSwitch(cfg.host, switch_id=cfg.switch_id, api="rpc")
    if t == "shelly_gen1":
        if not cfg.host:
            raise ValueError("PowerSwitchConfig.host vide pour shelly_gen1")
        return ShellyPowerSwitch(cfg.host, switch_id=cfg.switch_id, api="legacy")
    raise ValueError("PowerSwitchConfig.type inconnu: " + repr(cfg.type))


class CimierService:
    """Orchestrateur cycle cimier — commande-driven via IPC."""

    def __init__(
        self,
        cimier_config: CimierConfig,
        power_switch: PowerSwitchProtocol,
        http_client: Optional[HttpClient] = None,
        ipc_manager: Optional[CimierIpcManager] = None,
        weather_provider: Optional[WeatherProvider] = None,
        site_config: Optional[SiteConfig] = None,
        scheduler: Optional[CimierScheduler] = None,
        motor_ipc: Optional[MotorIpcWriter] = None,
        clock: Callable[[], float] = time.monotonic,
        sleep: Callable[[float], None] = time.sleep,
        boot_poll_interval_s: float = DEFAULT_BOOT_POLL_INTERVAL_S,
        cycle_poll_interval_s: float = DEFAULT_CYCLE_POLL_INTERVAL_S,
        run_loop_interval_s: float = DEFAULT_RUN_LOOP_INTERVAL_S,
    ):
        self._config = cimier_config
        self._power_switch = power_switch
        self._http = http_client or HttpClient()
        self._ipc = ipc_manager or CimierIpcManager()
        self._weather_provider = weather_provider or NoopWeatherProvider()
        self._clock = clock
        self._sleep = sleep
        self._boot_poll_interval_s = float(boot_poll_interval_s)
        self._cycle_poll_interval_s = float(cycle_poll_interval_s)
        self._run_loop_interval_s = float(run_loop_interval_s)

        self._stop_requested = False
        self._cooldown_end_ts: Optional[float] = None
        self._pending_command: Optional[Dict[str, Any]] = None
        self._last_pico_state: str = "unknown"

        # Phase 3 : scheduler astropy. Court-circuit complet si automation off.
        self._scheduler: Optional[CimierScheduler] = scheduler
        self._last_scheduler_check_ts: Optional[float] = None
        # Phase 4 : prochains horaires de trigger (pour countdown UI dashboard).
        # Mis à jour dans tick() après maybe_trigger, lus dans _publish_status().
        self._last_next_open_at: Optional[Any] = None  # datetime UTC ou None
        self._last_next_close_at: Optional[Any] = None  # datetime UTC ou None
        if self._scheduler is None and cimier_config.automation.mode != "manual":
            if site_config is None:
                logger.warning(
                    "cimier_event=automation_disabled reason=site_config_missing"
                )
            else:
                motor_ipc = motor_ipc or MotorIpcWriter()
                self._scheduler = CimierScheduler(
                    automation_config=cimier_config.automation,
                    site_config=site_config,
                    weather_provider=self._weather_provider,
                    cimier_ipc=self._ipc,
                    motor_ipc=motor_ipc,
                )

        self._publish_status(
            state=STATE_IDLE,
            phase=PHASE_IDLE,
            last_action="",
            command_id="",
            error_message="",
        )

    # ------------------------------------------------------------------
    # Boucle principale + lifecycle
    # ------------------------------------------------------------------

    def run_forever(self) -> None:
        """Boucle de poll IPC. Quitte sur SIGINT/SIGTERM."""
        if not self._config.enabled:
            logger.info("cimier_event=disabled enabled=False — exit run_forever")
            self._publish_status(
                state=STATE_DISABLED,
                phase=PHASE_IDLE,
                last_action="",
                command_id="",
                error_message="",
            )
            return

        if not self._config.host:
            logger.error(
                "cimier_event=config_error host vide — set cimier.host dans data/config.json"
            )
            self._publish_status(
                state=STATE_ERROR,
                phase=PHASE_IDLE,
                last_action="",
                command_id="",
                error_message="host_not_configured",
            )
            return

        self._install_signal_handlers()
        logger.info(
            "cimier_event=started host=%s port=%d invert=%s",
            self._config.host,
            self._config.port,
            self._config.invert_direction,
        )

        while not self._stop_requested:
            self.tick()
            self._sleep(self._run_loop_interval_s)

        logger.info("cimier_event=stopped")

    def request_stop(self) -> None:
        """Demande l'arrêt de la boucle run_forever (gracieux)."""
        self._stop_requested = True

    def tick(self) -> None:
        """Un coup de boucle : check IPC, traite cooldown, dispatch commande.

        Découplé pour les tests (avancer la clock entre ticks).
        """
        # 0. Phase 3 : scheduler astropy (toutes les scheduler_interval_seconds,
        #    pas à chaque tick). Court-circuit si scheduler None (automation off).
        if self._scheduler is not None:
            interval = self._config.automation.scheduler_interval_seconds
            now_mono = self._clock()
            if (
                self._last_scheduler_check_ts is None
                or (now_mono - self._last_scheduler_check_ts) >= interval
            ):
                # Hot-reload du mode auto depuis data/config.json (v6.0 Phase 4
                # fix UX) — évite à l'utilisateur d'avoir à redémarrer
                # cimier_service après un POST /api/cimier/automation/.
                # Pas critique si ça échoue (mode courant gardé).
                try:
                    if hasattr(self._scheduler, "refresh_mode_from_config"):
                        config_path = Path(__file__).resolve().parents[1] / "data" / "config.json"
                        self._scheduler.refresh_mode_from_config(config_path)
                except Exception as exc:  # noqa: BLE001
                    logger.warning(
                        "cimier_event=mode_refresh_exception exc=%s", exc
                    )
                current_state = self._derive_current_cimier_state()
                try:
                    decision = self._scheduler.maybe_trigger(current_state)
                    logger.debug(
                        "scheduler_decision trigger=%s alt=%s dir=%s",
                        decision.trigger,
                        decision.sun_alt_deg,
                        decision.direction,
                    )
                except Exception as exc:  # noqa: BLE001 — robustesse runtime, on log et on continue
                    logger.error("cimier_event=scheduler_exception exc=%s", exc)
                # Phase 4 : prochains horaires de trigger pour countdown UI.
                # Calculé 1× par scheduler_interval (gated comme maybe_trigger).
                # compute_next_triggers est défensif (retourne (None, None) sur exception).
                try:
                    if hasattr(self._scheduler, "compute_next_triggers"):
                        next_open, next_close = self._scheduler.compute_next_triggers(
                            datetime.now(timezone.utc)
                        )
                        self._last_next_open_at = next_open
                        self._last_next_close_at = next_close
                except Exception as exc:  # noqa: BLE001
                    logger.error(
                        "cimier_event=compute_next_triggers_exception exc=%s", exc
                    )
                    self._last_next_open_at = None
                    self._last_next_close_at = None
                self._last_scheduler_check_ts = now_mono

        # 1. Cooldown : republier remaining_quiet_s ; si expiré, débloquer.
        if self._cooldown_end_ts is not None:
            remaining = self._cooldown_end_ts - self._clock()
            if remaining > 0:
                cmd = self._ipc.read_command()
                if cmd is not None and self._pending_command is None:
                    self._pending_command = cmd
                self._publish_status(
                    state=STATE_COOLDOWN,
                    phase=PHASE_COOLDOWN,
                    last_action=self._last_action_for_status(),
                    command_id=self._last_command_id_for_status(),
                    error_message="",
                    remaining_quiet_s=remaining,
                )
                return
            self._cooldown_end_ts = None

        # 2. Cooldown terminé : si commande pending, la traiter.
        cmd = self._pending_command
        self._pending_command = None
        if cmd is None:
            cmd = self._ipc.read_command()
        if cmd is None:
            self._publish_status(
                state=STATE_IDLE,
                phase=PHASE_IDLE,
                last_action=self._last_action_for_status(),
                command_id=self._last_command_id_for_status(),
                error_message="",
            )
            return

        self.execute_command(cmd)

    # ------------------------------------------------------------------
    # Exécution d'une commande (synchrone)
    # ------------------------------------------------------------------

    def execute_command(self, command: Dict[str, Any]) -> None:
        """Exécute une commande complète (cycle ou stop). Synchrone.

        Met à jour cimier_status.json à chaque transition de phase.
        Active le cooldown anti-bounce à la fin (sauf pour stop quand idle).
        """
        action = str(command.get("action", "")).lower()
        cmd_id = str(command.get("id", ""))
        self._last_action_value = action
        self._last_command_id_value = cmd_id

        if action == ACTION_STOP:
            self._handle_stop(cmd_id)
            return

        if action not in _VALID_CYCLE_ACTIONS:
            logger.warning("cimier_event=unknown_action action=%s id=%s", action, cmd_id)
            self._publish_status(
                state=STATE_ERROR,
                phase=PHASE_IDLE,
                last_action=action,
                command_id=cmd_id,
                error_message="unknown_action:" + action,
            )
            return

        self._run_cycle(action, cmd_id)

    # ------------------------------------------------------------------
    # Pipeline cycle
    # ------------------------------------------------------------------

    def _run_cycle(self, action: str, cmd_id: str) -> None:
        """Pipeline phases : power_on → boot_poll → push_config → command_pico
        → cycle_poll → power_off → cooldown.

        turn_off() est TOUJOURS appelé en cleanup (sécurité 220V).
        """
        cycle_start = self._clock()
        error_message = ""

        # Snapshot meteo au demarrage (Phase 2 : log seulement, pas de blocage).
        # Phase 3 consultera is_safe_to_open() pour refuser une ouverture auto.
        weather_desc = self._weather_provider.describe()
        logger.info(
            "cimier_event=cycle_start action=%s id=%s weather=%s",
            action,
            cmd_id,
            json.dumps(weather_desc, separators=(",", ":"), sort_keys=True),
        )

        try:
            # Phase 1 : power_on
            self._publish_phase(
                PHASE_POWER_ON, action, cmd_id, error_message=""
            )
            try:
                self._power_switch.turn_on()
            except PowerSwitchError as exc:
                logger.error("cimier_event=power_on_failed exc=%s", exc)
                error_message = "power_on_failed"
                return

            # Phase 2 : boot_poll
            self._publish_phase(
                PHASE_BOOT_POLL, action, cmd_id, error_message=""
            )
            ready = self._poll_pico_ready(action, cmd_id)
            if ready == "stopped":
                error_message = ""
                return
            if not ready:
                logger.error("cimier_event=boot_timeout id=%s", cmd_id)
                error_message = "boot_timeout"
                return

            # Phase 3 : push_config (uniquement si invert non-défaut)
            if self._config.invert_direction:
                self._publish_phase(
                    PHASE_PUSH_CONFIG, action, cmd_id, error_message=""
                )
                pushed = self._push_invert_config()
                if not pushed:
                    logger.error("cimier_event=push_config_failed id=%s", cmd_id)
                    error_message = "push_config_failed"
                    return

            # Phase 4 : command_pico
            self._publish_phase(
                PHASE_COMMAND_PICO, action, cmd_id, error_message=""
            )
            commanded = self._post_action(action)
            if not commanded:
                logger.error("cimier_event=command_failed action=%s id=%s", action, cmd_id)
                error_message = "command_failed"
                # Tenter un /stop pour ne pas laisser le moteur tourner
                self._try_post_stop_silent()
                return

            # Phase 5 : cycle_poll
            self._publish_phase(
                PHASE_CYCLE_POLL, action, cmd_id, error_message=""
            )
            outcome = self._poll_cycle_complete(action, cmd_id)
            if outcome == "timeout":
                logger.error("cimier_event=cycle_timeout id=%s", cmd_id)
                error_message = "cycle_timeout"
                self._try_post_stop_silent()
                return
            if outcome == "pico_error":
                logger.error("cimier_event=pico_error id=%s state=%s", cmd_id, self._last_pico_state)
                error_message = "pico_error"
                return
            if outcome == "stopped":
                error_message = ""
                return

        finally:
            # Phase 6 : power_off — TOUJOURS appelé (sécurité 220V)
            self._publish_phase(
                PHASE_POWER_OFF,
                action,
                cmd_id,
                error_message=error_message,
            )
            try:
                self._power_switch.turn_off()
            except PowerSwitchError as exc:
                logger.error("cimier_event=power_off_failed exc=%s", exc)

            duration_ms = int((self._clock() - cycle_start) * 1000)
            logger.info(
                "cimier_event=cycle_end action=%s id=%s duration_ms=%d error=%s",
                action,
                cmd_id,
                duration_ms,
                error_message or "none",
            )

            # Phase 7 : cooldown — démarrer la fenêtre anti-bounce
            self._cooldown_end_ts = self._clock() + self._config.post_off_quiet_s
            state = STATE_ERROR if error_message else STATE_COOLDOWN
            self._publish_status(
                state=state,
                phase=PHASE_COOLDOWN,
                last_action=action,
                command_id=cmd_id,
                error_message=error_message,
                remaining_quiet_s=self._config.post_off_quiet_s,
            )

    # ------------------------------------------------------------------
    # Phases helpers (HTTP)
    # ------------------------------------------------------------------

    def _poll_pico_ready(self, action: str, cmd_id: str):
        """Boucle GET /status jusqu'à 200 OK. Retourne True / False / 'stopped'."""
        deadline = self._clock() + self._config.boot_poll_timeout_s
        url = self._base_url() + "/status"
        while self._clock() < deadline:
            if self._stop_requested:
                return False
            # Surveille une commande "stop" pendant le boot.
            stop_seen = self._check_for_stop_command()
            if stop_seen is not None:
                self._try_post_stop_silent()
                return "stopped"
            try:
                status, payload = self._http.request("GET", url)
                if status == 200:
                    if isinstance(payload, dict):
                        self._last_pico_state = str(payload.get("state", "unknown"))
                    return True
            except (urllib.error.URLError, OSError, ConnectionError):
                pass  # boot pas terminé
            self._sleep(self._boot_poll_interval_s)
        return False

    def _push_invert_config(self) -> bool:
        """POST /config {invert_direction: true}. Retourne True si 200."""
        url = self._base_url() + "/config"
        try:
            status, _ = self._http.request(
                "POST", url, body={"invert_direction": True}
            )
            return status == 200
        except (urllib.error.URLError, OSError, ConnectionError) as exc:
            logger.warning("cimier_event=push_config_exception exc=%s", exc)
            return False

    def _post_action(self, action: str) -> bool:
        """POST /open ou /close. Retourne True si 200."""
        url = self._base_url() + "/" + action
        try:
            status, payload = self._http.request("POST", url)
            if isinstance(payload, dict):
                self._last_pico_state = str(payload.get("state", "unknown"))
            return status == 200
        except (urllib.error.URLError, OSError, ConnectionError) as exc:
            logger.warning("cimier_event=post_action_exception action=%s exc=%s", action, exc)
            return False

    def _poll_cycle_complete(self, action: str, cmd_id: str) -> str:
        """Boucle GET /status jusqu'à pico_state cible.

        Retourne :
          - "ok"        : pico_state cible atteint (open ou closed)
          - "timeout"   : cycle_timeout_s dépassé
          - "stopped"   : commande "stop" reçue et propagée au Pico
          - "pico_error": Pico a remonté state="error"
        """
        target = "open" if action == ACTION_OPEN else "closed"
        deadline = self._clock() + self._config.cycle_timeout_s
        url = self._base_url() + "/status"

        while self._clock() < deadline:
            if self._stop_requested:
                self._try_post_stop_silent()
                return "stopped"
            stop_seen = self._check_for_stop_command()
            if stop_seen is not None:
                self._try_post_stop_silent()
                return "stopped"
            try:
                status, payload = self._http.request("GET", url)
                if status == 200 and isinstance(payload, dict):
                    pico_state = str(payload.get("state", "unknown"))
                    self._last_pico_state = pico_state
                    if pico_state == target:
                        return "ok"
                    if pico_state == "error":
                        return "pico_error"
            except (urllib.error.URLError, OSError, ConnectionError) as exc:
                logger.debug("cimier_event=poll_status_exception exc=%s", exc)
            self._sleep(self._cycle_poll_interval_s)

        return "timeout"

    def _try_post_stop_silent(self) -> None:
        """Tente un POST /stop, ignore les erreurs (déjà en cleanup)."""
        url = self._base_url() + "/stop"
        try:
            self._http.request("POST", url)
        except (urllib.error.URLError, OSError, ConnectionError):
            pass

    def _check_for_stop_command(self) -> Optional[Dict[str, Any]]:
        """Lit l'IPC sans bloquer pour détecter une commande "stop" entrante.

        Retourne le dict si une commande nouvelle d'action="stop" est arrivée,
        None sinon. Toute autre commande (open/close) reçue pendant un cycle
        en cours est mémorisée comme pending pour exécution future.
        """
        cmd = self._ipc.read_command()
        if cmd is None:
            return None
        action = str(cmd.get("action", "")).lower()
        if action == ACTION_STOP:
            self._last_command_id_value = str(cmd.get("id", ""))
            return cmd
        # Commande non-stop pendant cycle : on la garde pending pour plus tard.
        if self._pending_command is None:
            self._pending_command = cmd
        return None

    # ------------------------------------------------------------------
    # Stop direct (commande "stop" reçue alors que rien en cours)
    # ------------------------------------------------------------------

    def _handle_stop(self, cmd_id: str) -> None:
        """Cas où "stop" arrive alors qu'aucun cycle n'est en cours.

        On publie last_action=stop dans le status pour traçabilité, mais on
        ne touche ni au power_switch ni au pico — c'est un no-op métier.
        """
        logger.info("cimier_event=stop_idle id=%s", cmd_id)
        self._publish_status(
            state=STATE_IDLE,
            phase=PHASE_IDLE,
            last_action=ACTION_STOP,
            command_id=cmd_id,
            error_message="",
        )

    # ------------------------------------------------------------------
    # Status publishing
    # ------------------------------------------------------------------

    def _publish_phase(
        self,
        phase: str,
        action: str,
        cmd_id: str,
        error_message: str,
    ) -> None:
        self._publish_status(
            state=STATE_CYCLE,
            phase=phase,
            last_action=action,
            command_id=cmd_id,
            error_message=error_message,
        )

    def _publish_status(
        self,
        *,
        state: str,
        phase: str,
        last_action: str,
        command_id: str,
        error_message: str,
        remaining_quiet_s: Optional[float] = None,
    ) -> None:
        payload = {
            "state": state,
            "phase": phase,
            "last_action": last_action,
            "last_action_ts": self._clock(),
            "command_id": command_id,
            "error_message": error_message,
            "pico_state": self._last_pico_state,
            # v6.0 Phase 4 : mode automation + prochains horaires de trigger
            # (consommés par GET /api/cimier/automation/ + countdown UI dashboard).
            "mode": self._config.automation.mode,
            "next_open_at": (
                self._last_next_open_at.isoformat()
                if self._last_next_open_at is not None
                else None
            ),
            "next_close_at": (
                self._last_next_close_at.isoformat()
                if self._last_next_close_at is not None
                else None
            ),
        }
        if remaining_quiet_s is not None:
            payload["remaining_quiet_s"] = max(0.0, float(remaining_quiet_s))
        self._ipc.write_status(payload)

    def _last_action_for_status(self) -> str:
        return getattr(self, "_last_action_value", "")

    def _last_command_id_for_status(self) -> str:
        return getattr(self, "_last_command_id_value", "")

    def _derive_current_cimier_state(self) -> str:
        """Mappe l'état interne du service vers les labels CIMIER_STATE_* du scheduler.

        - Cooldown actif → CIMIER_STATE_COOLDOWN
        - Pico state ∈ {open, opening} → CIMIER_STATE_OPEN (opening = en train de s'ouvrir)
        - Pico state == closed → CIMIER_STATE_CLOSED
        - Pico state == closing → CIMIER_STATE_CYCLE (cycle de fermeture en cours)
        - Pico state == error → CIMIER_STATE_ERROR
        - Pico state == unknown (boot) → "unknown" (ne matche aucun CIMIER_STATE_* →
          le scheduler retourne skip:state, comportement default-safe au boot)
        """
        if self._cooldown_end_ts is not None:
            return CIMIER_STATE_COOLDOWN
        state = self._last_pico_state
        if state in ("open", "opening"):
            return CIMIER_STATE_OPEN
        if state == "closing":
            return CIMIER_STATE_CYCLE
        if state == "closed":
            return CIMIER_STATE_CLOSED
        if state == "error":
            return CIMIER_STATE_ERROR
        return "unknown"

    # ------------------------------------------------------------------
    # Helpers
    # ------------------------------------------------------------------

    def _base_url(self) -> str:
        return "http://" + self._config.host + ":" + str(self._config.port)

    def _install_signal_handlers(self) -> None:
        """Handlers SIGINT/SIGTERM pour arrêt gracieux. Ignore si déjà installé
        ou si on n'est pas dans le main thread (cas tests)."""

        def _handler(signum, frame):  # noqa: ARG001
            logger.info("cimier_event=signal_received signum=%d", signum)
            self.request_stop()

        try:
            signal.signal(signal.SIGINT, _handler)
            signal.signal(signal.SIGTERM, _handler)
        except (ValueError, OSError):
            # Tests : signal handlers ne fonctionnent que dans main thread.
            pass


# ----------------------------------------------------------------------
# Entry-point
# ----------------------------------------------------------------------

def _build_service_from_config(config_path=None) -> CimierService:
    """Construit un service depuis le config.json local (entry-point réel)."""
    cfg = load_config(config_path) if config_path else ConfigLoader().load()
    power_switch = make_power_switch(cfg.cimier.power_switch)
    weather_provider = make_weather_provider(cfg.cimier.weather_provider)
    return CimierService(
        cimier_config=cfg.cimier,
        power_switch=power_switch,
        weather_provider=weather_provider,
        site_config=cfg.site,
    )


def main() -> int:
    """Entry-point CLI : `python -m services.cimier_service`."""
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
    )
    service = _build_service_from_config()
    service.run_forever()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
