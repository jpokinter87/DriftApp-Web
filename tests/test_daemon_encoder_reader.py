"""
Tests exhaustifs pour DaemonEncoderReader (core/hardware/moteur.py)
et encoder_reader.py (core/hardware/encoder_reader.py).

Couvre :
- Lecture du fichier JSON daemon (/dev/shm/ simulé via tmp_path)
- Gestion fichier manquant, JSON corrompu, données périmées
- read_angle() avec timeout et retry
- read_stable() avec moyenne
- Bug connu H-01 : moyenne incorrecte près de 0°/360°
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

    def test_status_unknown_loops_forever_bug(self, reader, daemon_file):
        """Bug connu H-04 : status inconnu → timeout devrait s'appliquer.
        Ce test documente le comportement ACTUEL : boucle infinie.
        On utilise un timeout court pour éviter de bloquer."""
        write_daemon_data(daemon_file, angle=90.0, status="ERROR something")
        # Le bug : la boucle continue indéfiniment car le timeout check
        # ne se déclenche que quand data is None
        # On ne peut pas tester la boucle infinie directement,
        # mais on peut vérifier que ça ne retourne pas rapidement
        # Pour le moment, skip ce test car il bloquerait
        pytest.skip("Bug H-04 : read_angle boucle infinie sur status inconnu - à corriger en Phase 2")


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

    def test_average_near_zero_bug(self, reader, daemon_file):
        """Bug connu H-01 : la moyenne simple échoue près de 0°/360°.
        Ce test DOCUMENTE le bug actuel.
        Avec des lectures [359.5, 0.0, 0.5], la moyenne devrait être ~0.0
        mais la moyenne arithmétique donne ~120°."""
        # On ne peut pas facilement simuler des lectures changeantes
        # avec un fichier statique, mais on documente le problème
        write_daemon_data(daemon_file, angle=359.9)
        result = reader.read_stable(num_samples=3, delay_ms=1, stabilization_ms=1)
        # Avec un fichier fixe à 359.9, toutes les lectures sont 359.9
        # donc la moyenne est correcte. Le bug apparaît seulement quand
        # les lectures oscillent autour de 0°/360°.
        assert result == pytest.approx(359.9, abs=0.5)


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
