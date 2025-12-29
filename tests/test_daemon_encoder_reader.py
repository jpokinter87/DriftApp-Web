"""
Tests pour le module core/hardware/daemon_encoder_reader.py

Ce module teste le lecteur du démon encodeur et les détections
de données périmées et d'encodeur figé.
"""

import json
import pytest
import time
from pathlib import Path
from unittest.mock import MagicMock, patch

from core.hardware.daemon_encoder_reader import (
    DaemonEncoderReader,
    StaleDataError,
    FrozenEncoderError,
    get_daemon_reader,
    set_daemon_reader,
    reset_daemon_reader
)


# =============================================================================
# FIXTURES
# =============================================================================

@pytest.fixture
def temp_json_file(tmp_path):
    """Crée un fichier JSON temporaire pour les tests."""
    json_file = tmp_path / "ems22_position.json"
    return json_file


@pytest.fixture
def daemon_reader(temp_json_file):
    """Crée un DaemonEncoderReader avec un fichier temporaire."""
    return DaemonEncoderReader(daemon_path=temp_json_file)


def write_json_data(json_file: Path, data: dict):
    """Helper pour écrire des données JSON."""
    json_file.write_text(json.dumps(data))


# =============================================================================
# TESTS BASIQUES
# =============================================================================

class TestDaemonEncoderReaderBasics:
    """Tests pour les fonctions de base."""

    def test_is_available_false_when_no_file(self, daemon_reader):
        """is_available retourne False si fichier n'existe pas."""
        assert daemon_reader.is_available() is False

    def test_is_available_true_when_file_exists(self, daemon_reader, temp_json_file):
        """is_available retourne True si fichier existe."""
        write_json_data(temp_json_file, {"angle": 45.0, "ts": time.time()})
        assert daemon_reader.is_available() is True

    def test_read_raw_returns_none_when_no_file(self, daemon_reader):
        """read_raw retourne None si fichier n'existe pas."""
        assert daemon_reader.read_raw() is None

    def test_read_raw_returns_dict(self, daemon_reader, temp_json_file):
        """read_raw retourne le dict du fichier JSON."""
        data = {"angle": 90.0, "ts": time.time(), "status": "OK"}
        write_json_data(temp_json_file, data)

        result = daemon_reader.read_raw()

        assert result["angle"] == 90.0
        assert result["status"] == "OK"


# =============================================================================
# TESTS READ_ANGLE
# =============================================================================

class TestReadAngle:
    """Tests pour la méthode read_angle."""

    def test_read_angle_success(self, daemon_reader, temp_json_file):
        """read_angle retourne l'angle correct."""
        data = {"angle": 123.5, "ts": time.time(), "status": "OK"}
        write_json_data(temp_json_file, data)

        angle = daemon_reader.read_angle()

        assert angle == pytest.approx(123.5)

    def test_read_angle_normalizes_to_360(self, daemon_reader, temp_json_file):
        """read_angle normalise l'angle entre 0 et 360."""
        data = {"angle": 400.0, "ts": time.time(), "status": "OK"}
        write_json_data(temp_json_file, data)

        angle = daemon_reader.read_angle()

        assert angle == pytest.approx(40.0)

    def test_read_angle_timeout_raises_error(self, daemon_reader):
        """read_angle lève RuntimeError si timeout."""
        with pytest.raises(RuntimeError, match="Démon encodeur non trouvé"):
            daemon_reader.read_angle(timeout_ms=50)

    def test_read_angle_with_spi_status(self, daemon_reader, temp_json_file):
        """read_angle accepte le statut SPI avec warning."""
        data = {"angle": 45.0, "ts": time.time(), "status": "SPI OK"}
        write_json_data(temp_json_file, data)

        angle = daemon_reader.read_angle()

        assert angle == pytest.approx(45.0)


# =============================================================================
# TESTS DÉTECTION DONNÉES PÉRIMÉES
# =============================================================================

class TestStaleDataDetection:
    """Tests pour la détection de données périmées."""

    def test_stale_data_raises_error(self, daemon_reader, temp_json_file):
        """read_angle lève StaleDataError si données trop anciennes."""
        # Timestamp d'il y a 2 secondes
        old_ts = time.time() - 2.0
        data = {"angle": 45.0, "ts": old_ts, "status": "OK"}
        write_json_data(temp_json_file, data)

        with pytest.raises(StaleDataError, match="périmées"):
            daemon_reader.read_angle(max_age_ms=500)

    def test_fresh_data_no_error(self, daemon_reader, temp_json_file):
        """read_angle accepte des données fraîches."""
        data = {"angle": 45.0, "ts": time.time(), "status": "OK"}
        write_json_data(temp_json_file, data)

        # Ne doit pas lever d'exception
        angle = daemon_reader.read_angle(max_age_ms=500)
        assert angle == pytest.approx(45.0)

    def test_max_age_zero_disables_check(self, daemon_reader, temp_json_file):
        """max_age_ms=0 désactive la vérification d'âge."""
        # Timestamp très ancien
        old_ts = time.time() - 100.0
        data = {"angle": 45.0, "ts": old_ts, "status": "OK"}
        write_json_data(temp_json_file, data)

        # Ne doit pas lever d'exception car vérification désactivée
        angle = daemon_reader.read_angle(max_age_ms=0)
        assert angle == pytest.approx(45.0)

    def test_default_max_age_is_500ms(self, daemon_reader, temp_json_file):
        """Le max_age par défaut est 500ms."""
        # Timestamp d'il y a 600ms - doit échouer
        old_ts = time.time() - 0.6
        data = {"angle": 45.0, "ts": old_ts, "status": "OK"}
        write_json_data(temp_json_file, data)

        with pytest.raises(StaleDataError):
            daemon_reader.read_angle()  # Utilise DEFAULT_MAX_AGE_MS


# =============================================================================
# TESTS DÉTECTION ENCODEUR FIGÉ
# =============================================================================

class TestFrozenEncoderDetection:
    """Tests pour la détection d'encodeur figé."""

    def test_frozen_status_raises_error(self, daemon_reader, temp_json_file):
        """read_angle lève FrozenEncoderError si statut FROZEN."""
        data = {
            "angle": 45.0,
            "ts": time.time(),
            "status": "FROZEN",
            "frozen": True,
            "frozen_duration": 5.0
        }
        write_json_data(temp_json_file, data)

        with pytest.raises(FrozenEncoderError, match="figé"):
            daemon_reader.read_angle()

    def test_frozen_error_contains_duration(self, daemon_reader, temp_json_file):
        """FrozenEncoderError contient la durée du blocage."""
        data = {
            "angle": 45.0,
            "ts": time.time(),
            "status": "FROZEN",
            "frozen": True,
            "frozen_duration": 10.5
        }
        write_json_data(temp_json_file, data)

        with pytest.raises(FrozenEncoderError, match="10.5"):
            daemon_reader.read_angle()

    def test_ok_status_no_frozen_error(self, daemon_reader, temp_json_file):
        """Pas d'erreur si statut OK."""
        data = {
            "angle": 45.0,
            "ts": time.time(),
            "status": "OK",
            "frozen": False,
            "frozen_duration": 0
        }
        write_json_data(temp_json_file, data)

        angle = daemon_reader.read_angle()
        assert angle == pytest.approx(45.0)


# =============================================================================
# TESTS READ_STABLE
# =============================================================================

class TestReadStable:
    """Tests pour la méthode read_stable."""

    def test_read_stable_averages_samples(self, daemon_reader, temp_json_file):
        """read_stable moyenne plusieurs échantillons."""
        data = {"angle": 45.0, "ts": time.time(), "status": "OK"}
        write_json_data(temp_json_file, data)

        # Devrait faire 3 lectures par défaut
        angle = daemon_reader.read_stable(num_samples=3, delay_ms=1, stabilization_ms=1)

        assert angle == pytest.approx(45.0)

    def test_read_stable_raises_if_no_data(self, daemon_reader):
        """read_stable lève RuntimeError si aucune donnée."""
        with pytest.raises(RuntimeError, match="Démon encodeur non trouvé"):
            daemon_reader.read_stable(num_samples=3, delay_ms=1, stabilization_ms=1)


# =============================================================================
# TESTS GESTION INSTANCE GLOBALE
# =============================================================================

class TestGlobalInstance:
    """Tests pour la gestion de l'instance globale."""

    def test_get_daemon_reader_creates_instance(self):
        """get_daemon_reader crée une instance si elle n'existe pas."""
        reset_daemon_reader()

        reader = get_daemon_reader()

        assert reader is not None
        assert isinstance(reader, DaemonEncoderReader)

    def test_get_daemon_reader_returns_same_instance(self):
        """get_daemon_reader retourne toujours la même instance."""
        reset_daemon_reader()

        reader1 = get_daemon_reader()
        reader2 = get_daemon_reader()

        assert reader1 is reader2

    def test_set_daemon_reader_replaces_instance(self):
        """set_daemon_reader remplace l'instance globale."""
        mock_reader = MagicMock(spec=DaemonEncoderReader)

        set_daemon_reader(mock_reader)

        assert get_daemon_reader() is mock_reader

        # Cleanup
        reset_daemon_reader()

    def test_reset_daemon_reader_clears_instance(self):
        """reset_daemon_reader remet l'instance à None."""
        get_daemon_reader()  # Crée une instance
        reset_daemon_reader()

        # Devrait créer une nouvelle instance
        reader1 = get_daemon_reader()
        reset_daemon_reader()
        reader2 = get_daemon_reader()

        assert reader1 is not reader2


# =============================================================================
# TESTS EXCEPTIONS
# =============================================================================

class TestExceptions:
    """Tests pour les classes d'exception."""

    def test_stale_data_error_is_runtime_error(self):
        """StaleDataError hérite de RuntimeError."""
        error = StaleDataError("test")
        assert isinstance(error, RuntimeError)

    def test_frozen_encoder_error_is_runtime_error(self):
        """FrozenEncoderError hérite de RuntimeError."""
        error = FrozenEncoderError("test")
        assert isinstance(error, RuntimeError)

    def test_stale_data_error_message(self):
        """StaleDataError conserve le message."""
        error = StaleDataError("Données périmées (1000ms > 500ms)")
        assert "1000ms" in str(error)

    def test_frozen_encoder_error_message(self):
        """FrozenEncoderError conserve le message."""
        error = FrozenEncoderError("Encodeur figé depuis 5.0s")
        assert "5.0s" in str(error)
