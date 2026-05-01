"""
Client IPC pour communiquer avec le Cimier Service (v6.0 Phase 1).

Module miroir de `web.common.ipc_client` mais dédié au cimier_service. Le
découplage est volontaire : pas d'import croisé Django ↔ services.* (les
deux processus tournent indépendamment). La duplication minime du
read/write atomique est acceptée — c'est la même convention que pour
motor_client.

Usage:
    from web.common.cimier_client import cimier_client

    cimier_client.send_command("open")     # écrit /dev/shm/cimier_command.json
    cimier_client.send_command("close")
    cimier_client.send_command("stop")
    state = cimier_client.get_status()     # lit /dev/shm/cimier_status.json
"""

import fcntl
import json
import uuid
from pathlib import Path
from time import time
from typing import Optional

from django.conf import settings


class CimierServiceClient:
    """Client IPC fichiers JSON partagés (/dev/shm) côté Django.

    Les chemins viennent uniquement de `settings.CIMIER_SERVICE_IPC` —
    pas de hardcode dans ce module (règle no-hardcoded-IPs/paths).
    """

    def __init__(self):
        self.command_file = Path(settings.CIMIER_SERVICE_IPC["COMMAND_FILE"])
        self.status_file = Path(settings.CIMIER_SERVICE_IPC["STATUS_FILE"])

    def _read_json_file_safe(self, file_path: Path) -> Optional[dict]:
        """Lecture atomique avec verrou partagé non-bloquant.

        Pattern strict de `web.common.ipc_client._read_json_file_safe`.
        """
        try:
            with open(file_path, "r") as f:
                fcntl.flock(f.fileno(), fcntl.LOCK_SH | fcntl.LOCK_NB)
                try:
                    return json.load(f)
                finally:
                    fcntl.flock(f.fileno(), fcntl.LOCK_UN)
        except (BlockingIOError, FileNotFoundError, IOError, json.JSONDecodeError):
            return None

    def send_command(self, action: str) -> bool:
        """Envoie une commande au cimier_service.

        action ∈ {"open", "close", "stop"}. Le service utilise
        `CimierIpcManager` qui dédoublonne par `id` (UUID4 généré ici).

        Returns:
            True si l'écriture a réussi, False sinon (IPC indisponible).
        """
        command = {
            "id": str(uuid.uuid4()),
            "action": action,
            "ts": time(),
        }

        try:
            if not self.command_file.exists():
                self.command_file.touch(mode=0o666)

            with open(self.command_file, "w") as f:
                fcntl.flock(f.fileno(), fcntl.LOCK_EX)
                try:
                    f.write(json.dumps(command))
                    f.flush()
                finally:
                    fcntl.flock(f.fileno(), fcntl.LOCK_UN)
            return True
        except (IOError, OSError):
            return False

    def get_status(self) -> dict:
        """Lit l'état courant publié par cimier_service.

        Returns:
            Le payload brut de cimier_status.json, ou un dict avec
            `state="unknown"` + `error=...` si le fichier est absent ou
            invalide (le service est probablement arrêté).
        """
        result = self._read_json_file_safe(self.status_file)
        if result is None:
            return {
                "state": "unknown",
                "error": "Cimier Service non disponible",
            }
        return result


cimier_client = CimierServiceClient()
