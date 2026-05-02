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

import json
from pathlib import Path

from core.config.config_loader import (
    VALID_AUTOMATION_MODES,
    CimierAutomationConfig,
    SiteConfig,
)
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

    def refresh_mode_from_config(self, config_path: Path) -> bool:
        """Hot-reload du mode auto depuis data/config.json.

        Re-lit `cimier.automation.mode` du fichier (et la rétro-compat lecture
        `enabled` legacy : true→full, false→manual). Si le mode a changé vs
        `self._cfg.mode`, met à jour la valeur in-memory et retourne True.

        Permet aux changements UI (POST /api/cimier/automation/) d'être pris
        en compte au prochain tick (max `scheduler_interval_seconds` plus tard,
        60s par défaut) **sans redémarrer cimier_service**.

        Fix UX 2026-05-02 : avant ce hot-reload, l'UI affichait
        « ⚠ redémarrage cimier_service requis » et l'utilisateur devait
        relancer le service à la main, ce qui était cryptique et inutilement
        contraignant.

        Returns:
            True si le mode a changé (à logger côté caller), False sinon.
        """
        try:
            with open(config_path, "r") as f:
                cfg = json.load(f)
        except (IOError, OSError, json.JSONDecodeError) as exc:
            logger.warning(
                "scheduler_event=mode_refresh_skip reason=config_read_error exc=%s",
                exc,
            )
            return False
        automation = cfg.get("cimier", {}).get("automation", {})
        explicit = automation.get("mode")
        if explicit in VALID_AUTOMATION_MODES:
            new_mode = explicit
        else:
            legacy_enabled = automation.get("enabled")
            new_mode = "full" if legacy_enabled is True else "manual"
        if new_mode == self._cfg.mode:
            return False
        old_mode = self._cfg.mode
        self._cfg.mode = new_mode
        logger.info(
            "scheduler_event=mode_refresh from=%s to=%s source=config_hot_reload",
            old_mode,
            new_mode,
        )
        return True

    def maybe_trigger(self, current_cimier_state: str) -> SchedulerDecision:
        """Évalue les conditions et émet open/close si nécessaire.

        Trois modes (v6.0 Phase 4) :
          - `manual` : court-circuit total → skip:disabled (aucun trigger).
          - `semi`   : skip OPEN inconditionnellement, garde la branche CLOSE.
                       L'utilisateur démarre manuellement la session, le
                       scheduler ne déclenche que la séquence fin de nuit.
          - `full`   : comportement v6.2 — déclenche OPEN et CLOSE selon les
                       éphémérides solaires.

        `current_cimier_state` : un des labels CIMIER_STATE_* ci-dessus.
        Retourne une `SchedulerDecision` avec le trigger résolu (ou skip:*).
        """
        now = self._clock()
        if self._cfg.mode == "manual":
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
        #    En mode "semi", l'ouverture est manuelle → on saute ce bloc en bloc.
        if direction == "descending" and alt_now <= self._cfg.opening_sun_altitude_deg:
            if self._cfg.mode == "semi":
                return SchedulerDecision("skip:semi_no_open", alt_now, direction, now)
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
    # Prévisions (countdown UI v6.0 Phase 4)
    # ------------------------------------------------------------------

    # Pas d'échantillonnage du balayage 24h. 5 min = 288 itérations sur 24h,
    # résolution largement suffisante pour un countdown UI affiché en "1h 23min".
    # Choix performance vs spec PLAN ("minute-par-minute") : sampling 5 min
    # acceptable car astropy.get_body coûte ~50-200ms par call, et la méthode
    # est appelée 1× par fenêtre `scheduler_interval_seconds` (60s par défaut).
    _NEXT_TRIGGER_SAMPLING_MINUTES = 5
    _NEXT_TRIGGER_HORIZON_HOURS = 24

    def compute_next_triggers(self, now: datetime) -> tuple[Optional[datetime], Optional[datetime]]:
        """Calcule les prochains triggers OPEN et CLOSE attendus dans les 24h.

        Retourne `(next_open_at, next_close_at)` en datetime UTC tz-aware,
        ou `None` si :
          - mode == "manual"  → (None, None)  (court-circuit total).
          - mode == "semi"    → next_open=None, next_close=datetime|None
          - mode == "full"    → les deux datetime|None selon disponibilité.

        Algo : échantillonne minute-par-(_NEXT_TRIGGER_SAMPLING_MINUTES) sur
        l'horizon `_NEXT_TRIGGER_HORIZON_HOURS`. **Détecte les transitions**
        (et non les conditions immédiates) : un trigger est émis seulement
        quand la condition passe de False (sample précédent) à True (sample
        courant). Cela évite le bug où, en pleine nuit, `next_open_at` se
        décalait de 4-5 min à chaque recalcul (la condition étant déjà vraie
        au sample 1, le code retournait now+sampling en boucle).

        - next_open : transition descending+alt<=opening_threshold passe de
          False à True (typiquement franchissement crépuscule du soir).
        - next_close : transition rising+alt(future)>=closing_target passe de
          False à True (typiquement franchissement crépuscule du matin).

        Si astropy indisponible ou erreur runtime : retourne (None, None) silencieusement.
        Consommée 1×/scheduler_interval côté `cimier_service.tick()` puis
        publiée dans `cimier_status.json` pour countdown UI dashboard.
        """
        if self._cfg.mode == "manual":
            return (None, None)

        if now.tzinfo is None:
            now = now.replace(tzinfo=timezone.utc)
        else:
            now = now.astimezone(timezone.utc)

        next_open: Optional[datetime] = None
        next_close: Optional[datetime] = None
        # En mode semi, next_open reste None (ouverture manuelle uniquement).
        skip_open = self._cfg.mode == "semi"

        sampling = timedelta(minutes=self._NEXT_TRIGGER_SAMPLING_MINUTES)
        horizon = timedelta(hours=self._NEXT_TRIGGER_HORIZON_HOURS)
        close_offset = timedelta(
            minutes=self._cfg.closing_advance_minutes
            + self._cfg.clock_safety_margin_minutes
        )
        delta_for_dir = timedelta(seconds=60)

        # Évalue la condition au temps t=now (sample 0) pour initialiser le
        # tracking de transition. Si la condition est déjà vraie à now, on
        # attendra qu'elle redevienne fausse puis vraie à nouveau (= prochaine
        # transition légitime).
        try:
            prev_open_match = self._open_condition_at(now, delta_for_dir) if not skip_open else False
            prev_close_match = self._close_condition_at(now, delta_for_dir, close_offset)
        except RuntimeError as exc:
            logger.warning("scheduler_event=compute_next_triggers_astropy_error exc=%s", exc)
            return (None, None)

        t = now + sampling  # premier sample dans le futur (pas inclure now)
        end = now + horizon
        while t <= end and (next_open is None or next_close is None):
            try:
                if not skip_open and next_open is None:
                    cur_open_match = self._open_condition_at(t, delta_for_dir)
                    if cur_open_match and not prev_open_match:
                        next_open = t  # transition False → True détectée
                    prev_open_match = cur_open_match
                if next_close is None:
                    cur_close_match = self._close_condition_at(t, delta_for_dir, close_offset)
                    if cur_close_match and not prev_close_match:
                        next_close = t  # transition False → True détectée
                    prev_close_match = cur_close_match
            except RuntimeError as exc:
                logger.warning("scheduler_event=compute_next_triggers_astropy_error exc=%s", exc)
                return (None, None)
            t += sampling
        return (next_open, next_close)

    def _open_condition_at(self, t: datetime, delta_for_dir: timedelta) -> bool:
        """True si la condition d'ouverture (descending + alt<=threshold) est
        remplie au temps t. Helper pour détection de transition."""
        direction = self._sun_direction_fn(
            t, t - delta_for_dir,
            self._site.latitude, self._site.longitude, self._site.altitude,
        )
        if direction != "descending":
            return False
        alt = self._sun_altitude_fn(
            t,
            self._site.latitude, self._site.longitude, self._site.altitude,
        )
        return alt <= self._cfg.opening_sun_altitude_deg

    def _close_condition_at(self, t: datetime, delta_for_dir: timedelta,
                            close_offset: timedelta) -> bool:
        """True si la condition de fermeture (rising + alt(t+offset)>=target)
        est remplie au temps t. Helper pour détection de transition."""
        direction = self._sun_direction_fn(
            t, t - delta_for_dir,
            self._site.latitude, self._site.longitude, self._site.altitude,
        )
        if direction != "rising":
            return False
        alt_future = self._sun_altitude_fn(
            t + close_offset,
            self._site.latitude, self._site.longitude, self._site.altitude,
        )
        return alt_future >= self._cfg.closing_target_sun_altitude_deg

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
