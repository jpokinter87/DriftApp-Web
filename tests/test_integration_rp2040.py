"""
Tests d'integration pour le flux RP2040 complet.

Verifie le flux config → MoteurRP2040 → communication serie → fallback GPIO.
Couvre l'integration motor_service avec le driver RP2040 en mode simulation.
"""

import json

import pytest

from core.config.config_loader import ConfigLoader
from core.hardware.moteur_rp2040 import MoteurRP2040
from core.hardware.serial_simulator import SerialSimulator


# ============================================================================
# FIXTURES
# ============================================================================

@pytest.fixture
def rp2040_config_file(tmp_path):
    """Config temporaire avec motor_driver type=rp2040."""
    config_data = {
        "site": {"latitude": 44.15, "longitude": 5.23, "altitude": 800,
                 "nom": "Test Obs", "fuseau": "Europe/Paris"},
        "motor_driver": {
            "type": "rp2040",
            "serial": {"port": "/dev/ttyACM0", "baudrate": 115200, "timeout": 2.0},
        },
        "moteur": {"gpio_pins": {"dir": 17, "step": 18},
                   "steps_per_revolution": 200, "microsteps": 4,
                   "gear_ratio": 2230, "steps_correction_factor": 1.08849,
                   "motor_delay_base": 0.002},
        "suivi": {"seuil_correction_deg": 0.5,
                  "intervalle_verification_sec": 60,
                  "abaque_file": "data/Loi_coupole.xlsx"},
        "encodeur": {"enabled": False, "spi": {"bus": 0, "device": 0,
                     "speed_hz": 1000000, "mode": 0},
                     "mecanique": {"wheel_diameter_mm": 50,
                     "ring_diameter_mm": 2303, "counts_per_rev": 1024},
                     "calibration_factor": 0.01},
    }
    config_file = tmp_path / "config.json"
    config_file.write_text(json.dumps(config_data))
    return config_file


@pytest.fixture
def config_no_motor_driver(tmp_path):
    """Config temporaire sans section motor_driver (defaut rp2040)."""
    config_data = {
        "site": {"latitude": 44.15, "longitude": 5.23, "altitude": 800,
                 "nom": "Test Obs", "fuseau": "Europe/Paris"},
        "moteur": {"gpio_pins": {"dir": 17, "step": 18},
                   "steps_per_revolution": 200, "microsteps": 4,
                   "gear_ratio": 2230, "steps_correction_factor": 1.08849,
                   "motor_delay_base": 0.002},
        "suivi": {"seuil_correction_deg": 0.5,
                  "intervalle_verification_sec": 60,
                  "abaque_file": "data/Loi_coupole.xlsx"},
        "encodeur": {"enabled": False, "spi": {"bus": 0, "device": 0,
                     "speed_hz": 1000000, "mode": 0},
                     "mecanique": {"wheel_diameter_mm": 50,
                     "ring_diameter_mm": 2303, "counts_per_rev": 1024},
                     "calibration_factor": 0.01},
    }
    config_file = tmp_path / "config.json"
    config_file.write_text(json.dumps(config_data))
    return config_file


# ============================================================================
# TESTS FLUX COMPLET
# ============================================================================

class TestFullFlowRP2040:
    """Tests du flux complet config → MoteurRP2040 → serie."""

    def test_full_flow_rp2040_simulation(self, rp2040_config_file):
        """Flux complet : config rp2040 → MoteurRP2040 → rotation → stop → nettoyer."""
        # 1. Charger config
        config = ConfigLoader(rp2040_config_file).load()
        assert config.motor_driver.type == "rp2040"

        # 2. Instancier avec SerialSimulator
        sim = SerialSimulator()
        moteur = MoteurRP2040(config.motor, sim)

        # 3. Verifier steps_per_dome_revolution
        expected = int(200 * 4 * 2230 * 1.08849)
        assert moteur.steps_per_dome_revolution == expected

        # 4. Capturer les commandes
        commands = []
        original_write = sim.write

        def capture(data):
            commands.append(data.decode("utf-8").strip())
            return original_write(data)

        sim.write = capture

        # 5. Rotation → MOVE envoye
        moteur.rotation(45.0, 0.002, use_ramp=True)
        move_cmds = [c for c in commands if c.startswith("MOVE")]
        assert len(move_cmds) == 1
        parts = move_cmds[0].split()
        assert parts[4] == "SCURVE"

        # 6. Stop → STOP envoye
        commands.clear()
        moteur.request_stop()
        stop_cmds = [c for c in commands if c == "STOP"]
        assert len(stop_cmds) == 1

        # 7. Nettoyer → port ferme
        moteur.nettoyer()
        assert not sim.is_open

    def test_full_flow_no_motor_driver_defaults_rp2040(self, config_no_motor_driver):
        """Config sans motor_driver → type rp2040 par defaut."""
        config = ConfigLoader(config_no_motor_driver).load()
        assert config.motor_driver.type == "rp2040"
        assert config.motor_driver.serial.port == "/dev/ttyACM0"

    def test_rotation_absolue_integration(self, rp2040_config_file):
        """rotation_absolue calcule le chemin le plus court via serie."""
        config = ConfigLoader(rp2040_config_file).load()
        sim = SerialSimulator()
        moteur = MoteurRP2040(config.motor, sim)

        commands = []
        original_write = sim.write

        def capture(data):
            commands.append(data.decode("utf-8").strip())
            return original_write(data)

        sim.write = capture

        # De 350° a 10° → delta +20° (chemin court, direction CW=1)
        moteur.rotation_absolue(10.0, 350.0, 0.002)

        move_cmds = [c for c in commands if c.startswith("MOVE")]
        assert len(move_cmds) == 1
        direction = int(move_cmds[0].split()[2])
        assert direction == 1  # CW

    def test_multiple_rotations_sequence(self, rp2040_config_file):
        """Enchainement de rotations sans erreur."""
        config = ConfigLoader(rp2040_config_file).load()
        sim = SerialSimulator()
        moteur = MoteurRP2040(config.motor, sim)

        # 5 rotations successives
        for angle in [10.0, -20.0, 45.0, -5.0, 180.0]:
            moteur.rotation(angle, 0.002)

        # Pas d'exception = succes
        moteur.nettoyer()


# ============================================================================
# TESTS MOTOR SERVICE INTEGRATION
# ============================================================================

# Ces tests necessitent astropy (via TrackingHandler)
try:
    import astropy  # noqa: F401
    HAS_ASTROPY = True
except ImportError:
    HAS_ASTROPY = False


@pytest.mark.skipif(not HAS_ASTROPY, reason="astropy requis pour MotorService")
class TestMotorServiceRP2040Integration:
    """Tests d'integration MotorService avec driver RP2040."""

    def test_motor_service_rp2040_simulation(self, rp2040_config_file):
        """MotorService instancie MoteurRP2040 en simulation avec config rp2040."""
        from unittest.mock import patch
        from services.motor_service import MotorService

        mock_hw_info = {
            'raspberry_pi': False, 'rpi_model': None,
            'gpio': False, 'gpio_error': 'Non teste',
            'encoder_daemon': False, 'encoder_error': 'Non teste',
            'encoder_position': None, 'daemon_process': False,
            'motor': False, 'motor_error': 'Non teste',
            'spi_available': False, 'spi_devices': [],
            'platform': 'Linux-test', 'machine': 'x86_64', 'system': 'Linux',
        }

        with patch('services.motor_service.HardwareDetector.detect_hardware',
                   return_value=(False, mock_hw_info)), \
             patch('services.motor_service.ConfigLoader') as mock_loader, \
             patch('services.motor_service.IpcManager'), \
             patch('services.motor_service.AdaptiveTrackingManager'):

            # Charger la vraie config depuis le fichier temporaire
            real_config = ConfigLoader(rp2040_config_file).load()
            mock_loader.return_value.load.return_value = real_config

            service = MotorService()

            # Verifier que MoteurRP2040 est instancie (pas MoteurSimule)
            assert isinstance(service.moteur, MoteurRP2040)

            # Verifier que le feedback_controller est un FeedbackController (pas self.moteur)
            from core.hardware.feedback_controller import FeedbackController
            assert isinstance(service.feedback_controller, FeedbackController)

            # Cleanup
            service.moteur.nettoyer()



# ============================================================================
# TESTS FEEDBACK CONTROLLER INTEGRATION
# ============================================================================

class TestFeedbackControllerRP2040:
    """Tests integration FeedbackController avec MoteurRP2040."""

    def test_get_feedback_controller(self, rp2040_config_file):
        """get_feedback_controller() retourne un FeedbackController valide."""
        from unittest.mock import patch, MagicMock
        from core.hardware.feedback_controller import FeedbackController

        config = ConfigLoader(rp2040_config_file).load()
        sim = SerialSimulator()
        moteur = MoteurRP2040(config.motor, sim)

        # Patcher le daemon reader
        mock_reader = MagicMock()
        with patch('core.hardware.moteur_rp2040.get_daemon_reader',
                   return_value=mock_reader):
            controller = moteur.get_feedback_controller()
            assert isinstance(controller, FeedbackController)

        moteur.nettoyer()
