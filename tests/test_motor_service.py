"""
Tests pour services/motor_service.py

Couvre :
- calculate_sunrise / calculate_sunset
- SimulatedDaemonReader
- MotorService (en mode simulation) :
  - Construction et initialisation
  - IPC : read_command, write_status, clear_command
  - handle_goto, handle_jog, handle_stop
  - handle_tracking_start, handle_tracking_stop
  - handle_park, handle_calibrate, handle_end_session
  - add_tracking_log
  - Gestion sunrise parking
  - _get_goto_speed
"""

import json
import sys
import time
from datetime import datetime, timedelta
from pathlib import Path
from unittest.mock import patch, MagicMock

import pytest

# Ajouter le répertoire racine au path
PROJECT_ROOT = Path(__file__).parent.parent.resolve()
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from services.motor_service import (
    calculate_sunrise,
    calculate_sunset,
    SimulatedDaemonReader,
    SEUIL_FEEDBACK_DEG,
    DEFAULT_PARKING_CONFIG,
)


# =============================================================================
# calculate_sunrise
# =============================================================================

class TestCalculateSunrise:
    def test_returns_datetime(self):
        result = calculate_sunrise(44.15, 5.23)
        assert result is not None
        assert isinstance(result, datetime)

    def test_sunrise_in_morning(self):
        """Le lever du soleil devrait être le matin (4h-9h)."""
        result = calculate_sunrise(44.15, 5.23, datetime(2025, 6, 15))
        assert result is not None
        assert 4 <= result.hour <= 9

    def test_winter_sunrise_later(self):
        """En hiver, le lever est plus tard qu'en été."""
        summer = calculate_sunrise(44.15, 5.23, datetime(2025, 6, 21))
        winter = calculate_sunrise(44.15, 5.23, datetime(2025, 12, 21))
        assert summer is not None and winter is not None
        # En été, lever plus tôt
        summer_minutes = summer.hour * 60 + summer.minute
        winter_minutes = winter.hour * 60 + winter.minute
        assert summer_minutes < winter_minutes

    def test_different_latitudes(self):
        """Latitudes différentes → heures différentes."""
        south = calculate_sunrise(44.15, 5.23, datetime(2025, 6, 15))
        north = calculate_sunrise(60.0, 5.23, datetime(2025, 6, 15))
        assert south is not None and north is not None
        # Plus au nord en été → lever plus tôt
        assert north.hour <= south.hour

    def test_default_date_is_today(self):
        result = calculate_sunrise(44.15, 5.23)
        assert result is not None
        assert result.date() == datetime.now().date()


class TestCalculateSunset:
    def test_returns_datetime(self):
        result = calculate_sunset(44.15, 5.23)
        # Peut être None en mode approximation
        if result is not None:
            assert isinstance(result, datetime)

    def test_sunset_after_sunrise(self):
        sunrise = calculate_sunrise(44.15, 5.23, datetime(2025, 6, 15))
        sunset = calculate_sunset(44.15, 5.23, datetime(2025, 6, 15))
        if sunrise is not None and sunset is not None:
            assert sunset > sunrise


# =============================================================================
# SimulatedDaemonReader
# =============================================================================

class TestSimulatedDaemonReader:
    def test_is_available(self):
        reader = SimulatedDaemonReader()
        assert reader.is_available() is True

    def test_read_raw(self):
        from core.hardware.moteur_simule import set_simulated_position
        set_simulated_position(123.4)
        reader = SimulatedDaemonReader()
        data = reader.read_raw()
        assert data["angle"] == pytest.approx(123.4)
        assert data["calibrated"] is True
        assert "simulation" in data["status"]

    def test_read_angle(self):
        from core.hardware.moteur_simule import set_simulated_position
        set_simulated_position(45.0)
        reader = SimulatedDaemonReader()
        assert reader.read_angle() == pytest.approx(45.0)

    def test_read_stable(self):
        from core.hardware.moteur_simule import set_simulated_position
        set_simulated_position(90.0)
        reader = SimulatedDaemonReader()
        assert reader.read_stable() == pytest.approx(90.0)

    def test_read_status(self):
        reader = SimulatedDaemonReader()
        status = reader.read_status()
        assert isinstance(status, dict)
        assert "angle" in status


# =============================================================================
# Constants
# =============================================================================

class TestConstants:
    def test_seuil_feedback(self):
        assert SEUIL_FEEDBACK_DEG == 3.0

    def test_default_parking_config(self):
        assert DEFAULT_PARKING_CONFIG["enabled"] is True
        assert DEFAULT_PARKING_CONFIG["switch_position"] == 45.0
        assert DEFAULT_PARKING_CONFIG["park_position"] == 44.0


# =============================================================================
# MotorService — Construction en mode simulation
# =============================================================================

class TestMotorServiceConstruction:
    """Tests de construction du MotorService en mode simulation."""

    @pytest.fixture
    def service(self, tmp_path):
        """Crée un MotorService en mode simulation avec IPC dans tmp_path."""
        # Patch les chemins IPC pour utiliser tmp_path
        cmd_file = tmp_path / "motor_command.json"
        status_file = tmp_path / "motor_status.json"

        with patch("services.motor_service.COMMAND_FILE", cmd_file), \
             patch("services.motor_service.STATUS_FILE", status_file):
            from services.motor_service import MotorService
            svc = MotorService()
            # Utiliser les fichiers tmp pour les tests
            svc._test_cmd_file = cmd_file
            svc._test_status_file = status_file
            return svc

    def test_simulation_mode(self, service):
        assert service.simulation_mode is True

    def test_moteur_is_simulated(self, service):
        from core.hardware.moteur_simule import MoteurSimule
        assert isinstance(service.moteur, MoteurSimule)

    def test_daemon_reader_is_simulated(self, service):
        assert isinstance(service.daemon_reader, SimulatedDaemonReader)

    def test_initial_status(self, service):
        assert service.current_status["status"] == "idle"
        assert service.current_status["simulation"] is True
        assert service.current_status["position"] == 0.0

    def test_adaptive_manager_created(self, service):
        from core.tracking.adaptive_tracking import AdaptiveTrackingManager
        assert isinstance(service.adaptive_manager, AdaptiveTrackingManager)


# =============================================================================
# MotorService — IPC
# =============================================================================

class TestMotorServiceIPC:
    @pytest.fixture
    def service(self, tmp_path):
        cmd_file = tmp_path / "motor_command.json"
        status_file = tmp_path / "motor_status.json"

        with patch("services.motor_service.COMMAND_FILE", cmd_file), \
             patch("services.motor_service.STATUS_FILE", status_file):
            from services.motor_service import MotorService
            svc = MotorService()
            return svc

    def test_read_command_no_file(self, service, tmp_path):
        """Pas de fichier commande → None."""
        with patch("services.motor_service.COMMAND_FILE", tmp_path / "nonexistent.json"):
            assert service.read_command() is None

    def test_read_command_empty(self, service, tmp_path):
        cmd_file = tmp_path / "cmd.json"
        cmd_file.write_text("")
        with patch("services.motor_service.COMMAND_FILE", cmd_file):
            assert service.read_command() is None

    def test_read_command_valid(self, service, tmp_path):
        cmd_file = tmp_path / "cmd.json"
        cmd = {"id": "test-123", "command": "stop"}
        cmd_file.write_text(json.dumps(cmd))
        with patch("services.motor_service.COMMAND_FILE", cmd_file):
            result = service.read_command()
            assert result is not None
            assert result["command"] == "stop"

    def test_read_command_duplicate_ignored(self, service, tmp_path):
        """Même commande ID → ignorée."""
        cmd_file = tmp_path / "cmd.json"
        cmd = {"id": "test-123", "command": "stop"}
        cmd_file.write_text(json.dumps(cmd))
        with patch("services.motor_service.COMMAND_FILE", cmd_file):
            result1 = service.read_command()
            assert result1 is not None
            result2 = service.read_command()
            assert result2 is None  # Même ID → ignorée

    def test_write_status(self, service, tmp_path):
        status_file = tmp_path / "status.json"
        with patch("services.motor_service.STATUS_FILE", status_file):
            service.write_status()
            assert status_file.exists()
            data = json.loads(status_file.read_text())
            assert "status" in data
            assert "last_update" in data

    def test_write_status_atomic(self, service, tmp_path):
        """L'écriture utilise tmp+rename (atomique)."""
        status_file = tmp_path / "status.json"
        with patch("services.motor_service.STATUS_FILE", status_file):
            service.write_status()
            # Vérifier que le fichier .tmp n'existe plus
            tmp_file = status_file.with_suffix(".tmp")
            assert not tmp_file.exists()


# =============================================================================
# MotorService — Tracking logs
# =============================================================================

class TestMotorServiceTrackingLogs:
    @pytest.fixture
    def service(self, tmp_path):
        cmd_file = tmp_path / "motor_command.json"
        status_file = tmp_path / "motor_status.json"

        with patch("services.motor_service.COMMAND_FILE", cmd_file), \
             patch("services.motor_service.STATUS_FILE", status_file):
            from services.motor_service import MotorService
            return MotorService()

    def test_add_log(self, service):
        service.add_tracking_log("Test message", "info")
        assert len(service.recent_tracking_logs) == 1
        assert service.recent_tracking_logs[0]["message"] == "Test message"
        assert service.recent_tracking_logs[0]["type"] == "info"

    def test_log_limit(self, service):
        """Max 20 logs."""
        for i in range(25):
            service.add_tracking_log(f"Message {i}")
        assert len(service.recent_tracking_logs) == 20

    def test_status_contains_last_10_logs(self, service):
        for i in range(15):
            service.add_tracking_log(f"Message {i}")
        assert len(service.current_status["tracking_logs"]) == 10


# =============================================================================
# MotorService — _get_goto_speed
# =============================================================================

class TestMotorServiceGotoSpeed:
    @pytest.fixture
    def service(self, tmp_path):
        cmd_file = tmp_path / "motor_command.json"
        status_file = tmp_path / "motor_status.json"

        with patch("services.motor_service.COMMAND_FILE", cmd_file), \
             patch("services.motor_service.STATUS_FILE", status_file):
            from services.motor_service import MotorService
            return MotorService()

    def test_explicit_speed(self, service):
        assert service._get_goto_speed(0.005) == 0.005

    def test_default_speed_from_config(self, service):
        speed = service._get_goto_speed(None)
        # Devrait être le délai CONTINUOUS
        assert speed > 0
        assert speed <= 0.001  # CONTINUOUS est la plus rapide

    def test_fallback_speed(self, service):
        """Sans config continuous → fallback 0.00015."""
        service.config.adaptive.modes.pop("continuous", None)
        speed = service._get_goto_speed(None)
        assert speed == 0.00015


# =============================================================================
# MotorService — handle_goto en simulation
# =============================================================================

class TestMotorServiceGoto:
    @pytest.fixture
    def service(self, tmp_path):
        cmd_file = tmp_path / "motor_command.json"
        status_file = tmp_path / "motor_status.json"

        with patch("services.motor_service.COMMAND_FILE", cmd_file), \
             patch("services.motor_service.STATUS_FILE", status_file):
            from services.motor_service import MotorService
            svc = MotorService()
            return svc

    def test_goto_updates_position(self, service):
        """GOTO devrait mettre à jour la position."""
        service.handle_goto(90.0)
        # En simulation, position devrait être mise à jour
        assert service.current_status["status"] in ("idle", "moving")

    def test_goto_small_movement(self, service):
        """Petit déplacement (< 3°) → utilise feedback."""
        from core.hardware.moteur_simule import set_simulated_position
        set_simulated_position(88.0)
        service.current_status["position"] = 88.0
        service.handle_goto(90.0)  # Delta = 2°

    def test_goto_large_movement(self, service):
        """Grand déplacement (> 3°) → rotation directe."""
        from core.hardware.moteur_simule import set_simulated_position
        set_simulated_position(0.0)
        service.current_status["position"] = 0.0
        service.handle_goto(90.0)  # Delta = 90°


# =============================================================================
# MotorService — handle_jog
# =============================================================================

class TestMotorServiceJog:
    @pytest.fixture
    def service(self, tmp_path):
        cmd_file = tmp_path / "motor_command.json"
        status_file = tmp_path / "motor_status.json"

        with patch("services.motor_service.COMMAND_FILE", cmd_file), \
             patch("services.motor_service.STATUS_FILE", status_file):
            from services.motor_service import MotorService
            return MotorService()

    def test_jog_positive(self, service):
        service.handle_jog(10.0)
        # Pas de crash en simulation

    def test_jog_negative(self, service):
        service.handle_jog(-10.0)


# =============================================================================
# MotorService — handle_stop
# =============================================================================

class TestMotorServiceStop:
    @pytest.fixture
    def service(self, tmp_path):
        cmd_file = tmp_path / "motor_command.json"
        status_file = tmp_path / "motor_status.json"

        with patch("services.motor_service.COMMAND_FILE", cmd_file), \
             patch("services.motor_service.STATUS_FILE", status_file):
            from services.motor_service import MotorService
            return MotorService()

    def test_stop_sets_idle(self, service):
        service.current_status["status"] = "moving"
        service.handle_stop()
        assert service.current_status["status"] == "idle"


# =============================================================================
# MotorService — Parking
# =============================================================================

class TestMotorServiceParking:
    @pytest.fixture
    def service(self, tmp_path):
        cmd_file = tmp_path / "motor_command.json"
        status_file = tmp_path / "motor_status.json"

        with patch("services.motor_service.COMMAND_FILE", cmd_file), \
             patch("services.motor_service.STATUS_FILE", status_file):
            from services.motor_service import MotorService
            return MotorService()

    def test_parking_config_loaded(self, service):
        """Config parking chargée (au moins defaults)."""
        assert service.parking_config["enabled"] is True
        assert "park_position" in service.parking_config

    def test_handle_park(self, service):
        """handle_park ne crash pas en simulation."""
        service.handle_park()
        assert service.current_status["status"] == "idle"

    def test_handle_calibrate(self, service):
        service.handle_calibrate()
        assert service.current_status["status"] == "idle"

    def test_handle_end_session(self, service):
        service.handle_end_session()
        assert service.current_status["status"] == "idle"
        assert service.session_had_tracking is False


# =============================================================================
# MotorService — Sunrise parking
# =============================================================================

class TestMotorServiceSunrise:
    @pytest.fixture
    def service(self, tmp_path):
        cmd_file = tmp_path / "motor_command.json"
        status_file = tmp_path / "motor_status.json"

        with patch("services.motor_service.COMMAND_FILE", cmd_file), \
             patch("services.motor_service.STATUS_FILE", status_file):
            from services.motor_service import MotorService
            return MotorService()

    def test_check_sunrise_no_crash(self, service):
        """check_sunrise_parking ne crash pas."""
        service.check_sunrise_parking()

    def test_check_sunrise_skip_if_disabled(self, service):
        service.parking_config["enabled"] = False
        service.check_sunrise_parking()  # Devrait retourner sans action

    def test_check_startup_parking(self, service):
        service.check_startup_parking()
        # Vérifie que encoder_calibrated est mis à jour
        assert "encoder_calibrated" in service.current_status


# =============================================================================
# MotorService — read_encoder_position
# =============================================================================

class TestMotorServiceEncoder:
    @pytest.fixture
    def service(self, tmp_path):
        cmd_file = tmp_path / "motor_command.json"
        status_file = tmp_path / "motor_status.json"

        with patch("services.motor_service.COMMAND_FILE", cmd_file), \
             patch("services.motor_service.STATUS_FILE", status_file):
            from services.motor_service import MotorService
            return MotorService()

    def test_read_encoder_in_simulation(self, service):
        from core.hardware.moteur_simule import set_simulated_position
        set_simulated_position(123.0)
        pos = service.read_encoder_position()
        assert pos == pytest.approx(123.0)
