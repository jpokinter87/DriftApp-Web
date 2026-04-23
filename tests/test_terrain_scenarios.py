"""
Tests des scénarios terrain — validation des décisions tracking sur monture réelle.

Vérifie le comportement du système pour des objets réels à des positions critiques :
transit méridien, zénith, bas horizon. Basé sur les incidents NGC 5033 et LBN 166.

Note: Ces tests nécessitent astropy.
"""

from datetime import datetime, timedelta
from pathlib import Path

import pytest

pytest.importorskip("astropy", reason="astropy requis pour les tests terrain")

pytestmark = pytest.mark.slow

from core.config.config_loader import load_config
from core.observatoire import AstronomicalCalculations
from core.tracking.abaque_manager import AbaqueManager
from core.utils.angle_utils import shortest_angular_distance


# =============================================================================
# FIXTURES
# =============================================================================

@pytest.fixture
def config():
    return load_config()


@pytest.fixture
def calc(config):
    return AstronomicalCalculations(
        config.site.latitude, config.site.longitude, config.site.tz_offset
    )


@pytest.fixture
def abaque(config):
    path = str(Path(__file__).parent.parent / config.tracking.abaque_file)
    mgr = AbaqueManager(path)
    assert mgr.load_abaque(), "Échec chargement abaque"
    return mgr


# Coordonnées J2000 réelles
NGC5033_RA = 198.36
NGC5033_DEC = 36.59
LBN166_RA = 81.89
LBN166_DEC = 42.97
M42_RA = 83.82
M42_DEC = -5.39

# Date des incidents
SIM_DATE = datetime(2026, 3, 16)


def find_transit_time(calc, ra_deg, sim_date):
    """Trouve l'heure du transit méridien."""
    best_time = None
    best_ha = 999.0
    for minutes in range(0, 1440, 5):
        t = datetime(sim_date.year, sim_date.month, sim_date.day) + timedelta(minutes=minutes)
        ha = calc.calculer_angle_horaire(ra_deg, t)
        ha_norm = ha if ha <= 180 else ha - 360
        if abs(ha_norm) < abs(best_ha):
            best_ha = ha_norm
            best_time = t
    return best_time


# =============================================================================
# TESTS TRANSIT MÉRIDIEN NGC 5033
# =============================================================================

class TestNGC5033MeridianTransit:

    def test_transit_detected(self, calc):
        """L'angle horaire change de signe au transit de NGC 5033."""
        transit = find_transit_time(calc, NGC5033_RA, SIM_DATE)
        assert transit is not None

        before = transit - timedelta(minutes=30)
        after = transit + timedelta(minutes=30)

        ha_before = calc.calculer_angle_horaire(NGC5033_RA, before)
        ha_after = calc.calculer_angle_horaire(NGC5033_RA, after)

        # Normaliser dans [-180, 180]
        ha_before = ha_before if ha_before <= 180 else ha_before - 360
        ha_after = ha_after if ha_after <= 180 else ha_after - 360

        assert ha_before < 0, f"HA avant transit devrait être négatif: {ha_before}"
        assert ha_after > 0, f"HA après transit devrait être positif: {ha_after}"

    def test_large_delta_at_transit(self, calc, abaque):
        """Le delta de correction au transit de NGC 5033 est > 30°."""
        transit = find_transit_time(calc, NGC5033_RA, SIM_DATE)

        before = transit - timedelta(minutes=10)
        after = transit + timedelta(minutes=10)

        az_before, alt_before = calc.calculer_coords_horizontales(NGC5033_RA, NGC5033_DEC, before)
        az_after, alt_after = calc.calculer_coords_horizontales(NGC5033_RA, NGC5033_DEC, after)

        dome_before, _ = abaque.get_dome_position(alt_before, az_before)
        dome_after, _ = abaque.get_dome_position(alt_after, az_after)

        delta = shortest_angular_distance(dome_before, dome_after)
        assert abs(delta) > 30, f"Delta au transit NGC 5033 devrait être > 30°: {delta:.1f}°"

    def test_altitude_at_transit(self, calc):
        """NGC 5033 est à haute altitude (~82°) au transit depuis lat 44°."""
        transit = find_transit_time(calc, NGC5033_RA, SIM_DATE)
        _, alt = calc.calculer_coords_horizontales(NGC5033_RA, NGC5033_DEC, transit)
        assert alt > 75, f"Altitude NGC 5033 au transit devrait être > 75°: {alt:.1f}°"


# =============================================================================
# TESTS LBN 166 ZÉNITH
# =============================================================================

class TestLBN166Zenith:

    def test_zenith_altitude_at_transit(self, calc):
        """LBN 166 est proche du zénith (>85°) au transit."""
        transit = find_transit_time(calc, LBN166_RA, SIM_DATE)
        _, alt = calc.calculer_coords_horizontales(LBN166_RA, LBN166_DEC, transit)
        assert alt > 85, f"Altitude LBN 166 au transit devrait être > 85°: {alt:.1f}°"

    def test_large_delta_at_zenith_transit(self, calc, abaque):
        """Le delta au transit de LBN 166 est > 30° (zénith + flip)."""
        transit = find_transit_time(calc, LBN166_RA, SIM_DATE)

        before = transit - timedelta(minutes=10)
        after = transit + timedelta(minutes=10)

        az_b, alt_b = calc.calculer_coords_horizontales(LBN166_RA, LBN166_DEC, before)
        az_a, alt_a = calc.calculer_coords_horizontales(LBN166_RA, LBN166_DEC, after)

        dome_b, _ = abaque.get_dome_position(alt_b, az_b)
        dome_a, _ = abaque.get_dome_position(alt_a, az_a)

        delta = abs(shortest_angular_distance(dome_b, dome_a))
        assert delta > 30, f"Delta LBN 166 au transit devrait être > 30°: {delta:.1f}°"


# =============================================================================
# TESTS M42 OBJET STANDARD
# =============================================================================

class TestM42Standard:

    def test_low_altitude(self, calc):
        """M42 reste à altitude modérée (<50°) depuis lat 44°N."""
        transit = find_transit_time(calc, M42_RA, SIM_DATE)
        _, alt = calc.calculer_coords_horizontales(M42_RA, M42_DEC, transit)
        assert alt < 50, f"Altitude M42 au transit devrait être < 50°: {alt:.1f}°"


# =============================================================================
# TESTS COHÉRENCE ABAQUE
# =============================================================================

class TestAbaqueCoherence:

    def test_all_positions_valid_ngc5033(self, calc, abaque):
        """Toutes les positions abaque sont dans [0, 360] pour NGC 5033."""
        transit = find_transit_time(calc, NGC5033_RA, SIM_DATE)
        start = transit - timedelta(hours=3)

        for i in range(36):  # 6 heures, pas de 10 min
            t = start + timedelta(minutes=i * 10)
            az, alt = calc.calculer_coords_horizontales(NGC5033_RA, NGC5033_DEC, t)
            dome_pos, _ = abaque.get_dome_position(alt, az)
            assert 0 <= dome_pos <= 360, \
                f"Position abaque hors bornes à {t}: {dome_pos}° (az={az:.1f}° alt={alt:.1f}°)"

    def test_shortest_path_at_meridian(self, calc, abaque):
        """shortest_angular_distance choisit le bon sens au méridien."""
        transit = find_transit_time(calc, NGC5033_RA, SIM_DATE)

        before = transit - timedelta(minutes=10)
        after = transit + timedelta(minutes=10)

        az_b, alt_b = calc.calculer_coords_horizontales(NGC5033_RA, NGC5033_DEC, before)
        az_a, alt_a = calc.calculer_coords_horizontales(NGC5033_RA, NGC5033_DEC, after)

        dome_b, _ = abaque.get_dome_position(alt_b, az_b)
        dome_a, _ = abaque.get_dome_position(alt_a, az_a)

        delta = shortest_angular_distance(dome_b, dome_a)
        # Le chemin le plus court ne devrait jamais dépasser 180°
        assert abs(delta) <= 180, f"Delta > 180° signifie mauvais sens: {delta:.1f}°"
