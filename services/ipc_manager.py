"""
IPC Manager - Gestion des fichiers de communication inter-processus.

Ce module gère la lecture/écriture des fichiers JSON partagés entre
Motor Service et Django.

Fichiers IPC:
- /dev/shm/motor_command.json : Commandes reçues de Django
- /dev/shm/motor_status.json : État publié vers Django
- /dev/shm/ems22_position.json : Position encodeur (daemon externe)

Date: Décembre 2025
Version: 4.5 - Ajout verrous fcntl pour éviter race conditions
"""

import fcntl
import json
import logging
import os
from datetime import datetime
from pathlib import Path
from typing import Dict, Any, Optional

# Chemins des fichiers IPC
COMMAND_FILE = Path("/dev/shm/motor_command.json")
STATUS_FILE = Path("/dev/shm/motor_status.json")
ENCODER_FILE = Path("/dev/shm/ems22_position.json")

logger = logging.getLogger(__name__)


class IpcManager:
    """
    Gestionnaire des communications IPC via fichiers JSON.

    Gère la lecture des commandes et l'écriture de l'état
    de manière atomique et thread-safe.
    """

    def __init__(self):
        """Initialise le gestionnaire IPC."""
        self.last_command_id: Optional[str] = None

    def read_command(self) -> Optional[Dict[str, Any]]:
        """
        Lit une commande depuis le fichier IPC.

        Utilise un verrou partagé (LOCK_SH) pour éviter de lire
        pendant une écriture en cours par Django.

        Returns:
            dict: Commande à exécuter ou None si aucune nouvelle commande
        """
        if not COMMAND_FILE.exists():
            return None

        try:
            with open(COMMAND_FILE, 'r') as f:
                # Verrou partagé : plusieurs lecteurs OK, bloque si écriture en cours
                fcntl.flock(f.fileno(), fcntl.LOCK_SH | fcntl.LOCK_NB)
                try:
                    text = f.read()
                finally:
                    fcntl.flock(f.fileno(), fcntl.LOCK_UN)

            if not text.strip():
                return None

            command = json.loads(text)

            # Vérifier si c'est une nouvelle commande
            cmd_id = command.get('id')
            if cmd_id == self.last_command_id:
                return None

            self.last_command_id = cmd_id
            return command

        except BlockingIOError:
            # Fichier verrouillé en écriture, réessayer plus tard
            return None
        except (json.JSONDecodeError, IOError, OSError) as e:
            logger.warning(f"Erreur lecture commande: {e}")
            return None

    def write_status(self, status: Dict[str, Any]):
        """
        Écrit l'état actuel dans le fichier IPC.

        Utilise un verrou exclusif (LOCK_EX) pour empêcher les lectures
        pendant l'écriture, puis renomme atomiquement.

        Args:
            status: Dictionnaire d'état à écrire
        """
        status['last_update'] = datetime.now().isoformat()

        try:
            tmp_file = STATUS_FILE.with_suffix('.tmp')
            content = json.dumps(status, indent=2)

            with open(tmp_file, 'w') as f:
                # Verrou exclusif pendant l'écriture
                fcntl.flock(f.fileno(), fcntl.LOCK_EX)
                try:
                    f.write(content)
                    f.flush()
                    os.fsync(f.fileno())  # Force l'écriture sur disque
                finally:
                    fcntl.flock(f.fileno(), fcntl.LOCK_UN)

            # Renommage atomique (POSIX)
            tmp_file.rename(STATUS_FILE)

        except (IOError, OSError) as e:
            logger.error(f"Erreur écriture status: {e}")

    def clear_command(self):
        """
        Efface le fichier de commande après traitement.

        Utilise un verrou exclusif pour éviter les conflits.
        """
        try:
            if COMMAND_FILE.exists():
                with open(COMMAND_FILE, 'w') as f:
                    fcntl.flock(f.fileno(), fcntl.LOCK_EX)
                    try:
                        f.write('')
                        f.flush()
                    finally:
                        fcntl.flock(f.fileno(), fcntl.LOCK_UN)
        except (IOError, OSError):
            pass

    def read_encoder_file(self) -> Optional[Dict[str, Any]]:
        """
        Lit le fichier de position encodeur.

        Utilise un verrou partagé pour éviter de lire pendant
        une écriture par le daemon encodeur.

        Returns:
            dict: Données encodeur ou None si non disponible
        """
        if not ENCODER_FILE.exists():
            return None

        try:
            with open(ENCODER_FILE, 'r') as f:
                # Verrou partagé non-bloquant
                fcntl.flock(f.fileno(), fcntl.LOCK_SH | fcntl.LOCK_NB)
                try:
                    text = f.read()
                finally:
                    fcntl.flock(f.fileno(), fcntl.LOCK_UN)

            if not text.strip():
                return None
            return json.loads(text)

        except BlockingIOError:
            # Fichier verrouillé, réessayer plus tard
            return None
        except (json.JSONDecodeError, IOError, OSError) as e:
            logger.warning(f"Erreur lecture encodeur: {e}")
            return None
