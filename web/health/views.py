"""
Health check endpoints pour DriftApp Web.

Fournit un endpoint /api/health/ qui vérifie l'état de tous les composants :
- Motor Service (processus de contrôle moteur)
- Encoder Daemon (lecture position encodeur)
- Fichiers IPC (communication inter-processus)

Usage:
    GET /api/health/        -> État global de tous les composants
    GET /api/health/motor/  -> État détaillé du Motor Service
    GET /api/health/encoder/ -> État détaillé de l'Encoder Daemon
"""

import time
from datetime import datetime
from pathlib import Path

from django.conf import settings
from rest_framework.decorators import api_view
from rest_framework.response import Response

from web.common.ipc_client import motor_client


# Seuil en secondes pour considérer un fichier comme "stale"
STALE_THRESHOLD_SEC = 10.0


def _check_file_freshness(file_path: Path) -> dict:
    """
    Vérifie si un fichier IPC existe et est récent.

    Args:
        file_path: Chemin vers le fichier à vérifier

    Returns:
        dict avec 'exists', 'age_sec', 'fresh'
    """
    if not file_path.exists():
        return {
            'exists': False,
            'age_sec': None,
            'fresh': False
        }

    try:
        mtime = file_path.stat().st_mtime
        age_sec = time.time() - mtime
        return {
            'exists': True,
            'age_sec': round(age_sec, 1),
            'fresh': age_sec < STALE_THRESHOLD_SEC
        }
    except OSError:
        return {
            'exists': False,
            'age_sec': None,
            'fresh': False
        }


def _check_motor_service() -> dict:
    """
    Vérifie l'état du Motor Service.

    Returns:
        dict avec 'healthy', 'status', 'details'
    """
    status_file = Path(settings.MOTOR_SERVICE_IPC['STATUS_FILE'])
    file_check = _check_file_freshness(status_file)

    if not file_check['exists']:
        return {
            'healthy': False,
            'status': 'unavailable',
            'details': 'Fichier status non trouvé - Motor Service non démarré',
            'file': file_check
        }

    if not file_check['fresh']:
        return {
            'healthy': False,
            'status': 'stale',
            'details': f"Fichier status trop ancien ({file_check['age_sec']}s)",
            'file': file_check
        }

    # Lire le contenu du status
    motor_status = motor_client.get_motor_status()

    if motor_status.get('status') == 'unknown':
        return {
            'healthy': False,
            'status': 'error',
            'details': motor_status.get('error', 'Erreur inconnue'),
            'file': file_check
        }

    return {
        'healthy': True,
        'status': motor_status.get('status', 'unknown'),
        'details': {
            'mode': motor_status.get('mode'),
            'position': motor_status.get('position'),
            'simulation': motor_status.get('simulation', False),
            'tracking_object': motor_status.get('tracking_object')
        },
        'file': file_check
    }


def _check_encoder_daemon() -> dict:
    """
    Vérifie l'état de l'Encoder Daemon.

    Returns:
        dict avec 'healthy', 'status', 'details'
    """
    encoder_file = Path(settings.MOTOR_SERVICE_IPC['ENCODER_FILE'])
    file_check = _check_file_freshness(encoder_file)

    if not file_check['exists']:
        return {
            'healthy': False,
            'status': 'unavailable',
            'details': 'Fichier encodeur non trouvé - Daemon non démarré',
            'file': file_check
        }

    if not file_check['fresh']:
        return {
            'healthy': False,
            'status': 'stale',
            'details': f"Fichier encodeur trop ancien ({file_check['age_sec']}s)",
            'file': file_check
        }

    # Lire le contenu
    encoder_status = motor_client.get_encoder_status()

    if encoder_status.get('status') == 'unavailable':
        return {
            'healthy': False,
            'status': 'error',
            'details': encoder_status.get('error', 'Erreur inconnue'),
            'file': file_check
        }

    return {
        'healthy': True,
        'status': encoder_status.get('status', 'ok'),
        'details': {
            'angle': encoder_status.get('angle'),
            'calibrated': encoder_status.get('calibrated', False),
            'raw_value': encoder_status.get('raw_value')
        },
        'file': file_check
    }


def _check_ipc_files() -> dict:
    """
    Vérifie l'état des fichiers IPC.

    Returns:
        dict avec l'état de chaque fichier
    """
    return {
        'command_file': _check_file_freshness(
            Path(settings.MOTOR_SERVICE_IPC['COMMAND_FILE'])
        ),
        'status_file': _check_file_freshness(
            Path(settings.MOTOR_SERVICE_IPC['STATUS_FILE'])
        ),
        'encoder_file': _check_file_freshness(
            Path(settings.MOTOR_SERVICE_IPC['ENCODER_FILE'])
        )
    }


@api_view(['GET'])
def health_check(request):
    """
    Endpoint principal de health check.

    Retourne l'état de tous les composants du système.
    HTTP 200 si tout est sain, HTTP 503 si un composant est défaillant.
    """
    motor = _check_motor_service()
    encoder = _check_encoder_daemon()

    # Le système est healthy si Motor Service ET Encoder sont OK
    overall_healthy = motor['healthy'] and encoder['healthy']

    response_data = {
        'healthy': overall_healthy,
        'timestamp': datetime.now().isoformat(),
        'components': {
            'motor_service': motor,
            'encoder_daemon': encoder
        }
    }

    status_code = 200 if overall_healthy else 503
    return Response(response_data, status=status_code)


@api_view(['GET'])
def motor_health(request):
    """
    Health check détaillé du Motor Service uniquement.
    """
    motor = _check_motor_service()
    motor['timestamp'] = datetime.now().isoformat()

    status_code = 200 if motor['healthy'] else 503
    return Response(motor, status=status_code)


@api_view(['GET'])
def encoder_health(request):
    """
    Health check détaillé de l'Encoder Daemon uniquement.
    """
    encoder = _check_encoder_daemon()
    encoder['timestamp'] = datetime.now().isoformat()

    status_code = 200 if encoder['healthy'] else 503
    return Response(encoder, status=status_code)


@api_view(['GET'])
def ipc_status(request):
    """
    Statut des fichiers IPC (pour debug).
    """
    return Response({
        'timestamp': datetime.now().isoformat(),
        'files': _check_ipc_files()
    })