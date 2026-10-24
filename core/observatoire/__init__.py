"""Module de calculs astronomiques (étoiles et planètes)."""

from astropy.utils import iers

# Si les serveurs IERS sont injoignables et le cache a plus de 30 jours,
# astropy lève une ValueError au lieu de calculer : suivi et scheduler cimier
# tombent. On garde la dernière table connue (erreur de l'ordre de la seconde
# d'arc, sans effet sur la coupole) ; le téléchargement reste tenté.
iers.conf.auto_max_age = None

from core.observatoire.calculations import AstronomicalCalculations  # noqa: E402
from core.observatoire.ephemerides import PlanetaryEphemerides  # noqa: E402

__all__ = ["AstronomicalCalculations", "PlanetaryEphemerides"]
