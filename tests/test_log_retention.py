"""
Tests pour la rétention temporelle des logs et la sauvegarde session robuste.

Vérifie :
- Rétention par âge (7 jours) au lieu de par nombre de fichiers
- Sauvegarde session même en cas d'erreur dans _log_session_summary
- Fallback de sécurité (nombre max absolu)
"""

import os
import time
from unittest.mock import patch, MagicMock


# =========================================================================
# Tests rétention temporelle motor_service logs
# =========================================================================


class TestMotorServiceLogRetention:
    """Tests pour cleanup_old_logs dans services/motor_service.py."""

    def test_cleanup_removes_old_files_only(self, tmp_path):
        """Les fichiers > 7 jours sont supprimés, les récents préservés."""
        now = time.time()
        day = 86400

        # Créer des fichiers avec des âges variés
        files = {
            "motor_service_recent_1d.log": now - 1 * day,
            "motor_service_recent_5d.log": now - 5 * day,
            "motor_service_old_8d.log": now - 8 * day,
            "motor_service_old_10d.log": now - 10 * day,
        }

        for name, mtime in files.items():
            f = tmp_path / name
            f.write_text("log content")
            os.utime(f, (mtime, mtime))

        # Importer et patcher LOGS_DIR
        with patch("services.motor_service.LOGS_DIR", tmp_path):
            from services.motor_service import cleanup_old_logs

            cleanup_old_logs()

        remaining = [f.name for f in tmp_path.glob("motor_service_*.log")]
        assert "motor_service_recent_1d.log" in remaining
        assert "motor_service_recent_5d.log" in remaining
        assert "motor_service_old_8d.log" not in remaining
        assert "motor_service_old_10d.log" not in remaining

    def test_cleanup_preserves_all_recent_files(self, tmp_path):
        """Même avec beaucoup de fichiers récents, aucun n'est supprimé."""
        now = time.time()

        # Créer 30 fichiers récents (< 7 jours)
        for i in range(30):
            f = tmp_path / f"motor_service_{i:02d}.log"
            f.write_text("log content")
            mtime = now - (i * 3600)  # Espacés d'une heure
            os.utime(f, (mtime, mtime))

        with patch("services.motor_service.LOGS_DIR", tmp_path):
            from services.motor_service import cleanup_old_logs

            cleanup_old_logs()

        remaining = list(tmp_path.glob("motor_service_*.log"))
        assert len(remaining) == 30

    def test_cleanup_safety_fallback(self, tmp_path):
        """Le fallback de sécurité supprime si > MAX_LOG_FILES_SAFETY."""
        now = time.time()

        # Créer plus de fichiers que le fallback (simulé)
        with (
            patch("services.motor_service.LOGS_DIR", tmp_path),
            patch("services.motor_service.MAX_LOG_FILES_SAFETY", 5),
        ):
            # Créer 10 fichiers récents
            for i in range(10):
                f = tmp_path / f"motor_service_{i:02d}.log"
                f.write_text("log content")
                mtime = now - (i * 3600)
                os.utime(f, (mtime, mtime))

            from services.motor_service import cleanup_old_logs

            cleanup_old_logs()

        remaining = list(tmp_path.glob("motor_service_*.log"))
        assert len(remaining) == 5


# =========================================================================
# Tests rétention temporelle session_storage
# =========================================================================


class TestSessionStorageRetention:
    """Tests pour _cleanup_old_sessions dans web/session/session_storage.py."""

    def test_cleanup_removes_old_sessions_only(self, tmp_path):
        """Les sessions > 7 jours sont supprimées, les récentes préservées."""
        now = time.time()
        day = 86400

        files = {
            "20260315_120000_M__42.json": now - 1 * day,
            "20260310_120000_NGC__7000.json": now - 5 * day,
            "20260307_120000_IC__405.json": now - 8 * day,
            "20260305_120000_M__31.json": now - 10 * day,
        }

        for name, mtime in files.items():
            f = tmp_path / name
            f.write_text('{"session_id": "test"}')
            os.utime(f, (mtime, mtime))

        with patch("web.session.session_storage.SESSIONS_DIR", tmp_path):
            from web.session.session_storage import _cleanup_old_sessions

            _cleanup_old_sessions()

        remaining = [f.name for f in tmp_path.glob("*.json")]
        assert "20260315_120000_M__42.json" in remaining
        assert "20260310_120000_NGC__7000.json" in remaining
        assert "20260307_120000_IC__405.json" not in remaining
        assert "20260305_120000_M__31.json" not in remaining

    def test_cleanup_safety_fallback_sessions(self, tmp_path):
        """Le fallback de sécurité limite le nombre total de sessions."""
        now = time.time()

        with (
            patch("web.session.session_storage.SESSIONS_DIR", tmp_path),
            patch("web.session.session_storage.MAX_SESSIONS_SAFETY", 3),
        ):
            for i in range(8):
                f = tmp_path / f"session_{i:02d}.json"
                f.write_text('{"session_id": "test"}')
                mtime = now - (i * 3600)
                os.utime(f, (mtime, mtime))

            from web.session.session_storage import _cleanup_old_sessions

            _cleanup_old_sessions()

        remaining = list(tmp_path.glob("*.json"))
        assert len(remaining) == 3


# =========================================================================
# Tests sauvegarde session robuste
# =========================================================================


class TestRobustSessionSave:
    """Tests pour la sauvegarde session même en cas d'erreur."""

    def test_save_called_even_if_summary_fails(self):
        """_save_session_to_file est appelé même si _log_session_summary échoue."""
        from core.tracking.tracker import TrackingSession

        session = MagicMock(spec=TrackingSession)
        session.logger = MagicMock()

        # Simuler l'appel à stop() avec _log_session_summary qui échoue
        session._log_session_summary = MagicMock(side_effect=RuntimeError("summary error"))
        session._save_session_to_file = MagicMock()
        session._finalize_stop = MagicMock()

        # Appeler la vraie méthode stop
        TrackingSession.stop(session)

        # _save_session_to_file doit être appelé malgré l'erreur
        session._save_session_to_file.assert_called_once()
        session._finalize_stop.assert_called_once()
        session.logger.error.assert_called_once()

    def test_save_session_logs_error_not_silent(self):
        """_save_session_to_file logge les erreurs au lieu de les ignorer."""
        from core.tracking.tracker import TrackingSession

        session = MagicMock(spec=TrackingSession)
        session.logger = MagicMock()
        session.objet = "M42"
        session.ra_deg = 83.8
        session.dec_deg = -5.4

        # Mock get_session_data pour lever une exception
        session.get_session_data = MagicMock(side_effect=RuntimeError("data error"))

        # Appeler la vraie méthode
        TrackingSession._save_session_to_file(session)

        # Doit logger un warning (pas silencieux)
        session.logger.warning.assert_called_once()
        assert "data error" in str(session.logger.warning.call_args)

    def test_tracking_handler_stop_fallback_save(self):
        """TrackingHandler.stop() tente la sauvegarde même si session.stop() échoue."""
        from services.command_handlers import TrackingHandler

        handler = MagicMock(spec=TrackingHandler)
        mock_session = MagicMock()
        mock_session.stop = MagicMock(side_effect=RuntimeError("stop error"))
        mock_session._save_session_to_file = MagicMock()
        handler.session = mock_session
        handler.simulation_mode = False
        handler.active = True
        handler.status_callback = MagicMock()

        current_status = {
            "status": "tracking",
            "tracking_object": "M42",
            "tracking_pending": False,
            "goto_info": None,
            "mode": "normal",
        }

        # Appeler la vraie méthode stop
        TrackingHandler.stop(handler, current_status)

        # Fallback sauvegarde doit être tenté
        mock_session._save_session_to_file.assert_called_once()
        assert handler.session is None  # Session nettoyée
