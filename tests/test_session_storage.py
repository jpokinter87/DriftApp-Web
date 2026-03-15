"""
Tests pour web/session/session_storage.py

Couvre :
- generate_session_id : format et sanitisation
- save_session : sauvegarde JSON avec ID auto-généré
- list_sessions : tri, limite, répertoire vide
- load_session : existant, manquant
- delete_session : succès, manquant
- _cleanup_old_sessions : garde ≤ MAX_SESSIONS
"""

import json
from datetime import datetime

import pytest

from web.session import session_storage


@pytest.fixture
def sessions_dir(tmp_path, monkeypatch):
    """Répertoire temporaire pour les sessions."""
    sessions = tmp_path / "sessions"
    sessions.mkdir()
    monkeypatch.setattr(session_storage, "SESSIONS_DIR", sessions)
    return sessions


# =============================================================================
# generate_session_id
# =============================================================================


class TestGenerateSessionId:
    def test_format(self):
        dt = datetime(2025, 6, 21, 22, 0, 0)
        sid = session_storage.generate_session_id("M42", dt)
        assert sid == "20250621_220000_M42"

    def test_special_chars_sanitized(self):
        dt = datetime(2025, 1, 1, 0, 0, 0)
        sid = session_storage.generate_session_id("NGC 7000", dt)
        assert sid == "20250101_000000_NGC_7000"

    def test_default_time(self):
        sid = session_storage.generate_session_id("Vega")
        assert "Vega" in sid
        assert len(sid) > 15  # YYYYMMDD_HHMMSS_Name


# =============================================================================
# save_session
# =============================================================================


class TestSaveSession:
    def test_save_with_auto_id(self, sessions_dir):
        data = {
            "object": {"name": "M31"},
            "timing": {"start_time": "2025-06-21T22:00:00"},
        }
        sid = session_storage.save_session(data)
        assert sid is not None
        assert "M31" in sid
        assert (sessions_dir / f"{sid}.json").exists()

    def test_save_with_provided_id(self, sessions_dir):
        data = {"session_id": "test_session_001"}
        sid = session_storage.save_session(data)
        assert sid == "test_session_001"
        assert (sessions_dir / "test_session_001.json").exists()

    def test_save_creates_valid_json(self, sessions_dir):
        data = {"object": {"name": "M42"}, "summary": {"total": 5}}
        sid = session_storage.save_session(data)
        content = json.loads((sessions_dir / f"{sid}.json").read_text())
        assert content["object"]["name"] == "M42"
        assert content["version"] == "1.0"


# =============================================================================
# list_sessions
# =============================================================================


class TestListSessions:
    def test_empty_dir(self, sessions_dir):
        result = session_storage.list_sessions()
        assert result == []

    def test_returns_sessions(self, sessions_dir):
        for i in range(3):
            (sessions_dir / f"session_{i:02d}.json").write_text(
                json.dumps({"session_id": f"session_{i:02d}", "object": {"name": f"M{i}"}})
            )
        result = session_storage.list_sessions()
        assert len(result) == 3

    def test_respects_limit(self, sessions_dir):
        for i in range(10):
            (sessions_dir / f"session_{i:02d}.json").write_text(
                json.dumps({"session_id": f"session_{i:02d}"})
            )
        result = session_storage.list_sessions(limit=3)
        assert len(result) == 3

    def test_sorted_newest_first(self, sessions_dir):
        (sessions_dir / "a_old.json").write_text(json.dumps({"session_id": "a_old"}))
        (sessions_dir / "z_new.json").write_text(json.dumps({"session_id": "z_new"}))
        result = session_storage.list_sessions()
        # Sorted reverse by filename
        assert result[0]["session_id"] == "z_new"


# =============================================================================
# load_session
# =============================================================================


class TestLoadSession:
    def test_load_existing(self, sessions_dir):
        data = {"session_id": "test", "object": {"name": "M42"}}
        (sessions_dir / "test.json").write_text(json.dumps(data))
        result = session_storage.load_session("test")
        assert result is not None
        assert result["object"]["name"] == "M42"

    def test_load_missing(self, sessions_dir):
        result = session_storage.load_session("nonexistent")
        assert result is None


# =============================================================================
# delete_session
# =============================================================================


class TestDeleteSession:
    def test_delete_existing(self, sessions_dir):
        (sessions_dir / "to_delete.json").write_text("{}")
        assert session_storage.delete_session("to_delete") is True
        assert not (sessions_dir / "to_delete.json").exists()

    def test_delete_missing(self, sessions_dir):
        assert session_storage.delete_session("nonexistent") is False


# =============================================================================
# _cleanup_old_sessions
# =============================================================================


class TestCleanupOldSessions:
    def test_cleanup_removes_old_sessions(self, sessions_dir, monkeypatch):
        """Les sessions > MAX_SESSION_AGE_DAYS sont supprimées."""
        import os
        import time

        now = time.time()
        day = 86400
        monkeypatch.setattr(session_storage, "MAX_SESSION_AGE_DAYS", 7)

        # 2 récentes, 2 anciennes
        for i, age_days in enumerate([1, 3, 8, 10]):
            f = sessions_dir / f"session_{i:02d}.json"
            f.write_text("{}")
            mtime = now - (age_days * day)
            os.utime(f, (mtime, mtime))

        session_storage._cleanup_old_sessions()
        remaining = list(sessions_dir.glob("*.json"))
        assert len(remaining) == 2

    def test_no_cleanup_recent_sessions(self, sessions_dir, monkeypatch):
        """Les sessions récentes sont préservées quel que soit leur nombre."""
        monkeypatch.setattr(session_storage, "MAX_SESSION_AGE_DAYS", 7)
        for i in range(10):
            (sessions_dir / f"session_{i:02d}.json").write_text("{}")

        session_storage._cleanup_old_sessions()
        remaining = list(sessions_dir.glob("*.json"))
        assert len(remaining) == 10
