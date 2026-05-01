"""
Cimier IPC Manager — fichiers de communication inter-processus pour le cimier.

Rôle dédié :
  - /dev/shm/cimier_command.json : commandes Django (ou autre client) → cimier_service
  - /dev/shm/cimier_status.json  : état publié par cimier_service → consommateurs

Schéma command : {"id": str, "action": "open"|"close"|"stop", "ts": float}
Schéma status  : voir docstring de write_status() / states publiés par cimier_service.

Conventions identiques à services/ipc_manager.py (verrous fcntl, écriture
atomique via tmp + rename POSIX). Module séparé pour ne pas mélanger avec
le manager moteur principal — séparation des concerns explicite.

v6.0 Phase 1 sub-plan 02.
"""

from __future__ import annotations

import fcntl
import json
import logging
import os
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, Optional

DEFAULT_COMMAND_FILE = Path("/dev/shm/cimier_command.json")
DEFAULT_STATUS_FILE = Path("/dev/shm/cimier_status.json")

logger = logging.getLogger(__name__)


class CimierIpcManager:
    """Lecture commandes + écriture status pour le cimier_service.

    Les chemins par défaut pointent sur /dev/shm/cimier_*.json. Les tests
    peuvent injecter des chemins alternatifs via le constructeur (pour
    isolation tmp_path).
    """

    def __init__(
        self,
        command_file: Path = DEFAULT_COMMAND_FILE,
        status_file: Path = DEFAULT_STATUS_FILE,
    ):
        self.command_file = Path(command_file)
        self.status_file = Path(status_file)
        self.last_command_id: Optional[str] = None
        self._ensure_command_file_exists()

    def _ensure_command_file_exists(self) -> None:
        """Crée le fichier de commande s'il n'existe pas et assure mode 666.

        Un client externe (Django, tests) doit pouvoir écrire dedans même
        si le service tourne en root.
        """
        try:
            if not self.command_file.exists():
                self.command_file.touch()
                logger.info("Fichier commande cimier IPC créé: %s", self.command_file)

            current_mode = self.command_file.stat().st_mode & 0o777
            if current_mode != 0o666:
                try:
                    os.chmod(self.command_file, 0o666)
                except PermissionError:
                    # Tests en tmp_path : on ne peut pas forcer 666 si pas root.
                    pass
        except (IOError, OSError) as exc:
            logger.error("Erreur init fichier commande cimier: %s", exc)

    def read_command(self) -> Optional[Dict[str, Any]]:
        """Lit une commande nouvelle (id != last_command_id).

        Retourne None si :
          - fichier absent ou vide ;
          - JSON invalide ;
          - id manquant ou identique à la dernière commande déjà vue.
        """
        if not self.command_file.exists():
            return None

        try:
            with open(self.command_file, "r") as f:
                fcntl.flock(f.fileno(), fcntl.LOCK_SH | fcntl.LOCK_NB)
                try:
                    text = f.read()
                finally:
                    fcntl.flock(f.fileno(), fcntl.LOCK_UN)

            if not text.strip():
                return None

            command = json.loads(text)
            cmd_id = command.get("id")
            if cmd_id is None:
                logger.warning("Commande cimier sans id, ignorée: %s", command)
                return None
            if cmd_id == self.last_command_id:
                return None

            self.last_command_id = cmd_id
            return command

        except BlockingIOError:
            return None
        except (json.JSONDecodeError, IOError, OSError) as exc:
            logger.warning("Erreur lecture commande cimier: %s", exc)
            return None

    def write_status(self, status: Dict[str, Any]) -> None:
        """Écrit l'état cimier dans le fichier IPC (atomique, verrou exclusif).

        Le champ `last_update` (ISO local) est ajouté automatiquement.
        """
        payload = dict(status)
        payload["last_update"] = datetime.now().isoformat()

        try:
            tmp_file = self.status_file.with_suffix(".tmp")
            content = json.dumps(payload, indent=2)
            with open(tmp_file, "w") as f:
                fcntl.flock(f.fileno(), fcntl.LOCK_EX)
                try:
                    f.write(content)
                    f.flush()
                finally:
                    fcntl.flock(f.fileno(), fcntl.LOCK_UN)
            tmp_file.rename(self.status_file)

        except (IOError, OSError) as exc:
            logger.error("Erreur écriture status cimier: %s", exc)

    def write_command(self, command: Dict[str, Any]) -> None:
        """Écrit une commande dans le fichier IPC (utilitaire pour clients/tests).

        Pas de verrou exclusif côté lecteur pour ne pas bloquer la lecture —
        on accepte que le rename POSIX soit atomique.
        """
        try:
            tmp_file = self.command_file.with_suffix(".tmp")
            content = json.dumps(command)
            with open(tmp_file, "w") as f:
                f.write(content)
                f.flush()
            tmp_file.rename(self.command_file)
        except (IOError, OSError) as exc:
            logger.error("Erreur écriture commande cimier: %s", exc)
