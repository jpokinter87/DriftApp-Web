import json
import time
from pathlib import Path
from typing import Tuple, Optional

# Chemin vers la mémoire partagée (RAM)
SHARED_FILE = Path("/dev/shm/ems22_position.json")


def read_encoder_daemon(max_age_seconds: float = 2.0) -> Tuple[Optional[float], bool, float]:
    """
    Lit la position depuis le démon de manière sécurisée.

    Returns:
        Tuple (angle, status_ok, timestamp)
        - angle: Position en degrés (0-360) ou None si erreur
        - status_ok: True si démon OK et données fraîches
        - timestamp: Heure de la mesure
    """
    if not SHARED_FILE.exists():
        return None, False, 0.0

    try:
        with open(SHARED_FILE, "r") as f:
            data = json.load(f)

        timestamp = data.get("ts", 0)
        age = time.time() - timestamp

        # Vérifier si les données sont périmées
        if age > max_age_seconds:
            return data.get("angle"), False, timestamp

        is_ok = (data.get("status") == "OK")
        return data.get("angle"), is_ok, timestamp

    except (json.JSONDecodeError, OSError):
        return None, False, 0.0