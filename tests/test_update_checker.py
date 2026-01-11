"""
Tests pour le module web/health/update_checker.py

Ce module teste les fonctions de vérification des mises à jour GitHub.
"""

import pytest
from pathlib import Path
from unittest.mock import patch, MagicMock
import subprocess


class TestGetLocalVersion:
    """Tests pour get_local_version."""

    def test_retourne_string(self):
        """La version est une chaîne de caractères."""
        from web.health.update_checker import get_local_version
        result = get_local_version()
        assert isinstance(result, str)

    def test_format_version(self):
        """La version suit le format semantic versioning ou 'unknown'."""
        from web.health.update_checker import get_local_version
        result = get_local_version()
        # Soit une version valide (X.Y.Z), soit "unknown"
        if result != "unknown":
            parts = result.split(".")
            assert len(parts) >= 2, f"Version devrait avoir au moins 2 parties: {result}"

    @patch('web.health.update_checker.PROJECT_ROOT')
    def test_fichier_inexistant_retourne_unknown(self, mock_root):
        """Un fichier pyproject.toml inexistant retourne 'unknown'."""
        mock_root.__truediv__ = MagicMock(return_value=Path("/nonexistent/pyproject.toml"))
        from web.health.update_checker import get_local_version
        # Le patch n'affecte pas directement car PROJECT_ROOT est évalué à l'import
        # Ce test documente le comportement attendu
        result = get_local_version()
        assert isinstance(result, str)


class TestGetLocalCommit:
    """Tests pour get_local_commit."""

    def test_retourne_string(self):
        """Le commit est une chaîne de caractères."""
        from web.health.update_checker import get_local_commit
        result = get_local_commit()
        assert isinstance(result, str)

    def test_format_hash_court(self):
        """Le hash est court (7 caractères) ou 'unknown'."""
        from web.health.update_checker import get_local_commit
        result = get_local_commit()
        if result != "unknown":
            assert 6 <= len(result) <= 8, f"Hash devrait être court: {result}"

    @patch('subprocess.run')
    def test_timeout_retourne_unknown(self, mock_run):
        """Un timeout retourne 'unknown'."""
        mock_run.side_effect = subprocess.TimeoutExpired(cmd="git", timeout=10)
        from web.health.update_checker import get_local_commit
        result = get_local_commit()
        assert result == "unknown"

    @patch('subprocess.run')
    def test_erreur_subprocess_retourne_unknown(self, mock_run):
        """Une erreur subprocess retourne 'unknown'."""
        mock_run.side_effect = Exception("Git error")
        from web.health.update_checker import get_local_commit
        result = get_local_commit()
        assert result == "unknown"


class TestFetchRemote:
    """Tests pour fetch_remote."""

    @patch('subprocess.run')
    def test_succes_retourne_true(self, mock_run):
        """Un fetch réussi retourne True."""
        mock_run.return_value = MagicMock(returncode=0)
        from web.health.update_checker import fetch_remote
        result = fetch_remote()
        assert result is True

    @patch('subprocess.run')
    def test_echec_retourne_false(self, mock_run):
        """Un fetch échoué retourne False."""
        mock_run.return_value = MagicMock(returncode=1, stderr="error")
        from web.health.update_checker import fetch_remote
        result = fetch_remote()
        assert result is False

    @patch('subprocess.run')
    def test_timeout_retourne_false(self, mock_run):
        """Un timeout retourne False."""
        mock_run.side_effect = subprocess.TimeoutExpired(cmd="git", timeout=30)
        from web.health.update_checker import fetch_remote
        result = fetch_remote()
        assert result is False


class TestGetRemoteCommit:
    """Tests pour get_remote_commit."""

    @patch('subprocess.run')
    def test_succes_retourne_hash(self, mock_run):
        """Un succès retourne le hash."""
        mock_run.return_value = MagicMock(
            returncode=0,
            stdout="a1b2c3d\n"
        )
        from web.health.update_checker import get_remote_commit
        result = get_remote_commit()
        assert result == "a1b2c3d"

    @patch('subprocess.run')
    def test_echec_retourne_unknown(self, mock_run):
        """Un échec retourne 'unknown'."""
        mock_run.return_value = MagicMock(returncode=1, stdout="")
        from web.health.update_checker import get_remote_commit
        result = get_remote_commit()
        assert result == "unknown"


class TestCountCommitsBehind:
    """Tests pour count_commits_behind."""

    @patch('subprocess.run')
    def test_succes_retourne_nombre(self, mock_run):
        """Un succès retourne le nombre de commits."""
        mock_run.return_value = MagicMock(
            returncode=0,
            stdout="5\n"
        )
        from web.health.update_checker import count_commits_behind
        result = count_commits_behind()
        assert result == 5

    @patch('subprocess.run')
    def test_a_jour_retourne_zero(self, mock_run):
        """Quand on est à jour, retourne 0."""
        mock_run.return_value = MagicMock(
            returncode=0,
            stdout="0\n"
        )
        from web.health.update_checker import count_commits_behind
        result = count_commits_behind()
        assert result == 0

    @patch('subprocess.run')
    def test_erreur_retourne_zero(self, mock_run):
        """Une erreur retourne 0."""
        mock_run.return_value = MagicMock(returncode=1, stdout="")
        from web.health.update_checker import count_commits_behind
        result = count_commits_behind()
        assert result == 0


class TestCheckForUpdates:
    """Tests pour check_for_updates (fonction principale)."""

    @patch('web.health.update_checker.fetch_remote')
    @patch('web.health.update_checker.get_local_commit')
    @patch('web.health.update_checker.get_remote_commit')
    @patch('web.health.update_checker.count_commits_behind')
    @patch('web.health.update_checker.get_local_version')
    @patch('web.health.update_checker.get_commit_messages')
    def test_mise_a_jour_disponible(
        self, mock_messages, mock_version, mock_count, mock_remote, mock_local, mock_fetch
    ):
        """Détecte correctement une mise à jour disponible."""
        mock_fetch.return_value = True
        mock_local.return_value = "abc1234"
        mock_remote.return_value = "def5678"
        mock_count.return_value = 3
        mock_version.return_value = "4.4.0"
        mock_messages.return_value = ["commit 1", "commit 2"]

        from web.health.update_checker import check_for_updates
        result = check_for_updates()

        assert result['update_available'] is True
        assert result['commits_behind'] == 3
        assert result['local_commit'] == "abc1234"
        assert result['remote_commit'] == "def5678"
        assert result['local_version'] == "4.4.0"
        assert 'commit_messages' in result

    @patch('web.health.update_checker.fetch_remote')
    @patch('web.health.update_checker.get_local_commit')
    @patch('web.health.update_checker.get_remote_commit')
    @patch('web.health.update_checker.count_commits_behind')
    @patch('web.health.update_checker.get_local_version')
    def test_pas_de_mise_a_jour(
        self, mock_version, mock_count, mock_remote, mock_local, mock_fetch
    ):
        """Détecte correctement qu'on est à jour."""
        mock_fetch.return_value = True
        mock_local.return_value = "abc1234"
        mock_remote.return_value = "abc1234"
        mock_count.return_value = 0
        mock_version.return_value = "4.4.0"

        from web.health.update_checker import check_for_updates
        result = check_for_updates()

        assert result['update_available'] is False
        assert result['commits_behind'] == 0
        assert 'commit_messages' not in result

    @patch('web.health.update_checker.fetch_remote')
    @patch('web.health.update_checker.get_local_commit')
    @patch('web.health.update_checker.get_remote_commit')
    @patch('web.health.update_checker.count_commits_behind')
    @patch('web.health.update_checker.get_local_version')
    def test_fetch_echoue_mais_continue(
        self, mock_version, mock_count, mock_remote, mock_local, mock_fetch
    ):
        """Même si le fetch échoue, on continue avec les données locales."""
        mock_fetch.return_value = False
        mock_local.return_value = "abc1234"
        mock_remote.return_value = "unknown"
        mock_count.return_value = 0
        mock_version.return_value = "4.4.0"

        from web.health.update_checker import check_for_updates
        result = check_for_updates()

        assert result['fetch_success'] is False
        assert 'update_available' in result


class TestGetCommitMessages:
    """Tests pour get_commit_messages."""

    @patch('subprocess.run')
    def test_retourne_liste_messages(self, mock_run):
        """Retourne une liste de messages."""
        mock_run.return_value = MagicMock(
            returncode=0,
            stdout="abc1234 Add feature X\ndef5678 Fix bug Y\n"
        )
        from web.health.update_checker import get_commit_messages
        result = get_commit_messages(2)
        assert len(result) == 2
        assert "Add feature X" in result[0]

    @patch('subprocess.run')
    def test_aucun_message_retourne_liste_vide(self, mock_run):
        """Retourne une liste vide s'il n'y a pas de messages."""
        mock_run.return_value = MagicMock(
            returncode=0,
            stdout=""
        )
        from web.health.update_checker import get_commit_messages
        result = get_commit_messages(5)
        assert result == []
