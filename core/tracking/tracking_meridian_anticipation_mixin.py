"""
Mixin d'orchestration de l'anticipation du flip méridien (stratégie E).

Câble les briques posées par Phase 1 (MeridianFlipDetector, MeridianSlewScheduler,
build_lookahead_trajectory) et Plan 02-01 (flag config + force_direction moteur)
dans le cycle start() → check_and_correct() du TrackingSession.

Principe :
- Au start(), si le flag meridian_anticipation.enabled est True et l'objet n'est
  pas une planète, on calcule un SlewSchedule pour la fenêtre 1h à venir.
- Pendant check_and_correct(), un re-scan glissant ré-évalue périodiquement la
  fenêtre 1h tant qu'aucun schedule n'est armé (ou après consommation), pour
  capter les flips qui n'étaient pas dans l'horizon initial.
- Si l'instant optimal (schedule.t_start) est atteint, on exécute un GOTO
  directif vers schedule.target avec force_direction imposé.
- Le slew est consommé une seule fois ; la boucle abaque reprend ensuite.

Flag OFF ou exception → fallback silencieux vers le comportement v5.10.
"""

from __future__ import annotations

import logging
from datetime import datetime
from typing import Optional

from core.config.config import SINGLE_SPEED_MOTOR_DELAY
from core.tracking.meridian_anticipation import (
    MeridianFlipDetector,
    MeridianSlewScheduler,
    SlewSchedule,
    build_lookahead_trajectory,
)
from core.utils.angle_utils import shortest_angular_distance

_LOOKAHEAD_DURATION_SEC = 3600
_LOOKAHEAD_SAMPLING_SEC = 10
_RESCAN_INTERVAL_SEC = 300


class TrackingMeridianAnticipationMixin:
    """Orchestration de l'anticipation méridien dans TrackingSession.

    Ne manipule pas le hardware directement — utilise `self.moteur`,
    `self.calc`, `self.abaque_manager`, etc. fournis par les autres mixins.
    """

    _anticipation_enabled: bool
    _anticipation_schedule: Optional[SlewSchedule]
    _anticipation_anchor_utc: Optional[datetime]
    _anticipation_consumed: bool
    _anticipation_last_scan_at: Optional[datetime]

    def _init_anticipation(self, anticipation_config) -> None:
        """Initialise l'état d'anticipation à partir de la config.

        Appelé depuis TrackingSession.__init__ (après les autres _init_*).
        """
        if not hasattr(self, "logger"):
            self.logger = logging.getLogger(__name__)
        self._anticipation_enabled = bool(getattr(anticipation_config, "enabled", False))
        self._anticipation_schedule = None
        self._anticipation_anchor_utc = None
        self._anticipation_consumed = False
        self._anticipation_last_scan_at = None
        self.logger.info(
            f"meridian_anticipation_init | enabled={self._anticipation_enabled}"
        )

    def _compute_anticipation_schedule(self, log_no_flip: bool = True) -> None:
        """Calcule le schedule pour la fenêtre 1h à venir.

        Appelé depuis TrackingSession.start() après que ra_deg/dec_deg/is_planet
        soient connus, et depuis `_maybe_rescan_anticipation()` pour les
        ré-évaluations périodiques. Reset systématique de l'état avant calcul :
        un re-scan ré-arme `_anticipation_consumed=False` quand un nouveau flip
        est détecté.
        """
        if not self._anticipation_enabled:
            return

        if getattr(self, "is_planet", False):
            self.logger.info(
                f"meridian_anticipation_skipped_planet | object={getattr(self, 'objet', '?')}"
            )
            return

        # Reset systématique : permet le ré-armement après consommation,
        # ou la prise en compte d'un nouveau flip apparu dans la fenêtre.
        self._anticipation_schedule = None
        self._anticipation_anchor_utc = None
        self._anticipation_consumed = False
        # Tracker le timestamp pour throttler les re-scans : aussi mis à jour
        # quand start() appelle directement (évite double-scan immédiat).
        self._anticipation_last_scan_at = datetime.utcnow()

        try:
            steps_per_rev = self.moteur.steps_per_dome_revolution
            dome_speed = 360.0 / (steps_per_rev * SINGLE_SPEED_MOTOR_DELAY)

            anchor = datetime.utcnow()
            trajectory = build_lookahead_trajectory(
                self.calc,
                self.abaque_manager,
                self.ra_deg,
                self.dec_deg,
                sim_start=anchor,
                duration_sec=_LOOKAHEAD_DURATION_SEC,
                sampling_sec=_LOOKAHEAD_SAMPLING_SEC,
            )

            flip = MeridianFlipDetector().detect(trajectory)
            if flip is None:
                if log_no_flip:
                    self.logger.info(
                        f"meridian_anticipation_no_flip | object={getattr(self, 'objet', '?')} "
                        f"window={_LOOKAHEAD_DURATION_SEC}s"
                    )
                else:
                    self.logger.debug(
                        f"meridian_anticipation_rescan_no_flip | object={getattr(self, 'objet', '?')}"
                    )
                return

            schedule = MeridianSlewScheduler().schedule(flip, dome_speed)
            self._anticipation_schedule = schedule
            self._anticipation_anchor_utc = anchor
            self.logger.info(
                f"meridian_anticipation_scheduled | object={getattr(self, 'objet', '?')} "
                f"t_start_offset={schedule.t_start_offset:.1f}s "
                f"target={schedule.target:.1f}° "
                f"direction={schedule.direction:+d} "
                f"amplitude={flip.amplitude:.1f}°"
            )

        except Exception as e:
            self.logger.warning(
                f"meridian_anticipation_compute_failed | error={e}"
            )
            self._anticipation_schedule = None
            self._anticipation_anchor_utc = None

    def _maybe_rescan_anticipation(self, now_utc: datetime) -> None:
        """Ré-évalue le schedule sur fenêtre glissante 1h, throttlé à 5 min.

        Ne perturbe jamais un schedule armé en attente : ne re-scan QUE si
        aucun schedule n'est armé, ou s'il a déjà été consommé. Permet aux
        sessions longues (>1h) de capter un flip qui n'était pas dans
        l'horizon initial du `start()`.
        """
        if not self._anticipation_enabled:
            return
        # Skip si un schedule est armé en attente (ne pas perturber le timing).
        if self._anticipation_schedule is not None and not self._anticipation_consumed:
            return
        # Throttle : 1 scan max toutes les _RESCAN_INTERVAL_SEC secondes.
        # `_compute_anticipation_schedule` met lui-même `_anticipation_last_scan_at`
        # à jour, donc start() initialise le timer et le rescan le rafraîchit.
        if self._anticipation_last_scan_at is not None:
            elapsed = (now_utc - self._anticipation_last_scan_at).total_seconds()
            if elapsed < _RESCAN_INTERVAL_SEC:
                return
        self._compute_anticipation_schedule(log_no_flip=False)

    def _should_execute_anticipatory_slew(self, now_utc: datetime) -> bool:
        """True si un slew anticipatif est dû à l'instant `now_utc`."""
        if self._anticipation_schedule is None:
            return False
        if self._anticipation_consumed:
            return False
        if not getattr(self, "running", False):
            return False
        if self._anticipation_anchor_utc is None:
            return False
        elapsed_sec = (now_utc - self._anticipation_anchor_utc).total_seconds()
        return elapsed_sec >= self._anticipation_schedule.t_start

    def _execute_anticipatory_slew(self) -> None:
        """Exécute le GOTO directif vers schedule.target avec force_direction imposé.

        Marque le schedule consommé qu'il y ait succès ou échec, pour éviter
        une ré-exécution en boucle. En cas d'échec, la boucle abaque reprendra
        et rattrapera la position au prochain tick.
        """
        schedule = self._anticipation_schedule
        if schedule is None:
            return
        if self._anticipation_consumed:
            return

        target = schedule.target
        direction = schedule.direction
        previous_position = self.position_relative

        if direction == 0:
            self.logger.warning(
                "meridian_anticipation_direction_indeterminate | "
                "fallback shortest path"
            )

        self.logger.info(
            f"meridian_anticipation_slew_start | target={target:.1f} "
            f"direction={direction:+d} current={previous_position:.1f}"
        )

        try:
            self.moteur.rotation_absolue(
                position_cible_deg=target,
                position_actuelle_deg=previous_position,
                vitesse=SINGLE_SPEED_MOTOR_DELAY,
                use_ramp=True,
                force_direction=direction,
            )
            self.position_relative = target % 360
            self.total_corrections += 1
            self.total_movement += abs(
                shortest_angular_distance(previous_position, target)
            )

            if getattr(self, "encoder_available", False):
                try:
                    self._resync_encoder_offset(target)
                except Exception as e:
                    self.logger.debug(
                        f"meridian_anticipation_resync_non_critical | error={e}"
                    )

            self.logger.info(
                f"meridian_anticipation_slew_done | target={target:.1f} "
                f"direction={direction:+d}"
            )

        except (RuntimeError, IOError, OSError) as e:
            self.logger.error(
                f"meridian_anticipation_slew_failed | error={e}"
            )
        finally:
            self._anticipation_consumed = True
