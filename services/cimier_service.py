"""
Cimier Service — orchestre un cycle complet du cimier (Bloc 2 archi Shelly).

Flow d'un cycle (commande "open" ou "close") — cinématique Shelly (spec §3) :
  0. preflight     : lit les butées via ``ShellySwitchReader.read()`` AVANT
                     toute alim (déjà en butée → noop, both_switches → error,
                     unreachable → error).
  1. power_on      : ``power_switch.turn_on()`` (Shelly 220V cascade).
  2. settle        : ``sleep(shelly_settle_s)`` — attente appairage WiFi
                     Shelly MOTOR + DIR après montée 24V.
  3. motor_off     : ``motor_shelly.turn_off()`` défensif (état connu avant
                     énergisation).
  4. set_direction : ``motor_shelly.set_direction(open_direction=...)``
                     (relais DIR).
  5. motor_on      : ``motor_shelly.turn_on(timer_s=timer_safety_sec)``
                     (relais MOTOR + filet hardware Shelly toggle_after).
  6. poll_switch   : boucle ``ShellySwitchReader.read()`` jusqu'à
                     ``open_switch`` ou ``closed_switch == True``
                     (ou ``cycle_timeout_s``, ou commande stop, ou
                     both_switches → error).
  7. motor_off     : ``motor_shelly.turn_off()`` (cleanup, dans finally).
  8. power_off     : ``power_switch.turn_off()`` — TOUJOURS appelé (sécurité
                     220V, invariant).
  9. cooldown      : attente ``post_off_quiet_s`` avant d'accepter une
                     nouvelle commande (anti-bounce hardware).

Bus : commande-driven via /dev/shm/cimier_command.json (pas de scheduler
éphémérides — c'est Phase 3 v6.2).

Le service est testable sans hardware : NoopPowerSwitch + SimMotorShelly
(piloté par CimierMechanismSim) + FakeSwitchReader pour les butées.
"""

from __future__ import annotations

import json
import logging
import os
import signal
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Callable, Dict, Optional, Tuple

from core.config.config_loader import (
    CimierConfig,
    ConfigLoader,
    MotorShellyConfig,
    PowerSwitchConfig,
    SiteConfig,
    SwitchReaderConfig,
    load_config,
)
from core.hardware.motor_shelly import MotorShelly, NoopMotorShelly
from core.hardware.power_switch import (
    NoopPowerSwitch,
    PowerSwitchError,
    ShellyPowerSwitch,
)
from core.hardware.shelly_switch_reader import (
    NoopSwitchReader,
    ShellySwitchReader,
    SwitchReaderError,
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
    CIMIER_STATE_ERROR,
    CIMIER_STATE_OPEN,
    CimierScheduler,
)
from services.motor_ipc_writer import MotorIpcWriter

logger = logging.getLogger(__name__)


# Phases publiées dans cimier_status.json["phase"] — archi Shelly (Bloc 2)
PHASE_IDLE = "idle"
PHASE_PREFLIGHT = "preflight"
PHASE_POWER_ON = "power_on"
PHASE_SETTLE = "settle"
PHASE_MOTOR_OFF = "motor_off"
PHASE_SET_DIR = "set_dir"
PHASE_MOTOR_ON = "motor_on"
PHASE_POLL_SWITCH = "poll_switch"
PHASE_POWER_OFF = "power_off"
PHASE_COOLDOWN = "cooldown"

# États de haut niveau publiés dans cimier_status.json["state"]
STATE_IDLE = "idle"
STATE_CYCLE = "cycle"  # un cycle est en cours (phase = sous-état)
STATE_COOLDOWN = "cooldown"
STATE_ERROR = "error"
STATE_DISABLED = "disabled"

# Actions valides
ACTION_OPEN = "open"
ACTION_CLOSE = "close"
ACTION_STOP = "stop"
_VALID_CYCLE_ACTIONS = (ACTION_OPEN, ACTION_CLOSE)

# Polling intervals par défaut (overridables par constructeur pour tests rapides)
DEFAULT_CYCLE_POLL_INTERVAL_S = 0.5
DEFAULT_RUN_LOOP_INTERVAL_S = 0.5


PowerSwitchProtocol = Any  # duck-typed : turn_on() / turn_off()
MotorShellyProtocol = Any  # duck-typed : set_direction() / turn_on() / turn_off()
SwitchReaderProtocol = Any  # duck-typed : read() -> SwitchState


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


def make_motor_shelly(cfg: MotorShellyConfig) -> MotorShellyProtocol:
    """Factory MotorShelly. Retourne NoopMotorShelly si hosts incomplets.

    Note : ``cfg.timer_safety_sec`` (filet hardware Shelly toggle_after) est
    distinct du timeout HTTP de MotorShelly — il sera passé à ``turn_on()``
    lors de l'orchestration dans T4. Le constructeur MotorShelly reçoit le
    timeout réseau par défaut (3 s).
    """
    if not cfg.host_motor or not cfg.host_dir:
        return NoopMotorShelly()
    return MotorShelly(
        host_motor=cfg.host_motor,
        host_dir=cfg.host_dir,
        relay_motor=cfg.relay_motor,
        relay_dir=cfg.relay_dir,
        open_dir_state=cfg.open_dir_state,
        motor_on_relay_state=cfg.motor_on_relay_state,
        api=cfg.api,
    )


def make_switch_reader(cfg: SwitchReaderConfig) -> SwitchReaderProtocol:
    """Factory : instancie le reader de butées d'après la config.

    type ∈ {noop, shelly_uni}.
    """
    t = (cfg.type or "noop").lower()
    if t == "noop":
        return NoopSwitchReader()
    if t == "shelly_uni":
        if not cfg.host:
            raise ValueError("SwitchReaderConfig.host vide pour shelly_uni")
        return ShellySwitchReader(
            host=cfg.host,
            api=cfg.api,
            open_input_id=cfg.open_input_id,
            closed_input_id=cfg.closed_input_id,
            invert=cfg.invert,
            timeout_s=cfg.timeout_s,
        )
    raise ValueError("SwitchReaderConfig.type inconnu: " + repr(cfg.type))


class CimierService:
    """Orchestrateur cycle cimier — commande-driven via IPC."""

    def __init__(
        self,
        cimier_config: CimierConfig,
        power_switch: PowerSwitchProtocol,
        motor_shelly: Optional[MotorShellyProtocol] = None,
        switch_reader: Optional[SwitchReaderProtocol] = None,
        ipc_manager: Optional[CimierIpcManager] = None,
        weather_provider: Optional[WeatherProvider] = None,
        site_config: Optional[SiteConfig] = None,
        scheduler: Optional[CimierScheduler] = None,
        motor_ipc: Optional[MotorIpcWriter] = None,
        clock: Callable[[], float] = time.monotonic,
        sleep: Callable[[float], None] = time.sleep,
        cycle_poll_interval_s: float = DEFAULT_CYCLE_POLL_INTERVAL_S,
        run_loop_interval_s: float = DEFAULT_RUN_LOOP_INTERVAL_S,
    ):
        self._config = cimier_config
        self._power_switch = power_switch
        self._motor_shelly = (
            motor_shelly
            if motor_shelly is not None
            else make_motor_shelly(cimier_config.motor_shelly)
        )
        self._switch_reader = (
            switch_reader
            if switch_reader is not None
            else make_switch_reader(cimier_config.switch_reader)
        )
        self._ipc = ipc_manager or CimierIpcManager()
        self._weather_provider = weather_provider or NoopWeatherProvider()
        self._clock = clock
        self._sleep = sleep
        self._cycle_poll_interval_s = float(cycle_poll_interval_s)
        self._run_loop_interval_s = float(run_loop_interval_s)

        self._stop_requested = False
        self._cooldown_end_ts: Optional[float] = None
        # Erreur du dernier cycle, republiée pendant le cooldown pour rester
        # visible dans l'UI (sinon écrasée dès le tick suivant — fix review).
        self._last_cycle_error: str = ""
        # Dernière commande traitée (traçabilité status pendant idle/cooldown).
        self._last_action_value: str = ""
        self._last_command_id_value: str = ""
        # Butées Shelly Uni+ observées en dernier (alimente le mapping vers
        # CIMIER_STATE_* pour le scheduler).
        self._last_open_switch: bool = False
        self._last_closed_switch: bool = False

        # Phase 3 : scheduler astropy. Court-circuit complet si automation off.
        self._scheduler: Optional[CimierScheduler] = scheduler
        self._last_scheduler_check_ts: Optional[float] = None
        # Phase 4 : prochains horaires de trigger (pour countdown UI dashboard).
        # Mis à jour dans tick() après maybe_trigger, lus dans _publish_status().
        self._last_next_open_at: Optional[Any] = None  # datetime UTC ou None
        self._last_next_close_at: Optional[Any] = None  # datetime UTC ou None
        if self._scheduler is None and cimier_config.automation.mode != "manual":
            if site_config is None:
                logger.warning("cimier_event=automation_disabled reason=site_config_missing")
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

        sr_cfg = self._config.switch_reader
        if sr_cfg.type == "shelly_uni" and not sr_cfg.host:
            logger.error(
                "cimier_event=config_error switch_reader.host vide — "
                "set cimier.switch_reader.host dans data/config.json"
            )
            self._publish_status(
                state=STATE_ERROR,
                phase=PHASE_IDLE,
                last_action="",
                command_id="",
                error_message="switch_reader_not_configured",
            )
            return

        self._install_signal_handlers()
        logger.info(
            "cimier_event=started switch_reader=%s power=%s motor_host=%s dir_host=%s",
            self._config.switch_reader.host or "(noop)",
            self._config.power_switch.host or "(noop)",
            self._config.motor_shelly.host_motor or "(noop)",
            self._config.motor_shelly.host_dir or "(noop)",
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
                    logger.warning("cimier_event=mode_refresh_exception exc=%s", exc)
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
                    logger.error("cimier_event=compute_next_triggers_exception exc=%s", exc)
                    self._last_next_open_at = None
                    self._last_next_close_at = None
                self._last_scheduler_check_ts = now_mono

        # 1. Cooldown : republier remaining_quiet_s ; si expiré, débloquer.
        if self._cooldown_end_ts is not None:
            remaining = self._cooldown_end_ts - self._clock()
            if remaining > 0:
                # Mode drop : on consomme (et jette) toute commande reçue pendant
                # le cooldown pour qu'elle ne soit pas rejouée ensuite — pilotage
                # manuel, pas de file d'attente d'ordres périmés.
                self._ipc.read_command()
                self._publish_status(
                    state=STATE_ERROR if self._last_cycle_error else STATE_COOLDOWN,
                    phase=PHASE_COOLDOWN,
                    last_action=self._last_action_for_status(),
                    command_id=self._last_command_id_for_status(),
                    error_message=self._last_cycle_error,
                    remaining_quiet_s=remaining,
                )
                return
            self._cooldown_end_ts = None
            self._last_cycle_error = ""

        # 2. Cooldown terminé : traiter une commande fraîche (mode drop, pas de rejeu).
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

    def _preflight_switches(self, action: str, cmd_id: str) -> Tuple[str, str, Dict[str, Any]]:
        """Lit les butées (Shelly Uni+) avant toute action électrique.

        Retourne (decision, reason, payload) :
          - decision: "noop"|"proceed"|"error"|"unreachable"
          - reason: chaîne lisible (vide si proceed)
          - payload: dict {open_switch, closed_switch} si lu, {} sinon
        """
        t0 = self._clock()
        try:
            state = self._switch_reader.read()
        except SwitchReaderError as exc:
            latency_ms = int((self._clock() - t0) * 1000)
            logger.info(
                "cimier_event=preflight action=%s id=%s decision=unreachable latency_ms=%d exc=%s",
                action,
                cmd_id,
                latency_ms,
                exc,
            )
            return ("unreachable", "precheck_unreachable", {})

        latency_ms = int((self._clock() - t0) * 1000)
        open_sw = state.open_switch
        closed_sw = state.closed_switch
        payload = {"open_switch": open_sw, "closed_switch": closed_sw}
        self._last_open_switch = open_sw
        self._last_closed_switch = closed_sw

        if state.both_switches:
            logger.info(
                "cimier_event=preflight action=%s id=%s decision=error "
                "reason=both_switches_triggered open_switch=%s closed_switch=%s latency_ms=%d",
                action,
                cmd_id,
                str(open_sw).lower(),
                str(closed_sw).lower(),
                latency_ms,
            )
            return ("error", "both_switches_triggered", payload)

        if action == ACTION_OPEN and open_sw:
            logger.info(
                "cimier_event=preflight action=%s id=%s decision=noop reason=already_open latency_ms=%d",
                action,
                cmd_id,
                latency_ms,
            )
            return ("noop", "already_open", payload)

        if action == ACTION_CLOSE and closed_sw:
            logger.info(
                "cimier_event=preflight action=%s id=%s decision=noop reason=already_closed latency_ms=%d",
                action,
                cmd_id,
                latency_ms,
            )
            return ("noop", "already_closed", payload)

        logger.info(
            "cimier_event=preflight action=%s id=%s decision=proceed "
            "open_switch=%s closed_switch=%s latency_ms=%d",
            action,
            cmd_id,
            str(open_sw).lower(),
            str(closed_sw).lower(),
            latency_ms,
        )
        return ("proceed", "", payload)

    def _call_motor_logged(self, call_name: str, fn: Callable[[], None], **ctx: Any) -> None:
        """Appelle une méthode de motor_shelly en chronométrant et journalisant.

        Args:
            call_name: nom de la méthode appelée (turn_off / set_direction / turn_on).
            fn: callable sans argument (lambda fermée sur les args réels).
            **ctx: clés/valeurs additionnelles à inclure dans le log
                   (ex: open=True, timer_s=90.0).

        Log INFO sur succès (cimier_event=shelly_call), ERROR sur exception.
        Ré-émet l'exception pour propagation.
        """
        host = getattr(self._motor_shelly, "host_motor", "noop")
        t0 = self._clock()
        try:
            fn()
            latency_ms = int((self._clock() - t0) * 1000)
            extras = (" " + " ".join("%s=%s" % (k, v) for k, v in ctx.items())) if ctx else ""
            logger.info(
                "cimier_event=shelly_call call=%s host=%s latency_ms=%d%s",
                call_name,
                host,
                latency_ms,
                extras,
            )
        except Exception as exc:
            latency_ms = int((self._clock() - t0) * 1000)
            logger.error(
                "cimier_event=shelly_call_failed call=%s host=%s latency_ms=%d exc=%s",
                call_name,
                host,
                latency_ms,
                exc,
            )
            raise

    def _run_cycle(self, action: str, cmd_id: str) -> None:
        """Pipeline phases — cinématique Shelly (spec §3) :
        preflight → power_on → settle → motor_off → set_direction → motor_on
        → poll_switch → motor_off (cleanup) → power_off → cooldown.

        ``power_switch.turn_off()`` et ``motor_shelly.turn_off()`` sont TOUJOURS
        appelés dans ``finally`` (sécurité 220V + état moteur connu).
        """
        cycle_start = self._clock()
        error_message = ""
        poll_outcome = (
            ""  # "ok"/"stopped"/"timeout"/"error" — propagé au mapping result= du finally
        )

        # Snapshot meteo au demarrage (Phase 2 : log seulement, pas de blocage).
        # Phase 3 consultera is_safe_to_open() pour refuser une ouverture auto.
        weather_desc = self._weather_provider.describe()
        logger.info(
            "cimier_event=cycle_start action=%s id=%s weather=%s",
            action,
            cmd_id,
            json.dumps(weather_desc, separators=(",", ":"), sort_keys=True),
        )

        # ----- Pré-vol garde-fou (avant toute alim) -----
        self._publish_phase(PHASE_PREFLIGHT, action, cmd_id, error_message="")
        decision, reason, _ = self._preflight_switches(action, cmd_id)
        if decision == "noop":
            if action == ACTION_OPEN:
                target_state = CIMIER_STATE_OPEN
            elif action == ACTION_CLOSE:
                target_state = CIMIER_STATE_CLOSED
            else:
                raise AssertionError("preflight noop unreachable for action=" + repr(action))
            self._publish_status(
                state=target_state,
                phase=PHASE_IDLE,
                last_action=action,
                command_id=cmd_id,
                error_message="",
            )
            duration_ms = int((self._clock() - cycle_start) * 1000)
            logger.info(
                "cimier_event=cycle_end action=%s id=%s duration_ms=%d result=noop reason=%s",
                action,
                cmd_id,
                duration_ms,
                reason,
            )
            return
        if decision in ("error", "unreachable"):
            self._publish_status(
                state=STATE_ERROR,
                phase=PHASE_IDLE,
                last_action=action,
                command_id=cmd_id,
                error_message=reason,
            )
            duration_ms = int((self._clock() - cycle_start) * 1000)
            logger.info(
                "cimier_event=cycle_end action=%s id=%s duration_ms=%d result=%s error=%s",
                action,
                cmd_id,
                duration_ms,
                decision,
                reason,
            )
            return

        # ----- Cinématique Shelly (spec §3.1 → §3.4) -----
        try:
            # Phase A : power_on (Shelly 220V cascade).
            self._publish_phase(PHASE_POWER_ON, action, cmd_id, error_message="")
            try:
                self._power_switch.turn_on()
            except PowerSwitchError as exc:
                logger.error("cimier_event=power_on_failed id=%s exc=%s", cmd_id, exc)
                error_message = "power_on_failed"
                return
            logger.info(
                "cimier_event=phase phase=%s action=%s id=%s elapsed_ms=%d",
                PHASE_POWER_ON,
                action,
                cmd_id,
                int((self._clock() - cycle_start) * 1000),
            )

            # Phase B : settle (appairage WiFi Shelly aval — 24V montant).
            self._publish_phase(PHASE_SETTLE, action, cmd_id, error_message="")
            settle = float(self._config.shelly_settle_s)
            if settle > 0:
                self._sleep(settle)
            logger.info(
                "cimier_event=phase phase=%s action=%s id=%s elapsed_ms=%d",
                PHASE_SETTLE,
                action,
                cmd_id,
                int((self._clock() - cycle_start) * 1000),
            )

            # Phase C : turn_off moteur défensif (état connu avant énergisation).
            self._publish_phase(PHASE_MOTOR_OFF, action, cmd_id, error_message="")
            try:
                self._call_motor_logged("turn_off", lambda: self._motor_shelly.turn_off())
            except Exception:
                error_message = "motor_off_defensive_failed"
                return
            logger.info(
                "cimier_event=phase phase=%s action=%s id=%s elapsed_ms=%d",
                PHASE_MOTOR_OFF,
                action,
                cmd_id,
                int((self._clock() - cycle_start) * 1000),
            )

            # Phase D : set_direction selon action.
            self._publish_phase(PHASE_SET_DIR, action, cmd_id, error_message="")
            open_direction = action == ACTION_OPEN
            try:
                self._call_motor_logged(
                    "set_direction",
                    lambda: self._motor_shelly.set_direction(open_direction=open_direction),
                    open=open_direction,
                )
            except Exception:
                error_message = "set_direction_failed"
                return
            logger.info(
                "cimier_event=phase phase=%s action=%s id=%s elapsed_ms=%d",
                PHASE_SET_DIR,
                action,
                cmd_id,
                int((self._clock() - cycle_start) * 1000),
            )

            # Settle DPDT : laisser le relais DIR (Shelly UPDN) + le DPDT externe
            # finir de commuter AVANT d'énergiser le moteur. Sans ce délai, turn_on
            # part ~quelques ms après set_direction (mesuré ~8 ms terrain), trop tôt
            # pour une bascule mécanique → sens de rotation indéterminé au démarrage.
            dir_settle = float(self._config.dir_settle_s)
            if dir_settle > 0:
                self._sleep(dir_settle)

            # Phase E : turn_on moteur (filet hardware Shelly toggle_after).
            self._publish_phase(PHASE_MOTOR_ON, action, cmd_id, error_message="")
            timer_safety = float(self._config.motor_shelly.timer_safety_sec)
            try:
                self._call_motor_logged(
                    "turn_on",
                    lambda: self._motor_shelly.turn_on(timer_s=timer_safety),
                    timer_s=timer_safety,
                )
            except Exception:
                error_message = "motor_on_failed"
                return
            logger.info(
                "cimier_event=phase phase=%s action=%s id=%s elapsed_ms=%d",
                PHASE_MOTOR_ON,
                action,
                cmd_id,
                int((self._clock() - cycle_start) * 1000),
            )

            # Phase F : poll target switch jusqu'à fin de course / timeout / stop.
            self._publish_phase(PHASE_POLL_SWITCH, action, cmd_id, error_message="")
            outcome = self._poll_target_switch(action, cmd_id)
            poll_outcome = outcome
            logger.info(
                "cimier_event=phase phase=%s action=%s id=%s elapsed_ms=%d",
                PHASE_POLL_SWITCH,
                action,
                cmd_id,
                int((self._clock() - cycle_start) * 1000),
            )
            if outcome == "timeout":
                logger.error("cimier_event=poll_timeout id=%s", cmd_id)
                error_message = "cycle_timeout"
                return
            if outcome == "error":
                error_message = "both_switches_triggered"
                return
            if outcome == "stopped":
                error_message = ""  # stop = OK (cleanup garanti)
                return
            # outcome == "ok" → fall through, cleanup ci-dessous.

        finally:
            # Cleanup garanti : motor_off + power_off (invariant 220V).
            try:
                self._motor_shelly.turn_off()
            except Exception as exc:
                logger.error("cimier_event=motor_off_cleanup_failed id=%s exc=%s", cmd_id, exc)

            self._publish_phase(PHASE_POWER_OFF, action, cmd_id, error_message=error_message)
            try:
                self._power_switch.turn_off()
            except PowerSwitchError as exc:
                logger.error("cimier_event=power_off_failed exc=%s", exc)
            logger.info(
                "cimier_event=phase phase=%s action=%s id=%s elapsed_ms=%d",
                PHASE_POWER_OFF,
                action,
                cmd_id,
                int((self._clock() - cycle_start) * 1000),
            )

            duration_ms = int((self._clock() - cycle_start) * 1000)
            if error_message == "cycle_timeout":
                result = "timeout"
            elif poll_outcome == "stopped":
                # Interruption utilisateur pendant le polling — cleanup garanti
                # mais distinct d'un cycle nominal (Bloc 3 dette T4).
                result = "stopped"
            elif error_message == "":
                result = "ok"
            else:
                result = "error"
            logger.info(
                "cimier_event=cycle_end action=%s id=%s duration_ms=%d result=%s error=%s",
                action,
                cmd_id,
                duration_ms,
                result,
                error_message or "none",
            )

            # Cooldown : démarrer la fenêtre anti-bounce.
            self._cooldown_end_ts = self._clock() + self._config.post_off_quiet_s
            self._last_cycle_error = error_message
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
    # Phases helpers (lecture butées Shelly Uni+)
    # ------------------------------------------------------------------

    def _poll_target_switch(self, action: str, cmd_id: str) -> str:
        """Boucle de lecture Shelly Uni+ jusqu'à fin de course cible atteinte.

        Returns:
            "ok"       : butée cible atteinte.
            "timeout"  : cycle_timeout_s dépassé.
            "stopped"  : commande stop reçue.
            "error"    : both_switches au cours du polling.
        """
        target_key = "open_switch" if action == ACTION_OPEN else "closed_switch"
        deadline = self._clock() + self._config.cycle_timeout_s

        while self._clock() < deadline:
            if self._stop_requested:
                logger.info(
                    "cimier_event=poll_stopped source=signal action=%s id=%s", action, cmd_id
                )
                return "stopped"
            if self._check_for_stop_command() is not None:
                logger.info(
                    "cimier_event=poll_stopped source=stop_command action=%s id=%s", action, cmd_id
                )
                return "stopped"
            try:
                t0 = self._clock()
                state = self._switch_reader.read()
                latency_ms = int((self._clock() - t0) * 1000)
            except SwitchReaderError as exc:
                logger.debug("cimier_event=poll_exception id=%s exc=%s", cmd_id, exc)
                self._sleep(self._cycle_poll_interval_s)
                continue

            self._last_open_switch = state.open_switch
            self._last_closed_switch = state.closed_switch
            target_now = state.open_switch if action == ACTION_OPEN else state.closed_switch

            if state.both_switches:
                logger.error("cimier_event=poll_both_switches id=%s", cmd_id)
                return "error"
            if target_now:
                logger.info(
                    "cimier_event=switch_transition switch=%s from=false to=true elapsed_ms=%d id=%s",
                    target_key,
                    latency_ms,
                    cmd_id,
                )
                return "ok"
            if self._config.verbose_logging or os.environ.get("CIMIER_DEV_MODE"):
                logger.debug(
                    "cimier_event=poll_status id=%s open_switch=%s closed_switch=%s",
                    cmd_id,
                    str(state.open_switch).lower(),
                    str(state.closed_switch).lower(),
                )
            self._sleep(self._cycle_poll_interval_s)
        return "timeout"

    def _check_for_stop_command(self) -> Optional[Dict[str, Any]]:
        """Lit l'IPC sans bloquer pour détecter une commande "stop" entrante.

        Retourne le dict si une commande nouvelle d'action="stop" est arrivée,
        None sinon. Mode drop : toute autre commande (open/close) reçue pendant
        un cycle est lue (donc consommée, jamais rejouée) puis ignorée — pas de
        file d'attente d'ordres périmés (pilotage manuel).
        """
        cmd = self._ipc.read_command()
        if cmd is None:
            return None
        action = str(cmd.get("action", "")).lower()
        if action == ACTION_STOP:
            self._last_command_id_value = str(cmd.get("id", ""))
            # Traçage de l'émetteur : id + ts d'émission de la commande stop reçue
            # pendant un cycle (permet de corréler avec le client qui l'a postée).
            logger.info(
                "cimier_event=stop_command_received id=%s ts=%s",
                cmd.get("id", ""),
                cmd.get("ts", ""),
            )
            return cmd
        # Mode drop : commande non-stop reçue pendant un cycle → ignorée.
        return None

    # ------------------------------------------------------------------
    # Stop direct (commande "stop" reçue alors que rien en cours)
    # ------------------------------------------------------------------

    def _handle_stop(self, cmd_id: str) -> None:
        """Cas où "stop" arrive alors qu'aucun cycle n'est en cours.

        On publie last_action=stop dans le status pour traçabilité, mais on
        ne touche ni au power_switch ni au moteur — c'est un no-op métier.
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
            # Butées Shelly Uni+ (alimente UI + scheduler mapping).
            "open_switch": self._last_open_switch,
            "closed_switch": self._last_closed_switch,
            # v6.0 Phase 4 : mode automation + prochains horaires de trigger
            # (consommés par GET /api/cimier/automation/ + countdown UI dashboard).
            "mode": self._config.automation.mode,
            "next_open_at": (
                self._last_next_open_at.isoformat() if self._last_next_open_at is not None else None
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
        return self._last_action_value

    def _last_command_id_for_status(self) -> str:
        return self._last_command_id_value

    def _derive_current_cimier_state(self) -> str:
        """Mappe l'état interne du service vers les labels CIMIER_STATE_* du scheduler.

        Archi Shelly (Bloc 2) : le Pico est capteur-only — pas de ``pico_state``
        legacy. On dérive l'état du cimier des derniers ``open_switch`` /
        ``closed_switch`` observés.

        - Cooldown actif → CIMIER_STATE_COOLDOWN
        - both switches True → CIMIER_STATE_ERROR (anomalie capteur)
        - open_switch True  → CIMIER_STATE_OPEN
        - closed_switch True → CIMIER_STATE_CLOSED
        - aucun switch (mouvement ou état inconnu au boot) → "unknown"
          (ne matche aucun CIMIER_STATE_* → le scheduler retourne skip:state,
          comportement default-safe au boot).
        """
        if self._cooldown_end_ts is not None:
            return CIMIER_STATE_COOLDOWN
        if self._last_open_switch and self._last_closed_switch:
            return CIMIER_STATE_ERROR
        if self._last_open_switch:
            return CIMIER_STATE_OPEN
        if self._last_closed_switch:
            return CIMIER_STATE_CLOSED
        return "unknown"

    # ------------------------------------------------------------------
    # Helpers
    # ------------------------------------------------------------------

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

# ----------------------------------------------------------------------
# Dev-mode overrides (v6.3.2)
# ----------------------------------------------------------------------
# Activées uniquement quand CIMIER_DEV_MODE=1 (ou autre valeur truthy) dans
# l'environnement. Ne touchent jamais data/config.json sur disque — patch
# en mémoire seulement. Permettent à `start_dev.sh` de lancer
# `cimier_service` contre le simulateur HTTP local (`localhost:8001`)
# au lieu des Shelly réels (cimier.switch_reader.host de data/config.json) sans modifier le template repo.
_DEV_MODE_TRUTHY = {"1", "true", "yes", "on"}


def _is_dev_mode_enabled() -> bool:
    raw = os.environ.get("CIMIER_DEV_MODE", "").strip().lower()
    return raw in _DEV_MODE_TRUTHY


def _apply_dev_mode_overrides(cimier_cfg) -> None:
    """Patche en place la config cimier pour pointer le simulateur dev unifié.

    Le simulateur (`core.hardware.cimier_simulator`) émule sur 127.0.0.1:8001 :
      - les butées Shelly Uni+ (RPC Input.GetStatus id=0 BAS / id=1 HAUT),
      - 3 relais legacy : id=0 → 24V, id=1 → MOT, id=2 → UPDN.
    Conventions naturelles côté sim (relais ON = actif) ; les conventions
    terrain potentiellement inversées sont validées au banc, pas en dev.
    Ne touche jamais data/config.json sur disque (patch mémoire seulement).
    """
    cimier_cfg.enabled = True
    cimier_cfg.switch_reader.type = "shelly_uni"
    cimier_cfg.switch_reader.host = "127.0.0.1:8001"
    cimier_cfg.switch_reader.api = "rpc"
    cimier_cfg.switch_reader.open_input_id = 1
    cimier_cfg.switch_reader.closed_input_id = 0
    cimier_cfg.switch_reader.invert = True
    cimier_cfg.power_switch.type = "shelly_gen1"
    cimier_cfg.power_switch.host = "127.0.0.1:8001"
    cimier_cfg.power_switch.switch_id = 0
    cimier_cfg.motor_shelly.host_motor = "127.0.0.1:8001"
    cimier_cfg.motor_shelly.host_dir = "127.0.0.1:8001"
    cimier_cfg.motor_shelly.relay_motor = 1
    cimier_cfg.motor_shelly.relay_dir = 2
    cimier_cfg.motor_shelly.api = "legacy"
    cimier_cfg.motor_shelly.motor_on_relay_state = True
    cimier_cfg.motor_shelly.open_dir_state = True
    cimier_cfg.motor_shelly.timer_safety_sec = 0.0


def _build_service_from_config(config_path=None) -> CimierService:
    """Construit un service depuis le config.json local (entry-point réel)."""
    cfg = load_config(config_path) if config_path else ConfigLoader().load()
    if _is_dev_mode_enabled():
        _apply_dev_mode_overrides(cfg.cimier)
        logger.info(
            "cimier_dev_mode=on switch_reader=%s power=%s",
            cfg.cimier.switch_reader.host,
            cfg.cimier.power_switch.host,
        )
    power_switch = make_power_switch(cfg.cimier.power_switch)
    switch_reader = make_switch_reader(cfg.cimier.switch_reader)
    weather_provider = make_weather_provider(cfg.cimier.weather_provider)
    return CimierService(
        cimier_config=cfg.cimier,
        power_switch=power_switch,
        switch_reader=switch_reader,
        weather_provider=weather_provider,
        site_config=cfg.site,
        cycle_poll_interval_s=cfg.cimier.cycle_poll_interval_s,
    )


def main() -> int:
    """Entry-point CLI : `python -m services.cimier_service`."""
    # Niveau DEBUG si verbose_logging (ou dev mode) : sans ça, les lignes
    # `logger.debug` du poll (poll_status open/closed_switch) restent filtrées
    # par le niveau INFO — verbose_logging était de fait inopérant.
    verbose = False
    try:
        verbose = bool(ConfigLoader().load().cimier.verbose_logging) or _is_dev_mode_enabled()
    except Exception:  # noqa: BLE001 — défaut sûr si config illisible au boot
        verbose = _is_dev_mode_enabled()
    logging.basicConfig(
        level=logging.DEBUG if verbose else logging.INFO,
        format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
    )
    service = _build_service_from_config()
    service.run_forever()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
