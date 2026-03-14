"""
Module de vérification des mises à jour GitHub pour DriftApp Web.

Compare le HEAD local avec origin/main pour détecter les mises à jour disponibles.
Utilise les commandes git en subprocess avec timeout et gestion d'erreurs.

Usage:
    from health.update_checker import check_for_updates
    result = check_for_updates()
    if result['update_available']:
        print(f"Mise à jour disponible: {result['commits_behind']} commit(s)")
"""

import logging
import re
import subprocess
from pathlib import Path

from core.config.config_loader import PROJECT_ROOT, get_version

logger = logging.getLogger(__name__)


def get_local_version() -> str:
    """Retourne la version locale depuis pyproject.toml."""
    return get_version()


def get_local_commit() -> str:
    """Obtient le hash court du commit HEAD local."""
    try:
        result = subprocess.run(
            ['git', 'rev-parse', '--short', 'HEAD'],
            cwd=PROJECT_ROOT,
            capture_output=True, text=True, timeout=10
        )
        return result.stdout.strip() if result.returncode == 0 else "unknown"
    except (subprocess.TimeoutExpired, subprocess.SubprocessError, OSError) as e:
        logger.warning(f"Erreur git rev-parse: {e}")
        return "unknown"


def fetch_remote() -> bool:
    """Télécharge les références de origin/main sans merger."""
    try:
        result = subprocess.run(
            ['git', 'fetch', 'origin', 'main'],
            cwd=PROJECT_ROOT,
            capture_output=True, text=True, timeout=30
        )
        if result.returncode != 0:
            logger.warning(f"git fetch a échoué: {result.stderr}")
        return result.returncode == 0
    except (subprocess.TimeoutExpired, subprocess.SubprocessError, OSError) as e:
        logger.warning(f"Erreur git fetch: {e}")
        return False


def get_remote_commit() -> str:
    """Obtient le hash court de origin/main."""
    try:
        result = subprocess.run(
            ['git', 'rev-parse', '--short', 'origin/main'],
            cwd=PROJECT_ROOT,
            capture_output=True, text=True, timeout=10
        )
        return result.stdout.strip() if result.returncode == 0 else "unknown"
    except (subprocess.TimeoutExpired, subprocess.SubprocessError, OSError) as e:
        logger.warning(f"Erreur git rev-parse origin/main: {e}")
        return "unknown"


def count_commits_behind() -> int:
    """Compte le nombre de commits de retard par rapport à origin/main."""
    try:
        result = subprocess.run(
            ['git', 'rev-list', '--count', 'HEAD..origin/main'],
            cwd=PROJECT_ROOT,
            capture_output=True, text=True, timeout=10
        )
        if result.returncode == 0:
            return int(result.stdout.strip())
        return 0
    except (subprocess.TimeoutExpired, ValueError, subprocess.SubprocessError, OSError) as e:
        logger.warning(f"Erreur count commits: {e}")
        return 0


def get_commit_messages(count: int = 5) -> list:
    """Obtient les messages des derniers commits sur origin/main."""
    try:
        result = subprocess.run(
            ['git', 'log', '--oneline', f'-{count}', 'HEAD..origin/main'],
            cwd=PROJECT_ROOT,
            capture_output=True, text=True, timeout=10
        )
        if result.returncode == 0 and result.stdout.strip():
            return result.stdout.strip().split('\n')
        return []
    except (subprocess.SubprocessError, OSError) as e:
        logger.warning(f"Erreur git log: {e}")
        return []


def get_remote_version() -> str:
    """Lit la version depuis pyproject.toml de origin/main."""
    try:
        result = subprocess.run(
            ['git', 'show', 'origin/main:pyproject.toml'],
            cwd=PROJECT_ROOT,
            capture_output=True, text=True, timeout=10
        )
        if result.returncode == 0:
            match = re.search(r'version\s*=\s*"([^"]+)"', result.stdout)
            return match.group(1) if match else "unknown"
        return "unknown"
    except (subprocess.TimeoutExpired, subprocess.SubprocessError, OSError) as e:
        logger.warning(f"Impossible de lire la version distante: {e}")
        return "unknown"


def check_for_updates() -> dict:
    """
    Vérifie si des mises à jour sont disponibles.

    Returns:
        dict avec update_available, versions, commits, etc.
    """
    fetch_success = fetch_remote()
    local_commit = get_local_commit()
    remote_commit = get_remote_commit()
    commits_behind = count_commits_behind()
    update_available = commits_behind > 0

    result = {
        'update_available': update_available,
        'local_version': get_local_version(),
        'local_commit': local_commit,
        'remote_commit': remote_commit,
        'commits_behind': commits_behind,
        'remote_version': get_remote_version(),
        'fetch_success': fetch_success
    }

    if update_available:
        result['commit_messages'] = get_commit_messages(min(commits_behind, 10))

    return result
