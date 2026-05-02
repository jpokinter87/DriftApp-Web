"""Writer pour pousser des commandes vers le Motor Service via IPC (v6.0 Phase 3).

Utilisé par `services.cimier_scheduler` qui doit déclencher `tracking_stop`,
`goto`, `jog` sans dépendre de Django (les services tournent en root via
systemd, hors-process Django). Mirror du pattern `web.common.ipc_client.MotorServiceClient.send_command`
mais en Python pur (testable sans Django settings, chemin overridable).

Format de commande identique : `{"id": <uuid4>, "command": <type>, **params}`,
écriture atomique avec verrou fcntl LOCK_EX dans `/dev/shm/motor_command.json`.
Le `motor_service.process_command()` accepte déjà ces types (lignes 469-510 :
`goto`, `jog`, `stop`, `tracking_start`, `tracking_stop`).
"""

from __future__ import annotations

import fcntl
import json
import logging
import uuid
from pathlib import Path
from typing import Any, Dict

DEFAULT_MOTOR_COMMAND_FILE = Path("/dev/shm/motor_command.json")

logger = logging.getLogger(__name__)


class MotorIpcWriter:
    """Écrit les commandes Motor Service via fichier IPC, sans dépendance Django."""

    def __init__(self, command_file: Path = DEFAULT_MOTOR_COMMAND_FILE):
        self.command_file = Path(command_file)

    def _send(self, command: str, **params: Any) -> bool:
        """Émet une commande IPC. Retourne True si écriture réussie."""
        payload: Dict[str, Any] = {"id": str(uuid.uuid4()), "command": command, **params}
        try:
            if not self.command_file.exists():
                self.command_file.touch(mode=0o666)
            with open(self.command_file, "w") as f:
                fcntl.flock(f.fileno(), fcntl.LOCK_EX)
                try:
                    f.write(json.dumps(payload))
                    f.flush()
                finally:
                    fcntl.flock(f.fileno(), fcntl.LOCK_UN)
            return True
        except (IOError, OSError) as exc:
            logger.error("motor_ipc_writer error: cmd=%s exc=%s", command, exc)
            return False

    def send_goto(self, angle: float) -> bool:
        """Envoie `goto angle=<deg>` au Motor Service (parking 45° en fin de session)."""
        return self._send("goto", angle=float(angle))

    def send_jog(self, delta: float) -> bool:
        """Envoie `jog delta=<deg>` au Motor Service (déparking +1° au lever)."""
        return self._send("jog", delta=float(delta))

    def send_tracking_stop(self) -> bool:
        """Envoie `tracking_stop` au Motor Service (fin de session, hard-stop côté Pi)."""
        return self._send("tracking_stop")

    def send_stop(self) -> bool:
        """Envoie `stop` au Motor Service (arrêt général)."""
        return self._send("stop")
