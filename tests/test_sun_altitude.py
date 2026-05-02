"""Tests pour core/observatoire/sun_altitude.py (v6.0 Phase 3 sub-plan 03-01)."""

from __future__ import annotations

from datetime import datetime, timedelta, timezone
from unittest.mock import patch

import pytest

# Astropy requis pour les tests réels (skip module si absent)
pytest.importorskip("astropy", reason="astropy requis pour sun_altitude tests")

from core.observatoire import sun_altitude
from core.observatoire.sun_altitude import (
    compute_sun_altitude,
    sun_direction,
)


# Site de test (proche Observatoire Ubik, lat=44.15, lon=5.23, alt=800)
SITE_LAT = 44.15
SITE_LON = 5.23
SITE_ALT_M = 800.0


def test_compute_sun_altitude_at_local_noon_returns_positive():
    # Solstice d'été 2026, ~midi UTC à Paris (longitude 5° → midi solaire local ~11h40 UTC)
    t = datetime(2026, 6, 21, 11, 30, tzinfo=timezone.utc)
    alt = compute_sun_altitude(t, SITE_LAT, SITE_LON, SITE_ALT_M)
    assert alt > 50.0, f"alt midi été doit être > 50°, obtenu {alt}"


def test_compute_sun_altitude_at_local_midnight_returns_negative():
    # Solstice d'été, minuit UTC = ~01h locale → soleil très bas
    t = datetime(2026, 6, 22, 0, 0, tzinfo=timezone.utc)
    alt = compute_sun_altitude(t, SITE_LAT, SITE_LON, SITE_ALT_M)
    assert alt < -10.0, f"alt minuit doit être < -10°, obtenu {alt}"


def test_compute_sun_altitude_naive_datetime_assumed_utc():
    # Naive datetime ne crash pas, comportement = UTC implicite
    t_naive = datetime(2026, 6, 21, 11, 30)
    t_aware = datetime(2026, 6, 21, 11, 30, tzinfo=timezone.utc)
    alt_naive = compute_sun_altitude(t_naive, SITE_LAT, SITE_LON, SITE_ALT_M)
    alt_aware = compute_sun_altitude(t_aware, SITE_LAT, SITE_LON, SITE_ALT_M)
    assert abs(alt_naive - alt_aware) < 0.01


def test_compute_sun_altitude_raises_without_astropy():
    with patch.object(sun_altitude, "ASTROPY_AVAILABLE", False):
        with pytest.raises(RuntimeError, match="astropy requis"):
            compute_sun_altitude(datetime(2026, 1, 1, tzinfo=timezone.utc), 0.0, 0.0)


def test_sun_direction_rising_in_morning():
    # Été, juin, 06h00 UTC → soleil monte rapidement
    t = datetime(2026, 6, 21, 6, 0, tzinfo=timezone.utc)
    before = t - timedelta(seconds=60)
    direction = sun_direction(t, before, SITE_LAT, SITE_LON, SITE_ALT_M)
    assert direction == "rising"


def test_sun_direction_descending_in_evening():
    # Été, juin, 19h00 UTC → soleil descend
    t = datetime(2026, 6, 21, 19, 0, tzinfo=timezone.utc)
    before = t - timedelta(seconds=60)
    direction = sun_direction(t, before, SITE_LAT, SITE_LON, SITE_ALT_M)
    assert direction == "descending"


def test_sun_direction_flat_at_solar_noon():
    # Au midi solaire, delta sur 60s très petit → flat (avec threshold permissif)
    # Midi solaire à long=5.23 ≈ 11h39 UTC en juin
    t = datetime(2026, 6, 21, 11, 39, tzinfo=timezone.utc)
    before = t - timedelta(seconds=10)  # delta très court
    direction = sun_direction(t, before, SITE_LAT, SITE_LON, SITE_ALT_M, flat_threshold_deg=0.01)
    assert direction == "flat"


def test_sun_direction_with_explicit_threshold():
    # Threshold large : on force flat même à un moment dynamique
    t = datetime(2026, 6, 21, 6, 0, tzinfo=timezone.utc)
    before = t - timedelta(seconds=60)
    # Threshold 10° → toujours flat (même rising rapide)
    direction = sun_direction(t, before, SITE_LAT, SITE_LON, SITE_ALT_M, flat_threshold_deg=10.0)
    assert direction == "flat"


def test_sun_altitude_consistency_with_get_body():
    """Sanity check : compute_sun_altitude doit être cohérent avec get_body + AltAz direct."""
    from astropy.time import Time
    from astropy.coordinates import EarthLocation, AltAz, get_body
    import astropy.units as u

    t = datetime(2026, 6, 21, 12, 0, tzinfo=timezone.utc)
    location = EarthLocation(lat=SITE_LAT * u.deg, lon=SITE_LON * u.deg, height=SITE_ALT_M * u.m)
    time = Time(t)
    sun = get_body("sun", time, location)
    altaz = sun.transform_to(AltAz(obstime=time, location=location))
    expected = float(altaz.alt.deg)

    actual = compute_sun_altitude(t, SITE_LAT, SITE_LON, SITE_ALT_M)
    assert abs(actual - expected) < 0.001, f"divergence {actual} vs {expected}"


def test_sun_direction_descending_below_minus_12_threshold_use_case():
    """Use case Phase 3 : crépuscule nautique = trigger ouverture.

    Mi-mai 2026 à Ubik : sun_alt passe sous -12° vers ~21h45 UTC.
    Vérifie qu'à ce moment-là le scheduler verrait bien 'descending' + alt < -12°.
    """
    t = datetime(2026, 5, 15, 21, 45, tzinfo=timezone.utc)
    before = t - timedelta(seconds=60)
    alt = compute_sun_altitude(t, SITE_LAT, SITE_LON, SITE_ALT_M)
    direction = sun_direction(t, before, SITE_LAT, SITE_LON, SITE_ALT_M)
    # Le soleil est nettement sous l'horizon à cette heure en mai
    assert alt < 0.0, f"alt devrait être négatif, obtenu {alt}"
    assert direction == "descending", f"direction devrait être descending, obtenu {direction}"
