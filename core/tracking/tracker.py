"""
Logique principale du suivi de coupole - VERSION ABAQUE AVEC DÉMON.

Ce module utilise la méthode abaque uniquement : interpolation à partir de mesures réelles sur site.

VERSION DÉMON : Utilise le démon encodeur externe au lieu du singleton.
"""

import logging
import time
from collections import deque
from datetime import datetime, timedelta
from typing import Tuple, Optional

from core.hardware.moteur import MoteurCoupole
from core.hardware.moteur_simule import MoteurSimule
from core.observatoire import AstronomicalCalculations
from core.observatoire import PlanetaryEphemerides
from core.observatoire.catalogue import GestionnaireCatalogue
from core.tracking.adaptive_tracking import AdaptiveTrackingManager
from core.tracking.tracking_logger import TrackingLogger


class TrackingSession:
    """
    Gère une session de suivi d'objet avec méthode abaque.

    VERSION 4.1 : Refactorisé pour lisibilité et maintenabilité.
    """

    def __init__(
            self,
            moteur: Optional[MoteurCoupole | MoteurSimule],
            calc: AstronomicalCalculations,
            logger: TrackingLogger,
            seuil: float = 0.5,
            intervalle: int = 300,
            abaque_file: str = None,
            adaptive_config=None,
            motor_config=None,
            encoder_config=None
    ):
        """
        Initialise une session de suivi.

        Args:
            moteur: Instance du moteur de la coupole
            calc: Calculateur astronomique
            logger: Logger de suivi
            seuil: Seuil de correction en degrés
            intervalle: Intervalle entre corrections en secondes
            abaque_file: Chemin vers le fichier d'abaque (requis)
        """
        self.moteur = moteur
        self.calc = calc
        self.logger = logger
        self.seuil = seuil
        self.intervalle = intervalle
        self.python_logger = logging.getLogger(__name__)

        # Initialisation par étapes
        self._init_encoder(encoder_config)
        self._init_adaptive_manager(intervalle, seuil, adaptive_config)
        self._init_abaque(abaque_file)
        self._init_tracking_state()
        self._init_statistics(motor_config)

    # =========================================================================
    # INITIALISATION (méthodes privées)
    # =========================================================================

    def _init_encoder(self, encoder_config):
        """Initialise et vérifie l'encodeur."""
        encoder_enabled = encoder_config.enabled if encoder_config else False
        self.encoder_available = False
        self.encoder_offset = 0.0

        if not encoder_enabled:
            self.python_logger.info("Encodeur désactivé dans configuration")
            return

        from core.hardware.hardware_detector import HardwareDetector
        encoder_ok, encoder_error, _ = HardwareDetector.check_encoder_daemon()

        if not encoder_ok:
            self.python_logger.warning(f"Encodeur config activé mais: {encoder_error}")
            return

        try:
            pos = MoteurCoupole.get_daemon_angle(timeout_ms=200)
            self.encoder_available = True
            self.python_logger.info(f"Encodeur actif - Position: {pos:.1f}°")
        except Exception as e:
            self.python_logger.warning(f"Encodeur config activé mais démon inaccessible: {e}")

        if not self.encoder_available:
            self.python_logger.info("Mode position logicielle (relatif)")

    def _init_adaptive_manager(self, intervalle, seuil, adaptive_config):
        """Initialise le gestionnaire adaptatif."""
        self.adaptive_manager = AdaptiveTrackingManager(
            base_interval=intervalle,
            base_threshold=seuil,
            adaptive_config=adaptive_config
        )

    def _init_abaque(self, abaque_file):
        """Charge le fichier d'abaque."""
        if abaque_file is None:
            raise ValueError("abaque_file requis")

        from core.tracking.abaque_manager import AbaqueManager
        self.abaque_manager = AbaqueManager(abaque_file)

        if not self.abaque_manager.load_abaque():
            raise RuntimeError("Échec du chargement de l'abaque")

        self.python_logger.info("Mode abaque activé")

    def _init_tracking_state(self):
        """Initialise l'état du suivi."""
        # Position relative de la coupole
        self.position_relative = 0.0

        # Données de l'objet suivi
        self.objet = None
        self.ra_deg = None
        self.dec_deg = None
        self.is_planet = False

        # Position initiale de référence
        self.azimut_initial = None
        self.altitude_initiale = None
        self.angle_horaire_initial = None

        # État
        self.running = False
        self.next_correction_time = None

        # Protection contre les oscillations
        self.correction_history = deque(maxlen=10)
        self.oscillation_count = 0
        self.consecutive_errors = 0
        self.max_consecutive_errors = 5

        # Protection contre corrections feedback échouées
        self.failed_feedback_count = 0
        self.max_failed_feedback = 3

        # Indicateur de grand déplacement (basculement méridien ou GOTO)
        self.is_large_movement_in_progress = False

        # Cache position cible pour éviter oscillations UI
        # La position cible est lissée pour éviter les sauts visuels
        self._cached_position_cible = None
        self._position_cible_history = deque(maxlen=5)  # Moyenne glissante sur 5 valeurs

    def _init_statistics(self, motor_config):
        """Initialise les statistiques et paramètres de correction."""
        self.total_corrections = 0
        self.total_movement = 0.0
        self.steps_correction_factor = motor_config.steps_correction_factor if motor_config else 1.0

        self.drift_tracking = {
            'start_time': datetime.now(),
            'corrections_log': []
        }

        self.python_logger.info(f"Facteur de correction pas: {self.steps_correction_factor:.4f}")

    def _calculate_current_coords(self, now: datetime) -> Tuple[float, float]:
        """
        Méthode CENTRALISÉE pour calculer Azimut/Altitude.
        Gère aussi bien les étoiles (Fixes J2000) que les planètes (Calcul dynamique).

        Args:
            now: Timestamp pour le calcul

        Returns:
            Tuple (azimut, altitude) en degrés
        """
        if self.is_planet:
            ephemerides = PlanetaryEphemerides()
            planet_pos = ephemerides.get_planet_position(
                self.objet.capitalize(),
                now,
                self.calc.latitude,
                self.calc.longitude
            )
            if planet_pos:
                ra, dec = planet_pos
                return self.calc.calculer_coords_horizontales(ra, dec, now)
            # En cas d'erreur, utiliser les dernières valeurs connues

        # Cas standard (étoiles fixes ou fallback planète)
        return self.calc.calculer_coords_horizontales(self.ra_deg, self.dec_deg, now)

    def _calculate_target_position(
        self,
        azimut_objet: float,
        altitude_objet: float
    ) -> Tuple[float, dict]:
        """
        Calcule la position cible de la coupole par interpolation de l'abaque.

        Args:
            azimut_objet: Azimut de l'objet (degrés)
            altitude_objet: Altitude de l'objet (degrés)

        Returns:
            Tuple (position_cible, infos_debug)
        """
        # Méthode abaque : interpolation des mesures réelles
        position_cible, infos = self.abaque_manager.get_dome_position(
            altitude_objet,
            azimut_objet
        )
        infos['method'] = 'abaque'

        return position_cible, infos
    
    # =========================================================================
    # DÉMARRAGE DU SUIVI
    # =========================================================================

    def start(self, objet_name: str) -> Tuple[bool, str]:
        """
        Démarre le suivi d'un objet.

        IMPORTANT : On suppose que l'utilisateur a :
        1. Pointé le télescope sur l'objet
        2. Centré manuellement la trappe sur le tube
        3. Lancé le programme
        → Position initiale = 0° relatif

        NOUVEAU (Dec 2025) : Si l'encodeur est calibré (passage par le switch),
        le système fait un GOTO initial vers la position cible si nécessaire.

        Args:
            objet_name: Nom de l'objet à suivre

        Returns:
            Tuple (success, message)
        """
        # Rechercher et valider l'objet
        success, error_msg = self._rechercher_objet(objet_name)
        if not success:
            return False, error_msg

        now = datetime.now()

        # Pour les planètes, mettre à jour RA/DEC
        if self.is_planet:
            success, error_msg = self._update_planet_coords(objet_name, now)
            if not success:
                return False, error_msg

        # Calculer positions initiales
        azimut, altitude = self._calculate_current_coords(now)
        position_cible_init, _ = self._calculate_target_position(azimut, altitude)

        # Vérifier si on doit faire un GOTO initial (encodeur calibré)
        goto_needed, goto_delta = self._check_initial_goto(position_cible_init)

        # Initialiser le suivi
        self._setup_initial_position(azimut, altitude, position_cible_init)
        self._sync_encoder(position_cible_init)

        # Si GOTO nécessaire, évaluer le mode adaptatif et faire la correction
        if goto_needed:
            tracking_params = self.adaptive_manager.evaluate_tracking_zone(
                altitude, azimut, abs(goto_delta)
            )
            self.python_logger.info(
                f"🎯 GOTO initial requis: {goto_delta:+.1f}° en mode {tracking_params.mode.value}"
            )
            # Exécuter le GOTO initial (méthode dédiée pour éviter bug position_relative)
            self._execute_initial_goto(position_cible_init, tracking_params.motor_delay)
            # Démarrer le suivi avec l'intervalle approprié au mode
            self._start_tracking(objet_name, now, initial_interval=tracking_params.check_interval)
        else:
            self._start_tracking(objet_name, now)

        # Log et message de retour
        self._log_start(objet_name, azimut, altitude, position_cible_init)

        return True, self._format_start_message(
            objet_name, azimut, altitude, position_cible_init
        )

    def _check_initial_goto(self, position_cible: float) -> Tuple[bool, float]:
        """
        Vérifie si un GOTO initial est nécessaire (encodeur calibré).

        Si l'encodeur est calibré (passage par le switch), on peut connaître
        la position réelle de la coupole et faire un GOTO vers la position cible.

        NOTE: Cette fonction lit le daemon INDÉPENDAMMENT de encoder_available.
        Le GOTO initial fonctionne même si le feedback boucle fermée est désactivé.

        Args:
            position_cible: Position où la coupole devrait être (degrés)

        Returns:
            Tuple (goto_needed, delta_degrees)
            - goto_needed: True si un GOTO est nécessaire
            - delta_degrees: Déplacement à effectuer (0 si pas de GOTO)
        """
        try:
            # Vérifier si le daemon est disponible et si l'encodeur est calibré
            # NOTE: On ne vérifie PAS encoder_available car le GOTO initial
            # est une fonctionnalité distincte du feedback boucle fermée
            encoder_status = MoteurCoupole.get_daemon_status()
            if not encoder_status:
                self.python_logger.debug("Daemon encodeur non disponible")
                return False, 0.0

            is_calibrated = encoder_status.get('calibrated', False)
            if not is_calibrated:
                self.python_logger.info(
                    "Encodeur non calibré - Pas de GOTO initial "
                    "(passez par le switch pour activer le mode absolu)"
                )
                return False, 0.0

            # Lire la position réelle
            real_position = MoteurCoupole.get_daemon_angle()

            # Calculer le delta via le chemin le plus court
            delta, path_info = self.adaptive_manager.verify_shortest_path(
                real_position, position_cible
            )

            # Si le delta est significatif (> seuil de correction), GOTO nécessaire
            if abs(delta) > self.seuil:
                self.python_logger.info(
                    f"🔄 Encodeur calibré - Position réelle: {real_position:.1f}° | "
                    f"Position cible: {position_cible:.1f}° | Delta: {delta:+.1f}°"
                )
                return True, delta

            self.python_logger.info(
                f"Position OK - Réelle: {real_position:.1f}° ≈ Cible: {position_cible:.1f}° "
                f"(delta={delta:+.2f}° < seuil={self.seuil}°)"
            )
            return False, 0.0

        except Exception as e:
            self.python_logger.debug(f"Daemon non accessible: {e}")
            return False, 0.0

    def _rechercher_objet(self, objet_name: str) -> Tuple[bool, str]:
        """Recherche l'objet dans le catalogue."""
        catalog = GestionnaireCatalogue()
        result = catalog.rechercher(objet_name)

        if not result or 'ra_deg' not in result or 'dec_deg' not in result:
            return False, f"Objet '{objet_name}' introuvable"

        self.objet = objet_name
        self.ra_deg = result['ra_deg']
        self.dec_deg = result['dec_deg']
        self.is_planet = result.get('is_planet', False)

        return True, ""

    def _update_planet_coords(self, objet_name: str, now: datetime) -> Tuple[bool, str]:
        """Met à jour les coordonnées d'une planète."""
        ephemerides = PlanetaryEphemerides()
        planet_pos = ephemerides.get_planet_position(
            objet_name.capitalize(), now,
            self.calc.latitude, self.calc.longitude
        )
        if planet_pos:
            self.ra_deg, self.dec_deg = planet_pos
            return True, ""
        return False, f"Impossible de calculer la position de {objet_name}"

    def _setup_initial_position(self, azimut: float, altitude: float,
                                 position_cible: float):
        """Configure la position initiale."""
        self.azimut_initial = azimut
        self.altitude_initiale = altitude
        self.position_relative = position_cible

    def _sync_encoder(self, position_cible: float):
        """Synchronise l'offset encodeur."""
        if not self.encoder_available:
            return

        try:
            encoder_status = MoteurCoupole.get_daemon_status()
            if encoder_status:
                is_calibrated = encoder_status.get('calibrated', False)
                if is_calibrated:
                    self.python_logger.info("Encodeur calibré - Mode absolu disponible")
                else:
                    self.python_logger.warning(
                        "Encodeur non calibré - Mode relatif. "
                        "Passez par le switch (45°) pour le mode absolu."
                    )

            real_position = MoteurCoupole.get_daemon_angle()
            self.encoder_offset = position_cible - real_position
            self.python_logger.info(
                f"SYNC: Coupole={position_cible:.1f}° | "
                f"Encodeur={real_position:.1f}° | Offset={self.encoder_offset:.1f}°"
            )
        except Exception as e:
            self.python_logger.warning(f"Encodeur: {e}")
            self.encoder_available = False

    def _execute_initial_goto(self, position_cible: float, motor_delay: float):
        """
        Exécute le GOTO initial vers la position cible.

        IMPORTANT: Cette méthode est spécifique au GOTO initial et diffère
        de _apply_correction() car elle NE MODIFIE PAS position_relative.

        Après le GOTO, position_relative reste à position_cible (correct)
        car la coupole est maintenant à cette position.

        Args:
            position_cible: Position absolue cible (degrés)
            motor_delay: Délai entre les pas (secondes)
        """
        try:
            # Lire la position actuelle de l'encodeur
            position_actuelle = MoteurCoupole.get_daemon_angle()

            self.python_logger.info(
                f"GOTO initial: {position_actuelle:.1f}° → {position_cible:.1f}° "
                f"(vitesse: {motor_delay}s/pas)"
            )

            # Utiliser rotation_avec_feedback si l'encodeur est disponible
            if self.encoder_available:
                # Calculer l'angle cible pour l'encodeur (sans offset car GOTO initial)
                # Pour le GOTO initial, on cible directement position_cible
                result = self.moteur.rotation_avec_feedback(
                    angle_cible=position_cible,
                    vitesse=motor_delay,
                    tolerance=0.5,
                    max_iterations=10
                )

                if result['success']:
                    self.python_logger.info(
                        f"GOTO initial réussi: {result['position_initiale']:.1f}° → "
                        f"{result['position_finale']:.1f}° "
                        f"(erreur: {result['erreur_finale']:.2f}°, {result['iterations']} iter)"
                    )
                else:
                    self.python_logger.warning(
                        f"GOTO initial imprécis: erreur finale = {result['erreur_finale']:.2f}°"
                    )

                # Mettre à jour l'offset encodeur après le GOTO
                try:
                    position_finale = MoteurCoupole.get_daemon_angle()
                    self.encoder_offset = position_cible - position_finale
                    self.python_logger.info(
                        f"Offset encodeur recalculé: {self.encoder_offset:.1f}°"
                    )
                except Exception:
                    pass

            else:
                # Sans feedback, utiliser rotation simple
                delta, _ = self.adaptive_manager.verify_shortest_path(
                    position_actuelle, position_cible
                )
                self.moteur.rotation(delta, motor_delay)
                self.python_logger.info(f"GOTO initial (sans feedback): {delta:+.1f}°")

            # NE PAS modifier position_relative - elle est déjà correcte !
            # position_relative = position_cible (mise par _setup_initial_position)

        except Exception as e:
            self.python_logger.error(f"Erreur GOTO initial: {e}")
            # En cas d'erreur, position_relative reste à position_cible
            # ce qui est l'hypothèse de départ

    def _start_tracking(self, objet_name: str, now: datetime, initial_interval: int = None):
        """Active le suivi."""
        self.running = True
        self.drift_tracking['start_time'] = now
        # Utiliser l'intervalle adaptatif si fourni, sinon l'intervalle par défaut
        interval = initial_interval if initial_interval is not None else self.intervalle
        self.next_correction_time = now + timedelta(seconds=interval)
        self.logger.start_tracking(objet_name, f"{self.ra_deg:.2f}°", f"{self.dec_deg:.2f}°")

    def _log_start(self, objet_name: str, azimut: float, altitude: float,
                   position_cible: float):
        """Log le démarrage du suivi."""
        self.python_logger.info(
            f"Méthode: ABAQUE | Az={azimut:.1f}° Alt={altitude:.1f}° | "
            f"Position cible={position_cible % 360:.1f}°"
        )

    def _format_start_message(self, objet_name: str, azimut: float,
                               altitude: float, position_cible: float) -> str:
        """Formate le message de démarrage."""
        return (
            f"Suivi démarré : {objet_name}\n"
            f"  RA={self.ra_deg:.2f}° DEC={self.dec_deg:.2f}°\n"
            f"  Azimut: {azimut:.1f}° | Altitude: {altitude:.1f}°\n"
            f"  Position coupole: {position_cible % 360:.1f}°\n"
            f"  Méthode: ABAQUE"
        )
    

    # =========================================================================
    # STATUT
    # =========================================================================

    # Mapping des icônes de mode
    MODE_ICONS = {
        'normal': '🟢',
        'critical': '🟠',
        'continuous': '🔴',
        'fast_track': '🟣'
    }

    # Seuil pour déclencher le mode FAST_TRACK (grands déplacements)
    LARGE_MOVEMENT_THRESHOLD = 30.0  # degrés - au-delà, on utilise FAST_TRACK

    def get_status(self) -> dict:
        """
        Retourne l'état actuel du suivi.

        Returns:
            Dictionnaire avec les informations de statut
        """
        if not self.running:
            return {'running': False}

        now = datetime.now()
        azimut, altitude = self._calculate_current_coords(now)
        position_cible, infos = self._calculate_target_position(azimut, altitude)

        delta, _ = self.adaptive_manager.verify_shortest_path(
            self.position_relative, position_cible
        )
        diag_info = self.adaptive_manager.get_diagnostic_info(altitude, azimut, delta)
        remaining = self._calculate_remaining_time(now)

        return self._build_status_dict(
            azimut, altitude, position_cible, remaining, diag_info, infos
        )

    def _calculate_remaining_time(self, now: datetime) -> int:
        """Calcule le temps restant avant prochaine correction."""
        remaining = int((self.next_correction_time - now).total_seconds())
        return max(0, remaining)

    def _build_status_dict(self, azimut: float, altitude: float,
                           position_cible: float, remaining: int,
                           diag_info: dict, infos: dict) -> dict:
        """Construit le dictionnaire de statut."""
        # Lisser la position cible pour éviter les oscillations visuelles
        position_cible_lissee = self._smooth_position_cible(position_cible)

        return {
            'running': True,
            'objet': self.objet,
            'obj_az_raw': azimut,
            'obj_alt': altitude,
            'position_cible': position_cible_lissee,
            'position_relative': self.position_relative % 360,
            'remaining_seconds': remaining,
            'total_corrections': self.total_corrections,
            'total_movement': self.total_movement,
            # Informations adaptatives
            'adaptive_mode': diag_info['mode'],
            'adaptive_mode_description': diag_info['mode_description'],
            'adaptive_interval': diag_info['check_interval'],
            'adaptive_threshold': diag_info['correction_threshold'],
            'adaptive_motor_delay': diag_info['motor_delay'],
            'in_critical_zone': diag_info['in_critical_zone'],
            'is_high_altitude': diag_info['is_high_altitude'],
            'is_large_movement': diag_info['is_large_movement'],
            'mode_icon': self.MODE_ICONS.get(diag_info['mode'], '⚪'),
            # Autres informations
            'steps_correction_factor': self.steps_correction_factor,
            'encoder_daemon': self.encoder_available,
            'abaque_method': infos.get('method', 'interpolation'),
            'in_bounds': infos.get('in_bounds', True),
        }

    def _smooth_position_cible(self, new_position: float) -> float:
        """
        Lisse la position cible pour éviter les oscillations visuelles dans l'UI.

        Utilise une moyenne glissante avec gestion de la circularité des angles.
        Si le saut est trop grand (>10°), réinitialise l'historique.

        Args:
            new_position: Nouvelle position cible calculée par l'abaque

        Returns:
            Position lissée (0-360°)
        """
        new_position = new_position % 360

        # Si c'est la première valeur, initialiser le cache
        if self._cached_position_cible is None:
            self._cached_position_cible = new_position
            self._position_cible_history.append(new_position)
            return new_position

        # Calculer le delta avec gestion de la circularité
        delta = new_position - self._cached_position_cible
        if delta > 180:
            delta -= 360
        elif delta < -180:
            delta += 360

        # Si le saut est très grand (>10°), c'est un vrai changement, pas du bruit
        # → réinitialiser l'historique
        if abs(delta) > 10:
            self._position_cible_history.clear()
            self._position_cible_history.append(new_position)
            self._cached_position_cible = new_position
            return new_position

        # Ajouter à l'historique
        self._position_cible_history.append(new_position)

        # Calculer la moyenne circulaire
        if len(self._position_cible_history) < 2:
            self._cached_position_cible = new_position
            return new_position

        # Moyenne circulaire en utilisant le sinus/cosinus
        import math
        sin_sum = sum(math.sin(math.radians(p)) for p in self._position_cible_history)
        cos_sum = sum(math.cos(math.radians(p)) for p in self._position_cible_history)
        mean_rad = math.atan2(sin_sum, cos_sum)
        mean_deg = math.degrees(mean_rad) % 360

        self._cached_position_cible = mean_deg
        return mean_deg


    def check_and_correct(self) -> Tuple[bool, str]:
        """
        Vérifie si une correction est nécessaire et l'applique.
        VERSION ADAPTATIVE : Ajuste automatiquement les paramètres selon la zone.
        VERSION AVEC LOGS ENRICHIS + MESURE DE DURÉE

        Returns:
            Tuple (correction_applied, log_message)
        """
        if not self.running:
            return False, "Suivi non actif"

        now = datetime.now()
        timestamp = now.strftime("%H:%M:%S")

        # Calculer la position actuelle de l'objet (méthode centralisée)
        azimut, altitude = self._calculate_current_coords(now)

        # Calculer la position cible
        position_cible, infos = self._calculate_target_position(azimut, altitude)

        # === Vérification du chemin le plus court ===
        delta, path_verification = self.adaptive_manager.verify_shortest_path(
            self.position_relative,
            position_cible
        )

        # === Évaluation de la zone et obtention des paramètres adaptatifs ===
        tracking_params = self.adaptive_manager.evaluate_tracking_zone(
            altitude,
            azimut,
            abs(delta)
        )


        # Vérifier si la correction dépasse le seuil
        if abs(delta) < tracking_params.correction_threshold:
            # Mise à jour du temps de prochaine vérification
            self.next_correction_time = now + timedelta(seconds=tracking_params.check_interval)

            return False, f"Delta {delta:+.2f}° < seuil {tracking_params.correction_threshold:.2f}°"

        # === APPLIQUER LA CORRECTION ===
        self._apply_correction(delta, tracking_params.motor_delay)

        # === LOGS ENRICHIS ===
        log_message = (
            f"[{now.strftime('%H:%M:%S')}] Correction: {delta:+.2f}° | "
            f"Az={azimut:.1f}° Alt={altitude:.1f}° | "
            f"AzCoupole={position_cible:.1f}° | "
            f"Mode: {tracking_params.mode} (interval={tracking_params.check_interval}s, "
            f"seuil={tracking_params.correction_threshold}°)"
        )

        self.python_logger.info(log_message)

        # === Ajouter à l'historique de dérive ===
        self.drift_tracking['corrections_log'].append({
            'timestamp': now,
            'azimut': azimut,
            'altitude': altitude,
            'correction': delta,
            'mode': tracking_params.mode
        })

        # Enregistrer dans l'historique
        self.correction_history.append(delta)

        # Mise à jour du temps de prochaine vérification
        self.next_correction_time = now + timedelta(seconds=tracking_params.check_interval)

        return True, log_message

    def _apply_correction(self, delta_deg: float, motor_delay: float = 0.002):
        """
        Applique une correction AVEC FEEDBACK si encodeur disponible.

        VERSION DÉMON : Utilise le démon encodeur pour le feedback.

        Args:
            delta_deg: Correction en degrés (+ = horaire, - = anti-horaire)
            motor_delay: Délai entre les pas (secondes)
        """
        if self.encoder_available:
            self._apply_correction_avec_feedback(delta_deg, motor_delay)
        else:
            self._apply_correction_sans_feedback(delta_deg, motor_delay)

    def _apply_correction_avec_feedback(self, delta_deg: float, motor_delay: float):
        """Applique une correction avec feedback encodeur."""
        try:
            position_cible_logique, angle_cible_encodeur = self._calculer_cibles(delta_deg)
            result, duration = self._executer_rotation_feedback(
                angle_cible_encodeur, motor_delay
            )
            self._finaliser_correction(delta_deg, position_cible_logique)
            self._traiter_resultat_feedback(result, duration)

        except Exception as e:
            self.python_logger.error(f"Erreur correction feedback: {e}")
            self.python_logger.error("Traceback:", exc_info=True)
            self._apply_correction_sans_feedback(delta_deg, motor_delay)

    def _calculer_cibles(self, delta_deg: float) -> tuple:
        """Calcule les positions cibles logique et encodeur."""
        position_cible_logique = (self.position_relative + delta_deg) % 360
        angle_cible_encodeur = (position_cible_logique - self.encoder_offset) % 360
        return position_cible_logique, angle_cible_encodeur

    def _executer_rotation_feedback(self, angle_cible: float,
                                     motor_delay: float) -> tuple:
        """Exécute la rotation avec feedback et mesure la durée."""
        start_time = time.time()
        result = self.moteur.rotation_avec_feedback(
            angle_cible=angle_cible,
            vitesse=motor_delay,
            tolerance=0.5,
            max_iterations=10
        )
        duration = time.time() - start_time
        return result, duration

    def _finaliser_correction(self, delta_deg: float, position_cible: float):
        """Met à jour la position et les statistiques."""
        self.position_relative = position_cible
        self.total_corrections += 1
        self.total_movement += abs(delta_deg)

    def _traiter_resultat_feedback(self, result: dict, duration: float):
        """Traite le résultat de la correction feedback."""
        if result['success']:
            self._log_feedback_succes(result, duration)
        else:
            self._log_feedback_echec(result, duration)
            if self._verifier_echecs_consecutifs():
                return

        self._log_detail_iterations(result)

    def _log_feedback_succes(self, result: dict, duration: float):
        """Log une correction feedback réussie."""
        self.failed_feedback_count = 0
        self.python_logger.info(
            f"Correction feedback réussie: {result['position_initiale']:.1f}° -> "
            f"{result['position_finale']:.1f}° (erreur: {result['erreur_finale']:.2f}°, "
            f"AZCoupole: {result['position_cible']:.1f}°, "
            f"{result['iterations']}/10 iter, {duration:.1f}s)"
        )

    def _log_feedback_echec(self, result: dict, duration: float):
        """Log une correction feedback imprécise."""
        self.failed_feedback_count += 1
        self.python_logger.warning(
            f"Correction feedback imprécise: "
            f"{result['position_initiale']:.1f}° -> {result['position_finale']:.1f}° "
            f"(erreur: {result['erreur_finale']:.2f}°, "
            f"AZCoupole: {result['position_cible']:.1f}°, "
            f"{result['iterations']}/10 iter, {duration:.1f}s) "
            f"[{self.failed_feedback_count}/{self.max_failed_feedback} échecs]"
        )

    def _verifier_echecs_consecutifs(self) -> bool:
        """Vérifie si trop d'échecs consécutifs, arrête le suivi si nécessaire."""
        if self.failed_feedback_count >= self.max_failed_feedback:
            self.python_logger.error(
                f"SUIVI ARRÊTÉ : {self.max_failed_feedback} corrections "
                f"consécutives ont échoué."
            )
            self.python_logger.error(
                "Vérifiez l'encodeur et la calibration. "
                "Consultez BUG_CRITIQUE_ENCODEUR_NON_CALIBRE.md"
            )
            self.stop()
            return True
        return False

    def _log_detail_iterations(self, result: dict):
        """Log le détail des itérations en mode debug."""
        if result['iterations'] <= 1:
            return

        self.python_logger.debug("  Détail corrections:")
        for corr in result['corrections']:
            correction = corr.get('correction_demandee', corr.get('correction_commandee', 0))
            erreur_avant = corr.get('erreur_avant', corr.get('erreur', 0))
            erreur_apres = corr.get('erreur_apres', 0)
            self.python_logger.debug(
                f"    Iter {corr['iteration']}: {correction:+.2f}° "
                f"(erreur avant: {erreur_avant:+.2f}°, après: {erreur_apres:+.2f}°)"
            )
    
    def _apply_correction_sans_feedback(self, delta_deg: float, motor_delay: float = 0.002):
        """
        Applique une correction SANS feedback (ancienne méthode).
        
        Utilisée comme fallback si le démon n'est pas disponible.

        Args:
            delta_deg: Correction en degrés (+ = horaire, - = anti-horaire)
            motor_delay: Délai entre les pas (secondes)
        """
        # === CALCULER LE NOMBRE DE PAS AVEC FACTEUR DE CORRECTION ===
        steps = int(
            (abs(delta_deg) / 360.0) *
            self.moteur.steps_per_dome_revolution)

        if steps == 0:
            return

        # Définir la direction
        direction = 1 if delta_deg > 0 else -1
        self.moteur.definir_direction(direction)

        # Log
        self.python_logger.debug(
            f"Déplacement (sans feedback): {steps} pas à {motor_delay}s/pas "
            f"(facteur: {self.steps_correction_factor:.4f}, "
            f"vitesse: {1 / motor_delay:.0f} pas/s)"
            f"DEBUG: steps_per_dome_revolution = {self.moteur.steps_per_dome_revolution}"
        )

        # Faire les pas
        for _ in range(steps):
            self.moteur.faire_un_pas(delai=motor_delay)

        # Mettre à jour la position relative
        self.position_relative += delta_deg

        # Statistiques
        self.total_corrections += 1
        self.total_movement += abs(delta_deg)

 
    # =========================================================================
    # ARRÊT DU SUIVI
    # =========================================================================

    def stop(self):
        """Arrête le suivi et affiche un bilan de session."""
        self._log_session_summary()
        self._finalize_stop()

    def _log_session_summary(self):
        """Affiche le bilan de la session."""
        if not self.drift_tracking.get('start_time'):
            return

        duration = datetime.now() - self.drift_tracking['start_time']
        duration_hours = duration.total_seconds() / 3600

        self.python_logger.info("=" * 60)
        self.python_logger.info("BILAN DE LA SESSION")
        self.python_logger.info("=" * 60)

        self._log_basic_stats(duration_hours, duration)
        self._log_rate_stats(duration_hours)
        self._log_additional_info()

        self.python_logger.info("=" * 60)

    def _log_basic_stats(self, duration_hours: float, duration):
        """Log les statistiques de base."""
        self.python_logger.info(f"Objet: {self.objet}")
        self.python_logger.info(f"Méthode: ABAQUE")
        self.python_logger.info(
            f"Durée: {duration_hours:.2f}h ({duration.total_seconds() / 60:.1f}min)"
        )
        self.python_logger.info(f"Corrections appliquées: {self.total_corrections}")
        self.python_logger.info(f"Mouvement total: {self.total_movement:.1f}°")

    def _log_rate_stats(self, duration_hours: float):
        """Log les statistiques de fréquence."""
        if duration_hours <= 0:
            return

        corrections_per_hour = self.total_corrections / duration_hours
        movement_per_hour = self.total_movement / duration_hours
        self.python_logger.info(f"Fréquence: {corrections_per_hour:.1f} corrections/h")
        self.python_logger.info(f"Mouvement moyen: {movement_per_hour:.1f}°/h")

    def _log_additional_info(self):
        """Log les informations additionnelles."""
        if hasattr(self.adaptive_manager, 'current_mode'):
            self.python_logger.info(f"Mode final: {self.adaptive_manager.current_mode.value}")

        if self.steps_correction_factor != 1.0:
            self.python_logger.info(f"Facteur de correction: {self.steps_correction_factor:.4f}")

        encoder_status = 'Actif' if self.encoder_available else 'Inactif'
        self.python_logger.info(f"Démon encodeur: {encoder_status}")

    def _finalize_stop(self):
        """Finalise l'arrêt du suivi."""
        self.running = False
        self.python_logger.info("Suivi arrêté")

        avg_correction = (
            self.total_movement / self.total_corrections
            if self.total_corrections > 0
            else 0.0
        )
        self.logger.stop_tracking("Manuel")
        self.python_logger.info(
            f"Statistiques | Corrections: {self.total_corrections} | "
            f"Mouvement total: {self.total_movement:.1f}° | "
            f"Correction moyenne: {avg_correction:.2f}°"
        )
