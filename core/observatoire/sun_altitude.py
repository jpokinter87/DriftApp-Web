"""Helper pur : altitude du soleil + détection rising/descending pour scheduler v6.0 Phase 3.

Module isolé (pas de dépendance runtime au reste du projet) pour :
- isolement testable offline avec injection de site/datetime ;
- import lazy/optionnel d'astropy (le module échoue proprement si astropy absent).

Le scheduler `services.cimier_scheduler` consomme `compute_sun_altitude` et
`sun_direction` pour décider open/close auto.
"""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Literal

try:
    from astropy.time import Time
    from astropy.coordinates import EarthLocation, AltAz, get_body
    import astropy.units as u
    ASTROPY_AVAILABLE = True
except ImportError:  # pragma: no cover - environnement sans astropy
    ASTROPY_AVAILABLE = False
    Time = None
    EarthLocation = None
    AltAz = None
    get_body = None
    u = None


SunDirection = Literal["rising", "descending", "flat"]


def compute_sun_altitude(
    when: datetime,
    latitude_deg: float,
    longitude_deg: float,
    altitude_m: float = 0.0,
) -> float:
    """Retourne l'altitude du soleil en degrés à l'instant `when` pour le site donné.

    `when` : datetime aware (tz attachée) OU naive (assumé UTC pour cohérence runtime).
    Retourne float en degrés (positif = au-dessus de l'horizon, négatif = sous).
    Lève RuntimeError si astropy indisponible.
    """
    if not ASTROPY_AVAILABLE:
        raise RuntimeError("astropy requis pour compute_sun_altitude")
    if when.tzinfo is None:
        when = when.replace(tzinfo=timezone.utc)
    location = EarthLocation(
        lat=latitude_deg * u.deg,
        lon=longitude_deg * u.deg,
        height=altitude_m * u.m,
    )
    time = Time(when)
    sun = get_body("sun", time, location)
    altaz = sun.transform_to(AltAz(obstime=time, location=location))
    return float(altaz.alt.deg)


def sun_direction(
    when: datetime,
    before: datetime,
    latitude_deg: float,
    longitude_deg: float,
    altitude_m: float = 0.0,
    flat_threshold_deg: float = 0.001,
) -> SunDirection:
    """Retourne 'rising', 'descending' ou 'flat' en comparant alt(when) vs alt(before).

    `flat_threshold_deg` : delta angulaire en deçà duquel on considère « flat »
    (autour du midi/minuit solaire le soleil est quasi-statique en altitude).
    """
    a_now = compute_sun_altitude(when, latitude_deg, longitude_deg, altitude_m)
    a_before = compute_sun_altitude(before, latitude_deg, longitude_deg, altitude_m)
    delta = a_now - a_before
    if delta > flat_threshold_deg:
        return "rising"
    if delta < -flat_threshold_deg:
        return "descending"
    return "flat"
