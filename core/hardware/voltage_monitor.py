"""Tensions des batteries du cimier et du chargeur (cartouche « Tensions », 6.31.0).

Lues par ``cimier_service`` dans sa boucle, toutes les ``read_interval_s``,
via ``Voltmeter.GetStatus`` sur deux Shelly Uni déjà en place :

  - batteries : Uni+ des butées, dans le boîtier cimier. Alimenté seulement
    coupole sous tension : injoignable le reste du temps, sans que ce soit une
    panne (``voltage`` = None) ;
  - chargeur : Plus Uni du capteur de pluie, toujours sous tension.

Journal de nuit : un relevé toutes les ``journal_interval_s``, plus une ligne
immédiate quand une mesure apparaît ou disparaît (boîtier mis sous tension ou
coupé). Ne lève jamais : une mesure ratée est publiée comme telle.
"""

from __future__ import annotations

import logging
from datetime import datetime
from typing import Any, Callable, Dict, Optional

from core.config.config_loader import VoltagesConfig
from core.hardware.shelly_rpc import ShellyRpcError, read_voltage

logger = logging.getLogger(__name__)


class VoltageMonitor:
    def __init__(
        self,
        cfg: VoltagesConfig,
        reader: Optional[Callable[[str, int, float], float]] = None,
        journal: Optional[Callable[..., Any]] = None,
    ) -> None:
        if journal is None:
            from services import night_journal

            journal = night_journal.append_event
        self._cfg = cfg
        self._reader = reader or read_voltage
        self._journal = journal
        self._sources = {
            name: (host, vid)
            for name, host, vid in (
                ("battery", cfg.battery_host, cfg.battery_id),
                ("charger", cfg.charger_host, cfg.charger_id),
            )
            if host
        }
        self._readings: Dict[str, Dict[str, Any]] = {}
        self._last_read: Optional[float] = None
        self._last_journal: Optional[float] = None

    @property
    def enabled(self) -> bool:
        return bool(self._sources)

    def tick(self, now_mono: float) -> None:
        """Lit les tensions si l'intervalle est écoulé, journalise si besoin."""
        if not self.enabled:
            return
        if self._last_read is not None and now_mono - self._last_read < self._cfg.read_interval_s:
            return
        self._last_read = now_mono
        before = {name: r["voltage"] is not None for name, r in self._readings.items()}
        read_at = datetime.now().isoformat(timespec="seconds")
        for name, (host, vid) in self._sources.items():
            try:
                volts: Optional[float] = round(self._reader(host, vid, self._cfg.timeout_s), 2)
                error = ""
            except ShellyRpcError as exc:
                volts, error = None, str(exc)
            self._readings[name] = {"voltage": volts, "read_at": read_at, "error": error}

        after = {name: r["voltage"] is not None for name, r in self._readings.items()}
        if self._last_journal is None:
            reason = "start"
        elif after != before:
            reason = "change"
        elif now_mono - self._last_journal >= self._cfg.journal_interval_s:
            reason = "periodic"
        else:
            return
        self._last_journal = now_mono
        values = {name: r["voltage"] for name, r in self._readings.items()}
        logger.info(
            "cimier_event=voltages %s reason=%s",
            " ".join(f"{k}={v}" for k, v in values.items()),
            reason,
        )
        self._journal("voltages", **values, reason=reason)

    def describe(self) -> Dict[str, Any]:
        """Dernières mesures + seuils, pour ``cimier_status.json``."""
        payload: Dict[str, Any] = dict(self._readings)
        payload["battery_good_v"] = self._cfg.battery_good_v
        payload["battery_low_v"] = self._cfg.battery_low_v
        return payload
