import fcntl
import json
import time
from pathlib import Path
from typing import Tuple, Optional

from core.config.config import IPC_ENCODER_POSITION

# Alias for backward compatibility
SHARED_FILE = IPC_ENCODER_POSITION


def read_encoder_daemon(max_age_seconds: float = 2.0) -> Tuple[Optional[float], bool, float]:
    """
    Lit la position depuis le démon de manière sécurisée.

    Utilise un verrou fcntl partagé pour éviter les race conditions
    avec le daemon encodeur qui écrit dans ce fichier.

    Returns:
        Tuple (angle, status_ok, timestamp)
        - angle: Position en degrés (0-360) ou None si erreur
        - status_ok: True si démon OK et données fraîches
        - timestamp: Heure de la mesure
    """
    try:
        with open(SHARED_FILE, "r") as f:
            # Verrou partagé non-bloquant
            fcntl.flock(f.fileno(), fcntl.LOCK_SH | fcntl.LOCK_NB)
            try:
                data = json.load(f)
            finally:
                fcntl.flock(f.fileno(), fcntl.LOCK_UN)

        timestamp = data.get("ts", 0)
        age = time.time() - timestamp

        # Vérifier si les données sont périmées
        if age > max_age_seconds:
            return data.get("angle"), False, timestamp

        is_ok = (data.get("status") == "OK")
        return data.get("angle"), is_ok, timestamp

    except (BlockingIOError, FileNotFoundError, json.JSONDecodeError, OSError):
        return None, False, 0.0