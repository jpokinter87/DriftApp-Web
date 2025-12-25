"""
Session API Views - Endpoints pour les rapports de session.

Endpoints:
    GET  /api/session/current/     - Session de tracking en cours
    GET  /api/session/history/     - Liste des sessions sauvegardées
    GET  /api/session/history/<id>/ - Détail d'une session passée
    POST /api/session/save/        - Sauvegarde manuelle de la session
"""

from rest_framework import status
from rest_framework.decorators import api_view
from rest_framework.response import Response

from web.common.ipc_client import motor_client
from web.session import session_storage


@api_view(['GET'])
def current_session(request):
    """
    Retourne les données de la session de tracking en cours.

    Si aucun tracking n'est actif, retourne 404.
    """
    motor_status = motor_client.get_motor_status()

    # Vérifier si un tracking est actif
    if motor_status.get('status') != 'tracking':
        return Response(
            {'error': 'Aucune session de tracking active'},
            status=status.HTTP_404_NOT_FOUND
        )

    # Extraire les données de session depuis le status
    session_data = motor_status.get('session_data', {})
    tracking_info = motor_status.get('tracking_info', {})

    # Construire la réponse
    response_data = {
        'active': True,
        'object': {
            'name': motor_status.get('tracking_object'),
            'ra_deg': tracking_info.get('ra_deg'),
            'dec_deg': tracking_info.get('dec_deg'),
        },
        'timing': {
            'start_time': session_data.get('start_time'),
            'duration_seconds': session_data.get('duration_seconds', 0),
        },
        'current_state': {
            'altitude': tracking_info.get('altitude'),
            'azimut': tracking_info.get('azimut'),
            'dome_position': motor_status.get('position'),
            'mode': motor_status.get('mode'),
        },
        'summary': session_data.get('summary', {
            'total_corrections': motor_status.get('total_corrections', 0),
            'total_movement_deg': motor_status.get('total_movement', 0),
            'clockwise_movement_deg': session_data.get('clockwise_movement_deg', 0),
            'counterclockwise_movement_deg': session_data.get('counterclockwise_movement_deg', 0),
            'mode_distribution': session_data.get('mode_distribution', {}),
        }),
        'corrections_log': session_data.get('corrections_log', []),
        'position_log': session_data.get('position_log', []),
        'goto_log': session_data.get('goto_log', []),
    }

    return Response(response_data)


@api_view(['GET'])
def session_history(request):
    """
    Liste les sessions de tracking sauvegardées.

    Query params:
        limit: Nombre max de sessions (défaut: 50)
    """
    limit = int(request.query_params.get('limit', 50))
    sessions = session_storage.list_sessions(limit=limit)

    return Response({
        'count': len(sessions),
        'sessions': sessions
    })


@api_view(['GET'])
def session_detail(request, session_id):
    """
    Retourne les données complètes d'une session passée.
    """
    session = session_storage.load_session(session_id)

    if session is None:
        return Response(
            {'error': f'Session non trouvée: {session_id}'},
            status=status.HTTP_404_NOT_FOUND
        )

    return Response(session)


@api_view(['POST'])
def save_session(request):
    """
    Sauvegarde manuelle de la session en cours.

    Permet de sauvegarder sans arrêter le tracking.
    """
    motor_status = motor_client.get_motor_status()

    # Vérifier si un tracking est actif
    if motor_status.get('status') != 'tracking':
        return Response(
            {'error': 'Aucune session de tracking active à sauvegarder'},
            status=status.HTTP_400_BAD_REQUEST
        )

    # Récupérer les données de session
    session_data = motor_status.get('session_data', {})
    tracking_info = motor_status.get('tracking_info', {})

    # Construire les données complètes pour sauvegarde
    save_data = {
        'version': '1.0',
        'object': {
            'name': motor_status.get('tracking_object'),
            'ra_deg': tracking_info.get('ra_deg'),
            'dec_deg': tracking_info.get('dec_deg'),
        },
        'timing': {
            'start_time': session_data.get('start_time'),
            'duration_seconds': session_data.get('duration_seconds', 0),
        },
        'summary': session_data.get('summary', {}),
        'corrections_log': session_data.get('corrections_log', []),
        'position_log': session_data.get('position_log', []),
        'goto_log': session_data.get('goto_log', []),
    }

    session_id = session_storage.save_session(save_data)

    if session_id:
        return Response({
            'success': True,
            'session_id': session_id,
            'message': 'Session sauvegardée'
        })
    else:
        return Response(
            {'error': 'Erreur lors de la sauvegarde'},
            status=status.HTTP_500_INTERNAL_SERVER_ERROR
        )


@api_view(['DELETE'])
def delete_session(request, session_id):
    """
    Supprime une session sauvegardée.
    """
    success = session_storage.delete_session(session_id)

    if success:
        return Response({
            'success': True,
            'message': f'Session {session_id} supprimée'
        })
    else:
        return Response(
            {'error': f'Session non trouvée: {session_id}'},
            status=status.HTTP_404_NOT_FOUND
        )
