"""
Tests pour les vues API Django du module cimier (v6.0 Phase 1).

Couvre :
- CimierServiceClient (singleton IPC)
- Vues : OpenView, CloseView, StopView, StatusView
- Réponses 503 quand l'IPC est indisponible
- AC-6 : aucune IP en dur dans les fichiers Python livrés

Pattern : monkeypatch direct des attributs `command_file` / `status_file`
du singleton `cimier_client`, plus simple et robuste que le reload-after-
patch utilisé pour le moteur (le moteur lit aussi `encoder_file` et a
besoin du reload pour des raisons historiques).
"""

import json
import os
import re
import sys
from pathlib import Path
from unittest.mock import patch

import pytest

PROJECT_ROOT = Path(__file__).parent.parent.resolve()
sys.path.insert(0, str(PROJECT_ROOT))
sys.path.insert(0, str(PROJECT_ROOT / "web"))
os.environ.setdefault("DJANGO_SETTINGS_MODULE", "driftapp_web.settings")
os.environ.setdefault("DRIFTAPP_DEBUG", "1")

import django  # noqa: E402

django.setup()

from rest_framework.test import APIClient  # noqa: E402


# =============================================================================
# Fixtures
# =============================================================================


@pytest.fixture
def api_client():
    return APIClient()


@pytest.fixture
def mock_cimier_ipc(tmp_path, monkeypatch):
    """Pointe le singleton cimier_client vers tmp_path/{cimier_command,cimier_status}.json."""
    cmd_file = tmp_path / "cimier_command.json"
    status_file = tmp_path / "cimier_status.json"

    from web.common.cimier_client import cimier_client

    monkeypatch.setattr(cimier_client, "command_file", cmd_file)
    monkeypatch.setattr(cimier_client, "status_file", status_file)

    yield {
        "cmd_file": cmd_file,
        "status_file": status_file,
    }


# =============================================================================
# Vues commandes — open / close / stop
# =============================================================================


class TestCimierViewsCommands:
    def test_open_writes_command_to_ipc(self, api_client, mock_cimier_ipc):
        response = api_client.post("/api/cimier/open/", {}, format="json")

        assert response.status_code == 200
        assert response.json()["action"] == "open"
        assert mock_cimier_ipc["cmd_file"].exists()

        payload = json.loads(mock_cimier_ipc["cmd_file"].read_text())
        assert payload["action"] == "open"
        assert "id" in payload and len(payload["id"]) >= 16  # uuid4 string

    def test_close_writes_command_to_ipc(self, api_client, mock_cimier_ipc):
        response = api_client.post("/api/cimier/close/", {}, format="json")

        assert response.status_code == 200
        assert response.json()["action"] == "close"

        payload = json.loads(mock_cimier_ipc["cmd_file"].read_text())
        assert payload["action"] == "close"
        assert "id" in payload

    def test_stop_writes_command_to_ipc(self, api_client, mock_cimier_ipc):
        response = api_client.post("/api/cimier/stop/", {}, format="json")

        assert response.status_code == 200
        assert response.json()["action"] == "stop"

        payload = json.loads(mock_cimier_ipc["cmd_file"].read_text())
        assert payload["action"] == "stop"

    def test_each_command_uses_unique_id(self, api_client, mock_cimier_ipc):
        api_client.post("/api/cimier/open/", {}, format="json")
        first = json.loads(mock_cimier_ipc["cmd_file"].read_text())["id"]

        api_client.post("/api/cimier/close/", {}, format="json")
        second = json.loads(mock_cimier_ipc["cmd_file"].read_text())["id"]

        assert first != second

    def test_open_returns_503_when_ipc_unwritable(self, api_client, mock_cimier_ipc):
        from web.common.cimier_client import cimier_client

        with patch.object(cimier_client, "send_command", return_value=False):
            response = api_client.post("/api/cimier/open/", {}, format="json")

        assert response.status_code == 503
        assert "error" in response.json()


# =============================================================================
# Vue status
# =============================================================================


class TestCimierViewsStatus:
    def test_status_returns_payload_when_file_exists(self, api_client, mock_cimier_ipc):
        status_payload = {
            "state": "cycle",
            "phase": "cycle_poll",
            "last_action": "open",
            "command_id": "abc-123",
            "error_message": "",
            "pico_state": "opening",
            "last_update": "2026-05-02T12:34:56",
        }
        mock_cimier_ipc["status_file"].write_text(json.dumps(status_payload))

        response = api_client.get("/api/cimier/status/")

        assert response.status_code == 200
        body = response.json()
        assert body["state"] == "cycle"
        assert body["phase"] == "cycle_poll"
        assert body["pico_state"] == "opening"

    def test_status_returns_unknown_when_file_missing(self, api_client, mock_cimier_ipc):
        # Le status_file n'existe pas (pas de write au préalable)
        assert not mock_cimier_ipc["status_file"].exists()

        response = api_client.get("/api/cimier/status/")

        assert response.status_code == 200
        body = response.json()
        assert body["state"] == "unknown"
        assert "error" in body


# =============================================================================
# AC-6 — aucune IP en dur dans le code Python livré
# =============================================================================


class TestNoHardcodedIps:
    def test_no_hardcoded_ips_in_web_cimier(self):
        """Grep `192\\.168\\.` sur les 5 fichiers Python livrés en Tâche 1."""
        files = [
            PROJECT_ROOT / "web" / "cimier" / "__init__.py",
            PROJECT_ROOT / "web" / "cimier" / "apps.py",
            PROJECT_ROOT / "web" / "cimier" / "urls.py",
            PROJECT_ROOT / "web" / "cimier" / "views.py",
            PROJECT_ROOT / "web" / "common" / "cimier_client.py",
        ]
        ip_pattern = re.compile(r"192\.168\.\d+")

        offenders = []
        for f in files:
            assert f.exists(), f"Fichier manquant: {f}"
            content = f.read_text()
            if ip_pattern.search(content):
                offenders.append(str(f))

        assert offenders == [], (
            f"IPs en dur détectées dans : {offenders}. Les chemins/IPs "
            "doivent vivre dans data/config.json (CimierConfig) et "
            "settings.CIMIER_SERVICE_IPC, jamais dans le code Python."
        )


# =============================================================================
# AC-4 (sub-plan v6.0-04-01) — AutomationView GET + POST
# =============================================================================


@pytest.fixture
def writable_config_file(tmp_path, monkeypatch):
    """Pointe settings.DRIFTAPP_CONFIG vers un fichier tmp + payload réaliste."""
    from django.conf import settings as dj_settings
    cfg = {
        "site": {
            "latitude": 44.15, "longitude": 5.23, "altitude": 800,
            "nom": "Test", "fuseau": "Europe/Paris",
        },
        "moteur": {
            "gpio_pins": {"dir": 17, "step": 18},
            "steps_per_revolution": 200, "microsteps": 4,
            "gear_ratio": 2230, "steps_correction_factor": 1.08849,
            "motor_delay_base": 0.002, "motor_delay_min": 0.00001,
            "motor_delay_max": 0.01,
            "max_speed_steps_per_sec": 1000,
            "acceleration_steps_per_sec2": 500,
        },
        "suivi": {
            "seuil_correction_deg": 0.5, "intervalle_verification_sec": 60,
            "abaque_file": "data/Loi_coupole.xlsx",
        },
        "encodeur": {"enabled": True, "spi": {}, "mecanique": {}},
        "cimier": {
            "enabled": True,
            "automation": {"mode": "manual"},
        },
    }
    config_file = tmp_path / "config.json"
    config_file.write_text(json.dumps(cfg, indent=2))
    monkeypatch.setattr(dj_settings, "DRIFTAPP_CONFIG", str(config_file))
    return config_file


class TestAutomationView:
    def test_get_returns_mode_and_next_triggers_from_status(
        self, api_client, mock_cimier_ipc
    ):
        status_payload = {
            "state": "idle",
            "mode": "full",
            "next_open_at": "2026-05-15T21:30:00+00:00",
            "next_close_at": "2026-05-16T04:45:00+00:00",
        }
        mock_cimier_ipc["status_file"].write_text(json.dumps(status_payload))
        response = api_client.get("/api/cimier/automation/")
        assert response.status_code == 200
        body = response.json()
        assert body["mode"] == "full"
        assert body["next_open_at"] == "2026-05-15T21:30:00+00:00"
        assert body["next_close_at"] == "2026-05-16T04:45:00+00:00"

    def test_get_returns_manual_default_when_status_missing(
        self, api_client, mock_cimier_ipc
    ):
        # status_file absent → cimier_client.get_status retourne {state: unknown, ...}
        assert not mock_cimier_ipc["status_file"].exists()
        response = api_client.get("/api/cimier/automation/")
        assert response.status_code == 200
        body = response.json()
        # Pas de mode dans le payload "unknown" → fallback "manual"
        assert body["mode"] == "manual"
        assert body["next_open_at"] is None
        assert body["next_close_at"] is None

    def test_post_valid_mode_persists_to_config_json(
        self, api_client, writable_config_file
    ):
        response = api_client.post(
            "/api/cimier/automation/", {"mode": "semi"}, format="json"
        )
        assert response.status_code == 200
        body = response.json()
        assert body == {"mode": "semi", "applied": True, "restart_required": True}
        # Fichier réécrit avec mode="semi"
        cfg = json.loads(writable_config_file.read_text())
        assert cfg["cimier"]["automation"]["mode"] == "semi"
        # Reste de la config préservé
        assert cfg["site"]["nom"] == "Test"
        assert cfg["moteur"]["gear_ratio"] == 2230

    def test_post_invalid_mode_returns_400_and_does_not_modify_config(
        self, api_client, writable_config_file
    ):
        original = writable_config_file.read_text()
        response = api_client.post(
            "/api/cimier/automation/", {"mode": "yolo"}, format="json"
        )
        assert response.status_code == 400
        body = response.json()
        assert "error" in body
        assert set(body["valid"]) == {"manual", "semi", "full"}
        # Config inchangée
        assert writable_config_file.read_text() == original

    def test_post_missing_mode_returns_400(self, api_client, writable_config_file):
        response = api_client.post(
            "/api/cimier/automation/", {}, format="json"
        )
        assert response.status_code == 400

    def test_post_strips_legacy_enabled_key(
        self, api_client, writable_config_file
    ):
        # Pré-écriture : config legacy avec enabled
        cfg = json.loads(writable_config_file.read_text())
        cfg["cimier"]["automation"] = {"enabled": True}
        writable_config_file.write_text(json.dumps(cfg))
        response = api_client.post(
            "/api/cimier/automation/", {"mode": "semi"}, format="json"
        )
        assert response.status_code == 200
        cfg_after = json.loads(writable_config_file.read_text())
        assert cfg_after["cimier"]["automation"]["mode"] == "semi"
        assert "enabled" not in cfg_after["cimier"]["automation"]


# =============================================================================
# AC-5 (sub-plan v6.0-04-01) — ParkingSessionView POST atomique
# =============================================================================


@pytest.fixture
def mock_motor_ipc(tmp_path, monkeypatch):
    """Pointe settings.MOTOR_SERVICE_IPC['COMMAND_FILE'] vers tmp."""
    from django.conf import settings as dj_settings
    motor_cmd = tmp_path / "motor_command.json"
    new_ipc = dict(dj_settings.MOTOR_SERVICE_IPC)
    new_ipc["COMMAND_FILE"] = str(motor_cmd)
    monkeypatch.setattr(dj_settings, "MOTOR_SERVICE_IPC", new_ipc)
    return motor_cmd


class TestParkingSessionView:
    def test_post_emits_three_ipc_writes_and_returns_200(
        self,
        api_client,
        mock_cimier_ipc,
        mock_motor_ipc,
        writable_config_file,
    ):
        # ParkingSessionView lit parking_target_azimuth_deg de config.json (45.0 default)
        response = api_client.post("/api/cimier/parking-session/", {}, format="json")
        assert response.status_code == 200
        body = response.json()
        assert body["applied"] is True
        assert body["tracking_stopped"] is True
        assert body["goto_45_sent"] is True
        assert body["cimier_close_sent"] is True
        assert body["parking_target_deg"] == 45.0
        # IPC cimier : last write = close
        cimier_payload = json.loads(mock_cimier_ipc["cmd_file"].read_text())
        assert cimier_payload["action"] == "close"
        # IPC motor : dernier write = goto 45 (writes successifs au même fichier,
        # tracking_stop puis goto, donc on lit le dernier).
        motor_payload = json.loads(mock_motor_ipc.read_text())
        assert motor_payload["command"] == "goto"
        assert motor_payload["angle"] == 45.0

    def test_post_uses_configured_parking_target_azimuth(
        self,
        api_client,
        mock_cimier_ipc,
        mock_motor_ipc,
        writable_config_file,
    ):
        # Override du parking target dans la config
        cfg = json.loads(writable_config_file.read_text())
        cfg["cimier"]["automation"]["parking_target_azimuth_deg"] = 180.0
        writable_config_file.write_text(json.dumps(cfg))
        response = api_client.post("/api/cimier/parking-session/", {}, format="json")
        assert response.status_code == 200
        body = response.json()
        assert body["parking_target_deg"] == 180.0
        motor_payload = json.loads(mock_motor_ipc.read_text())
        assert motor_payload["angle"] == 180.0

    def test_post_returns_503_when_cimier_close_fails(
        self,
        api_client,
        mock_cimier_ipc,
        mock_motor_ipc,
        writable_config_file,
    ):
        from web.common.cimier_client import cimier_client
        # cimier IPC down (send_command renvoie False)
        with patch.object(cimier_client, "send_command", return_value=False):
            response = api_client.post(
                "/api/cimier/parking-session/", {}, format="json"
            )
        assert response.status_code == 503
        body = response.json()
        assert body["applied"] is False
        # Motor commands quand même envoyées (best-effort)
        assert body["tracking_stopped"] is True
        assert body["goto_45_sent"] is True
        assert body["cimier_close_sent"] is False
        assert "error" in body

    def test_get_method_not_allowed(self, api_client):
        response = api_client.get("/api/cimier/parking-session/")
        assert response.status_code == 405
