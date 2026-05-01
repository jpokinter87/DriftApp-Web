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
