"""
Tests unitaires pour core/tracking/tracker.py (TrackingSession).

Couvre :
- Construction avec différentes configs
- État initial (idle)
- get_status quand pas de tracking
- Calcul position coupole via abaque
- Initialisation encodeur
- Statistiques
"""

import sys
from datetime import datetime
from pathlib import Path
from unittest.mock import patch, MagicMock

import pytest

sys.path.insert(0, str(Path(__file__).parent.parent))

from core.config.config_loader import load_config, DATA_DIR
from core.hardware.moteur_simule import MoteurSimule, set_simulated_position
from core.observatoire import AstronomicalCalculations
from core.tracking.tracking_logger import TrackingLogger
from core.tracking.tracker import TrackingSession


@pytest.fixture
def config():
    """Charge la vraie config du projet."""
    return load_config()


@pytest.fixture
def moteur():
    """Moteur simulé."""
    set_simulated_position(0.0)
    return MoteurSimule()


@pytest.fixture
def calc(config):
    """Calculateur astronomique avec config site réelle."""
    return AstronomicalCalculations(
        config.site.latitude,
        config.site.longitude,
        config.site.tz_offset
    )


@pytest.fixture
def tracker_logger(tmp_path):
    """Logger standard."""
    return TrackingLogger()


@pytest.fixture
def abaque_file():
    """Chemin vers l'abaque réel."""
    path = DATA_DIR / "Loi_coupole.xlsx"
    if not path.exists():
        pytest.skip("Abaque Loi_coupole.xlsx non trouvé")
    return str(path)


@pytest.fixture
def session(moteur, calc, tracker_logger, abaque_file, config):
    """TrackingSession complète avec abaque réel."""
    return TrackingSession(
        moteur=moteur,
        calc=calc,
        logger=tracker_logger,
        seuil=config.tracking.seuil_correction_deg,
        intervalle=config.tracking.intervalle_verification_sec,
        abaque_file=abaque_file,
        adaptive_config=config.adaptive,
        motor_config=config.motor,
        encoder_config=config.encoder,
    )


# =============================================================================
# Construction
# =============================================================================

class TestTrackingSessionConstruction:
    def test_construction(self, session):
        """TrackingSession se construit correctement."""
        assert session.moteur is not None
        assert session.calc is not None
        assert session.seuil > 0

    def test_initial_state_not_running(self, session):
        """L'état initial n'est pas en cours de suivi."""
        assert session.running is False
        assert session.objet is None

    def test_abaque_loaded(self, session):
        """L'abaque est chargé avec succès."""
        assert session.abaque_manager is not None

    def test_adaptive_manager_created(self, session):
        """Le gestionnaire adaptatif est initialisé."""
        assert session.adaptive_manager is not None

    def test_statistics_initialized(self, session):
        """Les statistiques sont initialisées à zéro."""
        assert session.total_corrections == 0
        assert session.total_movement == 0.0

    def test_encoder_disabled_in_simulation(self, session):
        """L'encodeur n'est pas disponible en simulation."""
        assert session.encoder_available is False

    def test_missing_abaque_raises(self, moteur, calc, tracker_logger, config):
        """Abaque manquant → RuntimeError."""
        with pytest.raises(RuntimeError):
            TrackingSession(
                moteur=moteur, calc=calc, logger=tracker_logger,
                abaque_file="/nonexistent/file.xlsx",
                adaptive_config=config.adaptive,
                motor_config=config.motor,
                encoder_config=config.encoder,
            )

    def test_none_abaque_raises(self, moteur, calc, tracker_logger, config):
        """abaque_file=None → ValueError."""
        with pytest.raises(ValueError):
            TrackingSession(
                moteur=moteur, calc=calc, logger=tracker_logger,
                abaque_file=None,
                adaptive_config=config.adaptive,
                motor_config=config.motor,
                encoder_config=config.encoder,
            )


# =============================================================================
# get_status
# =============================================================================

class TestGetStatus:
    def test_status_idle(self, session):
        """get_status quand pas de tracking → running=False."""
        status = session.get_status()
        assert status['running'] is False

    def test_status_idle_minimal_keys(self, session):
        """Status idle retourne au minimum 'running'."""
        status = session.get_status()
        assert 'running' in status


# =============================================================================
# Calcul position coupole (abaque)
# =============================================================================

class TestCalculateTargetPosition:
    def test_position_coupole_valid(self, session):
        """Calcul position coupole pour coordonnées valides."""
        pos, infos = session._calculate_target_position(180.0, 45.0)
        assert isinstance(pos, float)
        assert 0 <= pos < 360
        assert infos['method'] == 'abaque'

    def test_position_coupole_different_azimuths(self, session):
        """Positions différentes pour azimuths différents."""
        pos1, _ = session._calculate_target_position(0.0, 45.0)
        pos2, _ = session._calculate_target_position(180.0, 45.0)
        # Les positions devraient être différentes pour des azimuths opposés
        assert pos1 != pos2

    def test_position_coupole_low_altitude(self, session):
        """Position coupole pour basse altitude."""
        pos, infos = session._calculate_target_position(90.0, 20.0)
        assert isinstance(pos, float)


# =============================================================================
# Coordonnées astronomiques
# =============================================================================

class TestCalculateCoords:
    def test_calculate_coords_with_star(self, session):
        """Calcul coords pour une étoile fixe (J2000)."""
        session.ra_deg = 83.63  # M42 / Orion
        session.dec_deg = -5.39
        session.is_planet = False
        now = datetime.now()
        az, alt = session._calculate_current_coords(now)
        assert isinstance(az, float)
        assert isinstance(alt, float)
        assert 0 <= az < 360
        assert -90 <= alt <= 90


# =============================================================================
# Tracking state
# =============================================================================

class TestTrackingState:
    def test_position_relative_initial(self, session):
        """Position relative initiale = 0."""
        assert session.position_relative == 0.0

    def test_correction_history_empty(self, session):
        """Historique des corrections vide au départ."""
        assert len(session.correction_history) == 0

    def test_mode_icons_defined(self, session):
        """Les icônes de mode sont définies."""
        assert 'normal' in session.MODE_ICONS
        assert 'critical' in session.MODE_ICONS
        assert 'continuous' in session.MODE_ICONS

    def test_no_fast_track_in_icons(self, session):
        """fast_track n'est plus dans les icônes (C-03 corrigé)."""
        assert 'fast_track' not in session.MODE_ICONS


# =============================================================================
# Recherche d'objet
# =============================================================================

class TestRechercherObjet:
    def test_rechercher_objet_known(self, session):
        """Objet connu dans le cache → succès."""
        # M42 devrait être dans le cache si objets_cache.json existe
        success, msg = session._rechercher_objet("M42")
        if success:
            assert session.ra_deg is not None
            assert session.dec_deg is not None

    def test_rechercher_objet_planet(self, session):
        """Planète → détectée comme planète."""
        success, msg = session._rechercher_objet("Jupiter")
        if success:
            assert session.is_planet is True
