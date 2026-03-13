"""
Configuration centralisée du logging pour DriftApp.

Ce module configure tous les loggers Python (moteur, tracker, encodeur, etc.)
pour écrire dans un fichier unique, en plus du DualLogger de l'UI.

Usage:
    from core.logging_config import setup_logging
    
    # Au démarrage de l'application
    setup_logging()
"""

import logging
from datetime import datetime
from logging.handlers import RotatingFileHandler
from pathlib import Path
from typing import Optional


def setup_logging(
    log_dir: str = "logs",
    log_level: str = "INFO",
    max_bytes: int = 10 * 1024 * 1024,  # 10 MB
    backup_count: int = 5
):
    """
    Configure le logging Python pour toute l'application.
    
    Crée un fichier de log unique qui capture TOUS les logs :
    - MoteurCoupole
    - TrackingSession
    - AdaptiveTrackingManager
    - etc.
    
    Args:
        log_dir: Répertoire des logs (défaut: "logs")
        log_level: Niveau de log ("DEBUG", "INFO", "WARNING", "ERROR")
        max_bytes: Taille max d'un fichier de log avant rotation (défaut: 10 MB)
        backup_count: Nombre de fichiers de backup (défaut: 5)
    """
    # Créer le répertoire de logs
    log_path = Path(log_dir)
    log_path.mkdir(exist_ok=True)
    
    # Nom du fichier de log avec timestamp
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
    
    # Format détaillé pour le fichier
    file_formatter = logging.Formatter(
        '%(asctime)s | %(name)-20s | %(levelname)-8s | %(message)s',
        datefmt='%Y-%m-%d %H:%M:%S'
    )
    file_handler.setFormatter(file_formatter)
    
    # === Handler console (optionnel, pour debugging) ===
    # Décommenter si vous voulez aussi voir les logs dans la console
    # console_handler = logging.StreamHandler(sys.stdout)
    # console_handler.setLevel(logging.WARNING)  # Seulement warnings et erreurs en console
    # console_formatter = logging.Formatter(
    #     '%(levelname)s: %(name)s - %(message)s'
    # )
    # console_handler.setFormatter(console_formatter)
    
    # Ajouter les handlers au logger racine
    root_logger.addHandler(file_handler)
    # root_logger.addHandler(console_handler)  # Décommenter si nécessaire
    
    # === Configurer les loggers spécifiques ===
    # Tous les loggers vont hériter du logger racine, mais on peut
    # ajuster individuellement si besoin
    
    # Logger moteur
    motor_logger = logging.getLogger("MoteurCoupole")
    motor_logger.setLevel(numeric_level)
    
    # Logger tracker
    tracker_logger = logging.getLogger("core.tracking.tracker")
    tracker_logger.setLevel(numeric_level)
    
    # Logger encodeur
    encoder_logger = logging.getLogger("EncoderManager")
    encoder_logger.setLevel(numeric_level)
    
    # Logger adaptive tracking
    adaptive_logger = logging.getLogger("AdaptiveTrackingManager")
    adaptive_logger.setLevel(numeric_level)
    
    # Logger anticipation
    anticipation_logger = logging.getLogger("PredictiveAnticipation")
    anticipation_logger.setLevel(numeric_level)
    
    # === Réduire la verbosité de certains modules externes ===
    # Matplotlib, etc. peuvent être bavards
    logging.getLogger('matplotlib').setLevel(logging.WARNING)
    logging.getLogger('PIL').setLevel(logging.WARNING)
    
    # === Message de confirmation ===
    root_logger.info("="*70)
    root_logger.info("🚀 DRIFTAPP - SYSTÈME DE SUIVI DE COUPOLE")
    root_logger.info("="*70)
    root_logger.info(f"📝 Logging configuré - Fichier : {log_file}")
    root_logger.info(f"📊 Niveau : {log_level}")
    root_logger.info(f"🔄 Rotation : {max_bytes / (1024*1024):.0f} MB, {backup_count} backups")
    root_logger.info("="*70)
    
    return log_file


def get_log_file_path() -> Optional[Path|None]:
    """
    Retourne le chemin du fichier de log actuel.
    
    Returns:
        Path du fichier de log
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
    root_logger.info("="*70)
    root_logger.info("🛑 ARRÊT DE L'APPLICATION")
    root_logger.info("="*70)
    
    # Fermer tous les handlers
    for handler in root_logger.handlers[:]:
        handler.close()
        root_logger.removeHandler(handler)


# === Fonction utilitaire pour debugging ===
def log_system_info():
    """
    Log des informations système utiles pour le debugging.
    """
    import platform
    import sys
    
    logger = logging.getLogger("SystemInfo")
    logger.info("="*70)
    logger.info("📊 INFORMATIONS SYSTÈME")
    logger.info("="*70)
    logger.info(f"Python : {sys.version}")
    logger.info(f"Plateforme : {platform.platform()}")
    logger.info(f"Processeur : {platform.processor()}")
    logger.info(f"Machine : {platform.machine()}")
    
    # Détecter Raspberry Pi
    try:
        with open('/proc/device-tree/model', 'r') as f:
            model = f.read().strip('\x00')
            logger.info(f"Raspberry Pi : {model}")
    except:
        pass
    
    logger.info("="*70)


if __name__ == "__main__":
    """Test du module de logging."""
    print("🧪 Test du module de logging\n")
    
    # Configuration
    log_file = setup_logging(log_level="DEBUG")
    print(f"✅ Logging configuré : {log_file}\n")
    
    # Log d'informations système
    log_system_info()
    
    # Tests avec différents loggers
    print("📝 Génération de logs de test...\n")
    
    logger_motor = logging.getLogger("MoteurCoupole")
    logger_motor.info("Test moteur - INFO")
    logger_motor.debug("Test moteur - DEBUG")
    
    logger_tracker = logging.getLogger("core.tracking.tracker")
    logger_tracker.info("Test tracker - INFO")
    logger_tracker.warning("Test tracker - WARNING")
    
    logger_encoder = logging.getLogger("EncoderManager")
    logger_encoder.info("Test encodeur - INFO")
    logger_encoder.error("Test encodeur - ERROR")
    
    # Fermeture
    close_logging()
    
    print(f"✅ Logs écrits dans : {log_file}")
    print(f"\nContenu du fichier :\n")
    
    # Afficher le contenu
    with open(log_file, 'r', encoding='utf-8') as f:
        print(f.read())
