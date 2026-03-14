"""
Client IPC partagé pour communiquer avec le Motor Service via fichiers.
"""
import json
import uuid
from pathlib import Path

from django.conf import settings


class MotorServiceClient:
    """Client pour communiquer avec le Motor Service via fichiers IPC."""

    def __init__(self):
        self.command_file = Path(settings.MOTOR_SERVICE_IPC['COMMAND_FILE'])
        self.status_file = Path(settings.MOTOR_SERVICE_IPC['STATUS_FILE'])
        self.encoder_file = Path(settings.MOTOR_SERVICE_IPC['ENCODER_FILE'])

    def send_command(self, command_type: str, **params) -> bool:
        """Envoie une commande au Motor Service."""
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
        """Lit le statut du Motor Service."""
        try:
            if self.status_file.exists():
                return json.loads(self.status_file.read_text())
        except (IOError, json.JSONDecodeError):
            pass

        return {'status': 'unknown', 'error': 'Motor Service non disponible'}

    def get_encoder_status(self) -> dict:
        """Lit le statut de l'encodeur depuis le daemon."""
        try:
            if self.encoder_file.exists():
                return json.loads(self.encoder_file.read_text())
        except (IOError, json.JSONDecodeError):
            pass

        return {'status': 'unavailable', 'error': 'Daemon encodeur non disponible'}


# Instance globale du client
motor_client = MotorServiceClient()
