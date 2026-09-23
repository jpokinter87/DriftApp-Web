"""
Vues API REST pour le suivi d'objets célestes.
"""
from rest_framework import status
from rest_framework.response import Response
from rest_framework.views import APIView

# Import du catalogue depuis core/
from core.observatoire.catalogue import GestionnaireCatalogue
from web.common.ipc_client import motor_client


def _parse_manual_coords(data):
    """
    Lit et valide des coordonnées J2000 saisies à la main (`ra_deg`, `dec_deg`).

    Returns:
        (coords, error) : coords = (ra_deg, dec_deg) ou None si aucune n'est
        fournie ; error = message si la saisie est incomplète ou hors bornes.
    """
    ra, dec = data.get('ra_deg'), data.get('dec_deg')
    if ra is None and dec is None:
        return None, None
    try:
        ra_deg, dec_deg = float(ra), float(dec)
    except (TypeError, ValueError):
        return None, 'Coordonnées invalides (ra_deg et dec_deg numériques requis)'
    if not 0.0 <= ra_deg < 360.0:
        return None, 'Ascension droite hors bornes (0 ≤ RA < 360°)'
    if not -90.0 <= dec_deg <= 90.0:
        return None, 'Déclinaison hors bornes (-90° ≤ DEC ≤ 90°)'
    return (ra_deg, dec_deg), None


def _add_meridian_info(result):
    """Ajoute le temps avant passage au méridien (`meridian_seconds`, `meridian_time`)."""
    from datetime import datetime
    from core.observatoire import AstronomicalCalculations
    from core.config.config import get_site_config

    ra_deg = result['ra_deg']
    latitude, longitude, tz_offset, _, _ = get_site_config()
    calc = AstronomicalCalculations(latitude, longitude, tz_offset)
    now = datetime.now()
    dec_deg = result.get('dec_deg', 0.0) or 0.0
    ha = calc.calculer_angle_horaire(
        ra_deg, now, deja_jnow=False, declinaison=dec_deg
    )
    result['meridian_seconds'] = round(-ha * 239.3447)

    passage = calc.calculer_heure_passage_meridien(
        ra_deg, now, declinaison=dec_deg
    )
    result['meridian_time'] = passage.strftime('%Hh%M')


class TrackingStartView(APIView):
    """
    POST /api/tracking/start/

    Démarre le suivi d'un objet céleste.
    Avec `ra_deg` + `dec_deg` (J2000), la cible est saisie à la main et le
    catalogue n'est pas consulté (objets faibles absents des bases).
    """

    def post(self, request):
        object_name = request.data.get('object') or request.data.get('name')
        skip_goto = request.data.get('skip_goto', False)

        if not object_name:
            return Response(
                {'error': 'Nom d\'objet requis'},
                status=status.HTTP_400_BAD_REQUEST
            )

        coords, coords_error = _parse_manual_coords(request.data)
        if coords_error:
            return Response({'error': coords_error}, status=status.HTTP_400_BAD_REQUEST)

        extra = {}
        if coords:
            # Coordonnées saisies à la main : pas de recherche catalogue
            result = {'nom': object_name, 'ra_deg': coords[0], 'dec_deg': coords[1]}
            extra = {'ra_deg': coords[0], 'dec_deg': coords[1]}
        else:
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
            skip_goto=skip_goto,
            **extra
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
            # Ajouter le temps avant passage au méridien
            if result.get('ra_deg') is not None:
                _add_meridian_info(result)

            return Response(result)
        else:
            return Response(
                {'error': f'Objet "{query}" introuvable'},
                status=status.HTTP_404_NOT_FOUND
            )


class ManualCoordsView(APIView):
    """
    GET /api/tracking/coords/?ra_deg=<RA>&dec_deg=<DEC>

    Valide des coordonnées J2000 saisies à la main et renvoie le même format
    que la recherche (avec infos méridien), pour les objets absents des bases.
    """

    def get(self, request):
        coords, coords_error = _parse_manual_coords(request.query_params)
        if not coords:
            return Response(
                {'error': coords_error or 'ra_deg et dec_deg requis'},
                status=status.HTTP_400_BAD_REQUEST
            )

        result = {'ra_deg': coords[0], 'dec_deg': coords[1]}
        _add_meridian_info(result)
        return Response(result)
