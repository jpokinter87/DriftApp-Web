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


# =============================================================================
# night_report — frise de nuit (2026-08)
# =============================================================================


@pytest.fixture
def mock_nights(tmp_path, monkeypatch):
    """Repointe le journal de nuit vers un répertoire temporaire."""
    from services import night_journal

    nights_dir = tmp_path / "nights"
    nights_dir.mkdir()
    monkeypatch.setattr(night_journal, "DEFAULT_NIGHTS_DIR", nights_dir)
    return nights_dir


def write_night_event(nights_dir, moment, event="rain", **fields):
    from services import night_journal

    night_journal.append_event(event, at=moment, nights_dir=nights_dir, **fields)


class TestNightView:
    """GET /api/session/night/ — données de la frise de nuit."""

    def test_returns_available_nights(self, api_client, mock_nights, mock_sessions):
        from datetime import datetime

        write_night_event(mock_nights, datetime(2026, 8, 14, 22, 0), state="wet")
        data = api_client.get("/api/session/night/").json()
        assert "2026-08-14" in data["available_nights"]

    def test_returns_events_of_requested_night(self, api_client, mock_nights, mock_sessions):
        from datetime import datetime

        write_night_event(mock_nights, datetime(2026, 8, 14, 22, 0), state="wet")
        data = api_client.get("/api/session/night/?date=2026-08-14").json()
        assert data["night"] == "2026-08-14"
        assert data["events"][0]["state"] == "wet"

    def test_unknown_night_returns_empty_not_404(self, api_client, mock_nights, mock_sessions):
        response = api_client.get("/api/session/night/?date=1999-01-01")
        assert response.status_code == 200
        assert response.json()["events"] == []

    def test_malformed_date_is_rejected(self, api_client, mock_nights, mock_sessions):
        assert api_client.get("/api/session/night/?date=pas-une-date").status_code == 400

    def test_no_journal_at_all_returns_empty_payload(self, api_client, mock_nights, mock_sessions):
        data = api_client.get("/api/session/night/").json()
        assert data["night"] is None
        assert data["available_nights"] == []

    def test_defaults_to_most_recent_night(self, api_client, mock_nights, mock_sessions):
        from datetime import datetime

        for day in (12, 14):
            write_night_event(mock_nights, datetime(2026, 8, day, 22, 0), state="wet")
        assert api_client.get("/api/session/night/").json()["night"] == "2026-08-14"

    def test_payload_carries_server_now(self, api_client, mock_nights, mock_sessions):
        # La frise prolonge le dernier état connu jusqu'à la borne qu'on lui
        # donne. Sans un « maintenant », elle peignait la pluie jusqu'à midi le
        # lendemain — elle affichait l'avenir (terrain 16/08/2026). L'autorité
        # horaire est le serveur : c'est lui qui horodate les événements.
        from datetime import datetime

        write_night_event(mock_nights, datetime(2026, 8, 14, 22, 0), state="wet")
        data = api_client.get("/api/session/night/?date=2026-08-14").json()
        assert datetime.fromisoformat(data["now"])

    def test_includes_tracking_sessions_of_the_night(self, api_client, mock_nights, mock_sessions):
        # 3e ligne de la frise : lue des sessions déjà persistées, sans
        # coupler cimier_service et motor_service.
        from datetime import datetime

        write_night_event(mock_nights, datetime(2026, 8, 14, 22, 0), state="wet")
        session_storage.save_session(
            {
                "session_id": "20260814_213000_M31",
                "object": {"name": "M31"},
                "timing": {
                    "start_time": "2026-08-14T21:30:00",
                    "end_time": "2026-08-15T02:00:00",
                },
            }
        )
        data = api_client.get("/api/session/night/?date=2026-08-14").json()
        assert data["tracking"][0]["object_name"] == "M31"

    def test_excludes_sessions_of_other_nights(self, api_client, mock_nights, mock_sessions):
        from datetime import datetime

        write_night_event(mock_nights, datetime(2026, 8, 14, 22, 0), state="wet")
        session_storage.save_session(
            {
                "session_id": "20260801_213000_M13",
                "object": {"name": "M13"},
                "timing": {
                    "start_time": "2026-08-01T21:30:00",
                    "end_time": "2026-08-02T02:00:00",
                },
            }
        )
        assert api_client.get("/api/session/night/?date=2026-08-14").json()["tracking"] == []

    def test_session_started_after_midnight_belongs_to_the_night(
        self, api_client, mock_nights, mock_sessions
    ):
        # Une session démarrée à 1 h du matin appartient à la nuit de la veille.
        from datetime import datetime

        write_night_event(mock_nights, datetime(2026, 8, 14, 22, 0), state="wet")
        session_storage.save_session(
            {
                "session_id": "20260815_010000_NGC7640",
                "object": {"name": "NGC 7640"},
                "timing": {
                    "start_time": "2026-08-15T01:00:00",
                    "end_time": "2026-08-15T04:00:00",
                },
            }
        )
        data = api_client.get("/api/session/night/?date=2026-08-14").json()
        assert data["tracking"][0]["object_name"] == "NGC 7640"

    def test_night_bounds_are_noon_to_noon(self, api_client, mock_nights, mock_sessions):
        from datetime import datetime

        write_night_event(mock_nights, datetime(2026, 8, 14, 22, 0), state="wet")
        data = api_client.get("/api/session/night/?date=2026-08-14").json()
        assert data["night_start"].startswith("2026-08-14T12:00")
        assert data["night_end"].startswith("2026-08-15T12:00")
