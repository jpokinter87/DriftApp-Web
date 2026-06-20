"""
Configuration centralisée du logging pour DriftApp.

Ce module configure tous les loggers Python pour écrire dans un fichier unique
avec horodatage par session et nettoyage automatique des anciens logs.

Convention: Tous les modules utilisent logging.getLogger(__name__) pour
permettre un filtrage hiérarchique (ex: "core.tracking.tracker").

Usage:
    from core.config.logging_config import setup_logging

    # Au démarrage de l'application
    setup_logging()
"""

import logging
from datetime import datetime
from logging.handlers import RotatingFileHandler
from pathlib import Path
from typing import Optional


def _cleanup_old_logs(log_path: Path, max_files: int):
    """
    Supprime les fichiers de log les plus anciens.

    Garde uniquement les `max_files` fichiers les plus récents.

    Args:
        log_path: Répertoire des logs
        max_files: Nombre maximum de fichiers à conserver
    """
    log_files = sorted(
        log_path.glob("driftapp_*.log*"),  # Inclut .log et .log.1, .log.2 (rotations)
        key=lambda f: f.stat().st_mtime,
        reverse=True  # Plus récent en premier
    )

    # Supprimer les fichiers au-delà de la limite
    files_to_delete = log_files[max_files:]
    for old_file in files_to_delete:
        try:
            old_file.unlink()
            print(f"🗑️  Log ancien supprimé: {old_file.name}")
        except OSError:
            pass  # Ignore si le fichier est verrouillé


def setup_logging(
    log_dir: str = "logs",
    log_level: str = "INFO",
    max_bytes: int = 10 * 1024 * 1024,  # 10 MB
    backup_count: int = 5,
    max_log_files: int = 10
):
    """
    Configure le logging Python pour toute l'application.

    Crée un fichier de log horodaté par session qui capture TOUS les logs
    via la convention __name__. Nettoie automatiquement les anciens fichiers.

    Args:
        log_dir: Répertoire des logs (défaut: "logs")
        log_level: Niveau de log ("DEBUG", "INFO", "WARNING", "ERROR")
        max_bytes: Taille max d'un fichier de log avant rotation (défaut: 10 MB)
        backup_count: Nombre de fichiers de backup par rotation (défaut: 5)
        max_log_files: Nombre max de sessions de log à conserver (défaut: 10)

    Returns:
        Path: Chemin du fichier de log créé
    """
    # Créer le répertoire de logs
    log_path = Path(log_dir)
    log_path.mkdir(exist_ok=True)

    # Nettoyer les anciens fichiers de log
    _cleanup_old_logs(log_path, max_log_files)

    # Nom du fichier de log avec timestamp de session
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    log_file = log_path / f"driftapp_{timestamp}.log"

    # Convertir le niveau de log
    numeric_level = getattr(logging, log_level.upper(), logging.INFO)

    # === Configuration du logger racine ===
    root_logger = logging.getLogger()
    root_logger.setLevel(numeric_level)

    # Supprimer les handlers existants pour éviter les doublons
    root_logger.handlers.clear()

    # === Handler de fichier avec rotation ===
    file_handler = RotatingFileHandler(
        log_file,
        maxBytes=max_bytes,
        backupCount=backup_count,
        encoding='utf-8'
    )
    file_handler.setLevel(numeric_level)

    # Format détaillé avec nom de module complet (via __name__)
    # Exemple: "core.tracking.tracker" au lieu de "TrackingSession"
    file_formatter = logging.Formatter(
        '%(asctime)s | %(name)-35s | %(levelname)-8s | %(message)s',
        datefmt='%Y-%m-%d %H:%M:%S'
    )
    file_handler.setFormatter(file_formatter)

    # Ajouter le handler au logger racine
    root_logger.addHandler(file_handler)

    # === Réduire la verbosité de certains modules externes ===
    logging.getLogger('matplotlib').setLevel(logging.WARNING)
    logging.getLogger('PIL').setLevel(logging.WARNING)
    logging.getLogger('urllib3').setLevel(logging.WARNING)
    logging.getLogger('astropy').setLevel(logging.WARNING)

    # === Message de confirmation ===
    root_logger.info("=" * 70)
    root_logger.info("DRIFTAPP - SYSTEME DE SUIVI DE COUPOLE")
    root_logger.info("=" * 70)
    root_logger.info(f"Logging configure - Fichier : {log_file}")
    root_logger.info(f"Niveau : {log_level}")
    root_logger.info(f"Rotation : {max_bytes / (1024*1024):.0f} MB, {backup_count} backups")
    root_logger.info(f"Retention : {max_log_files} sessions max")
    root_logger.info("=" * 70)

    return log_file


def get_log_file_path() -> Optional[Path]:
    """
    Retourne le chemin du fichier de log actuel.

    Returns:
        Path du fichier de log ou None si non configuré
    """
    root_logger = logging.getLogger()
    for handler in root_logger.handlers:
        if isinstance(handler, RotatingFileHandler):
            return Path(handler.baseFilename)
    return None


def close_logging():
    """
    Ferme proprement tous les handlers de logging.

    À appeler avant la fermeture de l'application.
    """
    root_logger = logging.getLogger()

    # Message final
    root_logger.info("=" * 70)
    root_logger.info("ARRET DE L'APPLICATION")
    root_logger.info("=" * 70)

    # Fermer tous les handlers
    for handler in root_logger.handlers[:]:
        handler.close()
        root_logger.removeHandler(handler)


def log_system_info():
    """
    Log des informations système utiles pour le debugging.
    """
    import platform
    import sys

    logger = logging.getLogger(__name__)
    logger.info("=" * 70)
    logger.info("INFORMATIONS SYSTEME")
    logger.info("=" * 70)
    logger.info(f"Python : {sys.version}")
    logger.info(f"Plateforme : {platform.platform()}")
    logger.info(f"Processeur : {platform.processor()}")
    logger.info(f"Machine : {platform.machine()}")

    # Détecter Raspberry Pi
    try:
        with open('/proc/device-tree/model', 'r') as f:
            model = f.read().strip('\x00')
            logger.info(f"Raspberry Pi : {model}")
    except (FileNotFoundError, PermissionError):
        pass

    logger.info("=" * 70)


if __name__ == "__main__":
    """Test du module de logging."""
    print("Test du module de logging\n")

    # Configuration
    log_file = setup_logging(log_level="DEBUG")
    print(f"Logging configure : {log_file}\n")

    # Log d'informations système
    log_system_info()

    # Tests avec différents loggers (simulant __name__ de différents modules)
    print("Generation de logs de test...\n")

    logger_motor = logging.getLogger("core.hardware.moteur")
    logger_motor.info("Test moteur - INFO")
    logger_motor.debug("Test moteur - DEBUG")

    logger_tracker = logging.getLogger("core.tracking.tracker")
    logger_tracker.info("Test tracker - INFO")
    logger_tracker.warning("Test tracker - WARNING")

    logger_service = logging.getLogger("services.motor_service")
    logger_service.info("Test service - INFO")
    logger_service.error("Test service - ERROR")

    # Fermeture
    close_logging()

    print(f"Logs ecrits dans : {log_file}")
    print("\nContenu du fichier :\n")

    # Afficher le contenu
    with open(log_file, 'r', encoding='utf-8') as f:
        print(f.read())
