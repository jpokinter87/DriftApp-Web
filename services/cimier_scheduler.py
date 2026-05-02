"""Scheduler astropy intégré à cimier_service (v6.0 Phase 3).

Polling 60 s : compute sun_alt(now) + sun_alt(now-60s) → détecte rising/descending.

- Trigger OPEN  : sun descendant + alt <= opening_sun_altitude_deg
                  + cimier closed + WeatherProvider.is_safe_to_open()
                  → emit "open" cimier IPC
                  + emit "jog delta=+1.0°" motor IPC
                  (déparking auto léger pour faire passer la couronne sur le
                  microswitch de calibration à 45°, référence absolue encodeur EMS22A)

- Trigger CLOSE : sun montant + alt(now + advance + safety) >= closing_target
                  + cimier open|cycle
                  → emit "tracking_stop" + "goto 45°" motor IPC
                  + emit "close" cimier IPC
                  (3 commandes parallèles, pas de waiting ; "fermeture forcée
                  sans parking au timeout 5 min" = propriété du design parallèle)

Idempotence intra-jour : after a trigger, ignore re-triggers for retrigger_cooldown_hours.
État désiré (pas event-driven) : au reboot, mémoire perdue → re-trigger si
conditions toujours remplies (volontaire — protection coupole).

Module logique pur, injectables (clock, sun_altitude_fn, weather_provider,
cimier_ipc, motor_ipc) — testable offline.
"""

from __future__ import annotations

import logging
import uuid
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from typing import Callable, Optional

from core.config.config_loader import CimierAutomationConfig, SiteConfig
from core.hardware.weather_provider import WeatherProvider
from core.observatoire.sun_altitude import compute_sun_altitude, sun_direction
from services.cimier_ipc_manager import CimierIpcManager
from services.motor_ipc_writer import MotorIpcWriter

logger = logging.getLogger(__name__)


# États cimier observables (utilisés par le scheduler pour décider trigger ou skip).
# Aligné sur le state machine de cimier_service (STATE_IDLE → "closed" mappé,
# STATE_CYCLE/COOLDOWN/ERROR → propres labels). cimier_service expose un
# helper `_derive_current_cimier_state()` qui retourne l'un de ces labels.
CIMIER_STATE_CLOSED = "closed"
CIMIER_STATE_OPEN = "open"
CIMIER_STATE_CYCLE = "cycle"
CIMIER_STATE_COOLDOWN = "cooldown"
CIMIER_STATE_ERROR = "error"


@dataclass
class SchedulerDecision:
    """Trace d'une décision : utile pour tests + logs structurés."""
    trigger: str
    sun_alt_deg: float
    direction: str
    timestamp_utc: datetime


class CimierScheduler:
    """Logic pure, injectable, testable offline."""

    def __init__(
        self,
        automation_config: CimierAutomationConfig,
        site_config: SiteConfig,
        weather_provider: WeatherProvider,
        cimier_ipc: CimierIpcManager,
        motor_ipc: MotorIpcWriter,
        clock: Callable[[], datetime] = None,
        sun_altitude_fn: Callable[..., float] = compute_sun_altitude,
        sun_direction_fn: Callable[..., str] = sun_direction,
    ):
        self._cfg = automation_config
        self._site = site_config
        self._weather = weather_provider
        self._cimier_ipc = cimier_ipc
        self._motor_ipc = motor_ipc
        self._clock = clock or (lambda: datetime.now(timezone.utc))
        self._sun_altitude_fn = sun_altitude_fn
        self._sun_direction_fn = sun_direction_fn
        self._last_open_trigger_ts: Optional[datetime] = None
        self._last_close_trigger_ts: Optional[datetime] = None

    def maybe_trigger(self, current_cimier_state: str) -> SchedulerDecision:
        """Évalue les conditions et émet open/close si nécessaire.

        `current_cimier_state` : un des labels CIMIER_STATE_* ci-dessus.
        Retourne une `SchedulerDecision` avec le trigger résolu (ou skip:*).
        """
        now = self._clock()
        if not self._cfg.enabled:
            return SchedulerDecision("skip:disabled", float("nan"), "flat", now)

        before = now - timedelta(seconds=60)
        try:
            alt_now = self._sun_altitude_fn(
                now,
                self._site.latitude,
                self._site.longitude,
                self._site.altitude,
            )
            direction = self._sun_direction_fn(
                now,
                before,
                self._site.latitude,
                self._site.longitude,
                self._site.altitude,
            )
        except RuntimeError as exc:
            logger.warning("scheduler_event=astropy_error exc=%s", exc)
            return SchedulerDecision("skip:none", float("nan"), "flat", now)

        # 1. OPEN trigger : descendant + alt <= seuil + cimier fermé
        if direction == "descending" and alt_now <= self._cfg.opening_sun_altitude_deg:
            if current_cimier_state == CIMIER_STATE_CLOSED:
                if self._is_in_cooldown(self._last_open_trigger_ts, now):
                    return SchedulerDecision("skip:cooldown", alt_now, direction, now)
                if not self._weather.is_safe_to_open():
                    logger.warning(
                        "cimier_event=automation_open_skipped reason=weather_unsafe alt=%.2f",
                        alt_now,
                    )
                    return SchedulerDecision("skip:weather", alt_now, direction, now)
                self._trigger_open()
                self._last_open_trigger_ts = now
                return SchedulerDecision("open", alt_now, direction, now)

        # 2. CLOSE trigger : montant + alt projeté(advance + safety) >= target + cimier ouvert ou en cycle
        if direction == "rising":
            advance_min = (
                self._cfg.closing_advance_minutes
                + self._cfg.clock_safety_margin_minutes
            )
            future = now + timedelta(minutes=advance_min)
            try:
                alt_future = self._sun_altitude_fn(
                    future,
                    self._site.latitude,
                    self._site.longitude,
                    self._site.altitude,
                )
            except RuntimeError:
                alt_future = alt_now
            if alt_future >= self._cfg.closing_target_sun_altitude_deg:
                if current_cimier_state in (CIMIER_STATE_OPEN, CIMIER_STATE_CYCLE):
                    if self._is_in_cooldown(self._last_close_trigger_ts, now):
                        return SchedulerDecision("skip:cooldown", alt_now, direction, now)
                    self._trigger_close()
                    self._last_close_trigger_ts = now
                    return SchedulerDecision("close", alt_now, direction, now)

        return SchedulerDecision("skip:state", alt_now, direction, now)

    # ------------------------------------------------------------------
    # Triggers (writes IPC)
    # ------------------------------------------------------------------

    def _trigger_open(self) -> None:
        """Emit open cimier IPC + jog +1° motor IPC pour déparking auto léger."""
        cimier_cmd_id = str(uuid.uuid4())
        self._cimier_ipc.write_command({"id": cimier_cmd_id, "action": "open"})
        self._motor_ipc.send_jog(self._cfg.deparking_nudge_deg)
        logger.info(
            "cimier_event=automation_open_triggered cimier_cmd_id=%s deparking_nudge_deg=%.2f",
            cimier_cmd_id,
            self._cfg.deparking_nudge_deg,
        )

    def _trigger_close(self) -> None:
        """Emit tracking_stop + goto 45° motor IPC + close cimier IPC.

        3 commandes IPC séquentielles dans le code, mais exécution parallèle
        côté motor_service / cimier_service indépendants.
        """
        self._motor_ipc.send_tracking_stop()
        self._motor_ipc.send_goto(self._cfg.parking_target_azimuth_deg)
        cimier_cmd_id = str(uuid.uuid4())
        self._cimier_ipc.write_command({"id": cimier_cmd_id, "action": "close"})
        logger.info(
            "cimier_event=automation_close_triggered cimier_cmd_id=%s parking_target_deg=%.2f",
            cimier_cmd_id,
            self._cfg.parking_target_azimuth_deg,
        )

    # ------------------------------------------------------------------
    # Helpers
    # ------------------------------------------------------------------

    def _is_in_cooldown(self, last_trigger_ts: Optional[datetime], now: datetime) -> bool:
        if last_trigger_ts is None:
            return False
        elapsed = (now - last_trigger_ts).total_seconds()
        return elapsed < self._cfg.retrigger_cooldown_hours * 3600
