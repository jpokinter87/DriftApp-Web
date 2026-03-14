"""
Tests pour web/session/views.py

Couvre :
- current_session : tracking actif → 200, idle → 404
- session_history : liste → 200, avec limit
- session_detail : existant → 200, manquant → 404
- save_session : tracking → 200, idle → 400
- delete_session : existant → 200, manquant → 404
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

from rest_framework.test import APIClient, APIRequestFactory
from web.session import session_storage
from web.session import views as session_views


@pytest.fixture
def api_client():
    return APIClient()


@pytest.fixture
def factory():
    return APIRequestFactory()


@pytest.fixture
def mock_sessions(tmp_path, monkeypatch):
    """Mock session storage dir."""
    sessions_dir = tmp_path / "sessions"
    sessions_dir.mkdir()
    monkeypatch.setattr(session_storage, "SESSIONS_DIR", sessions_dir)
    return sessions_dir


TRACKING_STATUS = {
    "status": "tracking",
    "tracking_object": "M42",
    "position": 123.4,
    "mode": "normal",
    "session_data": {
        "start_time": "2025-06-21T22:00:00",
        "duration_seconds": 3600,
        "summary": {"total_corrections": 5},
        "corrections_log": [],
        "position_log": [],
        "goto_log": [],
    },
    "tracking_info": {
        "ra_deg": 83.82,
        "dec_deg": -5.39,
        "altitude": 45.0,
        "azimut": 180.0,
    },
}


# =============================================================================
# current_session
# =============================================================================

class TestCurrentSession:
    def test_tracking_active(self, factory):
        request = factory.get("/api/session/current/")
        with patch.object(session_views, "motor_client") as mock:
            mock.get_motor_status.return_value = TRACKING_STATUS
            response = session_views.current_session(request)
        assert response.status_code == 200
        assert response.data["active"] is True
        assert response.data["object"]["name"] == "M42"

    def test_idle(self, factory):
        request = factory.get("/api/session/current/")
        with patch.object(session_views, "motor_client") as mock:
            mock.get_motor_status.return_value = {"status": "idle"}
            response = session_views.current_session(request)
        assert response.status_code == 404


# =============================================================================
# session_history
# =============================================================================

class TestSessionHistory:
    def test_empty(self, api_client, mock_sessions):
        response = api_client.get("/api/session/history/")
        assert response.status_code == 200
        assert response.data["count"] == 0
        assert response.data["sessions"] == []

    def test_with_sessions(self, api_client, mock_sessions):
        for i in range(3):
            (mock_sessions / f"session_{i}.json").write_text(
                json.dumps({"session_id": f"session_{i}", "object": {"name": f"M{i}"}})
            )
        response = api_client.get("/api/session/history/")
        assert response.status_code == 200
        assert response.data["count"] == 3

    def test_with_limit(self, api_client, mock_sessions):
        for i in range(5):
            (mock_sessions / f"session_{i}.json").write_text(
                json.dumps({"session_id": f"session_{i}"})
            )
        response = api_client.get("/api/session/history/?limit=2")
        assert response.status_code == 200
        assert response.data["count"] == 2


# =============================================================================
# session_detail
# =============================================================================

class TestSessionDetail:
    def test_existing(self, api_client, mock_sessions):
        data = {"session_id": "test123", "object": {"name": "M31"}}
        (mock_sessions / "test123.json").write_text(json.dumps(data))
        response = api_client.get("/api/session/history/test123/")
        assert response.status_code == 200
        assert response.data["session_id"] == "test123"

    def test_missing(self, api_client, mock_sessions):
        response = api_client.get("/api/session/history/nonexistent/")
        assert response.status_code == 404


# =============================================================================
# save_session
# =============================================================================

class TestSaveSession:
    def test_save_while_tracking(self, factory, mock_sessions):
        request = factory.post("/api/session/save/")
        with patch.object(session_views, "motor_client") as mock:
            mock.get_motor_status.return_value = TRACKING_STATUS
            response = session_views.save_session(request)
        assert response.status_code == 200
        assert response.data["success"] is True

    def test_save_while_idle(self, factory):
        request = factory.post("/api/session/save/")
        with patch.object(session_views, "motor_client") as mock:
            mock.get_motor_status.return_value = {"status": "idle"}
            response = session_views.save_session(request)
        assert response.status_code == 400


# =============================================================================
# delete_session
# =============================================================================

class TestDeleteSession:
    def test_delete_existing(self, api_client, mock_sessions):
        (mock_sessions / "to_delete.json").write_text("{}")
        response = api_client.delete("/api/session/delete/to_delete/")
        assert response.status_code == 200
        assert response.data["success"] is True

    def test_delete_missing(self, api_client, mock_sessions):
        response = api_client.delete("/api/session/delete/nonexistent/")
        assert response.status_code == 404
