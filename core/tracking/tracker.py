"""
Logique principale du suivi de coupole - VERSION ABAQUE AVEC DÉMON.

Ce module utilise la méthode abaque uniquement : interpolation à partir de mesures réelles sur site.

VERSION DÉMON : Utilise le démon encodeur externe au lieu du singleton.

Architecture Mixin (v4.5):
- TrackingStateMixin: Gestion de l'état et statistiques
- TrackingGotoMixin: Logique GOTO initial
- TrackingCorrectionsMixin: Logique de correction
"""

import logging
from datetime import datetime, timedelta
from typing import Tuple, Optional

from core.hardware.moteur import MoteurCoupole
from core.hardware.moteur_simule import MoteurSimule
from core.observatoire import AstronomicalCalculations
from core.observatoire import PlanetaryEphemerides
from core.tracking.adaptive_tracking import AdaptiveTrackingManager
from core.tracking.tracking_logger import TrackingLogger

# Mixins
from core.tracking.tracking_state_mixin import TrackingStateMixin
from core.tracking.tracking_goto_mixin import TrackingGotoMixin
from core.tracking.tracking_corrections_mixin import TrackingCorrectionsMixin


class TrackingSession(TrackingStateMixin, TrackingGotoMixin, TrackingCorrectionsMixin):
    """
    Gère une session de suivi d'objet avec méthode abaque.

    VERSION 4.5 : Refactorisé en mixins pour lisibilité et maintenabilité.

    Mixins:
    - TrackingStateMixin: _init_tracking_state, _init_statistics, _smooth_position_cible, logs session
    - TrackingGotoMixin: _check_initial_goto, _execute_initial_goto, recherche objet, sync encodeur
    - TrackingCorrectionsMixin: check_and_correct, _apply_correction (avec/sans feedback)
    """

    # Mapping des icônes de mode
    MODE_ICONS = {
        'normal': '🟢',
        'critical': '🟠',
        'continuous': '🔴',
        'fast_track': '🟣'
    }

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
            encoder_config=None,
            goto_callback=None
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
            goto_callback: Callback appelé avec les infos du GOTO initial
                          Signature: callback(goto_info: dict) où goto_info contient:
                          - current_position: position actuelle
                          - target_position: position cible
                          - delta: déplacement à effectuer
        """
        self.moteur = moteur
        self.calc = calc
        self.tracking_logger = logger  # TrackingLogger pour logs UI
        self.seuil = seuil
        self.intervalle = intervalle
        self.logger = logging.getLogger(__name__)  # Logger standard Python
        self.goto_callback = goto_callback

        # Initialisation par étapes
        self._init_encoder(encoder_config)
        self._init_adaptive_manager(intervalle, seuil, adaptive_config)
        self._init_abaque(abaque_file)
        self._init_tracking_state()  # Mixin TrackingStateMixin
        self._init_statistics(motor_config)  # Mixin TrackingStateMixin

    # =========================================================================
    # INITIALISATION (méthodes privées)
    # =========================================================================

    def _init_encoder(self, encoder_config):
        """Initialise et vérifie l'encodeur."""
        encoder_enabled = encoder_config.enabled if encoder_config else False
        self.encoder_available = False
        self.encoder_offset = 0.0

        if not encoder_enabled:
            self.logger.info("Encodeur désactivé dans configuration")
            return

        from core.hardware.hardware_detector import HardwareDetector
        encoder_ok, encoder_error, _ = HardwareDetector.check_encoder_daemon()

        if not encoder_ok:
            self.logger.warning(f"Encodeur config activé mais: {encoder_error}")
            return

        try:
            pos = MoteurCoupole.get_daemon_angle(timeout_ms=200)
            self.encoder_available = True
            self.logger.info(f"Encodeur actif - Position: {pos:.1f}°")
        except Exception as e:
            self.logger.warning(f"Encodeur config activé mais démon inaccessible: {e}")

        if not self.encoder_available:
            self.logger.info("Mode position logicielle (relatif)")

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

        self.logger.info("Mode abaque activé")

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

    def start(self, objet_name: str, skip_goto: bool = False) -> Tuple[bool, str]:
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
            skip_goto: Si True, ne pas faire de GOTO initial (position actuelle conservée).
                       Utile quand l'utilisateur a ajusté manuellement la coupole.

        Returns:
            Tuple (success, message)
        """
        # Rechercher et valider l'objet (Mixin TrackingGotoMixin)
        success, error_msg = self._rechercher_objet(objet_name)
        if not success:
            return False, error_msg

        now = datetime.now()

        # Pour les planètes, mettre à jour RA/DEC (Mixin TrackingGotoMixin)
        if self.is_planet:
            success, error_msg = self._update_planet_coords(objet_name, now)
            if not success:
                return False, error_msg

        # Calculer positions initiales
        azimut, altitude = self._calculate_current_coords(now)
        position_cible_init, _ = self._calculate_target_position(azimut, altitude)

        # Vérifier si on doit faire un GOTO initial (Mixin TrackingGotoMixin)
        # Si skip_goto=True, on saute le GOTO (l'utilisateur a ajusté manuellement)
        if skip_goto:
            goto_needed = False
            goto_delta = 0.0
            self.logger.info("⏭️ GOTO initial ignoré (skip_goto=True, position actuelle conservée)")
        else:
            goto_needed, goto_delta = self._check_initial_goto(position_cible_init)

        # Initialiser le suivi (Mixin TrackingGotoMixin)
        # Si skip_goto, on utilise la position actuelle de l'encodeur comme position_relative
        if skip_goto:
            # Utiliser la position réelle comme point de départ
            try:
                real_position = MoteurCoupole.get_daemon_angle()
                self._setup_initial_position(azimut, altitude, real_position)
                self._sync_encoder(real_position)
                self.logger.info(f"Position initiale depuis encodeur: {real_position:.1f}°")
            except Exception:
                # Fallback: utiliser la position cible calculée
                self._setup_initial_position(azimut, altitude, position_cible_init)
                self._sync_encoder(position_cible_init)
        else:
            self._setup_initial_position(azimut, altitude, position_cible_init)
            self._sync_encoder(position_cible_init)

        # Si GOTO nécessaire, toujours utiliser la vitesse CONTINUOUS (la plus rapide)
        if goto_needed:
            # Vitesse CONTINUOUS pour le GOTO initial (0.00015s = ~41°/min)
            continuous_speed = self.adaptive_manager.get_continuous_motor_delay()
            self.logger.info(
                f"🎯 GOTO initial requis: {goto_delta:+.1f}° en mode CONTINUOUS (vitesse max)"
            )
            # Exécuter le GOTO initial (Mixin TrackingGotoMixin)
            self._execute_initial_goto(position_cible_init, continuous_speed)
            # Démarrer le suivi avec l'intervalle approprié au mode adaptatif (basé sur altitude)
            tracking_params = self.adaptive_manager.evaluate_tracking_zone(altitude, azimut, 0)
            self._start_tracking(objet_name, now, initial_interval=tracking_params.check_interval)
        else:
            self._start_tracking(objet_name, now)

        # Log et message de retour
        self._log_start(objet_name, azimut, altitude, position_cible_init)

        return True, self._format_start_message(
            objet_name, azimut, altitude, position_cible_init
        )

    def _start_tracking(self, objet_name: str, now: datetime, initial_interval: int = None):
        """Active le suivi."""
        self.running = True
        self.drift_tracking['start_time'] = now
        # Utiliser l'intervalle adaptatif si fourni, sinon l'intervalle par défaut
        interval = initial_interval if initial_interval is not None else self.intervalle
        self.next_correction_time = now + timedelta(seconds=interval)
        self.tracking_logger.start_tracking(objet_name, f"{self.ra_deg:.2f}°", f"{self.dec_deg:.2f}°")

    def _log_start(self, objet_name: str, azimut: float, altitude: float,
                   position_cible: float):
        """Log le démarrage du suivi."""
        self.logger.info(
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
        # Lisser la position cible (Mixin TrackingStateMixin)
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

    # =========================================================================
    # ARRÊT DU SUIVI
    # =========================================================================

    def stop(self):
        """Arrête le suivi, sauvegarde la session et affiche un bilan."""
        self._log_session_summary()  # Mixin TrackingStateMixin
        self._save_session_to_file()  # Sauvegarde automatique
        self._finalize_stop()

    def _save_session_to_file(self):
        """
        Sauvegarde la session de tracking dans un fichier JSON.

        Appelée automatiquement à l'arrêt du tracking.
        """
        try:
            from web.session import session_storage

            # Construire les données complètes
            session_data = self.get_session_data()  # Mixin TrackingStateMixin

            # Ajouter les métadonnées de l'objet
            session_data['object'] = {
                'name': self.objet,
                'ra_deg': self.ra_deg,
                'dec_deg': self.dec_deg,
            }

            # Ajouter l'heure de fin
            session_data['timing'] = {
                'start_time': session_data.pop('start_time'),
                'end_time': datetime.now().isoformat(),
                'duration_seconds': session_data.pop('duration_seconds'),
            }

            # Sauvegarder
            session_id = session_storage.save_session(session_data)
            if session_id:
                self.logger.info(f"Session sauvegardée: {session_id}")
            else:
                self.logger.warning("Échec sauvegarde session")

        except ImportError:
            # Module session non disponible (ex: tests sans Django)
            self.logger.debug("Module session non disponible - sauvegarde ignorée")
        except Exception as e:
            self.logger.warning(f"Erreur sauvegarde session: {e}")

    def _finalize_stop(self):
        """Finalise l'arrêt du suivi."""
        self.running = False
        self.logger.info("Suivi arrêté")

        avg_correction = (
            self.total_movement / self.total_corrections
            if self.total_corrections > 0
            else 0.0
        )
        self.tracking_logger.stop_tracking("Manuel")
        self.logger.info(
            f"Statistiques | Corrections: {self.total_corrections} | "
            f"Mouvement total: {self.total_movement:.1f}° | "
            f"Correction moyenne: {avg_correction:.2f}°"
        )
