"""
Vues API REST pour le contrôle hardware (moteur, encodeur).
"""
import json
import uuid
from pathlib import Path

from django.conf import settings
from rest_framework import status
from rest_framework.response import Response
from rest_framework.views import APIView


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


class GotoView(APIView):
    """
    POST /api/hardware/goto/

    Effectue un GOTO vers une position absolue.

    Body:
        angle: float (0-360)
        speed: float (optionnel, delay en secondes)
    """

    def post(self, request):
        angle = request.data.get('angle')

        if angle is None:
            return Response(
                {'error': 'Angle requis'},
                status=status.HTTP_400_BAD_REQUEST
            )

        try:
            angle = float(angle) % 360
        except (TypeError, ValueError):
            return Response(
                {'error': 'Angle invalide'},
                status=status.HTTP_400_BAD_REQUEST
            )

        speed = request.data.get('speed')
        params = {'angle': angle}
        if speed is not None:
            params['speed'] = float(speed)

        success = motor_client.send_command('goto', **params)

        if success:
            return Response({
                'message': f'GOTO vers {angle:.1f}° lancé',
                'target': angle
            })
        else:
            return Response(
                {'error': 'Impossible de communiquer avec Motor Service'},
                status=status.HTTP_503_SERVICE_UNAVAILABLE
            )


class JogView(APIView):
    """
    POST /api/hardware/jog/

    Effectue une rotation relative.

    Body:
        delta: float (degrés, + = horaire)
        speed: float (optionnel)
    """

    def post(self, request):
        delta = request.data.get('delta')

        if delta is None:
            return Response(
                {'error': 'Delta requis'},
                status=status.HTTP_400_BAD_REQUEST
            )

        try:
            delta = float(delta)
        except (TypeError, ValueError):
            return Response(
                {'error': 'Delta invalide'},
                status=status.HTTP_400_BAD_REQUEST
            )

        speed = request.data.get('speed')
        params = {'delta': delta}
        if speed is not None:
            params['speed'] = float(speed)

        success = motor_client.send_command('jog', **params)

        if success:
            return Response({
                'message': f'Rotation de {delta:+.1f}° lancée',
                'delta': delta
            })
        else:
            return Response(
                {'error': 'Impossible de communiquer avec Motor Service'},
                status=status.HTTP_503_SERVICE_UNAVAILABLE
            )


class StopView(APIView):
    """
    POST /api/hardware/stop/

    Arrête immédiatement tout mouvement.
    """

    def post(self, request):
        success = motor_client.send_command('stop')

        if success:
            return Response({'message': 'Arrêt demandé'})
        else:
            return Response(
                {'error': 'Impossible de communiquer avec Motor Service'},
                status=status.HTTP_503_SERVICE_UNAVAILABLE
            )


class EncoderView(APIView):
    """
    GET /api/hardware/encoder/

    Retourne la position de l'encodeur.
    """

    def get(self, request):
        encoder_data = motor_client.get_encoder_status()

        if 'error' in encoder_data:
            return Response(encoder_data, status=status.HTTP_503_SERVICE_UNAVAILABLE)

        return Response({
            'angle': encoder_data.get('angle', 0),
            'calibrated': encoder_data.get('calibrated', False),
            'status': encoder_data.get('status', 'unknown'),
            'raw': encoder_data.get('raw', 0)
        })


class MotorStatusView(APIView):
    """
    GET /api/hardware/status/

    Retourne l'état complet du Motor Service.
    """

    def get(self, request):
        return Response(motor_client.get_motor_status())
