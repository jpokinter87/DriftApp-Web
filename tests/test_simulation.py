"""
Tests pour le module Simulation.

Ce module teste le lecteur d'encodeur simulé utilisé en mode développement.
"""

from unittest.mock import patch, MagicMock

import pytest


class TestSimulatedDaemonReader:
    """Tests pour la classe SimulatedDaemonReader."""

    @pytest.fixture
    def reader(self):
        """Crée un SimulatedDaemonReader."""
        from services.simulation import SimulatedDaemonReader
        return SimulatedDaemonReader()

    def test_is_available_always_true(self, reader):
        """Le lecteur simulé est toujours disponible."""
        assert reader.is_available() is True

    def test_read_raw_returns_dict(self, reader):
        """read_raw retourne un dictionnaire avec les bonnes clés."""
        from core.hardware.moteur_simule import set_simulated_position
        set_simulated_position(45.0)

        result = reader.read_raw()

        assert isinstance(result, dict)
        assert 'angle' in result
        assert 'calibrated' in result
        assert 'status' in result
        assert 'raw' in result

    def test_read_raw_calibrated_true(self, reader):
        """read_raw indique toujours calibré en simulation."""
        from core.hardware.moteur_simule import set_simulated_position
        set_simulated_position(0.0)
        result = reader.read_raw()
        assert result['calibrated'] is True

    def test_read_raw_status_simulation(self, reader):
        """read_raw indique le mode simulation dans le status."""
        from core.hardware.moteur_simule import set_simulated_position
        set_simulated_position(0.0)
        result = reader.read_raw()
        assert 'simulation' in result['status'].lower()

    def test_read_angle_returns_position(self, reader):
        """read_angle retourne la position simulée."""
        from core.hardware.moteur_simule import set_simulated_position
        set_simulated_position(123.5)
        result = reader.read_angle(timeout_ms=200)
        assert result == 123.5

    def test_read_angle_ignores_timeout(self, reader):
        """read_angle ignore le paramètre timeout (pas de blocage en simulation)."""
        from core.hardware.moteur_simule import set_simulated_position
        set_simulated_position(90.0)
        # Même avec un timeout court, pas de problème
        result = reader.read_angle(timeout_ms=1)
        assert result == 90.0

    def test_read_status_same_as_read_raw(self, reader):
        """read_status retourne les mêmes données que read_raw."""
        from core.hardware.moteur_simule import set_simulated_position
        set_simulated_position(180.0)
        raw = reader.read_raw()
        status = reader.read_status()
        assert raw == status

    def test_read_stable_returns_angle(self, reader):
        """read_stable retourne la position simulée sans moyennage."""
        from core.hardware.moteur_simule import set_simulated_position
        set_simulated_position(270.0)
        result = reader.read_stable(
            num_samples=5,
            delay_ms=10,
            stabilization_ms=50
        )
        assert result == 270.0

    def test_read_stable_ignores_parameters(self, reader):
        """read_stable ignore les paramètres de stabilisation."""
        from core.hardware.moteur_simule import set_simulated_position
        set_simulated_position(45.0)
        # Tous les paramètres sont ignorés en simulation
        result1 = reader.read_stable(num_samples=1)
        result2 = reader.read_stable(num_samples=100, delay_ms=1000)
        assert result1 == result2 == 45.0


class TestSimulatedPosition:
    """Tests pour la position simulée globale."""

    def test_position_default(self):
        """La position simulée par défaut est 0 (grâce au reset automatique)."""
        from core.hardware.moteur_simule import get_simulated_position
        # Le fixture reset_simulation_state remet à 0 avant chaque test
        assert get_simulated_position() == 0.0

    def test_set_simulated_position(self):
        """set_simulated_position modifie la position globale."""
        from core.hardware.moteur_simule import set_simulated_position, get_simulated_position

        set_simulated_position(123.5)
        assert get_simulated_position() == 123.5

        set_simulated_position(0.0)
        assert get_simulated_position() == 0.0

    def test_position_wraps_at_360(self):
        """La position est normalisée entre 0 et 360°."""
        from core.hardware.moteur_simule import set_simulated_position, get_simulated_position

        set_simulated_position(400.0)
        pos = get_simulated_position()
        assert pos == pytest.approx(40.0, abs=0.01)  # 400 % 360 = 40

    def test_reader_sees_updated_position(self):
        """Le lecteur voit la position mise à jour."""
        from services.simulation import SimulatedDaemonReader
        from core.hardware.moteur_simule import set_simulated_position

        reader = SimulatedDaemonReader()
        set_simulated_position(88.8)

        assert reader.read_angle() == 88.8
