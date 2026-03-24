"""
Controleur moteur pas-a-pas via RP2040 (communication serie).

Delegue la generation d'impulsions STEP/DIR au firmware MicroPython
sur Pi Pico, communiquant via USB CDC serie.

Interface publique standard pour le controleur moteur.

Protocole serie (defini en Phase 1 firmware) :
  Commandes: MOVE <steps> <direction> <delay_us> <ramp_type>
             STOP
             STATUS
  Reponses:  OK <steps_executed>
             STOPPED <steps_done>
             ERROR <message>
             BUSY
             IDLE
             MOVING <steps_remaining>
             READY

Version: 5.3
Date: Mars 2026
"""

import logging
import threading
import time
from typing import Dict, Any, Optional

from core.hardware.daemon_encoder_reader import get_daemon_reader
from core.hardware.motor_config_parser import parse_motor_config, validate_motor_params

logger = logging.getLogger(__name__)

# Timeout pour attendre READY au demarrage (secondes)
READY_TIMEOUT = 5.0

# Timeout par defaut pour les reponses serie (secondes)
RESPONSE_TIMEOUT = 30.0


class MoteurRP2040:
    """
    Controleur moteur via RP2040 serie.

    Controleur moteur via communication serie avec le firmware RP2040.
    """

    def __init__(self, config_moteur, serial_port):
        """
        Initialise le controleur RP2040.

        Args:
            config_moteur: Configuration moteur (dict ou dataclass via motor_config_parser)
            serial_port: Objet serie (pyserial.Serial ou SerialSimulator)
        """
        self.logger = logging.getLogger(__name__)
        self.serial_port = serial_port
        self.direction_actuelle = 1
        self.stop_requested = False
        self._needs_drain = False
        self._serial_lock = threading.Lock()

        # Parser la config moteur
        params = parse_motor_config(config_moteur)
        validate_motor_params(params)

        self.STEPS_PER_REV = params.steps_per_revolution
        self.MICROSTEPS = params.microsteps
        self.gear_ratio = params.gear_ratio
        self.steps_correction_factor = params.steps_correction_factor
        self.steps_per_dome_revolution = int(
            self.STEPS_PER_REV
            * self.MICROSTEPS
            * self.gear_ratio
            * self.steps_correction_factor
        )

        # Attendre le READY du firmware
        self._wait_ready()

        self.logger.info(
            f"MoteurRP2040 initialise - "
            f"Steps/tour coupole: {self.steps_per_dome_revolution}"
        )

    # =========================================================================
    # COMMUNICATION SERIE
    # =========================================================================

    def _send_command(self, cmd: str, timeout: float = None) -> str:
        """
        Envoie une commande au firmware et lit la reponse.

        Thread-safe via _serial_lock. Ne pas appeler depuis request_stop()
        qui utilise _send_stop() sans lock pour pouvoir interrompre un MOVE en cours.

        Args:
            cmd: Commande texte (sans newline)
            timeout: Timeout pour la reponse (secondes). Si None, utilise le timeout du port.

        Returns:
            Reponse du firmware (strippee)

        Raises:
            IOError: Si le port serie est ferme
        """
        if not self.serial_port.is_open:
            raise IOError("Port serie RP2040 ferme")

        with self._serial_lock:
            # Ajuster le timeout si specifie
            old_timeout = self.serial_port.timeout
            if timeout is not None:
                self.serial_port.timeout = timeout

            try:
                self.serial_port.write((cmd + "\n").encode("utf-8"))
                response = self.serial_port.readline()
            finally:
                if timeout is not None:
                    self.serial_port.timeout = old_timeout

            if not response:
                self.logger.warning(f"Pas de reponse pour commande: {cmd}")
                return ""

            return response.decode("utf-8", errors="replace").strip()

    def _drain_serial_buffer(self):
        """
        Lit et ignore les donnees residuelles dans le buffer serie.

        Utilise un timeout court (50ms) pour ne pas bloquer.
        Evite les reponses fantomes apres un STOP ou un mouvement interrompu.
        """
        old_timeout = self.serial_port.timeout
        self.serial_port.timeout = 0.05
        try:
            while True:
                data = self.serial_port.readline()
                if not data:
                    break
                text = data.decode("utf-8", errors="replace").strip()
                if text:
                    self.logger.debug(f"Drain buffer: {text}")
        finally:
            self.serial_port.timeout = old_timeout

    def _wait_ready(self):
        """
        Verifie que le firmware RP2040 est pret.

        Tente d'abord de lire un READY spontane (boot frais du Pico).
        Si rien recu, envoie STATUS pour verifier que le firmware repond
        (cas ou le Pico a boote avant l'ouverture du port serie).

        Raises:
            TimeoutError: Si le firmware ne repond pas dans le delai
        """
        start = time.time()

        # Phase 1 : attendre un READY spontane (boot frais)
        while time.time() - start < READY_TIMEOUT:
            response = self.serial_port.readline()
            if response:
                text = response.decode("utf-8", errors="replace").strip()
                if text == "READY":
                    self.logger.info("Firmware RP2040 pret (READY recu)")
                    return
                elif text == "IDLE":
                    self.logger.info("Firmware RP2040 pret (IDLE — deja demarre)")
                    return

        # Phase 2 : le READY a ete manque, envoyer STATUS pour verifier
        self.logger.debug("Pas de READY recu, envoi STATUS pour verifier le firmware")
        try:
            self.serial_port.write(b"STATUS\n")
            response = self.serial_port.readline()
            if response:
                text = response.decode("utf-8", errors="replace").strip()
                if text in ("IDLE", "READY"):
                    self.logger.info(f"Firmware RP2040 pret ({text} via STATUS)")
                    return
        except Exception:
            pass

        raise TimeoutError(
            f"Firmware RP2040 n'a pas repondu dans {READY_TIMEOUT}s"
        )

    def _parse_response(self, response: str, context: str = "") -> Optional[int]:
        """
        Parse une reponse du firmware.

        Args:
            response: Reponse texte du firmware
            context: Contexte pour les logs (ex: "rotation 45°")

        Returns:
            Nombre de pas executes (ou None si pas applicable)
        """
        if not response:
            self.logger.warning(f"Reponse vide du firmware ({context})")
            return None

        parts = response.split()
        status = parts[0].upper()

        if status == "OK":
            steps_done = int(parts[1]) if len(parts) > 1 else 0
            return steps_done

        elif status == "STOPPED":
            steps_done = int(parts[1]) if len(parts) > 1 else 0
            self._needs_drain = True
            self.logger.info(
                f"Mouvement arrete par firmware apres {steps_done} pas ({context})"
            )
            return steps_done

        elif status == "ERROR":
            msg = " ".join(parts[1:]) if len(parts) > 1 else "inconnu"
            self.logger.warning(f"Erreur firmware: {msg} ({context})")
            return None

        elif status == "BUSY":
            self.logger.warning(
                f"Firmware occupe, commande ignoree ({context})"
            )
            return None

        elif status == "IDLE":
            return None

        else:
            self.logger.warning(f"Reponse firmware inattendue: {response} ({context})")
            return None

    # =========================================================================
    # INTERFACE PUBLIQUE
    # =========================================================================

    def definir_direction(self, direction: int):
        """
        Definit la direction de rotation.

        Args:
            direction: 1 pour horaire, -1 pour anti-horaire
        """
        self.direction_actuelle = 1 if direction >= 0 else -1

    def rotation(self, angle_deg: float, vitesse: float = 0.0015, use_ramp: bool = True):
        """
        Fait tourner la coupole d'un angle donne.

        Traduit l'appel en commande MOVE serie pour le firmware RP2040.

        Args:
            angle_deg: Angle en degres (positif = horaire)
            vitesse: Delai nominal entre les pas en secondes
            use_ramp: Si True, utilise la rampe S-curve du firmware
        """
        self.clear_stop_request()

        deg_per_step = 360.0 / self.steps_per_dome_revolution
        steps = int(abs(angle_deg) / deg_per_step)

        if steps == 0:
            return

        direction = 1 if angle_deg >= 0 else 0
        self.direction_actuelle = 1 if angle_deg >= 0 else -1
        delay_us = max(1, int(vitesse * 1_000_000))
        ramp_type = "SCURVE" if use_ramp else "NONE"

        # Estimer la duree du mouvement pour le timeout serie
        # En mode SCURVE, le delai moyen est plus grand que delay_us (rampe)
        estimated_secs = (steps * max(delay_us, 500)) / 1_000_000
        move_timeout = estimated_secs + 5.0  # marge de 5s

        self.logger.debug(
            f"Rotation {angle_deg:+.2f}° ({steps} pas, "
            f"delay={delay_us}us, rampe={ramp_type}, timeout={move_timeout:.1f}s)"
        )

        # Drainer les reponses residuelles seulement apres un STOP
        # (la reponse IDLE peut rester dans le buffer apres interruption)
        if self._needs_drain:
            self._drain_serial_buffer()
            self._needs_drain = False

        response = self._send_command(
            f"MOVE {steps} {direction} {delay_us} {ramp_type}",
            timeout=move_timeout,
        )
        self._parse_response(response, f"rotation {angle_deg:+.2f}°")

    def rotation_absolue(
        self,
        position_cible_deg: float,
        position_actuelle_deg: float,
        vitesse: float = 0.0015,
        use_ramp: bool = True,
    ):
        """
        Rotation vers une position absolue.

        Args:
            position_cible_deg: Position cible en degres (0-360)
            position_actuelle_deg: Position actuelle en degres (0-360)
            vitesse: Delai entre les pas
            use_ramp: Si True, utilise la rampe S-curve
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
    # CONTROLE D'ARRET
    # =========================================================================

    def request_stop(self):
        """
        Demande l'arret du mouvement en cours.

        Envoie STOP directement sans prendre le lock serie, car un MOVE
        bloquant peut etre en cours dans un autre thread. Le firmware
        detecte STOP via check_for_stop() et repond STOPPED au MOVE
        en cours — la reponse sera lue par le thread qui attend le MOVE.
        """
        self.stop_requested = True
        self._needs_drain = True
        try:
            if self.serial_port.is_open:
                self.serial_port.write(b"STOP\n")
                self.logger.info("Arret demande au firmware RP2040")
        except Exception as e:
            self.logger.warning(f"Erreur envoi STOP: {e}")

    def clear_stop_request(self):
        """Efface le flag d'arret."""
        self.stop_requested = False

    # =========================================================================
    # METHODES DEMON ENCODEUR
    # =========================================================================

    @staticmethod
    def get_daemon_angle(timeout_ms: int = 200) -> float:
        """
        Lit l'angle calibre publie par le demon EMS22A.

        L'encodeur est independant du driver moteur (toujours SPI via daemon).
        """
        return get_daemon_reader().read_angle(timeout_ms)

    @staticmethod
    def get_daemon_status() -> Optional[dict]:
        """Lit le statut complet du demon EMS22A."""
        return get_daemon_reader().read_status()

    # =========================================================================
    # FEEDBACK CONTROLLER
    # =========================================================================

    def get_feedback_controller(self):
        """
        Cree et retourne un FeedbackController pour ce moteur.

        Returns:
            FeedbackController configure avec ce moteur et le daemon reader
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
        allow_large_movement: bool = False,
    ) -> Dict[str, Any]:
        """
        Rotation avec feedback via demon encodeur.

        Delegue au FeedbackController.
        """
        controller = self.get_feedback_controller()
        return controller.rotation_avec_feedback(
            angle_cible=angle_cible,
            vitesse=vitesse,
            tolerance=tolerance,
            max_iterations=max_iterations,
            max_correction_par_iteration=max_correction_par_iteration,
            allow_large_movement=allow_large_movement,
        )

    def rotation_relative_avec_feedback(
        self, delta_deg: float, **kwargs
    ) -> Dict[str, Any]:
        """
        Rotation relative avec feedback via demon.
        """
        controller = self.get_feedback_controller()
        return controller.rotation_relative_avec_feedback(delta_deg, **kwargs)

    # =========================================================================
    # NETTOYAGE
    # =========================================================================

    def nettoyer(self):
        """Ferme le port serie."""
        if self.serial_port and self.serial_port.is_open:
            self.serial_port.close()
            self.logger.info("Port serie RP2040 ferme")
