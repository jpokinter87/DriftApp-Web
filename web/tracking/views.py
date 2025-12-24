"""
Vues API REST pour le suivi d'objets célestes.
"""
import fcntl
import json
import uuid
from pathlib import Path
from typing import Optional

from django.conf import settings
from rest_framework import status
from rest_framework.response import Response
from rest_framework.views import APIView

# Import du catalogue depuis core/
from core.observatoire.catalogue import GestionnaireCatalogue


class MotorServiceClient:
    """Client pour communiquer avec le Motor Service via fichiers IPC."""

    def __init__(self):
        self.command_file = Path(settings.MOTOR_SERVICE_IPC['COMMAND_FILE'])
        self.status_file = Path(settings.MOTOR_SERVICE_IPC['STATUS_FILE'])

    def _read_json_file_safe(self, file_path: Path) -> Optional[dict]:
        """
        Lit un fichier JSON de manière atomique avec verrou fcntl.

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
            command_type: Type de commande (tracking_start, tracking_stop, etc.)
            **params: Paramètres de la commande

        Returns:
            bool: True si la commande a été envoyée
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

    def get_status(self) -> dict:
        """
        Lit le statut du Motor Service.

        Returns:
            dict: État actuel du service
        """
        result = self._read_json_file_safe(self.status_file)
        return result if result else {'status': 'unknown', 'error': 'Motor Service non disponible'}


# Instance globale du client
motor_client = MotorServiceClient()


class TrackingStartView(APIView):
    """
    POST /api/tracking/start/

    Démarre le suivi d'un objet céleste.
    """

    def post(self, request):
        object_name = request.data.get('object') or request.data.get('name')

        if not object_name:
            return Response(
                {'error': 'Nom d\'objet requis'},
                status=status.HTTP_400_BAD_REQUEST
            )

        # Vérifier que l'objet existe dans le catalogue
        catalogue = GestionnaireCatalogue()
        result = catalogue.rechercher(object_name)

        if not result:
            return Response(
                {'error': f'Objet "{object_name}" introuvable'},
                status=status.HTTP_404_NOT_FOUND
            )

        # Envoyer la commande au Motor Service
        success = motor_client.send_command('tracking_start', object=object_name)

        if success:
            return Response({
                'message': f'Suivi de {object_name} démarré',
                'object': result
            })
        else:
            return Response(
                {'error': 'Impossible de communiquer avec Motor Service'},
                status=status.HTTP_503_SERVICE_UNAVAILABLE
            )


class TrackingStopView(APIView):
    """
    POST /api/tracking/stop/

    Arrête le suivi en cours.
    """

    def post(self, request):
        success = motor_client.send_command('tracking_stop')

        if success:
            return Response({'message': 'Suivi arrêté'})
        else:
            return Response(
                {'error': 'Impossible de communiquer avec Motor Service'},
                status=status.HTTP_503_SERVICE_UNAVAILABLE
            )


class TrackingStatusView(APIView):
    """
    GET /api/tracking/status/

    Retourne l'état actuel du suivi.
    """

    def get(self, request):
        status_data = motor_client.get_status()
        return Response(status_data)


class ObjectListView(APIView):
    """
    GET /api/tracking/objects/

    Liste tous les objets disponibles dans le catalogue.
    """

    def get(self, request):
        catalogue = GestionnaireCatalogue()
        objects = catalogue.get_objets_disponibles()

        return Response({
            'count': len(objects),
            'objects': objects
        })


class ObjectSearchView(APIView):
    """
    GET /api/tracking/search/?q=<query>

    Recherche un objet dans le catalogue.
    """

    def get(self, request):
        query = request.query_params.get('q', '')

        if len(query) < 1:
            return Response(
                {'error': 'Requête trop courte'},
                status=status.HTTP_400_BAD_REQUEST
            )

        catalogue = GestionnaireCatalogue()
        result = catalogue.rechercher(query)

        if result:
            return Response(result)
        else:
            return Response(
                {'error': f'Objet "{query}" introuvable'},
                status=status.HTTP_404_NOT_FOUND
            )
