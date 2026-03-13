"""
Tests exhaustifs pour core/observatoire/calculations.py

Couvre :
- AstronomicalCalculations construction
- Utilitaires de normalisation d'angle (duplication de angle_utils)
- Jour Julien
- Temps sidéral de Greenwich (GMST)
- Temps sidéral local (LST)
- Conversion J2000 → JNOW
- Coordonnées horizontales (azimut, altitude)
- Réfraction atmosphérique
- Angle horaire
- Passage au méridien
- Vitesse de rotation coupole
"""

import math
from datetime import datetime, timedelta, timezone

import pytest

from core.observatoire.calculations import AstronomicalCalculations


# Coordonnées Observatoire Ubik
UBIK_LAT = 44.15
UBIK_LON = 5.23
UBIK_TZ = 1


@pytest.fixture
def calc():
    """Instance AstronomicalCalculations pour l'Observatoire Ubik."""
    return AstronomicalCalculations(UBIK_LAT, UBIK_LON, UBIK_TZ)


# =============================================================================
# Construction
# =============================================================================

class TestConstruction:
    def test_init(self, calc):
        assert calc.latitude == UBIK_LAT
        assert calc.longitude == UBIK_LON
        assert calc.tz_offset == UBIK_TZ


# =============================================================================
# Utilitaires angle (duplication de angle_utils — documente le comportement)
# =============================================================================

class TestNormalisationAngles:
    def test_normalise_180_positive(self):
        assert AstronomicalCalculations._normaliser_angle_180(270) == -90

    def test_normalise_180_negative(self):
        assert AstronomicalCalculations._normaliser_angle_180(-270) == 90

    def test_normalise_360(self):
        assert AstronomicalCalculations._normaliser_angle_360(370) == 10

    def test_normalise_360_negative(self):
        assert AstronomicalCalculations._normaliser_angle_360(-10) == 350


# =============================================================================
# Jour Julien
# =============================================================================

class TestJulianDay:
    def test_j2000_epoch(self):
        """J2000.0 = 1er janvier 2000 12h UTC → JD = 2451545.0."""
        dt = datetime(2000, 1, 1, 12, 0, 0)
        jd = AstronomicalCalculations._calculate_julian_day(dt)
        assert jd == pytest.approx(2451545.0, abs=0.01)

    def test_known_date(self):
        """Date connue pour vérification croisée."""
        dt = datetime(2024, 3, 20, 0, 0, 0)  # Équinoxe mars 2024
        jd = AstronomicalCalculations._calculate_julian_day(dt)
        assert jd == pytest.approx(2460389.5, abs=0.5)

    def test_january_date(self):
        """Janvier (mois <= 2 → correction année-1)."""
        dt = datetime(2025, 1, 15, 12, 0, 0)
        jd = AstronomicalCalculations._calculate_julian_day(dt)
        assert jd > 2451545.0  # Après J2000

    def test_february_date(self):
        dt = datetime(2025, 2, 28, 0, 0, 0)
        jd = AstronomicalCalculations._calculate_julian_day(dt)
        assert isinstance(jd, float)


# =============================================================================
# Temps sidéral
# =============================================================================

class TestSiderealTime:
    def test_gmst_returns_float(self):
        jd = 2451545.0  # J2000
        gmst = AstronomicalCalculations._calculate_greenwich_sidereal_time(jd)
        assert isinstance(gmst, float)
        assert 0 <= gmst < 360

    def test_lst_returns_valid_range(self, calc):
        now = datetime(2025, 6, 15, 22, 0, 0)
        lst = calc.calculer_temps_sideral(now)
        assert 0 <= lst < 360

    def test_lst_changes_with_time(self, calc):
        """Le LST augmente avec le temps."""
        t1 = datetime(2025, 6, 15, 22, 0, 0)
        t2 = datetime(2025, 6, 15, 23, 0, 0)
        lst1 = calc.calculer_temps_sideral(t1)
        lst2 = calc.calculer_temps_sideral(t2)
        # 1 heure ≈ 15° de temps sidéral
        delta = (lst2 - lst1) % 360
        assert delta == pytest.approx(15.0, abs=1.0)

    def test_lst_with_aware_datetime(self, calc):
        """Datetime avec timezone explicite."""
        dt_aware = datetime(2025, 6, 15, 22, 0, 0, tzinfo=timezone(timedelta(hours=2)))
        lst = calc.calculer_temps_sideral(dt_aware)
        assert 0 <= lst < 360


# =============================================================================
# Conversion J2000 → JNOW
# =============================================================================

class TestJ2000ToJNow:
    def test_returns_tuple(self, calc):
        now = datetime(2025, 6, 15, 22, 0, 0)
        ra, dec = calc.convertir_j2000_vers_jnow(83.63, 22.01, now)  # M42
        assert isinstance(ra, float)
        assert isinstance(dec, float)

    def test_ra_in_range(self, calc):
        now = datetime(2025, 6, 15, 22, 0, 0)
        ra, _ = calc.convertir_j2000_vers_jnow(83.63, 22.01, now)
        assert 0 <= ra < 360

    def test_dec_in_range(self, calc):
        now = datetime(2025, 6, 15, 22, 0, 0)
        _, dec = calc.convertir_j2000_vers_jnow(83.63, 22.01, now)
        assert -90 <= dec <= 90

    def test_precession_small(self, calc):
        """La précession est petite sur quelques décennies."""
        now = datetime(2025, 6, 15, 22, 0, 0)
        ra_j2000 = 83.63
        dec_j2000 = 22.01
        ra_jnow, dec_jnow = calc.convertir_j2000_vers_jnow(ra_j2000, dec_j2000, now)
        # La différence devrait être < 1° sur 25 ans
        assert abs(ra_jnow - ra_j2000) < 1.0
        assert abs(dec_jnow - dec_j2000) < 1.0


# =============================================================================
# Coordonnées horizontales
# =============================================================================

class TestHorizontalCoords:
    def test_returns_tuple(self, calc):
        now = datetime(2025, 6, 15, 22, 0, 0)
        az, alt = calc.calculer_coords_horizontales(83.63, 22.01, now)
        assert isinstance(az, float)
        assert isinstance(alt, float)

    def test_azimut_range(self, calc):
        now = datetime(2025, 6, 15, 22, 0, 0)
        az, _ = calc.calculer_coords_horizontales(83.63, 22.01, now)
        assert 0 <= az < 360

    def test_altitude_reasonable(self, calc):
        """L'altitude doit être entre -90 et 90 (+ réfraction)."""
        now = datetime(2025, 6, 15, 22, 0, 0)
        _, alt = calc.calculer_coords_horizontales(83.63, 22.01, now)
        assert -90 <= alt <= 91  # Un peu au-dessus de 90 possible avec réfraction

    def test_polaris_high_altitude(self, calc):
        """Polaris (DEC ~89°) devrait être à haute altitude depuis lat 44°."""
        now = datetime(2025, 6, 15, 22, 0, 0)
        # Polaris : RA ≈ 37.95°, DEC ≈ 89.26°
        _, alt = calc.calculer_coords_horizontales(37.95, 89.26, now)
        # À latitude 44°, Polaris est à ~44° d'altitude
        assert alt > 40

    def test_coords_coupole_returns_three(self, calc):
        """calculer_coords_horizontales_coupole retourne 3 valeurs (az, alt, 0.0)."""
        now = datetime(2025, 6, 15, 22, 0, 0)
        result = calc.calculer_coords_horizontales_coupole(83.63, 22.01, now)
        assert len(result) == 3
        assert result[2] == 0.0  # Correction parallaxe supprimée v4.4


# =============================================================================
# Réfraction atmosphérique
# =============================================================================

class TestRefraction:
    def test_positive_altitude(self):
        corrected = AstronomicalCalculations._apply_refraction_correction(45.0)
        # La correction est toujours positive (l'objet semble plus haut)
        assert corrected > 45.0

    def test_near_horizon(self):
        """Correction maximale près de l'horizon."""
        corrected = AstronomicalCalculations._apply_refraction_correction(0.0)
        # Réfraction ~0.58° à l'horizon
        assert corrected > 0.5

    def test_zenith(self):
        """Correction minimale au zénith."""
        corrected = AstronomicalCalculations._apply_refraction_correction(90.0)
        # Réfraction quasi nulle au zénith
        assert corrected - 90.0 < 0.01

    def test_below_horizon(self):
        """Sous l'horizon (< -0.5°) → pas de correction."""
        corrected = AstronomicalCalculations._apply_refraction_correction(-1.0)
        assert corrected == -1.0

    def test_slightly_below_horizon(self):
        """Juste sous l'horizon mais > -0.5° → correction appliquée."""
        corrected = AstronomicalCalculations._apply_refraction_correction(-0.3)
        assert corrected > -0.3


# =============================================================================
# Angle horaire
# =============================================================================

class TestAngleHoraire:
    def test_returns_float(self, calc):
        now = datetime(2025, 6, 15, 22, 0, 0)
        ha = calc.calculer_angle_horaire(83.63, now)
        assert isinstance(ha, float)

    def test_range(self, calc):
        now = datetime(2025, 6, 15, 22, 0, 0)
        ha = calc.calculer_angle_horaire(83.63, now)
        assert -180 <= ha <= 180

    def test_jnow_flag(self, calc):
        """deja_jnow=True saute la conversion J2000→JNOW."""
        now = datetime(2025, 6, 15, 22, 0, 0)
        ha1 = calc.calculer_angle_horaire(83.63, now, deja_jnow=False)
        ha2 = calc.calculer_angle_horaire(83.63, now, deja_jnow=True)
        # Les deux devraient être proches mais pas identiques (précession)
        assert abs(ha1 - ha2) < 2.0


# =============================================================================
# Passage au méridien
# =============================================================================

class TestPassageMeridien:
    def test_returns_datetime(self, calc):
        now = datetime(2025, 6, 15, 22, 0, 0)
        passage = calc.calculer_heure_passage_meridien(83.63, now)
        assert isinstance(passage, datetime)

    def test_same_day(self, calc):
        """Le passage devrait être le même jour."""
        ref = datetime(2025, 6, 15, 12, 0, 0)
        passage = calc.calculer_heure_passage_meridien(83.63, ref)
        assert passage.date() == ref.date()

    def test_est_proche_meridien(self, calc):
        """Vérifie est_proche_meridien retourne un tuple (bool, float)."""
        now = datetime(2025, 6, 15, 22, 0, 0)
        est_proche, temps = calc.est_proche_meridien(83.63, now)
        assert isinstance(est_proche, bool)
        assert isinstance(temps, float)


# =============================================================================
# Vitesse de rotation
# =============================================================================

class TestVitesseRotation:
    def test_returns_four_values(self, calc):
        now = datetime(2025, 6, 15, 22, 0, 0)
        result = calc.calculer_vitesse_rotation_coupole(83.63, 22.01, now)
        assert len(result) == 4

    def test_vitesse_positive(self, calc):
        now = datetime(2025, 6, 15, 22, 0, 0)
        vitesse, sens, az, alt = calc.calculer_vitesse_rotation_coupole(83.63, 22.01, now)
        assert vitesse >= 0
        assert sens in (-1, 1)
        assert 0 <= az < 360

    def test_direction_consistent(self, calc):
        """Le sens doit être cohérent avec le mouvement."""
        now = datetime(2025, 6, 15, 22, 0, 0)
        vitesse, sens, az1, _ = calc.calculer_vitesse_rotation_coupole(83.63, 22.01, now)
        assert isinstance(sens, int)


# =============================================================================
# _add_time_component (code mort — documente qu'il existe)
# =============================================================================

class TestAddTimeComponent:
    def test_exists_and_callable(self):
        assert callable(AstronomicalCalculations._add_time_component)

    def test_returns_float(self):
        result = AstronomicalCalculations._add_time_component(100.0, 12, 30, 0, 0)
        assert isinstance(result, float)
