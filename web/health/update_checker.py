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

logger = logging.getLogger(__name__)

# Répertoire racine du projet (parent de 'web')
PROJECT_ROOT = Path(__file__).resolve().parent.parent.parent


def get_local_version() -> str:
    """
    Lit la version depuis pyproject.toml.

    Returns:
        Version string (ex: "4.4.0") ou "unknown" si erreur
    """
    pyproject_path = PROJECT_ROOT / "pyproject.toml"
    try:
        content = pyproject_path.read_text()
        match = re.search(r'version\s*=\s*"([^"]+)"', content)
        return match.group(1) if match else "unknown"
    except (OSError, AttributeError) as e:
        logger.warning(f"Impossible de lire la version: {e}")
        return "unknown"


def get_local_commit() -> str:
    """
    Obtient le hash court du commit HEAD local.

    Returns:
        Hash court (ex: "4ee58f9") ou "unknown" si erreur
    """
    try:
        result = subprocess.run(
            ['git', 'rev-parse', '--short', 'HEAD'],
            cwd=PROJECT_ROOT,
            capture_output=True,
            text=True,
            timeout=10
        )
        return result.stdout.strip() if result.returncode == 0 else "unknown"
    except subprocess.TimeoutExpired:
        logger.warning("Timeout lors de git rev-parse HEAD")
        return "unknown"
    except (subprocess.SubprocessError, OSError) as e:
        logger.warning(f"Erreur git rev-parse: {e}")
        return "unknown"


def fetch_remote() -> bool:
    """
    Télécharge les références de origin/main sans merger.

    Returns:
        True si succès, False sinon
    """
    try:
        result = subprocess.run(
            ['git', 'fetch', 'origin', 'main'],
            cwd=PROJECT_ROOT,
            capture_output=True,
            text=True,
            timeout=30
        )
        if result.returncode != 0:
            logger.warning(f"git fetch a échoué: {result.stderr}")
        return result.returncode == 0
    except subprocess.TimeoutExpired:
        logger.warning("Timeout lors de git fetch (30s)")
        return False
    except (subprocess.SubprocessError, OSError) as e:
        logger.warning(f"Erreur git fetch: {e}")
        return False


def get_remote_commit() -> str:
    """
    Obtient le hash court de origin/main.

    Returns:
        Hash court (ex: "a1b2c3d") ou "unknown" si erreur
    """
    try:
        result = subprocess.run(
            ['git', 'rev-parse', '--short', 'origin/main'],
            cwd=PROJECT_ROOT,
            capture_output=True,
            text=True,
            timeout=10
        )
        return result.stdout.strip() if result.returncode == 0 else "unknown"
    except subprocess.TimeoutExpired:
        logger.warning("Timeout lors de git rev-parse origin/main")
        return "unknown"
    except (subprocess.SubprocessError, OSError) as e:
        logger.warning(f"Erreur git rev-parse origin/main: {e}")
        return "unknown"


def count_commits_behind() -> int:
    """
    Compte le nombre de commits de retard par rapport à origin/main.

    Returns:
        Nombre de commits de retard, 0 si erreur ou à jour
    """
    try:
        result = subprocess.run(
            ['git', 'rev-list', '--count', 'HEAD..origin/main'],
            cwd=PROJECT_ROOT,
            capture_output=True,
            text=True,
            timeout=10
        )
        if result.returncode == 0:
            return int(result.stdout.strip())
        return 0
    except (subprocess.TimeoutExpired, ValueError) as e:
        logger.warning(f"Erreur count commits: {e}")
        return 0
    except (subprocess.SubprocessError, OSError) as e:
        logger.warning(f"Erreur git rev-list: {e}")
        return 0


def get_commit_messages(count: int = 5) -> list[str]:
    """
    Obtient les messages des derniers commits sur origin/main.

    Args:
        count: Nombre de messages à récupérer

    Returns:
        Liste des messages de commit
    """
    try:
        result = subprocess.run(
            ['git', 'log', '--oneline', f'-{count}', 'HEAD..origin/main'],
            cwd=PROJECT_ROOT,
            capture_output=True,
            text=True,
            timeout=10
        )
        if result.returncode == 0 and result.stdout.strip():
            return result.stdout.strip().split('\n')
        return []
    except (subprocess.SubprocessError, OSError) as e:
        logger.warning(f"Erreur git log: {e}")
        return []


def check_for_updates() -> dict:
    """
    Vérifie si des mises à jour sont disponibles.

    Effectue un git fetch puis compare HEAD avec origin/main.

    Returns:
        dict avec:
            - update_available: bool
            - local_version: str (ex: "4.4.0")
            - local_commit: str (ex: "4ee58f9")
            - remote_commit: str (ex: "a1b2c3d")
            - commits_behind: int
            - commit_messages: list[str] (si mise à jour dispo)
            - fetch_success: bool
    """
    # Fetch les dernières références
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
        'fetch_success': fetch_success
    }

    # Ajouter les messages de commit si mise à jour disponible
    if update_available:
        result['commit_messages'] = get_commit_messages(min(commits_behind, 10))

    return result
