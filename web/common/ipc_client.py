"""
Client IPC pour communiquer avec le Motor Service.

Ce module centralise la logique de communication avec le Motor Service
via fichiers JSON partagés en mémoire (/dev/shm/).

Usage:
    from web.common.ipc_client import motor_client

    # Envoyer une commande
    motor_client.send_command('goto', angle=45.0)

    # Lire le statut
    status = motor_client.get_motor_status()
"""

import fcntl
import json
import uuid
from pathlib import Path
from typing import Optional

from django.conf import settings


class MotorServiceClient:
    """
    Client pour communiquer avec le Motor Service via fichiers IPC.

    Utilise des verrous fcntl pour garantir des lectures atomiques
    et éviter les race conditions avec le Motor Service.
    """

    def __init__(self):
        """Initialise les chemins des fichiers IPC depuis les settings Django."""
        self.command_file = Path(settings.MOTOR_SERVICE_IPC['COMMAND_FILE'])
        self.status_file = Path(settings.MOTOR_SERVICE_IPC['STATUS_FILE'])
        self.encoder_file = Path(settings.MOTOR_SERVICE_IPC['ENCODER_FILE'])

    def _read_json_file_safe(self, file_path: Path) -> Optional[dict]:
        """
        Lit un fichier JSON de manière atomique avec verrou fcntl.

        Utilise un verrou partagé non-bloquant pour éviter les race conditions
        avec le Motor Service qui écrit dans ces fichiers.

        Args:
            file_path: Chemin vers le fichier JSON à lire

        Returns:
            dict si succès, None si erreur ou fichier verrouillé
        """
        try:
            with open(file_path, 'r') as f:
                fcntl.flock(f.fileno(), fcntl.LOCK_SH | fcntl.LOCK_NB)
                try:
                    return json.load(f)
                finally:
                    fcntl.flock(f.fileno(), fcntl.LOCK_UN)
        except (BlockingIOError, FileNotFoundError, IOError, json.JSONDecodeError):
            return None

    def send_command(self, command_type: str, **params) -> bool:
        """
        Envoie une commande au Motor Service.

        Args:
            command_type: Type de commande (goto, jog, stop, tracking_start, etc.)
            **params: Paramètres de la commande

        Returns:
            bool: True si la commande a été écrite avec succès
        """
        command = {
            'id': str(uuid.uuid4()),
            'command': command_type,
            **params
        }

        try:
            self.command_file.write_text(json.dumps(command))
            return True
        except IOError:
            return False

    def get_motor_status(self) -> dict:
        """
        Lit le statut du Motor Service.

        Returns:
            dict: État actuel du service (status, position, mode, etc.)
        """
        result = self._read_json_file_safe(self.status_file)
        return result if result else {
            'status': 'unknown',
            'error': 'Motor Service non disponible'
        }

    def get_encoder_status(self) -> dict:
        """
        Lit le statut de l'encodeur depuis le daemon.

        Returns:
            dict: État de l'encodeur (angle, calibrated, status, etc.)
        """
        result = self._read_json_file_safe(self.encoder_file)
        return result if result else {
            'status': 'unavailable',
            'error': 'Daemon encodeur non disponible'
        }

    # Alias pour compatibilité avec tracking/views.py
    def get_status(self) -> dict:
        """Alias pour get_motor_status() - compatibilité."""
        return self.get_motor_status()


# Instance globale du client (singleton)
motor_client = MotorServiceClient()
