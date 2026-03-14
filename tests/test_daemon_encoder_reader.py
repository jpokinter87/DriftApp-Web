"""
Tests exhaustifs pour DaemonEncoderReader (core/hardware/moteur.py)
et encoder_reader.py (core/hardware/encoder_reader.py).

Couvre :
- Lecture du fichier JSON daemon (/dev/shm/ simulé via tmp_path)
- Gestion fichier manquant, JSON corrompu, données périmées
- read_angle() avec timeout et retry
- read_stable() avec moyenne
- H-01 corrigé : moyenne circulaire pour 0°/360°
- H-04 corrigé : timeout sur statut inconnu
"""

import json
import time

import pytest

from core.hardware.moteur import DaemonEncoderReader


@pytest.fixture
def daemon_file(tmp_path):
    """Crée un fichier daemon JSON temporaire."""
    return tmp_path / "ems22_position.json"


@pytest.fixture
def reader(daemon_file):
    """Crée un DaemonEncoderReader pointant vers le fichier temporaire."""
    return DaemonEncoderReader(daemon_path=daemon_file)


def write_daemon_data(daemon_file, angle=45.0, status="OK", calibrated=True):
    """Helper pour écrire des données daemon."""
    data = {
        "ts": time.time(),
        "angle": angle,
        "raw": 512,
        "status": status,
        "calibrated": calibrated,
    }
    daemon_file.write_text(json.dumps(data))


# =============================================================================
# is_available
# =============================================================================

class TestDaemonIsAvailable:
    def test_file_exists(self, reader, daemon_file):
        write_daemon_data(daemon_file)
        assert reader.is_available() is True

    def test_file_missing(self, reader):
        assert reader.is_available() is False


# =============================================================================
# read_raw
# =============================================================================

class TestDaemonReadRaw:
    def test_valid_json(self, reader, daemon_file):
        write_daemon_data(daemon_file, angle=123.4)
        data = reader.read_raw()
        assert data is not None
        assert data["angle"] == 123.4

    def test_file_missing(self, reader):
        assert reader.read_raw() is None

    def test_invalid_json(self, reader, daemon_file):
        daemon_file.write_text("{bad json")
        assert reader.read_raw() is None

    def test_empty_file(self, reader, daemon_file):
        daemon_file.write_text("")
        assert reader.read_raw() is None


# =============================================================================
# read_angle
# =============================================================================

class TestDaemonReadAngle:
    def test_normal_read(self, reader, daemon_file):
        write_daemon_data(daemon_file, angle=45.0)
        assert reader.read_angle() == pytest.approx(45.0)

    def test_angle_normalized_to_360(self, reader, daemon_file):
        write_daemon_data(daemon_file, angle=370.0)
        assert reader.read_angle() == pytest.approx(10.0)

    def test_status_ok(self, reader, daemon_file):
        write_daemon_data(daemon_file, angle=90.0, status="OK")
        assert reader.read_angle() == pytest.approx(90.0)

    def test_status_spi_warning(self, reader, daemon_file):
        """Status SPI → retourne quand même l'angle."""
        write_daemon_data(daemon_file, angle=90.0, status="SPI WARNING")
        assert reader.read_angle() == pytest.approx(90.0)

    def test_file_missing_timeout(self, reader):
        """Fichier manquant → RuntimeError après timeout."""
        with pytest.raises(RuntimeError, match="Démon encodeur non trouvé"):
            reader.read_angle(timeout_ms=50)

    def test_status_unknown_returns_after_timeout(self, reader, daemon_file):
        """H-04 corrigé : statut inconnu → retourne l'angle après timeout."""
        write_daemon_data(daemon_file, angle=90.0, status="CALIBRATING")
        # Doit retourner l'angle au lieu de boucler indéfiniment
        result = reader.read_angle(timeout_ms=50)
        assert result == pytest.approx(90.0)

    def test_status_error_returns_after_timeout(self, reader, daemon_file):
        """H-04 : statut ERROR → retourne l'angle après timeout."""
        write_daemon_data(daemon_file, angle=45.0, status="ERROR something")
        result = reader.read_angle(timeout_ms=50)
        assert result == pytest.approx(45.0)


# =============================================================================
# read_stable
# =============================================================================

class TestDaemonReadStable:
    def test_stable_reading(self, reader, daemon_file):
        write_daemon_data(daemon_file, angle=45.0)
        result = reader.read_stable(num_samples=3, delay_ms=1, stabilization_ms=1)
        assert result == pytest.approx(45.0, abs=0.1)

    def test_file_missing_raises(self, reader):
        with pytest.raises(RuntimeError):
            reader.read_stable(num_samples=3, delay_ms=1, stabilization_ms=1)

    def test_circular_mean_near_zero(self, reader, daemon_file, monkeypatch):
        """H-01 corrigé : moyenne circulaire correcte près de 0°/360°.
        [359.5, 0.2, 0.5] → ~0.07° (pas ~120°)."""
        readings = iter([359.5, 0.2, 0.5])

        def mock_read_angle(timeout_ms=200):
            return next(readings)

        monkeypatch.setattr(reader, "read_angle", mock_read_angle)
        result = reader.read_stable(num_samples=3, delay_ms=1, stabilization_ms=1)
        # Moyenne circulaire : doit être proche de 0° (pas 120°)
        assert result == pytest.approx(0.07, abs=0.5)

    def test_circular_mean_normal_range(self, reader, daemon_file, monkeypatch):
        """H-01 : moyenne circulaire fonctionne aussi pour les cas normaux."""
        readings = iter([10.0, 11.0, 12.0])

        def mock_read_angle(timeout_ms=200):
            return next(readings)

        monkeypatch.setattr(reader, "read_angle", mock_read_angle)
        result = reader.read_stable(num_samples=3, delay_ms=1, stabilization_ms=1)
        assert result == pytest.approx(11.0, abs=0.1)

    def test_stable_reading_near_180(self, reader, daemon_file, monkeypatch):
        """Moyenne circulaire correcte aussi autour de 180°."""
        readings = iter([179.0, 180.0, 181.0])

        def mock_read_angle(timeout_ms=200):
            return next(readings)

        monkeypatch.setattr(reader, "read_angle", mock_read_angle)
        result = reader.read_stable(num_samples=3, delay_ms=1, stabilization_ms=1)
        assert result == pytest.approx(180.0, abs=0.1)


# =============================================================================
# read_status
# =============================================================================

class TestDaemonReadStatus:
    def test_returns_full_data(self, reader, daemon_file):
        write_daemon_data(daemon_file, angle=45.0, calibrated=True)
        status = reader.read_status()
        assert status is not None
        assert "angle" in status
        assert "calibrated" in status

    def test_file_missing(self, reader):
        assert reader.read_status() is None


# =============================================================================
# encoder_reader.py (module séparé)
# =============================================================================

class TestEncoderReaderModule:
    """Tests pour core/hardware/encoder_reader.py (module potentiellement obsolète)."""

    def test_import(self):
        from core.hardware.encoder_reader import read_encoder_daemon
        assert callable(read_encoder_daemon)

    def test_file_missing(self):
        from core.hardware.encoder_reader import read_encoder_daemon
        # Avec le path par défaut /dev/shm/ qui n'existe probablement pas en dev
        angle, status_ok, ts = read_encoder_daemon()
        # Sur machine de dev sans daemon, angle = None
        assert angle is None or isinstance(angle, float)
        assert isinstance(status_ok, bool)
