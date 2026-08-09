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
import os
import time
import uuid
from pathlib import Path
from typing import Any, Dict

DEFAULT_MOTOR_COMMAND_FILE = Path("/dev/shm/motor_command.json")
DEFAULT_MOTOR_STATUS_FILE = Path("/dev/shm/motor_status.json")

# Attente max de la confirmation d'un `tracking_stop` avant d'enchaîner sur la
# commande suivante. `motor_service` consomme le slot IPC à 20 Hz puis arrête la
# session (sérialisation de la nuit sur disque) : quelques centaines de ms en
# pratique, 5 s couvre largement sans jamais bloquer un cycle cimier.
TRACKING_STOP_CONFIRM_TIMEOUT_S = 5.0
_TRACKING_STOP_POLL_INTERVAL_S = 0.05

logger = logging.getLogger(__name__)


class MotorIpcWriter:
    """Écrit les commandes Motor Service via fichier IPC, sans dépendance Django."""

    def __init__(
        self,
        command_file: Path = DEFAULT_MOTOR_COMMAND_FILE,
        status_file: Path = DEFAULT_MOTOR_STATUS_FILE,
    ):
        self.command_file = Path(command_file)
        self.status_file = Path(status_file)
        self.tracking_stop_confirm_timeout_s = TRACKING_STOP_CONFIRM_TIMEOUT_S

    def _send(self, command: str, **params: Any) -> bool:
        """Émet une commande IPC. Retourne True si écriture réussie."""
        payload: Dict[str, Any] = {"id": str(uuid.uuid4()), "command": command, **params}
        try:
            # Écriture atomique tmp+rename (pattern CimierIpcManager) : un échec
            # en cours d'écriture ne tronque jamais la dernière commande valide.
            tmp_file = self.command_file.with_suffix(".tmp")
            content = json.dumps(payload)
            with open(tmp_file, "w") as f:
                fcntl.flock(f.fileno(), fcntl.LOCK_EX)
                try:
                    f.write(content)
                    f.flush()
                finally:
                    fcntl.flock(f.fileno(), fcntl.LOCK_UN)
            # 666 : les services tournent en root (systemd) mais Django
            # (non-root) écrit aussi ce fichier — le rename ne doit pas
            # remplacer un fichier 666 par un 644 (umask root).
            os.chmod(tmp_file, 0o666)
            tmp_file.rename(self.command_file)
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

    def wait_tracking_stopped(self, timeout_s: float = None) -> bool:
        """Attend que `motor_service` ait consommé le `tracking_stop`.

        `motor_command.json` n'a **qu'un seul slot** et n'est lu qu'à 20 Hz :
        enchaîner deux écritures sans attendre fait écraser la première (elle
        n'est jamais consommée), et une écriture arrivée pendant le traitement
        de la précédente est effacée par `IpcManager.clear_command()`. On attend
        donc la confirmation dans `motor_status.json` (`tracking_object` remis à
        `None` par `TrackingHandler.stop`) avant d'enchaîner.

        Bug terrain 08-09/08/2026 : sans cette attente, le `goto` de parking
        écrasait le `tracking_stop`, le suivi restait actif et faisait dériver la
        coupole hors du parking pendant des heures.

        Returns:
            True si l'arrêt du suivi est confirmé, False au timeout (l'appelant
            enchaîne quand même : le parking est best-effort).
        """
        if timeout_s is None:
            timeout_s = self.tracking_stop_confirm_timeout_s
        deadline = time.monotonic() + timeout_s
        while True:
            if self._tracking_is_stopped():
                return True
            if time.monotonic() >= deadline:
                logger.warning(
                    "motor_ipc_writer | tracking_stop non confirmé après %.1fs "
                    "(motor_service arrêté ?) — commande suivante émise quand même",
                    timeout_s,
                )
                return False
            time.sleep(_TRACKING_STOP_POLL_INTERVAL_S)

    def _tracking_is_stopped(self) -> bool:
        """True si `motor_status.json` ne rapporte plus de suivi en cours."""
        try:
            status = json.loads(self.status_file.read_text())
        except (IOError, OSError, json.JSONDecodeError):
            return False
        return status.get("tracking_object") is None
