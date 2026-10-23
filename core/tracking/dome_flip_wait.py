"""Attente du retournement de la monture avant la bascule de la coupole (v6.24),
et bascule anticipée quand la monture retourne avant le méridien (v6.26).

Tant que la monture est encore du côté d'avant le méridien (``pier_west`` sur
l'ASIAIR), la coupole ne bascule pas ; elle part au changement de côté du pied.
« Objet passé au méridien » est jugé avec l'azimut DriftApp, celui qui fait
basculer l'abaque : comparer au méridien de l'ASIAIR laisserait une fenêtre où la
coupole partirait avant le feu vert (les deux calculs ne tombent pas à la même
seconde). Specs : ``docs/superpowers/specs/2026-10-21-bascule-coupole-signal-asiair.md``,
``docs/superpowers/specs/2026-10-23-monture-retournee-en-avance.md``.

Module pur : aucune I/O, l'heure (monotone, en secondes) est fournie par l'appelant.
"""

from __future__ import annotations

from datetime import datetime, timedelta
from typing import Callable, NamedTuple, Optional

from core.hardware.asiair_client import EtatMonture

COTE_AVANT_MERIDIEN = "pier_west"
COTE_APRES_MERIDIEN = "pier_east"
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


def monture_en_avance(etat: Optional[EtatMonture], azimut_objet: float) -> bool:
    """Monture déjà retournée alors que l'objet n'a pas passé le méridien
    (azimut dans [0°, 180°[) : cas inverse de ``monture_en_retard``."""
    return (
        etat is not None
        and etat.pier == COTE_APRES_MERIDIEN
        and abs(etat.delta_h) < DELTA_H_MAX
        and azimut_objet % 360.0 < 180.0
    )


def instant_meridien(
    azimut_a: Callable[[datetime], float], maintenant: datetime, fenetre_s: float
) -> Optional[datetime]:
    """Premier instant après ``maintenant`` où l'azimut entre dans [180°, 360°[,
    à 5 s près, ou None s'il n'arrive pas dans ``fenetre_s``.

    Pas de 60 s puis dichotomie : une trentaine de calculs pour 15 min.
    """

    def passe(t: datetime) -> bool:
        return azimut_a(t) % 360.0 >= 180.0

    avant = maintenant
    pas = timedelta(seconds=60)
    fin = maintenant + timedelta(seconds=fenetre_s)
    while avant < fin:
        apres = min(avant + pas, fin)
        if passe(apres):
            while (apres - avant).total_seconds() > 5.0:
                milieu = avant + (apres - avant) / 2
                if passe(milieu):
                    apres = milieu
                else:
                    avant = milieu
            return apres
        avant = apres
    return None


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
