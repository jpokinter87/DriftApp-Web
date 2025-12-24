"""
Contrôleur du moteur pas-à-pas de la coupole.
Support Raspberry Pi 1-4 (RPi.GPIO) et Raspberry Pi 5 (lgpio).

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

Date: 24 décembre 2025
"""

import json
import logging
import time
from pathlib import Path
from typing import Dict, Any, Optional

DAEMON_JSON = Path("/dev/shm/ems22_position.json")


# =============================================================================
# LECTEUR DÉMON ENCODEUR
# =============================================================================

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
        self.logger = logging.getLogger("DaemonEncoderReader")

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


# Tentative d'import des bibliothèques GPIO
GPIO_LIB = None
gpio_handle = None

try:
    import lgpio
    GPIO_LIB = "lgpio"
except ImportError:
    try:
        import RPi.GPIO as GPIO
        GPIO_LIB = "RPi.GPIO"
    except ImportError:
        GPIO_LIB = None


class MoteurCoupole:
    """
    Contrôleur pour moteur pas-à-pas de la coupole.
    Compatible Raspberry Pi 1-5.

    VERSION 4.1 : Refactorisé pour lisibilité et maintenabilité.
    - Méthodes GPIO unifiées
    - Découpage en responsabilités uniques
    """

    def __init__(self, config_moteur):
        """
        Initialise le contrôleur moteur depuis la configuration.

        Args:
            config_moteur: Configuration moteur (dict ou dataclass)
        """
        self.logger = logging.getLogger("MoteurCoupole")
        self.gpio_handle = None
        self.direction_actuelle = 1
        self.stop_requested = False

        self._verifier_gpio_disponible()
        self._charger_config(config_moteur)
        self._valider_config()
        self._calculer_steps_par_tour()
        self._init_parametres_rampe()
        self._init_gpio()

        self.logger.info(
            f"Moteur initialisé ({self.gpio_lib}) - "
            f"Steps/tour coupole: {self.steps_per_dome_revolution}"
        )

    # =========================================================================
    # INITIALISATION (méthodes privées)
    # =========================================================================

    def _verifier_gpio_disponible(self):
        """Vérifie qu'une bibliothèque GPIO est disponible."""
        if GPIO_LIB is None:
            raise RuntimeError(
                "Aucune bibliothèque GPIO disponible. "
                "Installez lgpio (Pi 5) ou RPi.GPIO (Pi 1-4)"
            )
        self.gpio_lib = GPIO_LIB

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

    def _valider_config(self):
        """Validation déjà effectuée par motor_config_parser."""
        pass  # Conservé pour compatibilité API, validation dans _charger_config

    def _calculer_steps_par_tour(self):
        """Calcule le nombre de pas par tour de coupole."""
        self.steps_per_dome_revolution = int(
            self.STEPS_PER_REV *
            self.MICROSTEPS *
            self.gear_ratio *
            self.steps_correction_factor
        )

    def _init_parametres_rampe(self):
        """
        Initialisation des paramètres de rampe.

        VERSION 4.5 : La rampe est maintenant gérée par le module
        acceleration_ramp.py qui fournit une S-curve pour des transitions
        douces. Voir AccelerationRamp pour les paramètres.

        La rampe est activée par défaut dans rotation() via use_ramp=True.
        """
        # Les paramètres de rampe sont maintenant dans acceleration_ramp.py
        # Pas de configuration ici pour ne pas modifier les réglages moteur
        pass

    # =========================================================================
    # ABSTRACTION GPIO (méthodes unifiées)
    # =========================================================================

    def _gpio_write(self, pin: int, value: int):
        """
        Écriture GPIO unifiée pour lgpio et RPi.GPIO.

        Args:
            pin: Numéro de broche GPIO
            value: 0 ou 1
        """
        if self.gpio_lib == "lgpio":
            import lgpio
            lgpio.gpio_write(self.gpio_handle, pin, value)
        else:  # RPi.GPIO
            gpio_value = self.gpio_handle.HIGH if value else self.gpio_handle.LOW
            self.gpio_handle.output(pin, gpio_value)

    def _gpio_high(self, pin: int):
        """Met la broche GPIO à l'état haut."""
        self._gpio_write(pin, 1)

    def _gpio_low(self, pin: int):
        """Met la broche GPIO à l'état bas."""
        self._gpio_write(pin, 0)

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

    def _pulse_step(self, delai: float):
        """
        Génère une impulsion sur la broche STEP.

        Args:
            delai: Délai total pour le pas (divisé en HIGH/LOW)
        """
        self._gpio_high(self.STEP)
        time.sleep(delai / 2)
        self._gpio_low(self.STEP)
        time.sleep(delai / 2)

    def _init_gpio(self):
        """Initialise les GPIO selon la bibliothèque disponible."""
        global gpio_handle

        if self.gpio_lib == "lgpio":
            # Raspberry Pi 5 avec lgpio
            try:
                import lgpio
                # Ouvrir le chip GPIO (chip 4 sur Pi 5, chip 0 sur Pi 1-4)
                try:
                    self.gpio_handle = lgpio.gpiochip_open(4)  # Pi 5
                except:
                    self.gpio_handle = lgpio.gpiochip_open(0)  # Fallback Pi 1-4

                gpio_handle = self.gpio_handle

                # Configurer les pins en sortie
                lgpio.gpio_claim_output(self.gpio_handle, self.DIR)
                lgpio.gpio_claim_output(self.gpio_handle, self.STEP)

                # État initial
                lgpio.gpio_write(self.gpio_handle, self.DIR, 0)
                lgpio.gpio_write(self.gpio_handle, self.STEP, 0)

                self.logger.info(f"GPIO initialisé avec lgpio")

            except Exception as e:
                self.logger.error(f"Erreur init lgpio: {e}")
                raise

        elif self.gpio_lib == "RPi.GPIO":
            # Raspberry Pi 1-4 avec RPi.GPIO
            try:
                GPIO.setmode(GPIO.BCM)
                GPIO.setwarnings(False)

                GPIO.setup(self.DIR, GPIO.OUT)
                GPIO.setup(self.STEP, GPIO.OUT)

                GPIO.output(self.DIR, GPIO.LOW)
                GPIO.output(self.STEP, GPIO.LOW)

                self.gpio_handle = GPIO

                self.logger.info("GPIO initialisé avec RPi.GPIO")

            except Exception as e:
                self.logger.error(f"Erreur init RPi.GPIO: {e}")
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
        Fait faire un pas au moteur.

        VERSION OPTIMISÉE INLINE (alignée sur Dome_v4) :
        - Pas d'appels de méthodes internes (6 appels → 0)
        - delai_min réduit à 10µs (était 50µs)
        - Code GPIO inline pour timing optimal

        Args:
            delai: Délai en secondes entre les impulsions
        """
        if self.gpio_handle is None:
            raise RuntimeError("GPIO non initialisé")

        # Validation inline (comme Dome_v4)
        delai_min = 0.00001  # 10µs comme Dome_v4 (était 50µs)
        if delai < delai_min:
            self.logger.warning(f"Délai {delai:.6f}s < minimum {delai_min:.6f}s")
            delai = delai_min

        # GPIO inline (comme Dome_v4) - PAS d'appels de méthodes
        if self.gpio_lib == "lgpio":
            import lgpio
            lgpio.gpio_write(self.gpio_handle, self.STEP, 1)
            time.sleep(delai / 2)
            lgpio.gpio_write(self.gpio_handle, self.STEP, 0)
            time.sleep(delai / 2)
        else:  # RPi.GPIO
            self.gpio_handle.output(self.STEP, self.gpio_handle.HIGH)
            time.sleep(delai / 2)
            self.gpio_handle.output(self.STEP, self.gpio_handle.LOW)
            time.sleep(delai / 2)

    def _calculer_delai_rampe(self, step_index: int, total_steps: int,
                               vitesse_nominale: float) -> float:
        """
        Retourne le délai constant - PAS DE RAMPE.

        ALIGNEMENT SUR calibration_moteur.py qui fonctionne parfaitement.

        La rampe a été supprimée car elle causait des problèmes :
        - Démarrage brutal pour vitesses rapides (rampe désactivée à tort)
        - Délai forcé à 0.0015s pour petits mouvements (<50 pas)
        - Comportement différent de calibration_moteur.py

        Les vitesses testées sur site (0.00012s à 0.0011s) fonctionnent
        en délai constant. Voir capture_Vitesses.png pour les mesures.

        Args:
            step_index: Index du pas actuel (ignoré)
            total_steps: Nombre total de pas (ignoré)
            vitesse_nominale: Délai cible en secondes

        Returns:
            Délai constant = vitesse_nominale
        """
        return vitesse_nominale

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
        """Nettoie les ressources GPIO."""
        if self.gpio_handle is None:
            return

        try:
            if self.gpio_lib == "lgpio":
                import lgpio
                try:
                    lgpio.gpio_free(self.gpio_handle, self.DIR)
                    lgpio.gpio_free(self.gpio_handle, self.STEP)
                except:
                    pass

                try:
                    lgpio.gpiochip_close(self.gpio_handle)
                except:
                    pass

                self.logger.info("GPIO nettoyé (lgpio)")

            elif self.gpio_lib == "RPi.GPIO":
                GPIO.cleanup()
                self.logger.info("GPIO nettoyé (RPi.GPIO)")

        except Exception as e:
            self.logger.error(f"Erreur nettoyage GPIO: {e}")
        finally:
            self.gpio_handle = None