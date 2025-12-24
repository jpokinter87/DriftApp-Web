"""
Vues API REST pour le contrôle hardware (moteur, encodeur).
"""
from rest_framework import status
from rest_framework.response import Response
from rest_framework.views import APIView

from web.common.ipc_client import motor_client


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


class ContinuousView(APIView):
    """
    POST /api/hardware/continuous/

    Démarre un mouvement continu dans une direction.

    Body:
        direction: str ('cw' ou 'ccw')
    """

    def post(self, request):
        direction = request.data.get('direction', 'cw')

        if direction not in ('cw', 'ccw'):
            return Response(
                {'error': 'Direction invalide (cw ou ccw)'},
                status=status.HTTP_400_BAD_REQUEST
            )

        success = motor_client.send_command('continuous', direction=direction)

        if success:
            return Response({
                'message': f'Mouvement continu {direction.upper()} démarré',
                'direction': direction
            })
        else:
            return Response(
                {'error': 'Impossible de communiquer avec Motor Service'},
                status=status.HTTP_503_SERVICE_UNAVAILABLE
            )


class EncoderView(APIView):
    """
    GET /api/hardware/encoder/

    Retourne la position de l'encodeur.
    En mode simulation, utilise la position du Motor Service.
    """

    def get(self, request):
        encoder_data = motor_client.get_encoder_status()

        # Si le daemon encodeur n'est pas disponible, essayer d'utiliser
        # la position du Motor Service (mode simulation)
        if 'error' in encoder_data:
            motor_status = motor_client.get_motor_status()

            # En mode simulation, utiliser la position du Motor Service
            if motor_status.get('simulation', False):
                return Response({
                    'angle': motor_status.get('position', 0),
                    'calibrated': True,
                    'status': 'simulation',
                    'raw': 0,
                    'simulation': True
                })

            # Sinon, retourner l'erreur mais avec status 200 pour éviter
            # les erreurs console répétitives
            return Response({
                'angle': motor_status.get('position', 0),
                'calibrated': False,
                'status': 'unavailable',
                'raw': 0,
                'error': encoder_data.get('error', 'Daemon encodeur non disponible')
            })

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
