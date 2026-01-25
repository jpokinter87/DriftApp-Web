"""
Exceptions personnalisees pour DriftApp.

Ce module definit une hierarchie d'exceptions specifiques pour les differentes
erreurs pouvant survenir dans l'application DriftApp. Toutes les exceptions
heritent de DriftAppError pour permettre un catch global si necessaire.

Les exceptions incluent des attributs contextuels pour faciliter le debug.

Date: Janvier 2026
"""

from typing import Optional


class DriftAppError(Exception):
    """
    Exception de base pour toutes les erreurs DriftApp.

    Permet de capturer toutes les exceptions specifiques a l'application
    avec un seul bloc except si necessaire.

    Example:
        try:
            # code DriftApp
        except DriftAppError as e:
            logger.error(f"Erreur DriftApp: {e}")
    """
    pass


class MotorError(DriftAppError):
    """
    Exception pour les erreurs de controle moteur.

    Levee lorsqu'une operation sur le moteur echoue: initialisation GPIO,
    rotation, rampe d'acceleration, etc.

    Attributes:
        pin: Pin GPIO implique (optionnel)
        delay: Delai moteur lors de l'erreur (optionnel)
        operation: Operation en cours lors de l'erreur (optionnel)

    Example:
        raise MotorError("Echec initialisation GPIO", pin=18, operation="init")
    """

    def __init__(
        self,
        message: str,
        *,
        pin: Optional[int] = None,
        delay: Optional[float] = None,
        operation: Optional[str] = None
    ):
        super().__init__(message)
        self.pin = pin
        self.delay = delay
        self.operation = operation


class EncoderError(DriftAppError):
    """
    Exception pour les erreurs de communication encodeur.

    Levee lorsque la lecture du daemon encodeur echoue ou que
    les donnees sont invalides/perimees.

    Attributes:
        daemon_path: Chemin vers le fichier daemon (optionnel)
        timeout_ms: Timeout lors de la tentative de lecture (optionnel)

    Example:
        raise EncoderError(
            "Daemon encodeur non accessible",
            daemon_path="/dev/shm/ems22_position.json",
            timeout_ms=200
        )
    """

    def __init__(
        self,
        message: str,
        *,
        daemon_path: Optional[str] = None,
        timeout_ms: Optional[int] = None
    ):
        super().__init__(message)
        self.daemon_path = daemon_path
        self.timeout_ms = timeout_ms


class AbaqueError(DriftAppError):
    """
    Exception pour les erreurs de chargement/interpolation d'abaque.

    Levee lorsque le fichier d'abaque ne peut pas etre charge
    ou que l'interpolation echoue pour les coordonnees donnees.

    Attributes:
        file_path: Chemin vers le fichier d'abaque (optionnel)
        altitude: Altitude lors de l'erreur d'interpolation (optionnel)
        azimut: Azimut lors de l'erreur d'interpolation (optionnel)

    Example:
        raise AbaqueError(
            "Echec interpolation hors limites",
            file_path="data/Loi_coupole.xlsx",
            altitude=95.0,
            azimut=180.0
        )
    """

    def __init__(
        self,
        message: str,
        *,
        file_path: Optional[str] = None,
        altitude: Optional[float] = None,
        azimut: Optional[float] = None
    ):
        super().__init__(message)
        self.file_path = file_path
        self.altitude = altitude
        self.azimut = azimut


class IPCError(DriftAppError):
    """
    Exception pour les erreurs de communication IPC.

    Levee lorsque la lecture/ecriture des fichiers JSON partages
    (/dev/shm/) echoue.

    Attributes:
        file_path: Chemin vers le fichier IPC (optionnel)
        operation: Operation tentee (read/write) (optionnel)

    Example:
        raise IPCError(
            "Echec lecture fichier IPC",
            file_path="/dev/shm/motor_status.json",
            operation="read"
        )
    """

    def __init__(
        self,
        message: str,
        *,
        file_path: Optional[str] = None,
        operation: Optional[str] = None
    ):
        super().__init__(message)
        self.file_path = file_path
        self.operation = operation


class ConfigError(DriftAppError):
    """
    Exception pour les erreurs de chargement de configuration.

    Levee lorsque le fichier de configuration ne peut pas etre lu
    ou qu'une cle requise est manquante.

    Attributes:
        config_path: Chemin vers le fichier de configuration (optionnel)
        key: Cle de configuration manquante/invalide (optionnel)

    Example:
        raise ConfigError(
            "Cle site.latitude manquante",
            config_path="data/config.json",
            key="site.latitude"
        )
    """

    def __init__(
        self,
        message: str,
        *,
        config_path: Optional[str] = None,
        key: Optional[str] = None
    ):
        super().__init__(message)
        self.config_path = config_path
        self.key = key
