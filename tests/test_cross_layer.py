"""
Tests d'integration cross-couche : Django (MotorServiceClient) <-> IPC <-> MotorService.

Verifie que le flux complet fonctionne de bout en bout :
  Django send_command -> fichier IPC -> MotorService process_command -> write_status -> Django get_motor_status

N'utilise PAS la boucle run() — appelle process_command directement.
"""

import json
import os
import sys
from pathlib import Path
from unittest.mock import patch

import pytest

PROJECT_ROOT = Path(__file__).parent.parent.resolve()
sys.path.insert(0, str(PROJECT_ROOT))
sys.path.insert(0, str(PROJECT_ROOT / "web"))
os.environ.setdefault("DJANGO_SETTINGS_MODULE", "driftapp_web.settings")
os.environ.setdefault("DRIFTAPP_DEBUG", "1")

import django
django.setup()


@pytest.fixture
def cross_layer(tmp_path):
    """
    Cree un environnement cross-couche complet :
    - MotorService avec fichiers IPC dans tmp_path
    - MotorServiceClient pointe vers les memes fichiers
    """
    cmd_file = tmp_path / "motor_command.json"
    status_file = tmp_path / "motor_status.json"
    encoder_file = tmp_path / "ems22_position.json"

    # Ecrire un fichier encodeur initial
    encoder_data = {
        "angle": 45.0,
        "calibrated": True,
        "status": "OK",
        "raw": 512,
    }
    encoder_file.write_text(json.dumps(encoder_data))

    # Patcher les deux cotes : services.ipc_manager ET django settings
    import services.ipc_manager as ipc_module

    ipc_settings = {
        "COMMAND_FILE": str(cmd_file),
        "STATUS_FILE": str(status_file),
        "ENCODER_FILE": str(encoder_file),
    }

    with patch.object(ipc_module, "COMMAND_FILE", cmd_file), \
         patch.object(ipc_module, "STATUS_FILE", status_file), \
         patch.object(ipc_module, "ENCODER_FILE", encoder_file), \
         patch("django.conf.settings.MOTOR_SERVICE_IPC", ipc_settings):

        from services.motor_service import MotorService
        from web.common.ipc_client import MotorServiceClient

        service = MotorService()
        client = MotorServiceClient()

        yield {
            "service": service,
            "client": client,
            "cmd_file": cmd_file,
            "status_file": status_file,
            "encoder_file": encoder_file,
        }


# =============================================================================
# Cross-layer: GOTO
# =============================================================================

class TestCrossLayerGoto:
    """Django envoie GOTO -> MotorService execute -> Django lit le status."""

    def test_goto_updates_position(self, cross_layer):
        """GOTO 90° via client -> service -> status lu par client."""
        client = cross_layer["client"]
        service = cross_layer["service"]

        # Django envoie la commande
        assert client.send_command("goto", angle=90.0) is True

        # MotorService lit et execute la commande
        cmd = service.ipc.read_command()
        assert cmd is not None
        assert cmd["command"] == "goto"
        assert cmd["angle"] == 90.0

        service.process_command(cmd)

        # Django lit le status
        status = client.get_motor_status()
        assert status["status"] == "idle"
        assert "last_update" in status

    def test_goto_with_speed(self, cross_layer):
        """GOTO avec vitesse specifique traverse les deux couches."""
        client = cross_layer["client"]
        service = cross_layer["service"]

        client.send_command("goto", angle=180.0, speed=0.001)
        cmd = service.ipc.read_command()
        assert cmd["speed"] == 0.001

        service.process_command(cmd)

        status = client.get_motor_status()
        assert status["status"] == "idle"


# =============================================================================
# Cross-layer: JOG
# =============================================================================

class TestCrossLayerJog:
    """Django envoie JOG -> MotorService execute -> Django lit le status."""

    def test_jog_relative(self, cross_layer):
        """JOG +10° via client -> service -> status lu par client."""
        client = cross_layer["client"]
        service = cross_layer["service"]

        client.send_command("jog", delta=10.0)
        cmd = service.ipc.read_command()
        assert cmd["command"] == "jog"
        assert cmd["delta"] == 10.0

        service.process_command(cmd)

        status = client.get_motor_status()
        assert status["status"] == "idle"

    def test_jog_negative(self, cross_layer):
        """JOG negatif traverse les deux couches."""
        client = cross_layer["client"]
        service = cross_layer["service"]

        client.send_command("jog", delta=-5.0)
        cmd = service.ipc.read_command()
        service.process_command(cmd)

        status = client.get_motor_status()
        assert status["status"] == "idle"


# =============================================================================
# Cross-layer: STOP
# =============================================================================

class TestCrossLayerStop:
    """Django envoie STOP -> MotorService execute -> Django lit idle."""

    def test_stop_sets_idle(self, cross_layer):
        """STOP via client -> service -> status idle lu par client."""
        client = cross_layer["client"]
        service = cross_layer["service"]

        client.send_command("stop")
        cmd = service.ipc.read_command()
        assert cmd["command"] == "stop"

        service.process_command(cmd)

        status = client.get_motor_status()
        assert status["status"] == "idle"
        assert status["tracking_object"] is None


# =============================================================================
# Cross-layer: Status & Encoder
# =============================================================================

class TestCrossLayerStatusEncoder:
    """Verification que le client lit correctement status et encodeur."""

    def test_status_readable_after_init(self, cross_layer):
        """Le status est lisible par le client des l'initialisation du service."""
        client = cross_layer["client"]
        status = client.get_motor_status()

        assert status["status"] == "idle"
        assert status["simulation"] is True
        assert "last_update" in status

    def test_encoder_read_through_client(self, cross_layer):
        """Le client lit le fichier encodeur ecrit par le daemon."""
        client = cross_layer["client"]
        encoder = client.get_encoder_status()

        assert encoder["angle"] == 45.0
        assert encoder["calibrated"] is True

    def test_sequential_commands(self, cross_layer):
        """Plusieurs commandes sequentielles restent coherentes."""
        client = cross_layer["client"]
        service = cross_layer["service"]

        # GOTO 90
        client.send_command("goto", angle=90.0)
        cmd = service.ipc.read_command()
        service.process_command(cmd)
        service.ipc.clear_command()

        status1 = client.get_motor_status()
        assert status1["status"] == "idle"

        # JOG +10
        client.send_command("jog", delta=10.0)
        cmd = service.ipc.read_command()
        service.process_command(cmd)
        service.ipc.clear_command()

        status2 = client.get_motor_status()
        assert status2["status"] == "idle"

        # STOP
        client.send_command("stop")
        cmd = service.ipc.read_command()
        service.process_command(cmd)

        status3 = client.get_motor_status()
        assert status3["status"] == "idle"
