"""
Tests pour web/health/views.py

Couvre :
- _check_file_freshness() : fichier frais/stale/manquant
- _read_ipc_file_content() : JSON valide/vide/corrompu/manquant
- _load_config() : config valide/manquante
- health_check : healthy → 200, unhealthy → 503
- motor_health : healthy/stale/missing
- encoder_health : healthy/stale/missing
- ipc_status : retourne fraîcheur des 3 fichiers
- diagnostic : bundle complet
- check_update : mocked
- apply_update : mocked
"""

import json
import os
import sys
import time
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

from rest_framework.test import APIClient


@pytest.fixture
def api_client():
    return APIClient()


@pytest.fixture
def health_ipc(tmp_path):
    """Fichiers IPC pour tests health."""
    cmd_file = tmp_path / "motor_command.json"
    status_file = tmp_path / "motor_status.json"
    encoder_file = tmp_path / "ems22_position.json"

    status_data = {
        "status": "idle",
        "position": 45.0,
        "mode": "idle",
        "simulation": True,
        "tracking_object": None,
        "last_update": "2025-01-01T00:00:00",
    }
    status_file.write_text(json.dumps(status_data))

    encoder_data = {
        "angle": 45.0,
        "calibrated": True,
        "status": "OK",
        "raw_value": 512,
    }
    encoder_file.write_text(json.dumps(encoder_data))

    ipc_settings = {
        "COMMAND_FILE": str(cmd_file),
        "STATUS_FILE": str(status_file),
        "ENCODER_FILE": str(encoder_file),
    }

    config_file = tmp_path / "config.json"
    config_file.write_text(json.dumps({
        "site": {"nom": "Test", "latitude": 44.15},
        "moteur": {"steps_per_revolution": 200, "microsteps": 4, "gear_ratio": 2230},
        "suivi": {"seuil_correction_deg": 0.5},
        "encodeur": {"enabled": True, "calibration_factor": 0.01},
        "simulation": False,
    }))

    with patch("django.conf.settings.MOTOR_SERVICE_IPC", ipc_settings), \
         patch("django.conf.settings.DRIFTAPP_CONFIG", str(config_file)):
        import importlib
        import web.health.views as health_views
        importlib.reload(health_views)

        import web.common.ipc_client as ipc_module
        importlib.reload(ipc_module)
        health_views.motor_client = ipc_module.motor_client

        yield {
            "cmd_file": cmd_file,
            "status_file": status_file,
            "encoder_file": encoder_file,
            "config_file": config_file,
        }


# =============================================================================
# _check_file_freshness
# =============================================================================

class TestCheckFileFreshness:
    def test_fresh_file(self, health_ipc):
        from web.health.views import _check_file_freshness
        result = _check_file_freshness(Path(health_ipc["status_file"]))
        assert result["exists"] is True
        assert result["fresh"] is True
        assert result["age_sec"] is not None

    def test_missing_file(self, health_ipc):
        from web.health.views import _check_file_freshness
        result = _check_file_freshness(Path("/nonexistent/file.json"))
        assert result["exists"] is False
        assert result["fresh"] is False
        assert result["age_sec"] is None

    def test_stale_file(self, health_ipc, tmp_path):
        from web.health.views import _check_file_freshness
        stale_file = tmp_path / "stale.json"
        stale_file.write_text("{}")
        # Set mtime to 60 seconds ago
        old_time = time.time() - 60
        os.utime(stale_file, (old_time, old_time))
        result = _check_file_freshness(stale_file)
        assert result["exists"] is True
        assert result["fresh"] is False


# =============================================================================
# _read_ipc_file_content
# =============================================================================

class TestReadIpcFileContent:
    def test_valid_json(self, health_ipc):
        from web.health.views import _read_ipc_file_content
        result = _read_ipc_file_content(Path(health_ipc["status_file"]))
        assert result["exists"] is True
        assert result["content"]["status"] == "idle"
        assert result["error"] is None
        assert result["empty"] is False

    def test_empty_file(self, health_ipc, tmp_path):
        from web.health.views import _read_ipc_file_content
        empty = tmp_path / "empty.json"
        empty.write_text("")
        result = _read_ipc_file_content(empty)
        assert result["exists"] is True
        assert result["empty"] is True
        assert result["content"] is None

    def test_corrupt_json(self, health_ipc, tmp_path):
        from web.health.views import _read_ipc_file_content
        bad = tmp_path / "bad.json"
        bad.write_text("{invalid json")
        result = _read_ipc_file_content(bad)
        assert result["exists"] is True
        assert "JSON invalide" in result["error"]

    def test_missing_file(self, health_ipc):
        from web.health.views import _read_ipc_file_content
        result = _read_ipc_file_content(Path("/nonexistent.json"))
        assert result["exists"] is False


# =============================================================================
# Health check endpoints
# =============================================================================

class TestHealthCheck:
    def test_healthy(self, api_client, health_ipc):
        response = api_client.get("/api/health/")
        assert response.status_code == 200
        assert response.data["healthy"] is True
        assert "components" in response.data

    def test_unhealthy_missing_status(self, api_client, health_ipc):
        health_ipc["status_file"].unlink()
        response = api_client.get("/api/health/")
        assert response.status_code == 503
        assert response.data["healthy"] is False


class TestMotorHealth:
    def test_healthy(self, api_client, health_ipc):
        response = api_client.get("/api/health/motor/")
        assert response.status_code == 200
        assert response.data["healthy"] is True

    def test_missing_file(self, api_client, health_ipc):
        health_ipc["status_file"].unlink()
        response = api_client.get("/api/health/motor/")
        assert response.status_code == 503
        assert response.data["status"] == "unavailable"


class TestEncoderHealth:
    def test_healthy(self, api_client, health_ipc):
        response = api_client.get("/api/health/encoder/")
        assert response.status_code == 200
        assert response.data["healthy"] is True

    def test_missing_file(self, api_client, health_ipc):
        health_ipc["encoder_file"].unlink()
        response = api_client.get("/api/health/encoder/")
        assert response.status_code == 503
        assert response.data["status"] == "unavailable"


class TestIpcStatus:
    def test_returns_all_files(self, api_client, health_ipc):
        response = api_client.get("/api/health/ipc/")
        assert response.status_code == 200
        assert "files" in response.data
        files = response.data["files"]
        assert "command_file" in files
        assert "status_file" in files
        assert "encoder_file" in files


class TestDiagnostic:
    def test_returns_complete_bundle(self, api_client, health_ipc):
        response = api_client.get("/api/health/diagnostic/")
        assert response.status_code == 200
        data = response.data
        assert "components" in data
        assert "ipc" in data
        assert "config" in data
        assert "timestamp" in data


class TestVersionTuple:
    """Tests pour _version_tuple."""

    def test_version_normale(self):
        from web.health.update_checker import _version_tuple
        assert _version_tuple("5.4.0") == (5, 4, 0)

    def test_version_deux_segments(self):
        from web.health.update_checker import _version_tuple
        assert _version_tuple("5.4") == (5, 4)

    def test_version_unknown(self):
        from web.health.update_checker import _version_tuple
        assert _version_tuple("unknown") == (0,)

    def test_version_vide(self):
        from web.health.update_checker import _version_tuple
        assert _version_tuple("") == (0,)

    def test_version_none(self):
        from web.health.update_checker import _version_tuple
        assert _version_tuple(None) == (0,)

    def test_comparaison_superieure(self):
        from web.health.update_checker import _version_tuple
        assert _version_tuple("5.5.0") > _version_tuple("5.4.0")

    def test_comparaison_egale(self):
        from web.health.update_checker import _version_tuple
        assert _version_tuple("5.4.0") == _version_tuple("5.4.0")


class TestCheckForUpdatesLogic:
    """Tests pour la logique de check_for_updates."""

    def test_meme_version_pas_de_mise_a_jour(self):
        """Même version locale/distante → update_available=False."""
        from web.health.update_checker import check_for_updates
        with patch("web.health.update_checker.fetch_remote", return_value=True), \
             patch("web.health.update_checker.get_local_commit", return_value="abc1234"), \
             patch("web.health.update_checker.get_remote_commit", return_value="def5678"), \
             patch("web.health.update_checker.count_commits_behind", return_value=3), \
             patch("web.health.update_checker.get_local_version", return_value="5.4.0"), \
             patch("web.health.update_checker.get_remote_version", return_value="5.4.0"):
            result = check_for_updates()
            assert result["update_available"] is False

    def test_version_distante_superieure_mise_a_jour(self):
        """Version distante > locale → update_available=True."""
        from web.health.update_checker import check_for_updates
        with patch("web.health.update_checker.fetch_remote", return_value=True), \
             patch("web.health.update_checker.get_local_commit", return_value="abc1234"), \
             patch("web.health.update_checker.get_remote_commit", return_value="def5678"), \
             patch("web.health.update_checker.count_commits_behind", return_value=5), \
             patch("web.health.update_checker.get_local_version", return_value="5.4.0"), \
             patch("web.health.update_checker.get_remote_version", return_value="5.5.0"), \
             patch("web.health.update_checker.get_commit_messages", return_value=["abc feat"]):
            result = check_for_updates()
            assert result["update_available"] is True
            assert result["commits_behind"] == 5

    def test_fetch_echoue_pas_de_mise_a_jour(self):
        """Fetch échoue → update_available=False."""
        from web.health.update_checker import check_for_updates
        with patch("web.health.update_checker.fetch_remote", return_value=False), \
             patch("web.health.update_checker.get_local_commit", return_value="abc1234"), \
             patch("web.health.update_checker.get_remote_commit", return_value="def5678"), \
             patch("web.health.update_checker.count_commits_behind", return_value=3), \
             patch("web.health.update_checker.get_local_version", return_value="5.4.0"), \
             patch("web.health.update_checker.get_remote_version", return_value="5.5.0"):
            result = check_for_updates()
            assert result["update_available"] is False
            assert result["fetch_success"] is False

    def test_version_locale_superieure_pas_de_mise_a_jour(self):
        """Version locale > distante (hotfix terrain) → update_available=False."""
        from web.health.update_checker import check_for_updates
        with patch("web.health.update_checker.fetch_remote", return_value=True), \
             patch("web.health.update_checker.get_local_commit", return_value="abc1234"), \
             patch("web.health.update_checker.get_remote_commit", return_value="def5678"), \
             patch("web.health.update_checker.count_commits_behind", return_value=1), \
             patch("web.health.update_checker.get_local_version", return_value="5.5.0"), \
             patch("web.health.update_checker.get_remote_version", return_value="5.4.0"):
            result = check_for_updates()
            assert result["update_available"] is False


class TestCheckUpdate:
    def test_check_update_success(self, api_client, health_ipc):
        mock_result = {"update_available": False, "local_version": "5.4.0"}
        with patch("web.health.update_checker.check_for_updates", return_value=mock_result):
            response = api_client.get("/api/health/update/check/")
            assert response.status_code == 200
            assert response.data["update_available"] is False

    def test_check_update_error(self, health_ipc):
        """check_update retourne 500 si check_for_updates lève une exception."""
        from rest_framework.test import APIRequestFactory
        from web.health.views import check_update
        factory = APIRequestFactory()
        request = factory.get("/api/health/update/check/")
        with patch("web.health.update_checker.check_for_updates", side_effect=OSError("git error")):
            response = check_update(request)
        assert response.status_code == 500
        assert "error" in response.data


class TestApplyUpdate:
    def test_apply_script_missing(self, api_client, health_ipc):
        with patch("web.health.views.UPDATE_SCRIPT", Path("/nonexistent/script.sh")):
            response = api_client.post("/api/health/update/apply/")
            assert response.status_code == 500
            assert response.data["success"] is False
