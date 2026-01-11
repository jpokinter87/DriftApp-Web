"""
Contrôleur du moteur pas-à-pas de la coupole.
Support Raspberry Pi 5 via lgpio.

VERSION 4.0 :
- Lecture encodeur via démon externe pour éviter les interférences SPI

VERSION 4.2 :
- Extraction de DaemonEncoderReader pour centraliser la lecture du démon

VERSION 4.3 :
- Extraction de FeedbackController pour isoler la logique de feedback
- MoteurCoupole se concentre sur le contrôle moteur pur

VERSION 4.5 :
- Rampe d'accélération/décélération S-curve (acceleration_ramp.py)
- Protection moteur au démarrage et à l'arrêt
- Paramètre use_ramp dans rotation() et rotation_absolue()

VERSION 4.6 :
- Extraction de DaemonEncoderReader vers daemon_encoder_reader.py
- moteur.py réduit de ~170 lignes

VERSION 4.7 :
- Simplification: support lgpio uniquement (Raspberry Pi 5)
- Suppression du support RPi.GPIO obsolète
- Code plus simple et maintenable

Date: 11 janvier 2026
"""

import logging
import time
from typing import Dict, Any, Optional

# Ré-export pour compatibilité (imports existants depuis moteur.py)
from core.hardware.daemon_encoder_reader import (
    DAEMON_JSON,
    DaemonEncoderReader,
    get_daemon_reader,
    set_daemon_reader,
    reset_daemon_reader,
)

# Import lgpio (Raspberry Pi 5)
try:
    import lgpio
    LGPIO_AVAILABLE = True
except ImportError:
    LGPIO_AVAILABLE = False
    lgpio = None  # Pour éviter NameError dans les tests


class MoteurCoupole:
    """
    Contrôleur pour moteur pas-à-pas de la coupole.
    Raspberry Pi 5 uniquement (lgpio).

    VERSION 4.7 : Simplifié pour lgpio uniquement.
    """

    def __init__(self, config_moteur):
        """
        Initialise le contrôleur moteur depuis la configuration.

        Args:
            config_moteur: Configuration moteur (dict ou dataclass)
        """
        self.logger = logging.getLogger(__name__)
        self.gpio_handle = None
        self.direction_actuelle = 1
        self.stop_requested = False

        self._verifier_gpio_disponible()
        self._charger_config(config_moteur)
        self._calculer_steps_par_tour()
        self._init_gpio()

        self.logger.info(
            f"Moteur initialisé (lgpio) - "
            f"Steps/tour coupole: {self.steps_per_dome_revolution}"
        )

    # =========================================================================
    # INITIALISATION (méthodes privées)
    # =========================================================================

    def _verifier_gpio_disponible(self):
        """Vérifie que lgpio est disponible."""
        if not LGPIO_AVAILABLE:
            raise RuntimeError(
                "lgpio non disponible. "
                "Installez lgpio: sudo apt install python3-lgpio"
            )

    def _charger_config(self, config_moteur):
        """Extrait les paramètres depuis dict ou dataclass via parser centralisé."""
        from core.hardware.motor_config_parser import parse_motor_config, validate_motor_params

        params = parse_motor_config(config_moteur)
        validate_motor_params(params)

        self.DIR = params.dir_pin
        self.STEP = params.step_pin
        self.STEPS_PER_REV = params.steps_per_revolution
        self.MICROSTEPS = params.microsteps
        self.gear_ratio = params.gear_ratio
        self.steps_correction_factor = params.steps_correction_factor

    def _calculer_steps_par_tour(self):
        """Calcule le nombre de pas par tour de coupole."""
        self.steps_per_dome_revolution = int(
            self.STEPS_PER_REV *
            self.MICROSTEPS *
            self.gear_ratio *
            self.steps_correction_factor
        )

    # =========================================================================
    # CONTRÔLE GPIO (lgpio uniquement)
    # =========================================================================

    def _gpio_write(self, pin: int, value: int):
        """
        Écriture GPIO via lgpio.

        Args:
            pin: Numéro de broche GPIO
            value: 0 ou 1
        """
        lgpio.gpio_write(self.gpio_handle, pin, value)

    def _gpio_high(self, pin: int):
        """Met la broche GPIO à l'état haut."""
        lgpio.gpio_write(self.gpio_handle, pin, 1)

    def _gpio_low(self, pin: int):
        """Met la broche GPIO à l'état bas."""
        lgpio.gpio_write(self.gpio_handle, pin, 0)

    def _valider_delai(self, delai: float) -> float:
        """
        Valide et corrige le délai moteur.

        Args:
            delai: Délai demandé en secondes

        Returns:
            Délai validé (au moins 50µs)
        """
        delai_min = 0.00005  # 50µs - limite de sécurité électrique
        if delai < delai_min:
            self.logger.warning(
                f"Délai {delai:.6f}s < minimum {delai_min:.6f}s"
            )
            return delai_min
        return delai

    def _init_gpio(self):
        """Initialise les GPIO avec lgpio."""
        try:
            # Ouvrir le chip GPIO (chip 4 sur Pi 5, chip 0 sur Pi 4 et antérieurs)
            try:
                self.gpio_handle = lgpio.gpiochip_open(4)  # Pi 5
            except lgpio.error:
                self.gpio_handle = lgpio.gpiochip_open(0)  # Fallback Pi 4

            # Configurer les pins en sortie
            lgpio.gpio_claim_output(self.gpio_handle, self.DIR)
            lgpio.gpio_claim_output(self.gpio_handle, self.STEP)

            # État initial (bas)
            lgpio.gpio_write(self.gpio_handle, self.DIR, 0)
            lgpio.gpio_write(self.gpio_handle, self.STEP, 0)

            self.logger.info("GPIO initialisé avec lgpio")

        except lgpio.error as e:
            self.logger.error(f"Erreur init lgpio: {e}")
            raise

    # =========================================================================
    # MÉTHODES DÉMON ENCODEUR (délégation à DaemonEncoderReader)
    # =========================================================================

    @staticmethod
    def get_daemon_angle(timeout_ms: int = 200) -> float:
        """
        Lit l'angle calibré publié par le démon EMS22A.

        Args:
            timeout_ms: Timeout en millisecondes

        Returns:
            float: Angle en degrés (0-360)

        Raises:
            RuntimeError: Si le démon n'est pas accessible
        """
        return get_daemon_reader().read_angle(timeout_ms)

    @staticmethod
    def get_daemon_status() -> Optional[dict]:
        """
        Lit le statut complet publié par le démon EMS22A.

        Returns:
            dict: Statut complet du démon (angle, calibrated, status, etc.)
            None si le démon n'est pas accessible
        """
        return get_daemon_reader().read_status()

    # =========================================================================
    # CONTRÔLE D'ARRÊT
    # =========================================================================

    def request_stop(self):
        """
        Demande l'arrêt de la boucle de feedback en cours.
        Cette méthode est non bloquante et permet d'arrêter
        la correction en cours sans attendre la fin de toutes les itérations.
        """
        self.stop_requested = True
        self.logger.info("Arrêt de la boucle feedback demandé")

    def clear_stop_request(self):
        """
        Efface le flag d'arrêt pour permettre de nouvelles corrections.
        """
        self.stop_requested = False

    # =========================================================================
    # CONTRÔLE MOTEUR DE BASE
    # =========================================================================

    def definir_direction(self, direction: int):
        """
        Définit la direction de rotation.

        Args:
            direction: 1 pour horaire, -1 pour anti-horaire
        """
        self.direction_actuelle = 1 if direction >= 0 else -1
        self._gpio_write(self.DIR, 1 if self.direction_actuelle == 1 else 0)

    def faire_un_pas(self, delai: float = 0.0015):
        """
        Fait faire un pas au moteur via lgpio.

        Args:
            delai: Délai en secondes entre les impulsions (min 10µs)
        """
        if self.gpio_handle is None:
            raise RuntimeError("GPIO non initialisé")

        # Validation du délai minimum
        delai_min = 0.00001  # 10µs
        if delai < delai_min:
            self.logger.warning(f"Délai {delai:.6f}s < minimum {delai_min:.6f}s")
            delai = delai_min

        # Impulsion STEP (lgpio)
        lgpio.gpio_write(self.gpio_handle, self.STEP, 1)
        time.sleep(delai / 2)
        lgpio.gpio_write(self.gpio_handle, self.STEP, 0)
        time.sleep(delai / 2)

    def rotation(self, angle_deg: float, vitesse: float = 0.0015, use_ramp: bool = True):
        """
        Fait tourner la coupole d'un angle donné.

        VERSION 4.5 : Rampe d'accélération/décélération pour protéger le moteur.
        - Démarre lentement pour éviter le stress mécanique
        - Accélère progressivement vers la vitesse nominale (S-curve)
        - Décélère en fin de mouvement pour un arrêt en douceur

        Args:
            angle_deg: Angle en degrés (positif = horaire)
            vitesse: Délai nominal entre les pas en secondes
            use_ramp: Si True, utilise la rampe d'accélération (défaut: True)
        """
        self.clear_stop_request()
        self.definir_direction(1 if angle_deg >= 0 else -1)

        deg_per_step = 360.0 / self.steps_per_dome_revolution
        steps = int(abs(angle_deg) / deg_per_step)

        if steps == 0:
            return

        # Créer la rampe d'accélération/décélération
        if use_ramp:
            from core.hardware.acceleration_ramp import AccelerationRamp
            ramp = AccelerationRamp(steps, vitesse)
            ramp_info = f", rampe={'activée' if ramp.ramp_enabled else 'désactivée'}"
        else:
            ramp = None
            ramp_info = ", rampe=off"

        self.logger.debug(
            f"Rotation de {angle_deg:.2f}° ({steps} pas, délai={vitesse}s{ramp_info})"
        )

        # Boucle avec vérification stop_requested périodique (tous les 500 pas)
        # et rampe d'accélération/décélération
        for i in range(steps):
            if i % 500 == 0 and self.stop_requested:
                self.logger.info(f"Rotation interrompue à {i}/{steps} pas")
                break

            # Calcul du délai avec ou sans rampe
            if ramp is not None:
                delay = ramp.get_delay(i)
            else:
                delay = vitesse

            self.faire_un_pas(delay)

    def rotation_absolue(self, position_cible_deg: float, position_actuelle_deg: float,
                        vitesse: float = 0.0015, use_ramp: bool = True):
        """
        Rotation vers une position absolue.

        Args:
            position_cible_deg: Position cible en degrés (0-360)
            position_actuelle_deg: Position actuelle en degrés (0-360)
            vitesse: Délai entre les pas
            use_ramp: Si True, utilise la rampe d'accélération (défaut: True)
        """
        position_cible = position_cible_deg % 360
        position_actuelle = position_actuelle_deg % 360

        diff = position_cible - position_actuelle

        # Chemin le plus court
        if diff > 180:
            diff -= 360
        elif diff < -180:
            diff += 360

        self.rotation(diff, vitesse, use_ramp=use_ramp)

    # =========================================================================
    # FEEDBACK CONTROLLER (délégation)
    # =========================================================================

    def get_feedback_controller(self) -> 'FeedbackController':
        """
        Crée et retourne un FeedbackController pour ce moteur.

        Returns:
            FeedbackController: Contrôleur de feedback configuré
        """
        from core.hardware.feedback_controller import FeedbackController
        return FeedbackController(self, get_daemon_reader())

    def rotation_avec_feedback(
        self,
        angle_cible: float,
        vitesse: float = 0.001,
        tolerance: float = 0.5,
        max_iterations: int = 10,
        max_correction_par_iteration: float = 45.0,
        allow_large_movement: bool = False
    ) -> Dict[str, Any]:
        """
        Rotation avec feedback via démon encodeur.

        Délègue au FeedbackController pour la logique de correction.

        Args:
            angle_cible: Angle cible absolu (0-360°)
            vitesse: Délai moteur (secondes/pas), défaut 0.001s
            tolerance: Tolérance acceptable (°), défaut 0.5°
            max_iterations: Nombre max d'itérations, défaut 10
            max_correction_par_iteration: Correction max par itération (°)
            allow_large_movement: Si True, autorise les grands mouvements (> 20°)
                                  Utilisé pour GOTO initial après calibration

        Returns:
            dict: Statistiques du mouvement (success, positions, erreur, etc.)
        """
        controller = self.get_feedback_controller()
        return controller.rotation_avec_feedback(
            angle_cible=angle_cible,
            vitesse=vitesse,
            tolerance=tolerance,
            max_iterations=max_iterations,
            max_correction_par_iteration=max_correction_par_iteration,
            allow_large_movement=allow_large_movement
        )

    def rotation_relative_avec_feedback(
        self,
        delta_deg: float,
        **kwargs
    ) -> Dict[str, Any]:
        """
        Rotation relative avec feedback via démon.

        Args:
            delta_deg: Déplacement relatif (°), positif = horaire
            **kwargs: Paramètres passés à rotation_avec_feedback()

        Returns:
            dict: Résultat de rotation_avec_feedback()
        """
        controller = self.get_feedback_controller()
        return controller.rotation_relative_avec_feedback(delta_deg, **kwargs)

    # =========================================================================
    # NETTOYAGE
    # =========================================================================

    def nettoyer(self):
        """Nettoie les ressources GPIO lgpio."""
        if self.gpio_handle is None:
            return

        try:
            # Libérer les pins
            try:
                lgpio.gpio_free(self.gpio_handle, self.DIR)
                lgpio.gpio_free(self.gpio_handle, self.STEP)
            except lgpio.error:
                pass  # Pin déjà libéré

            # Fermer le chip GPIO
            try:
                lgpio.gpiochip_close(self.gpio_handle)
            except lgpio.error:
                pass  # Chip déjà fermé

            self.logger.info("GPIO nettoyé (lgpio)")

        except Exception as e:
            self.logger.error(f"Erreur nettoyage GPIO: {e}")
        finally:
            self.gpio_handle = None