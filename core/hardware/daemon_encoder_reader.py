"""
Lecteur centralisé pour le démon encodeur EMS22A.

Extrait de moteur.py pour respecter le principe de responsabilité unique.
Ce module gère la communication avec le démon encodeur via fichier JSON partagé.

Date: 24 décembre 2025
"""

import json
import logging
import time
from pathlib import Path
from typing import Optional

DAEMON_JSON = Path("/dev/shm/ems22_position.json")


class DaemonEncoderReader:
    """
    Lecteur centralisé pour le démon encodeur EMS22A.

    Gère la lecture du fichier JSON partagé avec retry, timeout et moyennage.
    Utilisé par MoteurCoupole et potentiellement d'autres composants.
    """

    def __init__(self, daemon_path: Path = DAEMON_JSON):
        """
        Initialise le lecteur de démon.

        Args:
            daemon_path: Chemin vers le fichier JSON du démon
        """
        self.daemon_path = daemon_path
        self.logger = logging.getLogger(__name__)

    def is_available(self) -> bool:
        """Vérifie si le fichier démon existe."""
        return self.daemon_path.exists()

    def read_raw(self) -> Optional[dict]:
        """
        Lecture brute du fichier JSON sans retry.

        Returns:
            dict: Données complètes du démon ou None si erreur
        """
        try:
            text = self.daemon_path.read_text()
            return json.loads(text)
        except (FileNotFoundError, json.JSONDecodeError):
            return None

    def read_angle(self, timeout_ms: int = 200) -> float:
        """
        Lit l'angle calibré avec retry et timeout.

        Args:
            timeout_ms: Timeout en millisecondes

        Returns:
            float: Angle en degrés (0-360)

        Raises:
            RuntimeError: Si le démon n'est pas accessible dans le timeout
        """
        t0 = time.time()

        while True:
            elapsed_ms = (time.time() - t0) * 1000.0

            try:
                data = self.read_raw()
                if data is None:
                    if elapsed_ms > timeout_ms:
                        raise RuntimeError(
                            f"Démon encodeur non trouvé ({self.daemon_path})"
                        )
                    time.sleep(0.01)
                    continue

                angle = float(data.get("angle", 0.0)) % 360.0
                status = data.get("status", "OK")

                if status.startswith("OK"):
                    return angle
                elif status.startswith("SPI"):
                    self.logger.warning(f"Démon encodeur: {status}")
                    return angle

            except json.JSONDecodeError as e:
                if elapsed_ms > timeout_ms:
                    raise RuntimeError(f"Erreur lecture démon: {e}")
                time.sleep(0.01)

    def read_status(self) -> Optional[dict]:
        """
        Lit le statut complet du démon.

        Returns:
            dict: Statut complet (angle, calibrated, status, etc.) ou None
        """
        return self.read_raw()

    def read_stable(self, num_samples: int = 3, delay_ms: int = 10,
                    stabilization_ms: int = 50) -> float:
        """
        Lecture avec moyenne pour stabilité mécanique.

        Args:
            num_samples: Nombre d'échantillons à moyenner
            delay_ms: Délai entre échantillons en ms
            stabilization_ms: Délai initial de stabilisation en ms

        Returns:
            float: Position moyenne en degrés

        Raises:
            RuntimeError: Si impossible de lire suffisamment d'échantillons
        """
        # Pause de stabilisation mécanique
        time.sleep(stabilization_ms / 1000.0)

        positions = []
        for _ in range(num_samples):
            try:
                pos = self.read_angle(timeout_ms=100)
                positions.append(pos)
                time.sleep(delay_ms / 1000.0)
            except RuntimeError as e:
                self.logger.warning(f"Erreur lecture démon: {e}")
                if positions:
                    break
                else:
                    raise

        if not positions:
            raise RuntimeError("Impossible de lire la position du démon")

        return sum(positions) / len(positions)


# =============================================================================
# GESTION INSTANCE GLOBALE
# =============================================================================

# Instance globale du lecteur daemon (lazy initialization)
_daemon_reader: Optional[DaemonEncoderReader] = None


def get_daemon_reader() -> DaemonEncoderReader:
    """
    Retourne l'instance globale du lecteur daemon.

    Utilise lazy initialization pour créer l'instance à la première utilisation.
    Permet de partager une seule instance entre tous les composants.

    Returns:
        DaemonEncoderReader: Instance partagée du lecteur
    """
    global _daemon_reader
    if _daemon_reader is None:
        _daemon_reader = DaemonEncoderReader()
    return _daemon_reader


def set_daemon_reader(reader: DaemonEncoderReader):
    """
    Injecte un lecteur daemon personnalisé.

    Utilisé pour les tests (injection de mock) ou pour
    remplacer le lecteur par défaut.

    Args:
        reader: Instance de DaemonEncoderReader à utiliser
    """
    global _daemon_reader
    _daemon_reader = reader


def reset_daemon_reader():
    """
    Réinitialise le lecteur daemon à None.

    Utilisé dans les tests pour garantir l'isolation.
    """
    global _daemon_reader
    _daemon_reader = None
