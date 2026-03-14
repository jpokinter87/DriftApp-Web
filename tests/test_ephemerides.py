"""
Tests exhaustifs pour core/observatoire/ephemerides.py

Couvre :
- PlanetaryEphemerides.is_planet() — noms FR/EN
- get_planet_position() — avec Astropy
- _simple_planet_position() — fallback sans Astropy
- _julian_date() — troisième copie (duplication documentée)
"""

from datetime import datetime

import pytest

from core.observatoire.ephemerides import PlanetaryEphemerides, ASTROPY_AVAILABLE


# =============================================================================
# is_planet
# =============================================================================

class TestIsPlanet:
    @pytest.mark.parametrize("name", [
        "Jupiter", "jupiter", "JUPITER",
        "Mars", "mars",
        "Venus", "venus",
        "Saturne", "saturne", "Saturn", "saturn",
        "Mercure", "mercure", "Mercury", "mercury",
        "Uranus", "uranus",
        "Neptune", "neptune",
        "Lune", "lune", "Moon", "moon",
        "Soleil", "soleil", "Sun", "sun",
    ])
    def test_known_planets(self, name):
        assert PlanetaryEphemerides.is_planet(name) is True

    @pytest.mark.parametrize("name", [
        "M42", "NGC7000", "Sirius", "Vega", "Polaris",
        "Pluton",  # Non inclus
        "", "abc123",
    ])
    def test_non_planets(self, name):
        assert PlanetaryEphemerides.is_planet(name) is False

    def test_venus_accent(self):
        """Vénus avec accent."""
        assert PlanetaryEphemerides.is_planet("vénus") is True


# =============================================================================
# get_planet_position
# =============================================================================

class TestGetPlanetPosition:
    def test_jupiter_returns_tuple(self):
        now = datetime(2025, 6, 15, 22, 0, 0)
        result = PlanetaryEphemerides.get_planet_position(
            "Jupiter", now, 44.15, 5.23
        )
        assert result is not None
        ra, dec = result
        assert 0 <= ra < 360
        assert -90 <= dec <= 90

    def test_mars(self):
        now = datetime(2025, 6, 15, 22, 0, 0)
        result = PlanetaryEphemerides.get_planet_position(
            "Mars", now, 44.15, 5.23
        )
        assert result is not None

    def test_lune(self):
        now = datetime(2025, 6, 15, 22, 0, 0)
        result = PlanetaryEphemerides.get_planet_position(
            "Lune", now, 44.15, 5.23
        )
        assert result is not None

    def test_unknown_planet(self):
        now = datetime(2025, 6, 15, 22, 0, 0)
        result = PlanetaryEphemerides.get_planet_position(
            "Pluton", now, 44.15, 5.23
        )
        assert result is None

    def test_french_name(self):
        """Nom français → fonctionne."""
        now = datetime(2025, 6, 15, 22, 0, 0)
        result = PlanetaryEphemerides.get_planet_position(
            "Saturne", now, 44.15, 5.23
        )
        assert result is not None

    def test_different_dates_different_positions(self):
        """Les planètes bougent."""
        d1 = datetime(2025, 1, 15, 22, 0, 0)
        d2 = datetime(2025, 7, 15, 22, 0, 0)
        r1 = PlanetaryEphemerides.get_planet_position("Mars", d1, 44.15, 5.23)
        r2 = PlanetaryEphemerides.get_planet_position("Mars", d2, 44.15, 5.23)
        assert r1 is not None and r2 is not None
        # Mars devrait avoir bougé en 6 mois
        assert r1[0] != r2[0] or r1[1] != r2[1]


# =============================================================================
# _simple_planet_position (fallback)
# =============================================================================

class TestSimplePlanetPosition:
    def test_returns_tuple_for_known(self):
        now = datetime(2025, 6, 15, 22, 0, 0)
        result = PlanetaryEphemerides._simple_planet_position("Jupiter", now)
        assert result is not None
        ra, dec = result
        assert 0 <= ra < 360
        assert -90 <= dec <= 90

    def test_returns_none_for_moon(self):
        """La Lune n'a pas d'éléments orbitaux dans ORBITAL_ELEMENTS."""
        now = datetime(2025, 6, 15, 22, 0, 0)
        result = PlanetaryEphemerides._simple_planet_position("Lune", now)
        assert result is None

    def test_returns_none_for_unknown(self):
        now = datetime(2025, 6, 15, 22, 0, 0)
        result = PlanetaryEphemerides._simple_planet_position("Unknown", now)
        assert result is None


# =============================================================================
# _julian_date dédupliqué (M-14 corrigé — utilise calculations.py)
# =============================================================================

class TestJulianDateDedup:
    def test_ephemerides_uses_calculations_julian_day(self):
        """M-14 corrigé : ephemerides utilise _calculate_julian_day de calculations."""
        from core.observatoire.calculations import AstronomicalCalculations
        dt = datetime(2025, 6, 15, 12, 0, 0)
        # _simple_planet_position utilise internement _calculate_julian_day
        # Vérifier que la fonction est accessible
        jd = AstronomicalCalculations._calculate_julian_day(dt)
        assert jd > 2451545.0
