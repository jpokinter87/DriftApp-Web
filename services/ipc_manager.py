"""
IPC Manager - Gestion des fichiers de communication inter-processus.

Ce module gère la lecture/écriture des fichiers JSON partagés entre
Motor Service et Django.

Fichiers IPC:
- /dev/shm/motor_command.json : Commandes reçues de Django
- /dev/shm/motor_status.json : État publié vers Django
- /dev/shm/ems22_position.json : Position encodeur (daemon externe)

Date: Décembre 2025
Version: 4.4
"""

import json
import logging
from datetime import datetime
from pathlib import Path
from typing import Dict, Any, Optional

# Chemins des fichiers IPC
COMMAND_FILE = Path("/dev/shm/motor_command.json")
STATUS_FILE = Path("/dev/shm/motor_status.json")
ENCODER_FILE = Path("/dev/shm/ems22_position.json")

logger = logging.getLogger("IpcManager")


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

        Returns:
            dict: Commande à exécuter ou None si aucune nouvelle commande
        """
        if not COMMAND_FILE.exists():
            return None

        try:
            text = COMMAND_FILE.read_text()
            if not text.strip():
                return None

            command = json.loads(text)

            # Vérifier si c'est une nouvelle commande
            cmd_id = command.get('id')
            if cmd_id == self.last_command_id:
                return None

            self.last_command_id = cmd_id
            return command

        except (json.JSONDecodeError, IOError) as e:
            logger.warning(f"Erreur lecture commande: {e}")
            return None

    def write_status(self, status: Dict[str, Any]):
        """
        Écrit l'état actuel dans le fichier IPC.

        Args:
            status: Dictionnaire d'état à écrire
        """
        status['last_update'] = datetime.now().isoformat()

        try:
            # Écriture atomique avec fichier temporaire
            tmp_file = STATUS_FILE.with_suffix('.tmp')
            tmp_file.write_text(json.dumps(status, indent=2))
            tmp_file.rename(STATUS_FILE)
        except IOError as e:
            logger.error(f"Erreur écriture status: {e}")

    def clear_command(self):
        """Efface le fichier de commande après traitement."""
        try:
            if COMMAND_FILE.exists():
                COMMAND_FILE.write_text('')
        except IOError:
            pass

    def read_encoder_file(self) -> Optional[Dict[str, Any]]:
        """
        Lit le fichier de position encodeur.

        Returns:
            dict: Données encodeur ou None si non disponible
        """
        if not ENCODER_FILE.exists():
            return None

        try:
            text = ENCODER_FILE.read_text()
            if not text.strip():
                return None
            return json.loads(text)
        except (json.JSONDecodeError, IOError) as e:
            logger.warning(f"Erreur lecture encodeur: {e}")
            return None
