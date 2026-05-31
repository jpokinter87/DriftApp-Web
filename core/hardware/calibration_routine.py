"""Routine de calibration au boot du motor_service (v6.4 Phase 2, simplifiée v6.6.0).

Au démarrage du `motor_service` en mode production, cette routine ramène la
coupole sur le microswitch de calibration à 45° avant d'accepter des commandes
utilisateur. Depuis v6.6.0 elle se limite à un sweep court autour de la
position courante (`-fallback_sweep_deg` puis `+2×fallback_sweep_deg`) :
la coupole est toujours parquée près de 45° en fin de session précédente,
donc un sweep aveugle de quelques degrés suffit à franchir le switch.

Architecture du monitoring :
- Le main thread appelle `moteur.rotation(...)` (bloquant).
- Un thread daemon poll le payload IPC du daemon encodeur
  (`last_calibration_at`) toutes les `poll_interval_sec`. Dès qu'une transition
  est détectée (front descendant du switch capté par `ems22d_calibrated.py`),
  il appelle `moteur.request_stop()` pour interrompre la rotation en cours.
- Un timeout global (`timeout_sec`) borne la durée totale de la routine.

Pas de dépendance externe (stdlib + utilitaires projet uniquement).
"""

from __future__ import annotations

import logging
import threading
import time
from dataclasses import dataclass
from typing import Callable, Optional


SWITCH_CALIB_ANGLE: float = 45.0

SINGLE_SPEED_MOTOR_DELAY: float = 0.00026

logger = logging.getLogger(__name__)


@dataclass(frozen=True)
class CalibrationResult:
    """Résultat de la routine de calibration au boot."""

    status: str
    method: str
    last_calibration_at: Optional[str]
    duration_sec: float
    error_msg: Optional[str] = None


class CalibrationRoutine:
    """Orchestre la calibration au boot du motor_service.

    Le couplage avec le service est minimal : un `status_callback(state, payload)`
    permet à `motor_service` de propager l'avancement vers
    `current_status["calibration"]` sans que ce module n'accède à `IpcManager`.
    """

    def __init__(
        self,
        moteur,
        daemon_reader,
        config,
        simulation_mode: bool,
        status_callback: Callable[[str, dict], None],
    ) -> None:
        self.moteur = moteur
        self.daemon_reader = daemon_reader
        self.config = config
        self.simulation_mode = bool(simulation_mode)
        self.status_callback = status_callback

        self._timeout_deadline: float = 0.0
        self._calibrated_during_rotation: bool = False
        self._timeout_hit: bool = False
        self._start_time: float = 0.0

    # =========================================================================
    # API PUBLIQUE
    # =========================================================================

    def run(self) -> CalibrationResult:
        """Exécute la routine et retourne le résultat final."""
        self._start_time = time.monotonic()

        if self.simulation_mode:
            logger.info("boot_calibration | step=skipped reason=simulation_mode")
            return CalibrationResult(
                status="simulated",
                method="skipped_simulation",
                last_calibration_at=None,
                duration_sec=0.0,
            )

        self._initialize_timeout_deadline()
        self._safe_callback("calibrating", {"step": "sweep"})

        if self._attempt_sweep():
            return self._build_ok_result(method="sweep")

        if self._timeout_hit:
            return self._build_degraded_result(
                method="sweep",
                error_msg=f"timeout après {self.config.timeout_sec}s",
            )

        return self._build_degraded_result(
            method="sweep",
            error_msg=f"sweep ±{self.config.fallback_sweep_deg}° infructueux",
        )

    # =========================================================================
    # SWEEP
    # =========================================================================

    def _attempt_sweep(self) -> bool:
        """Sweep court autour de la position courante (séquence -N° puis +2N°).

        À vitesse single-speed (40°/min), avec `fallback_sweep_deg=7.0` :
        première branche ≈ 10 s, deuxième branche ≈ 20 s. Garantit le passage
        sur le switch tant que la coupole est parquée à ±7° de 45°.
        """
        sweep = float(self.config.fallback_sweep_deg)

        logger.info("boot_calibration | step=sweep first_branch=%.2f", -sweep)
        if self._execute_monitored_rotation(-sweep):
            return True
        if self._timeout_hit:
            return False

        logger.info("boot_calibration | step=sweep second_branch=%.2f", 2.0 * sweep)
        if self._execute_monitored_rotation(2.0 * sweep):
            return True

        return False

    # =========================================================================
    # MONITORED ROTATION
    # =========================================================================

    def _execute_monitored_rotation(self, delta_deg: float) -> bool:
        """Exécute une rotation surveillée par un thread watcher.

        Le watcher poll `last_calibration_at` et stoppe le moteur à la
        transition. Retourne True si la calibration est intervenue durant
        cette rotation.
        """
        baseline = self._read_calibration_timestamp()
        stop_event = threading.Event()
        self._calibrated_during_rotation = False

        watcher = threading.Thread(
            target=self._watcher_loop,
            args=(stop_event, baseline),
            daemon=True,
            name="boot-calib-watcher",
        )
        watcher.start()

        try:
            self.moteur.rotation(
                delta_deg,
                vitesse=SINGLE_SPEED_MOTOR_DELAY,
                use_ramp=True,
            )
        except Exception as e:
            logger.warning("boot_calibration | step=rotation error=%s delta=%.2f", e, delta_deg)
        finally:
            stop_event.set()
            watcher.join(timeout=1.0)

        # Re-lire le timestamp final pour confirmer la transition
        final = self._read_calibration_timestamp()
        calibrated = (final is not None and final != baseline) or self._calibrated_during_rotation

        logger.info(
            "boot_calibration | step=rotation_done delta=%.2f baseline=%s final=%s "
            "calibrated=%s timeout_hit=%s",
            delta_deg,
            baseline,
            final,
            calibrated,
            self._timeout_hit,
        )
        return calibrated

    def _watcher_loop(self, stop_event: threading.Event, baseline: Optional[str]) -> None:
        """Boucle du thread watcher : poll IPC + détection transition + timeout."""
        poll = max(0.001, float(self.config.poll_interval_sec))
        while not stop_event.is_set():
            now = time.monotonic()
            if now >= self._timeout_deadline:
                self._timeout_hit = True
                logger.warning("boot_calibration | step=watcher action=timeout deadline_reached")
                self._request_stop_safe()
                stop_event.set()
                return

            current = self._read_calibration_timestamp()
            if current is not None and current != baseline:
                self._calibrated_during_rotation = True
                logger.info(
                    "boot_calibration | step=watcher action=stop transition baseline=%s current=%s",
                    baseline,
                    current,
                )
                self._request_stop_safe()
                stop_event.set()
                return

            stop_event.wait(timeout=poll)

    def _request_stop_safe(self) -> None:
        """Appelle `request_stop` sans propager d'exception (best-effort)."""
        try:
            self.moteur.request_stop()
        except Exception as e:
            logger.warning("boot_calibration | step=watcher request_stop_failed=%s", e)

    # =========================================================================
    # HELPERS
    # =========================================================================

    def _initialize_timeout_deadline(self) -> None:
        self._timeout_deadline = time.monotonic() + float(self.config.timeout_sec)

    def _read_calibration_timestamp(self) -> Optional[str]:
        try:
            payload = self.daemon_reader.read_status()
        except Exception as e:
            logger.debug("boot_calibration | step=read_status error=%s", e)
            return None
        if not isinstance(payload, dict):
            return None
        ts = payload.get("last_calibration_at")
        return ts if isinstance(ts, str) else None

    def _safe_callback(self, state: str, payload: dict) -> None:
        if self.status_callback is None:
            return
        try:
            self.status_callback(state, payload)
        except Exception as e:
            logger.debug("boot_calibration | step=callback error=%s", e)

    def _elapsed(self) -> float:
        return time.monotonic() - self._start_time

    def _build_ok_result(self, method: str) -> CalibrationResult:
        return CalibrationResult(
            status="ok",
            method=method,
            last_calibration_at=self._read_calibration_timestamp(),
            duration_sec=self._elapsed(),
        )

    def _build_degraded_result(self, method: str, error_msg: str) -> CalibrationResult:
        return CalibrationResult(
            status="degraded",
            method=method,
            last_calibration_at=self._read_calibration_timestamp(),
            duration_sec=self._elapsed(),
            error_msg=error_msg,
        )
