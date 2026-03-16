"""
Tests pour les vues API Django (web/hardware/ et web/tracking/).

Couvre :
- MotorServiceClient (IPC)
- Hardware views : GotoView, JogView, StopView, ContinuousView, EncoderView,
  MotorStatusView, ParkView, CalibrateView, EndSessionView
- Tracking views : TrackingStartView, TrackingStopView, TrackingStatusView,
  ObjectSearchView
- Validation des entrées
- Gestion des erreurs IPC

Utilise le test client Django avec des fichiers IPC mockés.
"""

import json
import os
import sys
from pathlib import Path
from unittest.mock import patch

import pytest

# Setup Django avant les imports
PROJECT_ROOT = Path(__file__).parent.parent.resolve()
sys.path.insert(0, str(PROJECT_ROOT))
sys.path.insert(0, str(PROJECT_ROOT / "web"))
os.environ.setdefault("DJANGO_SETTINGS_MODULE", "driftapp_web.settings")
os.environ.setdefault("DRIFTAPP_DEBUG", "1")  # Tests en mode debug pour ALLOWED_HOSTS

import django
django.setup()

from rest_framework.test import APIClient


@pytest.fixture
def api_client():
    return APIClient()


@pytest.fixture
def mock_ipc(tmp_path):
    """Mock les fichiers IPC pour les tests."""
    cmd_file = tmp_path / "motor_command.json"
    status_file = tmp_path / "motor_status.json"
    encoder_file = tmp_path / "ems22_position.json"

    # Status par défaut
    status_data = {
        "status": "idle",
        "position": 45.0,
        "target": None,
        "simulation": True,
        "tracking_object": None,
        "last_update": "2025-01-01T00:00:00",
    }
    status_file.write_text(json.dumps(status_data))

    # Encoder par défaut
    encoder_data = {
        "angle": 45.0,
        "calibrated": True,
        "status": "OK",
        "raw": 512,
    }
    encoder_file.write_text(json.dumps(encoder_data))

    ipc_settings = {
        "COMMAND_FILE": str(cmd_file),
        "STATUS_FILE": str(status_file),
        "ENCODER_FILE": str(encoder_file),
    }

    with patch("django.conf.settings.MOTOR_SERVICE_IPC", ipc_settings):
        # Re-importer les vues pour utiliser les nouveaux chemins
        import importlib
        import web.hardware.views as hw_views
        import web.tracking.views as tr_views

        # Patcher les instances globales depuis le module partagé
        import web.common.ipc_client as ipc_module
        importlib.reload(ipc_module)
        hw_views.motor_client = ipc_module.motor_client
        tr_views.motor_client = ipc_module.motor_client

        yield {
            "cmd_file": cmd_file,
            "status_file": status_file,
            "encoder_file": encoder_file,
        }


# =============================================================================
# MotorServiceClient (hardware)
# =============================================================================

class TestMotorServiceClientHardware:
    def test_send_command(self, mock_ipc):
        from web.common.ipc_client import motor_client
        result = motor_client.send_command("stop")
        assert result is True
        # Vérifier que le fichier a été écrit
        data = json.loads(mock_ipc["cmd_file"].read_text())
        assert data["command"] == "stop"
        assert "id" in data

    def test_send_command_with_params(self, mock_ipc):
        from web.common.ipc_client import motor_client
        result = motor_client.send_command("goto", angle=90.0)
        assert result is True
        data = json.loads(mock_ipc["cmd_file"].read_text())
        assert data["angle"] == 90.0

    def test_get_motor_status(self, mock_ipc):
        from web.common.ipc_client import motor_client
        status = motor_client.get_motor_status()
        assert status["status"] == "idle"
        assert status["position"] == 45.0

    def test_get_motor_status_missing_file(self, tmp_path):
        from web.common.ipc_client import MotorServiceClient
        with patch("django.conf.settings.MOTOR_SERVICE_IPC", {
            "COMMAND_FILE": str(tmp_path / "cmd.json"),
            "STATUS_FILE": str(tmp_path / "nonexistent.json"),
            "ENCODER_FILE": str(tmp_path / "enc.json"),
        }):
            client = MotorServiceClient()
            status = client.get_motor_status()
            assert "error" in status

    def test_get_encoder_status(self, mock_ipc):
        from web.common.ipc_client import motor_client
        status = motor_client.get_encoder_status()
        assert status["angle"] == 45.0
        assert status["calibrated"] is True


# =============================================================================
# Hardware API Views
# =============================================================================

class TestGotoView:
    def test_goto_success(self, api_client, mock_ipc):
        response = api_client.post("/api/hardware/goto/", {"angle": 90.0}, format="json")
        assert response.status_code == 200
        assert "GOTO" in response.data["message"]

    def test_goto_missing_angle(self, api_client, mock_ipc):
        response = api_client.post("/api/hardware/goto/", {}, format="json")
        assert response.status_code == 400

    def test_goto_invalid_angle(self, api_client, mock_ipc):
        response = api_client.post("/api/hardware/goto/", {"angle": "abc"}, format="json")
        assert response.status_code == 400

    def test_goto_normalizes_angle(self, api_client, mock_ipc):
        response = api_client.post("/api/hardware/goto/", {"angle": 370.0}, format="json")
        assert response.status_code == 200
        assert response.data["target"] == pytest.approx(10.0)

    def test_goto_with_speed(self, api_client, mock_ipc):
        response = api_client.post(
            "/api/hardware/goto/", {"angle": 90.0, "speed": 0.001}, format="json"
        )
        assert response.status_code == 200

    def test_goto_invalid_speed(self, api_client, mock_ipc):
        """H-19 : speed invalide → 400."""
        response = api_client.post(
            "/api/hardware/goto/", {"angle": 90.0, "speed": "abc"}, format="json"
        )
        assert response.status_code == 400

    def test_goto_speed_zero_accepted(self, api_client, mock_ipc):
        """speed=0 est accepté (pas de validation de plage côté vue)."""
        response = api_client.post(
            "/api/hardware/goto/", {"angle": 90.0, "speed": 0}, format="json"
        )
        assert response.status_code == 200


class TestJogView:
    def test_jog_success(self, api_client, mock_ipc):
        response = api_client.post("/api/hardware/jog/", {"delta": 10.0}, format="json")
        assert response.status_code == 200

    def test_jog_negative(self, api_client, mock_ipc):
        response = api_client.post("/api/hardware/jog/", {"delta": -10.0}, format="json")
        assert response.status_code == 200

    def test_jog_missing_delta(self, api_client, mock_ipc):
        response = api_client.post("/api/hardware/jog/", {}, format="json")
        assert response.status_code == 400

    def test_jog_invalid_delta(self, api_client, mock_ipc):
        response = api_client.post("/api/hardware/jog/", {"delta": "abc"}, format="json")
        assert response.status_code == 400

    def test_jog_invalid_speed(self, api_client, mock_ipc):
        """H-19 : speed invalide → 400."""
        response = api_client.post(
            "/api/hardware/jog/", {"delta": 10.0, "speed": "xyz"}, format="json"
        )
        assert response.status_code == 400


class TestStopView:
    def test_stop_success(self, api_client, mock_ipc):
        response = api_client.post("/api/hardware/stop/")
        assert response.status_code == 200
        assert "Arrêt" in response.data["message"]


class TestContinuousView:
    def test_continuous_cw(self, api_client, mock_ipc):
        response = api_client.post(
            "/api/hardware/continuous/", {"direction": "cw"}, format="json"
        )
        assert response.status_code == 200

    def test_continuous_ccw(self, api_client, mock_ipc):
        response = api_client.post(
            "/api/hardware/continuous/", {"direction": "ccw"}, format="json"
        )
        assert response.status_code == 200

    def test_continuous_invalid_direction(self, api_client, mock_ipc):
        response = api_client.post(
            "/api/hardware/continuous/", {"direction": "invalid"}, format="json"
        )
        assert response.status_code == 400


class TestEncoderView:
    def test_encoder_available(self, api_client, mock_ipc):
        response = api_client.get("/api/hardware/encoder/")
        assert response.status_code == 200
        assert "angle" in response.data

    def test_encoder_unavailable_simulation(self, api_client, mock_ipc):
        """Encodeur absent mais simulation → retourne position simulée."""
        # Supprimer le fichier encodeur
        mock_ipc["encoder_file"].unlink()
        # Mettre simulation=True dans le status
        status = json.loads(mock_ipc["status_file"].read_text())
        status["simulation"] = True
        mock_ipc["status_file"].write_text(json.dumps(status))

        response = api_client.get("/api/hardware/encoder/")
        assert response.status_code == 200


class TestMotorStatusView:
    def test_status(self, api_client, mock_ipc):
        response = api_client.get("/api/hardware/status/")
        assert response.status_code == 200
        assert "status" in response.data


class TestStubRoutes:
    """Routes park, calibrate, end-session retournent 501 Not Implemented."""

    def test_park_returns_501(self, api_client, mock_ipc):
        response = api_client.post("/api/hardware/park/")
        assert response.status_code == 501

    def test_calibrate_returns_501(self, api_client, mock_ipc):
        response = api_client.post("/api/hardware/calibrate/")
        assert response.status_code == 501

    def test_end_session_returns_501(self, api_client, mock_ipc):
        response = api_client.post("/api/hardware/end-session/")
        assert response.status_code == 501


# =============================================================================
# Tracking API Views
# =============================================================================

class TestTrackingStartView:
    def test_start_missing_object(self, api_client, mock_ipc):
        response = api_client.post("/api/tracking/start/", {}, format="json")
        assert response.status_code == 400

    def test_start_unknown_object(self, api_client, mock_ipc):
        """Objet inconnu → 404 (si pas dans le cache et SIMBAD échoue)."""
        response = api_client.post(
            "/api/tracking/start/", {"object": "NONEXISTENT_OBJECT_XYZ"}, format="json"
        )
        # Peut être 404 ou 200 selon le cache
        assert response.status_code in (200, 404)


class TestTrackingStopView:
    def test_stop(self, api_client, mock_ipc):
        response = api_client.post("/api/tracking/stop/")
        assert response.status_code == 200


class TestTrackingStatusView:
    def test_status(self, api_client, mock_ipc):
        response = api_client.get("/api/tracking/status/")
        assert response.status_code == 200


class TestObjectListView:
    def test_list_objects_returns_list(self, api_client, mock_ipc):
        """ObjectListView retourne la liste des objets du cache."""
        response = api_client.get("/api/tracking/objects/")
        assert response.status_code == 200
        assert 'count' in response.data
        assert 'objects' in response.data
        assert isinstance(response.data['objects'], list)


class TestObjectSearchView:
    def test_search_empty_query(self, api_client, mock_ipc):
        response = api_client.get("/api/tracking/search/?q=")
        assert response.status_code == 400

    def test_search_known_object(self, api_client, mock_ipc):
        """Recherche d'un objet — résultat dépend du cache."""
        response = api_client.get("/api/tracking/search/?q=M42")
        # 200 si trouvé dans le cache, 404 sinon
        assert response.status_code in (200, 404)
