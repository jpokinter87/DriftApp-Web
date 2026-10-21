"""Surveillance du côté du pied de la monture sur l'ASIAIR (v6.24).

Thread démon qui interroge l'ASIAIR à intervalle fixe (``lire_etat_monture``) et
garde le dernier état lu avec son heure. La boucle de suivi ne fait ainsi jamais
d'appel réseau : elle lit ``etat_frais()``. Une erreur réseau n'est jamais
propagée (DEBUG à chaque échec, WARNING une fois par panne).
"""

from __future__ import annotations

import logging
import threading
import time
from typing import Optional

from core.hardware.asiair_client import AsiairError, EtatMonture, lire_etat_monture

logger = logging.getLogger(__name__)

PERIODE_S = 5.0


class AsiairPierWatcher:
    def __init__(self, host: str, port: int, timeout_s: float, periode_s: float = PERIODE_S):
        self.host = host
        self.port = port
        self.timeout_s = timeout_s
        self.periode_s = periode_s
        self._verrou = threading.Lock()
        self._etat: Optional[EtatMonture] = None
        self._lu_a = 0.0
        self._arret = threading.Event()
        self._thread = threading.Thread(target=self._boucle, name="asiair-pier", daemon=True)

    def start(self) -> "AsiairPierWatcher":
        self._thread.start()
        return self

    def stop(self) -> None:
        self._arret.set()
        self._thread.join(timeout=self.timeout_s + 1.0)

    def etat_frais(self, max_age_s: float = 30.0) -> Optional[EtatMonture]:
        """Dernier état lu il y a moins de `max_age_s`, sinon None (ASIAIR muet)."""
        with self._verrou:
            if self._etat is None or time.monotonic() - self._lu_a > max_age_s:
                return None
            return self._etat

    def _boucle(self) -> None:
        en_panne = False
        while not self._arret.is_set():
            try:
                etat = lire_etat_monture(self.host, self.port, self.timeout_s)
            except AsiairError as exc:
                logger.debug(f"asiair_pier_read_failed | {exc}")
                if not en_panne:
                    logger.warning(f"asiair_pier_unreachable | {exc}")
                    en_panne = True
            else:
                with self._verrou:
                    self._etat, self._lu_a = etat, time.monotonic()
                if en_panne:
                    logger.info(f"asiair_pier_back | pier={etat.pier}")
                    en_panne = False
            self._arret.wait(self.periode_s)
