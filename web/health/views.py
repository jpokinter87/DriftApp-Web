"""
Health check et mise à jour pour DriftApp Web.

Endpoints:
- GET  /api/health/                -> État global des composants
- GET  /api/health/update/check/   -> Vérifie si mise à jour disponible
- POST /api/health/update/apply/   -> Applique la mise à jour (git pull + restart)
"""

import logging
import subprocess
import time
from datetime import datetime
from pathlib import Path

from django.conf import settings
from rest_framework.decorators import api_view
from rest_framework.response import Response

from core.config.config_loader import PROJECT_ROOT
from web.common.ipc_client import motor_client

logger = logging.getLogger(__name__)

STALE_THRESHOLD_SEC = 10.0


def _check_file_freshness(file_path: Path) -> dict:
    """Vérifie si un fichier IPC existe et est récent."""
    if not file_path.exists():
        return {'exists': False, 'age_sec': None, 'fresh': False}
    try:
        age_sec = time.time() - file_path.stat().st_mtime
        return {'exists': True, 'age_sec': round(age_sec, 1), 'fresh': age_sec < STALE_THRESHOLD_SEC}
    except OSError:
        return {'exists': False, 'age_sec': None, 'fresh': False}


def _check_motor_service() -> dict:
    """Vérifie l'état du Motor Service."""
    status_file = Path(settings.MOTOR_SERVICE_IPC['STATUS_FILE'])
    file_check = _check_file_freshness(status_file)

    if not file_check['exists']:
        return {'healthy': False, 'status': 'unavailable',
                'details': 'Motor Service non démarré', 'file': file_check}

    if not file_check['fresh']:
        return {'healthy': False, 'status': 'stale',
                'details': f"Status trop ancien ({file_check['age_sec']}s)", 'file': file_check}

    motor_status = motor_client.get_motor_status()
    if motor_status.get('status') == 'unknown':
        return {'healthy': False, 'status': 'error',
                'details': motor_status.get('error', 'Erreur'), 'file': file_check}

    return {
        'healthy': True, 'status': motor_status.get('status', 'unknown'),
        'details': {
            'mode': motor_status.get('mode'),
            'position': motor_status.get('position'),
            'simulation': motor_status.get('simulation', False),
        },
        'file': file_check
    }


def _check_encoder_daemon() -> dict:
    """Vérifie l'état de l'Encoder Daemon."""
    encoder_file = Path(settings.MOTOR_SERVICE_IPC['ENCODER_FILE'])
    file_check = _check_file_freshness(encoder_file)

    if not file_check['exists']:
        return {'healthy': False, 'status': 'unavailable',
                'details': 'Daemon encodeur non démarré', 'file': file_check}

    if not file_check['fresh']:
        return {'healthy': False, 'status': 'stale',
                'details': f"Encodeur trop ancien ({file_check['age_sec']}s)", 'file': file_check}

    encoder_status = motor_client.get_encoder_status()
    return {
        'healthy': encoder_status.get('status') != 'unavailable',
        'status': encoder_status.get('status', 'ok'),
        'details': {
            'angle': encoder_status.get('angle'),
            'calibrated': encoder_status.get('calibrated', False),
        },
        'file': file_check
    }


@api_view(['GET'])
def health_check(request):
    """État global de tous les composants."""
    motor = _check_motor_service()
    encoder = _check_encoder_daemon()
    overall_healthy = motor['healthy'] and encoder['healthy']

    return Response({
        'healthy': overall_healthy,
        'timestamp': datetime.now().isoformat(),
        'components': {
            'motor_service': motor,
            'encoder_daemon': encoder
        }
    }, status=200 if overall_healthy else 503)


@api_view(['GET'])
def check_update(request):
    """Vérifie si une mise à jour est disponible."""
    from .update_checker import check_for_updates

    try:
        result = check_for_updates()
        result['timestamp'] = datetime.now().isoformat()
        return Response(result)
    except Exception as e:
        logger.exception("Erreur vérification mises à jour")
        return Response({
            'error': str(e),
            'update_available': False,
            'timestamp': datetime.now().isoformat()
        }, status=500)


@api_view(['POST'])
def apply_update(request):
    """
    Applique la mise à jour : git pull + restart services.

    Le frontend doit gérer la reconnexion après le restart.
    """
    from .update_checker import get_local_commit

    old_commit = get_local_commit()

    try:
        # 1. Git pull
        logger.info(f"Mise à jour depuis {old_commit}")
        pull_result = subprocess.run(
            ['git', 'pull', 'origin', 'main'],
            cwd=PROJECT_ROOT,
            capture_output=True, text=True, timeout=60
        )

        if pull_result.returncode != 0:
            return Response({
                'success': False,
                'error': f'git pull a échoué: {pull_result.stderr}',
                'old_commit': old_commit
            }, status=500)

        new_commit = get_local_commit()

        # 2. Restart services (en arrière-plan pour ne pas bloquer la réponse)
        subprocess.Popen(
            ['sudo', str(PROJECT_ROOT / 'start_web.sh'), 'restart'],
            cwd=PROJECT_ROOT,
            stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL
        )

        logger.info(f"Mise à jour réussie: {old_commit} -> {new_commit}")
        return Response({
            'success': True,
            'message': 'Mise à jour appliquée, services en cours de redémarrage',
            'old_commit': old_commit,
            'new_commit': new_commit,
            'output': pull_result.stdout[-1000:] if pull_result.stdout else ''
        })

    except subprocess.TimeoutExpired:
        logger.info("Timeout git pull — réseau lent ?")
        return Response({
            'success': False,
            'error': 'Timeout git pull (60s)',
            'old_commit': old_commit
        }, status=500)
    except PermissionError as e:
        return Response({
            'success': False,
            'error': f'Permission refusée: {e}',
            'old_commit': old_commit
        }, status=403)
    except Exception as e:
        logger.exception("Erreur mise à jour")
        return Response({
            'success': False,
            'error': str(e),
            'old_commit': old_commit
        }, status=500)
