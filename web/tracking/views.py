"""
Vues API REST pour le suivi d'objets célestes.
"""
from rest_framework import status
from rest_framework.response import Response
from rest_framework.views import APIView

# Import du catalogue depuis core/
from core.observatoire.catalogue import GestionnaireCatalogue
from web.common.ipc_client import motor_client


class TrackingStartView(APIView):
    """
    POST /api/tracking/start/

    Démarre le suivi d'un objet céleste.
    """

    def post(self, request):
        object_name = request.data.get('object') or request.data.get('name')
        skip_goto = request.data.get('skip_goto', False)

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
        # skip_goto=True : ne pas faire de GOTO initial (position actuelle conservée)
        success = motor_client.send_command(
            'tracking_start',
            object=object_name,
            skip_goto=skip_goto
        )

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
