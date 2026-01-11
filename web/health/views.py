"""
Health check endpoints pour DriftApp Web.

Fournit un endpoint /api/health/ qui vérifie l'état de tous les composants :
- Motor Service (processus de contrôle moteur)
- Encoder Daemon (lecture position encodeur)
- Fichiers IPC (communication inter-processus)

Endpoints de mise à jour :
- GET /api/health/update/check/  -> Vérifie si mise à jour disponible
- POST /api/health/update/apply/ -> Applique la mise à jour

Usage:
    GET /api/health/        -> État global de tous les composants
    GET /api/health/motor/  -> État détaillé du Motor Service
    GET /api/health/encoder/ -> État détaillé de l'Encoder Daemon
"""

import json
import logging
import subprocess
import time
from datetime import datetime
from pathlib import Path

from django.conf import settings
from rest_framework.decorators import api_view
from rest_framework.response import Response

from web.common.ipc_client import motor_client

logger = logging.getLogger(__name__)


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


def _read_ipc_file_content(file_path: Path) -> dict:
    """
    Lit le contenu brut d'un fichier IPC.

    Returns:
        dict avec 'exists', 'content', 'error', 'empty'
    """
    if not file_path.exists():
        return {'exists': False, 'content': None, 'error': 'Fichier non trouvé', 'empty': False}

    try:
        with open(file_path, 'r') as f:
            text = f.read().strip()

        # Fichier vide = état normal pour motor_command.json (après traitement)
        if not text:
            return {'exists': True, 'content': None, 'error': None, 'empty': True}

        content = json.loads(text)
        return {'exists': True, 'content': content, 'error': None, 'empty': False}
    except json.JSONDecodeError as e:
        return {'exists': True, 'content': None, 'error': f'JSON invalide: {e}', 'empty': False}
    except (OSError, IOError) as e:
        return {'exists': True, 'content': None, 'error': str(e), 'empty': False}


def _load_config() -> dict:
    """
    Charge la configuration depuis config.json.
    """
    try:
        config_path = settings.DRIFTAPP_CONFIG
        with open(config_path, 'r') as f:
            config = json.load(f)

        # Extraire les infos essentielles (sans les commentaires)
        return {
            'site': config.get('site', {}),
            'thresholds': config.get('thresholds', {}),
            'suivi': config.get('suivi', {}),
            'moteur': {
                'steps_per_revolution': config.get('moteur', {}).get('steps_per_revolution'),
                'microsteps': config.get('moteur', {}).get('microsteps'),
                'gear_ratio': config.get('moteur', {}).get('gear_ratio'),
                'motor_delay_base': config.get('moteur', {}).get('motor_delay_base'),
            },
            'encodeur': {
                'enabled': config.get('encodeur', {}).get('enabled'),
                'calibration_factor': config.get('encodeur', {}).get('calibration_factor'),
            },
            'adaptive_modes': {
                name: {
                    'interval_sec': mode.get('interval_sec'),
                    'threshold_deg': mode.get('threshold_deg'),
                    'motor_delay': mode.get('motor_delay'),
                }
                for name, mode in config.get('adaptive_tracking', {}).get('modes', {}).items()
                if isinstance(mode, dict) and 'interval_sec' in mode
            },
            'simulation': config.get('simulation', False),
        }
    except (OSError, IOError, json.JSONDecodeError, KeyError) as e:
        return {'error': str(e)}


@api_view(['GET'])
def diagnostic(request):
    """
    Endpoint de diagnostic complet pour la page système.

    Retourne toutes les informations nécessaires à l'affichage :
    - État des composants
    - Contenu brut des fichiers IPC
    - Configuration active
    """
    motor = _check_motor_service()
    encoder = _check_encoder_daemon()

    # Contenu brut des fichiers IPC
    ipc_contents = {
        'motor_status': _read_ipc_file_content(
            Path(settings.MOTOR_SERVICE_IPC['STATUS_FILE'])
        ),
        'encoder_position': _read_ipc_file_content(
            Path(settings.MOTOR_SERVICE_IPC['ENCODER_FILE'])
        ),
        'motor_command': _read_ipc_file_content(
            Path(settings.MOTOR_SERVICE_IPC['COMMAND_FILE'])
        ),
    }

    # Fraîcheur des fichiers
    ipc_freshness = _check_ipc_files()

    # Configuration
    config = _load_config()

    return Response({
        'timestamp': datetime.now().isoformat(),
        'overall_healthy': motor['healthy'] and encoder['healthy'],
        'components': {
            'motor_service': motor,
            'encoder_daemon': encoder
        },
        'ipc': {
            'contents': ipc_contents,
            'freshness': ipc_freshness
        },
        'config': config
    })


# =============================================================================
# Endpoints de mise à jour
# =============================================================================

# Chemin vers le script de mise à jour
PROJECT_ROOT = Path(__file__).resolve().parent.parent.parent
UPDATE_SCRIPT = PROJECT_ROOT / "scripts" / "update_to_web.sh"


@api_view(['GET'])
def check_update(request):
    """
    Vérifie si une mise à jour est disponible.

    Compare le HEAD local avec origin/main après un git fetch.

    Returns:
        JSON avec update_available, local_version, commits_behind, etc.
    """
    from .update_checker import check_for_updates

    try:
        result = check_for_updates()
        result['timestamp'] = datetime.now().isoformat()
        return Response(result)
    except (subprocess.SubprocessError, OSError, RuntimeError) as e:
        logger.exception("Erreur lors de la vérification des mises à jour")
        return Response({
            'error': str(e),
            'update_available': False,
            'timestamp': datetime.now().isoformat()
        }, status=500)


@api_view(['POST'])
def apply_update(request):
    """
    Applique la mise à jour en exécutant le script update_to_web.sh.

    Ce endpoint déclenche le script qui:
    1. Arrête les services (motor_service, ems22d, django)
    2. Fait un git pull (avec préservation de config.json)
    3. Installe les nouveaux fichiers de service
    4. Redémarre les services

    Note: La connexion sera perdue pendant le redémarrage.
    Le frontend doit gérer la reconnexion.

    Returns:
        JSON avec success, message, old_commit
    """
    from .update_checker import get_local_commit

    # Vérifier que le script existe
    if not UPDATE_SCRIPT.exists():
        return Response({
            'success': False,
            'error': f'Script de mise à jour non trouvé: {UPDATE_SCRIPT}'
        }, status=500)

    # Sauvegarder le commit actuel
    old_commit = get_local_commit()

    try:
        # Exécuter le script avec sudo
        # Note: Nécessite une configuration sudoers appropriée
        logger.info(f"Démarrage de la mise à jour depuis {old_commit}")

        result = subprocess.run(
            ['sudo', str(UPDATE_SCRIPT)],
            cwd=PROJECT_ROOT,
            capture_output=True,
            text=True,
            timeout=300  # 5 minutes max
        )

        if result.returncode == 0:
            new_commit = get_local_commit()
            logger.info(f"Mise à jour réussie: {old_commit} -> {new_commit}")
            return Response({
                'success': True,
                'message': 'Mise à jour terminée',
                'old_commit': old_commit,
                'new_commit': new_commit,
                'output': result.stdout[-2000:] if result.stdout else ''
            })
        else:
            logger.error(f"Échec de la mise à jour: {result.stderr}")
            return Response({
                'success': False,
                'error': f'Le script a échoué (code {result.returncode})',
                'old_commit': old_commit,
                'stderr': result.stderr[-1000:] if result.stderr else ''
            }, status=500)

    except subprocess.TimeoutExpired:
        # Timeout attendu si les services redémarrent
        logger.info("Timeout du script - services en cours de redémarrage")
        return Response({
            'success': True,
            'message': 'Mise à jour en cours (services redémarrent)',
            'old_commit': old_commit
        })
    except PermissionError as e:
        logger.error(f"Permission refusée: {e}")
        return Response({
            'success': False,
            'error': 'Permission refusée. Vérifiez la configuration sudoers.',
            'old_commit': old_commit
        }, status=403)
    except (subprocess.SubprocessError, OSError) as e:
        logger.exception("Erreur inattendue lors de la mise à jour")
        return Response({
            'success': False,
            'error': str(e),
            'old_commit': old_commit
        }, status=500)