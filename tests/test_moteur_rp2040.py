"""
Tests unitaires pour MoteurRP2040 et SerialSimulator.

Verifie la communication serie, le parsing des reponses,
le fallback config GPIO/RP2040, et la compatibilite d'interface.
"""

import json
import logging

import pytest

from core.hardware.moteur_rp2040 import MoteurRP2040
from core.hardware.serial_simulator import SerialSimulator
from core.config.config_loader import ConfigLoader


# ============================================================================
# FIXTURES
# ============================================================================

@pytest.fixture
def motor_config():
    """Config moteur standard du projet (dict format)."""
    return {
        "gpio_pins": {"dir": 17, "step": 18},
        "steps_per_revolution": 200,
        "microsteps": 4,
        "gear_ratio": 2230,
        "steps_correction_factor": 1.08849,
        "motor_delay_base": 0.002,
    }


@pytest.fixture
def serial_sim():
    """Instance de SerialSimulator."""
    return SerialSimulator()


@pytest.fixture
def moteur_rp2040(motor_config, serial_sim):
    """Instance de MoteurRP2040 avec simulateur serie."""
    return MoteurRP2040(motor_config, serial_sim)


# ============================================================================
# TESTS SerialSimulator
# ============================================================================

class TestSerialSimulator:
    """Tests pour le simulateur serie."""

    def test_ready_on_init(self, serial_sim):
        """Le simulateur envoie READY au demarrage."""
        response = serial_sim.readline()
        assert response == b"READY\n"

    def test_move_command_response(self, serial_sim):
        """MOVE retourne OK avec le nombre de pas."""
        # Consommer le READY initial
        serial_sim.readline()

        serial_sim.write(b"MOVE 1000 1 2000 SCURVE\n")
        response = serial_sim.readline()
        assert response == b"OK 1000\n"

    def test_stop_command_response(self, serial_sim):
        """STOP retourne IDLE."""
        serial_sim.readline()  # READY
        serial_sim.write(b"STOP\n")
        response = serial_sim.readline()
        assert response == b"IDLE\n"

    def test_status_command_response(self, serial_sim):
        """STATUS retourne IDLE."""
        serial_sim.readline()  # READY
        serial_sim.write(b"STATUS\n")
        response = serial_sim.readline()
        assert response == b"IDLE\n"

    def test_unknown_command_response(self, serial_sim):
        """Commande inconnue retourne ERROR."""
        serial_sim.readline()  # READY
        serial_sim.write(b"FOOBAR\n")
        response = serial_sim.readline()
        assert response == b"ERROR unknown_command\n"

    def test_invalid_move_response(self, serial_sim):
        """MOVE sans arguments retourne ERROR."""
        serial_sim.readline()  # READY
        serial_sim.write(b"MOVE\n")
        response = serial_sim.readline()
        assert response == b"ERROR invalid_command\n"

    def test_close(self, serial_sim):
        """close() ferme le port."""
        serial_sim.close()
        assert not serial_sim.is_open

    def test_write_after_close_raises(self, serial_sim):
        """Ecrire apres close() leve IOError."""
        serial_sim.close()
        with pytest.raises(IOError):
            serial_sim.write(b"STATUS\n")

    def test_context_manager(self):
        """Le simulateur fonctionne comme context manager."""
        with SerialSimulator() as sim:
            assert sim.is_open
        assert not sim.is_open


# ============================================================================
# TESTS MoteurRP2040
# ============================================================================

class TestMoteurRP2040Init:
    """Tests d'initialisation de MoteurRP2040."""

    def test_init_steps_per_dome_revolution(self, moteur_rp2040):
        """Verifie le calcul de steps_per_dome_revolution."""
        expected = int(200 * 4 * 2230 * 1.08849)
        assert moteur_rp2040.steps_per_dome_revolution == expected

    def test_init_waits_for_ready(self, motor_config):
        """L'init attend READY du firmware."""
        sim = SerialSimulator()
        # SerialSimulator met READY dans le buffer → l'init doit le consommer
        moteur = MoteurRP2040(motor_config, sim)
        # Si on arrive ici sans TimeoutError, READY a ete recu
        assert moteur.steps_per_dome_revolution > 0

    def test_init_fallback_status_when_no_ready(self, motor_config):
        """Fallback via STATUS si READY manque (Pico deja demarre)."""
        sim = SerialSimulator()
        # Vider le buffer READY pour simuler un Pico deja boote
        sim.readline()

        # Le constructeur envoie STATUS en fallback et accepte IDLE
        moteur = MoteurRP2040(motor_config, sim)
        assert moteur.steps_per_dome_revolution > 0

    def test_init_timeout_without_any_response(self, motor_config):
        """TimeoutError si le firmware ne repond pas du tout."""
        sim = SerialSimulator()
        sim.readline()  # Vider READY
        sim.close()     # Fermer pour empecher toute reponse

        with pytest.raises((TimeoutError, IOError)):
            MoteurRP2040(motor_config, sim)


class TestMoteurRP2040Rotation:
    """Tests de rotation."""

    def test_rotation_sends_move_command(self, moteur_rp2040, serial_sim):
        """rotation() envoie la bonne commande MOVE."""
        # Intercepter la commande envoyee
        commands_sent = []
        original_write = serial_sim.write

        def capture_write(data):
            commands_sent.append(data.decode("utf-8").strip())
            return original_write(data)

        serial_sim.write = capture_write

        moteur_rp2040.rotation(45.0, 0.002)

        # Verifier qu'une commande MOVE a ete envoyee
        move_cmds = [c for c in commands_sent if c.startswith("MOVE")]
        assert len(move_cmds) == 1

        parts = move_cmds[0].split()
        assert parts[0] == "MOVE"
        steps = int(parts[1])
        assert steps > 0
        direction = int(parts[2])
        assert direction == 1  # Positif = CW
        delay_us = int(parts[3])
        assert delay_us == 2000  # 0.002s * 1_000_000
        assert parts[4] == "SCURVE"  # use_ramp=True par defaut

    def test_rotation_negative_direction(self, moteur_rp2040, serial_sim):
        """rotation() avec angle negatif envoie direction=0 (CCW)."""
        commands_sent = []
        original_write = serial_sim.write

        def capture_write(data):
            commands_sent.append(data.decode("utf-8").strip())
            return original_write(data)

        serial_sim.write = capture_write

        moteur_rp2040.rotation(-30.0, 0.002)

        move_cmds = [c for c in commands_sent if c.startswith("MOVE")]
        assert len(move_cmds) == 1
        direction = int(move_cmds[0].split()[2])
        assert direction == 0  # Negatif = CCW

    def test_rotation_without_ramp(self, moteur_rp2040, serial_sim):
        """rotation() avec use_ramp=False envoie NONE."""
        commands_sent = []
        original_write = serial_sim.write

        def capture_write(data):
            commands_sent.append(data.decode("utf-8").strip())
            return original_write(data)

        serial_sim.write = capture_write

        moteur_rp2040.rotation(10.0, 0.002, use_ramp=False)

        move_cmds = [c for c in commands_sent if c.startswith("MOVE")]
        assert move_cmds[0].split()[4] == "NONE"

    def test_rotation_zero_angle(self, moteur_rp2040, serial_sim):
        """rotation(0) n'envoie pas de commande."""
        commands_sent = []
        original_write = serial_sim.write

        def capture_write(data):
            commands_sent.append(data.decode("utf-8").strip())
            return original_write(data)

        serial_sim.write = capture_write

        moteur_rp2040.rotation(0.0, 0.002)

        move_cmds = [c for c in commands_sent if c.startswith("MOVE")]
        assert len(move_cmds) == 0


class TestMoteurRP2040RotationAbsolue:
    """Tests de rotation absolue."""

    def test_rotation_absolue_shortest_path(self, moteur_rp2040, serial_sim):
        """rotation_absolue() prend le chemin le plus court."""
        commands_sent = []
        original_write = serial_sim.write

        def capture_write(data):
            commands_sent.append(data.decode("utf-8").strip())
            return original_write(data)

        serial_sim.write = capture_write

        # De 350° a 10° → devrait aller +20° (pas -340°)
        moteur_rp2040.rotation_absolue(10.0, 350.0, 0.002)

        move_cmds = [c for c in commands_sent if c.startswith("MOVE")]
        assert len(move_cmds) == 1
        # Direction positive (CW)
        direction = int(move_cmds[0].split()[2])
        assert direction == 1


class TestMoteurRP2040Stop:
    """Tests d'arret."""

    def test_request_stop_sends_stop(self, moteur_rp2040, serial_sim):
        """request_stop() envoie STOP au firmware."""
        commands_sent = []
        original_write = serial_sim.write

        def capture_write(data):
            commands_sent.append(data.decode("utf-8").strip())
            return original_write(data)

        serial_sim.write = capture_write

        moteur_rp2040.request_stop()

        stop_cmds = [c for c in commands_sent if c == "STOP"]
        assert len(stop_cmds) == 1
        assert moteur_rp2040.stop_requested is True

    def test_clear_stop_request(self, moteur_rp2040):
        """clear_stop_request() remet le flag a False."""
        moteur_rp2040.stop_requested = True
        moteur_rp2040.clear_stop_request()
        assert moteur_rp2040.stop_requested is False


class TestMoteurRP2040ErrorHandling:
    """Tests de gestion d'erreurs."""

    def test_error_response_logged(self, motor_config, caplog):
        """Une reponse ERROR est logguee sans lever d'exception."""
        sim = SerialSimulator()
        moteur = MoteurRP2040(motor_config, sim)

        # Remplacer le comportement du simulateur pour retourner ERROR
        original_write = sim.write

        def error_write(data):
            line = data.decode("utf-8").strip()
            if line.startswith("MOVE"):
                sim._response_buffer.append(b"ERROR test_error_msg\n")
                return len(data)
            return original_write(data)

        sim.write = error_write

        with caplog.at_level(logging.WARNING):
            # Ne doit PAS lever d'exception
            moteur.rotation(10.0, 0.002)

        assert any("test_error_msg" in record.message for record in caplog.records)


class TestMoteurRP2040Cleanup:
    """Tests de nettoyage."""

    def test_nettoyer_closes_serial(self, moteur_rp2040, serial_sim):
        """nettoyer() ferme le port serie."""
        assert serial_sim.is_open
        moteur_rp2040.nettoyer()
        assert not serial_sim.is_open


# ============================================================================
# TESTS CONFIG FALLBACK
# ============================================================================

class TestConfigFallback:
    """Tests du fallback config GPIO/RP2040."""

    def test_config_fallback_gpio_default(self, tmp_path):
        """Config sans motor_driver → type='gpio' par defaut."""
        config_data = {
            "site": {"latitude": 44.0, "longitude": 5.0, "altitude": 800,
                     "nom": "Test", "fuseau": "Europe/Paris", "tz_offset": 1},
            "moteur": {"gpio_pins": {"dir": 17, "step": 18},
                       "steps_per_revolution": 200, "microsteps": 4,
                       "gear_ratio": 2230, "steps_correction_factor": 1.0,
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

        config = ConfigLoader(config_file).load()
        assert config.motor_driver.type == "gpio"
        assert config.motor_driver.serial.port == "/dev/ttyACM0"

    def test_config_rp2040_parsing(self, tmp_path):
        """Config avec motor_driver rp2040 → type='rp2040', port correct."""
        config_data = {
            "site": {"latitude": 44.0, "longitude": 5.0, "altitude": 800,
                     "nom": "Test", "fuseau": "Europe/Paris", "tz_offset": 1},
            "motor_driver": {
                "type": "rp2040",
                "serial": {"port": "/dev/ttyUSB0", "baudrate": 9600, "timeout": 5.0},
            },
            "moteur": {"gpio_pins": {"dir": 17, "step": 18},
                       "steps_per_revolution": 200, "microsteps": 4,
                       "gear_ratio": 2230, "steps_correction_factor": 1.0,
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

        config = ConfigLoader(config_file).load()
        assert config.motor_driver.type == "rp2040"
        assert config.motor_driver.serial.port == "/dev/ttyUSB0"
        assert config.motor_driver.serial.baudrate == 9600
        assert config.motor_driver.serial.timeout == 5.0
