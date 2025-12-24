"""
Logger spécialisé pour le suivi astronomique et la correction de dérive.
"""
import logging
from datetime import datetime


class TrackingLogger:
    """Logger formaté pour le suivi et les corrections."""

    def __init__(self):
        self.logger = logging.getLogger(__name__)
        self.session_start = datetime.now()

    def start_tracking(self, object_name: str, ra: str, dec: str):
        """Log le début d'un suivi."""
        self.logger.info("="*60)
        self.logger.info(f"DÉBUT SUIVI: {object_name}")
        self.logger.info(f"Coordonnées: RA={ra}, DEC={dec}")
        self.logger.info(f"Heure début: {datetime.now().strftime('%H:%M:%S')}")
        self.logger.info("="*60)

    def log_position(self, azimut: float, altitude: float, vitesse: float, direction: str):
        """Log périodique de position (toutes les minutes)."""
        self.logger.debug(f"POS | Az: {azimut:7.2f}° | Alt: {altitude:6.2f}° | "
                         f"V: {vitesse:.4f} t/j | Dir: {direction:10s}")

    def log_drift_check(self, drift: float, threshold: float):
        """Log de vérification de dérive."""
        if abs(drift) > threshold * 0.5:  # Log seulement si significatif
            level = logging.WARNING if abs(drift) > threshold else logging.INFO
            self.logger.log(level, f"DÉRIVE | {drift:+.4f}° (seuil: {threshold}°)")

    def log_correction_start(self, drift: float, direction: str):
        """Log du début de correction."""
        self.logger.warning("="*40)
        self.logger.warning("CORRECTION DÉRIVE ACTIVÉE")
        self.logger.warning(f"Dérive mesurée: {drift:+.3f}°")
        self.logger.warning(f"Direction correction: {direction}")
        self.logger.warning("="*40)

    def log_correction_result(self, success: bool, duration: float = None, steps: int = None):
        """Log du résultat de correction."""
        if success:
            if duration and steps:
                self.logger.info(f"✓ Correction réussie | Durée: {duration:.1f}s | Pas: {steps}")
            else:
                self.logger.info("✓ Correction réussie")
        else:
            if duration:
                self.logger.error(f"✗ Correction échouée après {duration:.1f}s")
            else:
                self.logger.error("✗ Correction échouée")

    def log_motor_activity(self, message: str, level: str = "DEBUG"):
        """Log l'activité moteur (filtré par niveau)."""
        if level == "DEBUG":
            self.logger.debug(f"MOTEUR | {message}")
        else:
            self.logger.info(f"MOTEUR | {message}")

    def log_meridian(self, seconds_to_meridian: float):
        """Log du passage méridien."""
        if abs(seconds_to_meridian) < 300:  # Moins de 5 minutes
            self.logger.warning(f"MÉRIDIEN | Passage dans {seconds_to_meridian:.0f}s")

    def log_zenith(self, altitude: float):
        """Log de l'approche du zénith."""
        if altitude > 85:
            self.logger.warning(f"ZÉNITH | Altitude: {altitude:.1f}° - MODE ZÉNITH ACTIF")

    def stop_tracking(self, reason: str = "Utilisateur"):
        """Log de fin de suivi."""
        duration = (datetime.now() - self.session_start).total_seconds() / 60
        self.logger.info("="*60)
        self.logger.info(f"FIN SUIVI | Raison: {reason}")
        self.logger.info(f"Durée totale: {duration:.1f} minutes")
        self.logger.info("="*60)