"""Attente du retournement de la monture avant la bascule de la coupole (v6.24).

Tant que la monture est encore du côté d'avant le méridien (``pier_west`` sur
l'ASIAIR), la coupole ne bascule pas ; elle part au changement de côté du pied.
« Objet passé au méridien » est jugé avec l'azimut DriftApp, celui qui fait
basculer l'abaque : comparer au méridien de l'ASIAIR laisserait une fenêtre où la
coupole partirait avant le feu vert (les deux calculs ne tombent pas à la même
seconde). Spec : ``docs/superpowers/specs/2026-10-21-bascule-coupole-signal-asiair.md``.

Module pur : aucune I/O, l'heure (monotone, en secondes) est fournie par l'appelant.
"""

from __future__ import annotations

from typing import NamedTuple, Optional

from core.hardware.asiair_client import EtatMonture

COTE_AVANT_MERIDIEN = "pier_west"
DELTA_H_MAX = 6.0  # au-delà, passage inférieur : la monture ne retourne pas


def monture_en_retard(etat: Optional[EtatMonture], azimut_objet: float) -> bool:
    """Objet passé au méridien (azimut dans [180°, 360°[, soit angle horaire > 0)
    alors que la monture est encore du côté d'avant."""
    return (
        etat is not None
        and etat.pier == COTE_AVANT_MERIDIEN
        and abs(etat.delta_h) < DELTA_H_MAX
        and azimut_objet % 360.0 >= 180.0
    )


class Decision(NamedTuple):
    attendre: bool
    evenement: Optional[str]  # "start", "pierside", "timeout", "asiair_silent" ou None
    attente_s: float  # durée de l'attente qui vient de finir (0 sinon)


class AttenteRetournement:
    """Suit une attente : début, délai maximal, pas de relance après un timeout."""

    def __init__(self, max_wait_s: float):
        self.max_wait_s = max_wait_s
        self._debut: Optional[float] = None
        self._timeout_consomme = False

    def evaluer(
        self, etat: Optional[EtatMonture], azimut_objet: float, maintenant_s: float
    ) -> Decision:
        if not monture_en_retard(etat, azimut_objet):
            if etat is not None:
                self._timeout_consomme = False
            if self._debut is None:
                return Decision(False, None, 0.0)
            return self._fin("asiair_silent" if etat is None else "pierside", maintenant_s)
        if self._timeout_consomme:
            return Decision(False, None, 0.0)
        if self._debut is None:
            self._debut = maintenant_s
            return Decision(True, "start", 0.0)
        if maintenant_s - self._debut >= self.max_wait_s:
            self._timeout_consomme = True
            return self._fin("timeout", maintenant_s)
        return Decision(True, None, 0.0)

    def en_cours(self, maintenant_s: float) -> Optional[float]:
        """Secondes écoulées depuis le début de l'attente en cours, sinon None."""
        return None if self._debut is None else maintenant_s - self._debut

    def _fin(self, raison: str, maintenant_s: float) -> Decision:
        attente_s = maintenant_s - self._debut
        self._debut = None
        return Decision(False, raison, attente_s)
