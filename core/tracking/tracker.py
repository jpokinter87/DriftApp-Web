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

from core.config.config import (
    SINGLE_SPEED_CHECK_INTERVAL_S,
    SINGLE_SPEED_CORRECTION_THRESHOLD_DEG,
    SINGLE_SPEED_MOTOR_DELAY,
)
from core.hardware.daemon_encoder_reader import get_daemon_reader
from core.hardware.moteur_rp2040 import MoteurRP2040
from core.hardware.moteur_simule import MoteurSimule
from core.observatoire import AstronomicalCalculations
from core.tracking.tracking_logger import TrackingLogger

# Mixins
from core.tracking.tracking_state_mixin import TrackingStateMixin
from core.tracking.tracking_goto_mixin import TrackingGotoMixin
from core.tracking.tracking_corrections_mixin import TrackingCorrectionsMixin


class TrackingSession(TrackingStateMixin, TrackingGotoMixin, TrackingCorrectionsMixin):
    """
    Gère une session de suivi d'objet avec méthode abaque.

    VERSION 5.10 : Vitesse unique (260 µs) — suppression du mode adaptatif.

    Mixins:
    - TrackingStateMixin: _init_tracking_state, _init_statistics, _smooth_position_cible, logs session
    - TrackingGotoMixin: _check_initial_goto, _execute_initial_goto, recherche objet, sync encodeur
    - TrackingCorrectionsMixin: check_and_correct, _apply_correction (avec/sans feedback)
    """

    # Mapping des icônes de mode (conservé pour compat UI — un seul mode reste)
    MODE_ICONS = {"continuous": "🔴"}
    MODE_NAME = "continuous"

    def __init__(
        self,
        moteur: Optional[MoteurRP2040 | MoteurSimule],
        calc: AstronomicalCalculations,
        logger: TrackingLogger,
        seuil: float = SINGLE_SPEED_CORRECTION_THRESHOLD_DEG,
        intervalle: int = SINGLE_SPEED_CHECK_INTERVAL_S,
        abaque_file: str = None,
        motor_config=None,
        encoder_config=None,
        goto_callback=None,
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

        # Instance unique de PlanetaryEphemerides (évite de recréer à chaque correction)
        from core.observatoire import PlanetaryEphemerides

        self._ephemerides = PlanetaryEphemerides()

        # Initialisation par étapes
        self._init_encoder(encoder_config)
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
            pos = get_daemon_reader().read_angle(timeout_ms=200)
            self.encoder_available = True
            self.logger.info(f"Encodeur actif - Position: {pos:.1f}°")
        except Exception as e:
            self.logger.warning(f"Encodeur config activé mais démon inaccessible: {e}")

        if not self.encoder_available:
            self.logger.info("Mode position logicielle (relatif)")

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
            planet_pos = self._ephemerides.get_planet_position(
                self.objet.capitalize(), now, self.calc.latitude, self.calc.longitude
            )
            if planet_pos:
                ra, dec = planet_pos
                return self.calc.calculer_coords_horizontales(ra, dec, now)
            # En cas d'erreur, utiliser les dernières valeurs connues

        # Cas standard (étoiles fixes ou fallback planète)
        return self.calc.calculer_coords_horizontales(self.ra_deg, self.dec_deg, now)

    def _calculate_target_position(
        self, azimut_objet: float, altitude_objet: float
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
        position_cible, infos = self.abaque_manager.get_dome_position(altitude_objet, azimut_objet)
        infos["method"] = "abaque"

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
                real_position = get_daemon_reader().read_angle()
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

        # Si GOTO nécessaire, utiliser la vitesse unique (260 µs)
        if goto_needed:
            self.logger.info(
                f"🎯 GOTO initial requis: {goto_delta:+.1f}° "
                f"(vitesse unique {SINGLE_SPEED_MOTOR_DELAY * 1_000_000:.0f} µs/pas)"
            )
            # Exécuter le GOTO initial (Mixin TrackingGotoMixin)
            self._execute_initial_goto(position_cible_init, SINGLE_SPEED_MOTOR_DELAY)
            self._start_tracking(objet_name, now, initial_interval=SINGLE_SPEED_CHECK_INTERVAL_S)
        else:
            self._start_tracking(objet_name, now)

        # Log et message de retour
        self._log_start(objet_name, azimut, altitude, position_cible_init)

        return True, self._format_start_message(objet_name, azimut, altitude, position_cible_init)

    def _start_tracking(self, objet_name: str, now: datetime, initial_interval: int = None):
        """Active le suivi."""
        self.running = True
        self.drift_tracking["start_time"] = now
        self._last_milestone_time = now
        # Utiliser l'intervalle adaptatif si fourni, sinon l'intervalle par défaut
        interval = initial_interval if initial_interval is not None else self.intervalle
        self.next_correction_time = now + timedelta(seconds=interval)
        self.tracking_logger.start_tracking(
            objet_name, f"{self.ra_deg:.2f}°", f"{self.dec_deg:.2f}°"
        )

    def _check_session_milestone(self):
        """Émet un log session_health toutes les 5 minutes pendant le tracking."""
        if not self.running or not hasattr(self, '_last_milestone_time'):
            return

        now = datetime.now()
        elapsed = (now - self._last_milestone_time).total_seconds()
        if elapsed < 300:  # 5 minutes
            return

        start_time = self.drift_tracking.get('start_time', now)
        duration_min = int((now - start_time).total_seconds() / 60)
        enc_status = 'ok' if self.encoder_available else 'lost'

        self.logger.info(
            f"session_health | object={self.objet} duration_min={duration_min} "
            f"corrections={self.total_corrections} total_movement={self.total_movement:.1f} "
            f"mode={self.MODE_NAME} encoder={enc_status} failed={self.failed_feedback_count}"
        )
        self._last_milestone_time = now

    def _log_start(self, objet_name: str, azimut: float, altitude: float, position_cible: float):
        """Log le démarrage du suivi."""
        self.logger.info(
            f"Méthode: ABAQUE | Az={azimut:.1f}° Alt={altitude:.1f}° | "
            f"Position cible={position_cible % 360:.1f}°"
        )

    def _format_start_message(
        self, objet_name: str, azimut: float, altitude: float, position_cible: float
    ) -> str:
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
            return {"running": False}

        now = datetime.now()
        azimut, altitude = self._calculate_current_coords(now)
        position_cible, infos = self._calculate_target_position(azimut, altitude)

        remaining = self._calculate_remaining_time(now)

        return self._build_status_dict(
            azimut, altitude, position_cible, remaining, infos
        )

    def _calculate_remaining_time(self, now: datetime) -> int:
        """Calcule le temps restant avant prochaine correction."""
        remaining = int((self.next_correction_time - now).total_seconds())
        return max(0, remaining)

    def _build_status_dict(
        self,
        azimut: float,
        altitude: float,
        position_cible: float,
        remaining: int,
        infos: dict,
    ) -> dict:
        """Construit le dictionnaire de statut."""
        # Lisser la position cible (Mixin TrackingStateMixin)
        position_cible_lissee = self._smooth_position_cible(position_cible)

        return {
            "running": True,
            "objet": self.objet,
            "obj_az_raw": azimut,
            "obj_alt": altitude,
            "position_cible": position_cible_lissee,
            "position_relative": self.position_relative % 360,
            "remaining_seconds": remaining,
            "total_corrections": self.total_corrections,
            "total_movement": self.total_movement,
            # Mode unique v5.10 — clés conservées pour compat UI
            "adaptive_mode": self.MODE_NAME,
            "adaptive_mode_description": "Mode unique - Vitesse max (v5.10)",
            "adaptive_interval": SINGLE_SPEED_CHECK_INTERVAL_S,
            "adaptive_threshold": SINGLE_SPEED_CORRECTION_THRESHOLD_DEG,
            "adaptive_motor_delay": SINGLE_SPEED_MOTOR_DELAY,
            "mode_icon": self.MODE_ICONS.get(self.MODE_NAME, "⚪"),
            # Autres informations
            "steps_correction_factor": self.steps_correction_factor,
            "encoder_daemon": self.encoder_available,
            "abaque_method": infos.get("method", "interpolation"),
            "in_bounds": infos.get("in_bounds", True),
            "encoder_offset": self.encoder_offset,
        }

    # =========================================================================
    # ARRÊT DU SUIVI
    # =========================================================================

    def stop(self):
        """Arrête le suivi, sauvegarde la session et affiche un bilan."""
        try:
            self._log_session_summary()  # Mixin TrackingStateMixin
        except Exception as e:
            self.logger.error(
                f"Erreur log_session_summary (session sera quand même sauvegardée): {e}"
            )
        self._save_session_to_file()  # Sauvegarde automatique — toujours exécuté
        self._finalize_stop()

    def _save_session_to_file(self):
        """
        Sauvegarde la session de tracking dans un fichier JSON.

        Appelée automatiquement à l'arrêt du tracking.

        Note: Couplage inverse avec web.session.session_storage — ce module core/
        importe un composant web/ pour la persistance. Acceptable car la sauvegarde
        est optionnelle (protégée par try/except ImportError).
        """
        try:
            from web.session import session_storage

            # Construire les données complètes
            session_data = self.get_session_data()  # Mixin TrackingStateMixin

            # Ajouter les métadonnées de l'objet
            session_data["object"] = {
                "name": self.objet,
                "ra_deg": self.ra_deg,
                "dec_deg": self.dec_deg,
            }

            # Ajouter l'heure de fin
            session_data["timing"] = {
                "start_time": session_data.pop("start_time"),
                "end_time": datetime.now().isoformat(),
                "duration_seconds": session_data.pop("duration_seconds"),
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
            self.total_movement / self.total_corrections if self.total_corrections > 0 else 0.0
        )
        self.tracking_logger.stop_tracking("Manuel")
        self.logger.info(
            f"Statistiques | Corrections: {self.total_corrections} | "
            f"Mouvement total: {self.total_movement:.1f}° | "
            f"Correction moyenne: {avg_correction:.2f}°"
        )
