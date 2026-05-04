"""Persistance disque de la position absolue de la coupole (v6.4 Phase 1).

Le daemon `ems22d_calibrated` appelle `maybe_write()` à chaque publication IPC
quand la calibration est valide. Le persistor décide d'écrire ou non selon une
politique de throttling (delta angulaire + intervalle temporel) afin de
préserver la flash de la SD du Pi.

Le fichier produit (`data/last_known_position.json` par défaut) sert au plan 02
(routine boot du `motor_service`) pour reconstituer une position approximative
au démarrage et calculer le trajet le plus court vers le microswitch de
calibration à 45°.

Pas de dépendances externes (stdlib only). Atomicité POSIX via tmp + rename.
"""

from __future__ import annotations

import json
import logging
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional

from core.utils.angle_utils import shortest_angular_distance


IMMOBILE_DELTA_DEG = 0.05

logger = logging.getLogger(__name__)


class PositionPersistor:
    """Sauvegarde throttlée de la position absolue de la coupole sur disque."""

    def __init__(
        self,
        persist_path: Path,
        write_threshold_deg: float = 1.0,
        write_interval_sec: float = 30.0,
    ) -> None:
        if write_threshold_deg <= 0:
            raise ValueError(f"write_threshold_deg doit être > 0 (reçu {write_threshold_deg})")
        if write_interval_sec <= 0:
            raise ValueError(f"write_interval_sec doit être > 0 (reçu {write_interval_sec})")
        self.persist_path = Path(persist_path)
        self.write_threshold_deg = float(write_threshold_deg)
        self.write_interval_sec = float(write_interval_sec)
        self._last_written_angle: Optional[float] = None
        self._last_write_time: float = 0.0

    def maybe_write(self, angle_deg: float, calibrated: bool) -> bool:
        """Écrit la position si la politique de throttling l'autorise.

        Retourne True si une écriture a eu lieu, False sinon.
        """
        if not calibrated:
            return False

        if self._last_written_angle is None:
            self._atomic_write(angle_deg)
            self._last_written_angle = float(angle_deg)
            self._last_write_time = time.time()
            return True

        delta = abs(shortest_angular_distance(self._last_written_angle, angle_deg))

        if delta >= self.write_threshold_deg:
            self._atomic_write(angle_deg)
            self._last_written_angle = float(angle_deg)
            self._last_write_time = time.time()
            return True

        elapsed = time.time() - self._last_write_time
        if elapsed >= self.write_interval_sec and delta > IMMOBILE_DELTA_DEG:
            self._atomic_write(angle_deg)
            self._last_written_angle = float(angle_deg)
            self._last_write_time = time.time()
            return True

        return False

    def _atomic_write(self, angle_deg: float) -> None:
        """Écriture atomique via tmp + rename (le daemon ne crash jamais)."""
        payload = {
            "azimut_deg": float(angle_deg),
            "saved_at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        }
        tmp = self.persist_path.with_suffix(self.persist_path.suffix + ".tmp")
        try:
            tmp.write_text(json.dumps(payload))
            tmp.replace(self.persist_path)
        except (OSError, IOError):
            logger.exception("position_persistor: écriture échouée (%s)", self.persist_path)
            try:
                if tmp.exists():
                    tmp.unlink()
            except OSError:
                pass

    @classmethod
    def load_last_position(cls, persist_path: Path) -> Optional[dict]:
        """Charge la dernière position persistée (None si absent / corrompu)."""
        path = Path(persist_path)
        if not path.exists():
            logger.warning("position_persistor: load skip (reason=missing path=%s)", path)
            return None
        try:
            raw = path.read_text()
        except OSError:
            logger.warning("position_persistor: load skip (reason=read_error path=%s)", path)
            return None
        if not raw.strip():
            logger.warning("position_persistor: load skip (reason=empty path=%s)", path)
            return None
        try:
            data = json.loads(raw)
        except json.JSONDecodeError:
            logger.warning("position_persistor: load skip (reason=invalid_json path=%s)", path)
            return None
        if not isinstance(data, dict):
            logger.warning("position_persistor: load skip (reason=invalid_schema path=%s)", path)
            return None
        azimut = data.get("azimut_deg")
        saved_at = data.get("saved_at")
        if not isinstance(azimut, (int, float)) or not isinstance(saved_at, str):
            logger.warning("position_persistor: load skip (reason=invalid_schema path=%s)", path)
            return None
        if not (0.0 <= float(azimut) < 360.0):
            logger.warning("position_persistor: load skip (reason=invalid_schema path=%s azimut=%s)", path, azimut)
            return None
        return data
