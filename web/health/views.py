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
            'meridien': config.get('meridien', {}),
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
# Endpoints de mise à jour (refactor v5.8.0)
# =============================================================================
# Architecture :
#   POST /api/health/update/apply/  → lance scripts/update_driftapp.sh en détaché
#   GET  /api/health/update/status/ → lit logs/update_status.json (survit aux
#                                     restarts de Django pendant la MàJ)
#
# Le script écrit sa progression dans logs/update_status.json avant chaque
# étape. Le frontend poll cet endpoint toutes les 1s jusqu'à done=true.

PROJECT_ROOT = Path(__file__).resolve().parent.parent.parent
UPDATE_SCRIPT = PROJECT_ROOT / "scripts" / "update_driftapp.sh"
UPDATE_STATUS_FILE = PROJECT_ROOT / "logs" / "update_status.json"
UPDATE_LOG_FILE = PROJECT_ROOT / "logs" / "update.log"


@api_view(['GET'])
def check_update(request):
    """
    Vérifie si une mise à jour est disponible.

    Compare le HEAD local avec origin/main après un git fetch.

    Returns:
        JSON avec update_available, local_version, commits_behind,
        commit_messages, files_changed, config_files_affected, etc.
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
    Lance le script de mise à jour en détaché (via sudo NOPASSWD).

    Le script écrit sa progression dans logs/update_status.json que le
    frontend poll via /api/health/update/status/.
    """
    from .update_checker import get_local_commit

    if not UPDATE_SCRIPT.exists():
        return Response({
            'success': False,
            'error': f'Script introuvable : {UPDATE_SCRIPT}'
        }, status=500)

    old_commit = get_local_commit()
    logger.info(f"Lancement script MàJ depuis {old_commit}")

    # Reset du fichier de status (au cas où une ancienne MàJ l'aurait laissé)
    try:
        if UPDATE_STATUS_FILE.exists():
            UPDATE_STATUS_FILE.unlink()
    except OSError:
        pass

    try:
        # Le script s'auto-détache (nohup en background). Retour immédiat
        # avec "UPDATE_STARTED pid=XXX" via stdout.
        result = subprocess.run(
            ['sudo', '-n', str(UPDATE_SCRIPT)],
            cwd=str(PROJECT_ROOT),
            capture_output=True,
            text=True,
            timeout=10
        )

        output = (result.stdout or '').strip()
        if result.returncode == 0 and 'UPDATE_STARTED' in output:
            logger.info(f"Script MàJ lancé : {output}")
            return Response({
                'success': True,
                'message': 'Mise à jour lancée',
                'old_commit': old_commit,
                'detach_info': output,
            })

        # Échec du lancement
        err = (result.stderr or '').strip() or output or 'Erreur inconnue'
        logger.error(f"Lancement script MàJ échoué (rc={result.returncode}) : {err}")
        return Response({
            'success': False,
            'error': f'Lancement du script échoué : {err}',
            'old_commit': old_commit,
        }, status=500)

    except subprocess.TimeoutExpired:
        logger.warning("Timeout au lancement du script MàJ")
        return Response({
            'success': False,
            'error': 'Timeout au lancement du script',
            'old_commit': old_commit,
        }, status=500)
    except (subprocess.SubprocessError, OSError) as e:
        logger.exception("Erreur au lancement du script MàJ")
        return Response({
            'success': False,
            'error': str(e),
            'old_commit': old_commit,
        }, status=500)


@api_view(['GET'])
def update_status(request):
    """
    Renvoie l'état courant de la mise à jour en cours (ou la dernière).

    Lit logs/update_status.json écrit par update_driftapp.sh.
    Si le fichier n'existe pas → aucune MàJ n'a jamais été lancée.
    """
    if not UPDATE_STATUS_FILE.exists():
        return Response({
            'phase': 'idle',
            'step': 0,
            'total': 5,
            'message': 'Aucune mise à jour en cours',
            'success': None,
            'done': True,
            'error': None,
            'timestamp': None,
        })

    try:
        with open(UPDATE_STATUS_FILE, 'r', encoding='utf-8') as f:
            content = f.read().strip()
        if not content:
            return Response({
                'phase': 'starting',
                'step': 0,
                'total': 5,
                'message': 'Initialisation...',
                'success': None,
                'done': False,
                'error': None,
                'timestamp': None,
            })
        return Response(json.loads(content))
    except (OSError, json.JSONDecodeError) as e:
        logger.warning(f"Lecture update_status.json échouée : {e}")
        return Response({
            'phase': 'error',
            'step': 0,
            'total': 5,
            'message': 'Fichier de status illisible',
            'success': False,
            'done': False,
            'error': str(e),
            'timestamp': None,
        }, status=500)