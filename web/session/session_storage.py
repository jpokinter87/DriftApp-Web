"""
Session Storage - Gestion de la persistance des sessions de tracking.

Sauvegarde et lecture des sessions de suivi au format JSON.
"""

import json
import logging
from datetime import datetime
from pathlib import Path
from typing import Optional

logger = logging.getLogger(__name__)

# Répertoire de stockage des sessions
SESSIONS_DIR = Path(__file__).parent.parent.parent / 'data' / 'sessions'

# Nombre maximum de sessions conservées
MAX_SESSIONS = 100


def _ensure_sessions_dir():
    """Crée le répertoire sessions s'il n'existe pas."""
    SESSIONS_DIR.mkdir(parents=True, exist_ok=True)


def generate_session_id(object_name: str, start_time: datetime = None) -> str:
    """
    Génère un ID unique pour une session.

    Format: YYYYMMDD_HHMMSS_ObjectName
    """
    if start_time is None:
        start_time = datetime.now()

    # Nettoyer le nom d'objet pour le système de fichiers
    safe_name = "".join(c if c.isalnum() else "_" for c in object_name)

    return f"{start_time.strftime('%Y%m%d_%H%M%S')}_{safe_name}"


def save_session(session_data: dict) -> Optional[str]:
    """
    Sauvegarde une session dans un fichier JSON.

    Args:
        session_data: Données de session à sauvegarder

    Returns:
        session_id si succès, None sinon
    """
    _ensure_sessions_dir()

    try:
        session_id = session_data.get('session_id')
        if not session_id:
            # Générer un ID si non fourni
            object_name = session_data.get('object', {}).get('name', 'unknown')
            start_time_str = session_data.get('timing', {}).get('start_time')
            if start_time_str:
                start_time = datetime.fromisoformat(start_time_str)
            else:
                start_time = datetime.now()
            session_id = generate_session_id(object_name, start_time)
            session_data['session_id'] = session_id

        # Ajouter version si manquante
        if 'version' not in session_data:
            session_data['version'] = '1.0'

        file_path = SESSIONS_DIR / f"{session_id}.json"

        with open(file_path, 'w', encoding='utf-8') as f:
            json.dump(session_data, f, indent=2, ensure_ascii=False, default=str)

        logger.info(f"Session sauvegardée: {session_id}")

        # Nettoyage des anciennes sessions
        _cleanup_old_sessions()

        return session_id

    except (OSError, IOError, ValueError, TypeError) as e:
        logger.error(f"Erreur sauvegarde session: {e}")
        return None


def list_sessions(limit: int = 50) -> list:
    """
    Liste les sessions sauvegardées avec leurs métadonnées.

    Returns:
        Liste de dictionnaires avec résumé de chaque session
    """
    _ensure_sessions_dir()

    sessions = []

    try:
        # Lister tous les fichiers JSON
        json_files = sorted(SESSIONS_DIR.glob('*.json'), reverse=True)

        for file_path in json_files[:limit]:
            try:
                with open(file_path, 'r', encoding='utf-8') as f:
                    data = json.load(f)

                # Extraire le résumé
                sessions.append({
                    'session_id': data.get('session_id', file_path.stem),
                    'object_name': data.get('object', {}).get('name', 'Inconnu'),
                    'start_time': data.get('timing', {}).get('start_time'),
                    'end_time': data.get('timing', {}).get('end_time'),
                    'duration_seconds': data.get('timing', {}).get('duration_seconds', 0),
                    'total_corrections': data.get('summary', {}).get('total_corrections', 0),
                    'total_movement_deg': data.get('summary', {}).get('total_movement_deg', 0),
                })
            except (OSError, IOError, json.JSONDecodeError) as e:
                logger.warning(f"Erreur lecture session {file_path}: {e}")
                continue

    except OSError as e:
        logger.error(f"Erreur listage sessions: {e}")

    return sessions


def load_session(session_id: str) -> Optional[dict]:
    """
    Charge une session par son ID.

    Returns:
        Données complètes de la session ou None
    """
    _ensure_sessions_dir()

    file_path = SESSIONS_DIR / f"{session_id}.json"

    if not file_path.exists():
        logger.warning(f"Session non trouvée: {session_id}")
        return None

    try:
        with open(file_path, 'r', encoding='utf-8') as f:
            return json.load(f)
    except (OSError, IOError, json.JSONDecodeError) as e:
        logger.error(f"Erreur chargement session {session_id}: {e}")
        return None


def delete_session(session_id: str) -> bool:
    """
    Supprime une session.

    Returns:
        True si supprimée, False sinon
    """
    file_path = SESSIONS_DIR / f"{session_id}.json"

    try:
        if file_path.exists():
            file_path.unlink()
            logger.info(f"Session supprimée: {session_id}")
            return True
        return False
    except OSError as e:
        logger.error(f"Erreur suppression session {session_id}: {e}")
        return False


def _cleanup_old_sessions():
    """Supprime les sessions les plus anciennes si > MAX_SESSIONS."""
    try:
        json_files = sorted(SESSIONS_DIR.glob('*.json'), reverse=True)

        if len(json_files) > MAX_SESSIONS:
            # Supprimer les plus anciennes
            for file_path in json_files[MAX_SESSIONS:]:
                try:
                    file_path.unlink()
                    logger.debug(f"Session ancienne supprimée: {file_path.stem}")
                except OSError:
                    pass

    except OSError as e:
        logger.warning(f"Erreur nettoyage sessions: {e}")
