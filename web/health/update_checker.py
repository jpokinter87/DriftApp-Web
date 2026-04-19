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


def get_remote_version() -> str:
    """
    Lit la version depuis pyproject.toml de origin/main.

    Returns:
        Version string (ex: "5.0.1") ou "unknown" si erreur
    """
    try:
        result = subprocess.run(
            ['git', 'show', 'origin/main:pyproject.toml'],
            cwd=PROJECT_ROOT,
            capture_output=True,
            text=True,
            timeout=10
        )
        if result.returncode == 0:
            match = re.search(r'version\s*=\s*"([^"]+)"', result.stdout)
            return match.group(1) if match else "unknown"
        return "unknown"
    except (subprocess.TimeoutExpired, subprocess.SubprocessError, OSError) as e:
        logger.warning(f"Impossible de lire la version distante: {e}")
        return "unknown"


def get_files_changed() -> list[str]:
    """
    Liste les fichiers trackés qui vont être modifiés par le pull.

    Returns:
        Liste de chemins relatifs au repo (ex: ["data/config.json", "web/..."]).
        Liste vide si pas de mise à jour ou erreur.
    """
    try:
        result = subprocess.run(
            ['git', 'diff', '--name-only', 'HEAD..origin/main'],
            cwd=PROJECT_ROOT,
            capture_output=True,
            text=True,
            timeout=10
        )
        if result.returncode == 0 and result.stdout.strip():
            return result.stdout.strip().split('\n')
        return []
    except (subprocess.SubprocessError, OSError) as e:
        logger.warning(f"Erreur git diff --name-only: {e}")
        return []


# Fichiers utilisateur potentiellement personnalisés — avertir l'utilisateur
# si la MàJ les touche (ses réglages locaux seront préservés mais la version
# upstream doit être mergée manuellement).
_USER_CONFIG_PATTERNS = ('data/config.json', 'data/Loi_coupole.xlsx')


def get_config_files_affected(files_changed: list[str] | None = None) -> list[str]:
    """
    Filtre les fichiers de config utilisateur parmi les fichiers changés.

    Args:
        files_changed: Liste optionnelle (sinon appelle get_files_changed()).

    Returns:
        Sous-liste des fichiers matchant _USER_CONFIG_PATTERNS.
    """
    if files_changed is None:
        files_changed = get_files_changed()
    return [f for f in files_changed if f in _USER_CONFIG_PATTERNS]


def _version_tuple(version_str: str) -> tuple:
    """
    Convertit une version string en tuple pour comparaison.

    Args:
        version_str: Version (ex: "5.4.0")

    Returns:
        Tuple d'entiers (ex: (5, 4, 0)) ou (0,) si invalide
    """
    if not version_str or version_str == "unknown":
        return (0,)
    try:
        return tuple(int(x) for x in version_str.split('.'))
    except (ValueError, AttributeError):
        return (0,)


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
    local_ver = get_local_version()
    remote_ver = get_remote_version()

    # Mise à jour disponible seulement si :
    # 1. Le fetch a réussi (données fiables de origin/main)
    # 2. Il y a des commits de retard
    # 3. La version distante est strictement supérieure à la locale
    update_available = (
        fetch_success
        and commits_behind > 0
        and _version_tuple(remote_ver) > _version_tuple(local_ver)
    )

    result = {
        'update_available': update_available,
        'local_version': local_ver,
        'local_commit': local_commit,
        'remote_commit': remote_commit,
        'commits_behind': commits_behind,
        'remote_version': remote_ver,
        'fetch_success': fetch_success
    }

    # Ajouter les détails de la mise à jour si dispo
    if update_available:
        result['commit_messages'] = get_commit_messages(min(commits_behind, 10))
        files_changed = get_files_changed()
        result['files_changed'] = files_changed
        result['config_files_affected'] = get_config_files_affected(files_changed)

    return result
