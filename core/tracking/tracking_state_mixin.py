"""
Mixin pour la gestion de l'état et des statistiques du suivi.

Ce module contient les méthodes liées à:
- Initialisation de l'état du suivi
- Initialisation des statistiques
- Lissage de la position cible (moyenne circulaire)
- Bilan de session (logs de fin)

Date: Décembre 2025
Version: 4.5
"""

import math
from collections import deque
from datetime import datetime


class TrackingStateMixin:
    """
    Mixin pour la gestion de l'état et des statistiques.

    Fournit les méthodes d'initialisation de l'état interne
    et de calcul des statistiques de session.
    """

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

        # Lissage position cible (voir _smooth_position_cible pour algorithme détaillé)
        # - _cached_position_cible: dernière valeur lissée retournée
        # - _position_cible_history: fenêtre glissante pour moyenne circulaire
        self._cached_position_cible = None
        self._position_cible_history = deque(maxlen=5)

    def _init_statistics(self, motor_config):
        """Initialise les statistiques et paramètres de correction."""
        self.total_corrections = 0
        self.total_movement = 0.0
        self.clockwise_movement = 0.0
        self.counterclockwise_movement = 0.0
        self.steps_correction_factor = motor_config.steps_correction_factor if motor_config else 1.0

        # Timer pour le sampling des positions (graphiques)
        self._last_position_log_time = None
        self._position_log_interval = 30  # secondes

        # Distribution du temps par mode
        self._mode_time_tracker = {
            'normal': 0,
            'critical': 0,
            'continuous': 0,
            'last_mode': None,
            'last_mode_time': None
        }

        self.drift_tracking = {
            'start_time': datetime.now(),
            'corrections_log': [],
            'position_log': [],  # Sampling positions pour graphiques
            'goto_log': [],      # Mouvements GOTO
        }

        self.logger.info(f"Facteur de correction pas: {self.steps_correction_factor:.4f}")

    def _smooth_position_cible(self, new_position: float) -> float:
        """
        Lisse la position cible pour éviter les oscillations visuelles dans l'UI.

        ALGORITHME DE LISSAGE PAR MOYENNE CIRCULAIRE
        ============================================

        Problème résolu:
            L'abaque retourne des positions qui peuvent osciller légèrement
            (±0.5°) entre deux appels consécutifs, causant un "tremblement"
            visuel de l'affichage dans l'interface web.

        Solution:
            Moyenne glissante sur les 5 dernières valeurs avec:
            1. Gestion de la circularité (359° → 1° = +2°, pas -358°)
            2. Reset automatique si saut > 10° (changement réel, pas du bruit)
            3. Moyenne circulaire via atan2(Σsin, Σcos)

        Fonctionnement:
            1. Normaliser l'angle dans [0, 360[
            2. Si première valeur → initialiser et retourner
            3. Calculer delta circulaire avec la valeur cachée
            4. Si |delta| > 10° → reset historique (mouvement réel)
            5. Sinon → ajouter à l'historique et calculer moyenne circulaire

        Moyenne circulaire (angles):
            - Convertir chaque angle θ en vecteur unitaire (cos θ, sin θ)
            - Sommer les composantes: (Σcos θ, Σsin θ)
            - L'angle moyen = atan2(Σsin, Σcos)
            Cette méthode évite le problème de la moyenne arithmétique
            qui donnerait 180° pour [1°, 359°] au lieu de 0°.

        Paramètres:
            - Fenêtre: 5 valeurs (compromis réactivité/stabilité)
            - Seuil reset: 10° (au-delà = mouvement volontaire)

        Args:
            new_position: Nouvelle position cible calculée par l'abaque (degrés)

        Returns:
            Position lissée dans l'intervalle [0, 360[

        Example:
            >>> history = [44.5, 45.0, 44.8, 45.2, 44.9]  # oscillations ±0.5°
            >>> _smooth_position_cible(45.1)  # → ~44.9° (lissé)
            >>> # Saut important:
            >>> _smooth_position_cible(180.0)  # → 180.0° (reset, pas de lissage)
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
        sin_sum = sum(math.sin(math.radians(p)) for p in self._position_cible_history)
        cos_sum = sum(math.cos(math.radians(p)) for p in self._position_cible_history)
        mean_rad = math.atan2(sin_sum, cos_sum)
        mean_deg = math.degrees(mean_rad) % 360

        self._cached_position_cible = mean_deg
        return mean_deg

    def log_to_web(self, message: str, level: str = "info"):
        """
        Envoie un message au logger pour affichage dans l'interface web.

        Cette méthode permet aux mixins de logger des messages importants
        qui seront visibles dans l'interface utilisateur (via TrackingLogger).

        Args:
            message: Message à afficher
            level: Niveau de log - "info", "warning", "error", "debug"
        """
        log_method = getattr(self.logger, level, self.logger.info)
        log_method(message)

    # =========================================================================
    # SESSION DATA LOGGING
    # =========================================================================

    def _log_position_sample(self, azimut: float, altitude: float,
                             dome_position: float, mode: str):
        """
        Enregistre un échantillon de position pour les graphiques.

        Appelé périodiquement (toutes les 30s) pendant le tracking.
        """
        now = datetime.now()

        # Vérifier si assez de temps s'est écoulé depuis le dernier log
        if self._last_position_log_time is not None:
            elapsed = (now - self._last_position_log_time).total_seconds()
            if elapsed < self._position_log_interval:
                return

        self._last_position_log_time = now

        self.drift_tracking['position_log'].append({
            'timestamp': now.isoformat(),
            'azimut': round(azimut, 2),
            'altitude': round(altitude, 2),
            'dome_position': round(dome_position, 2),
            'mode': mode
        })

    def _log_goto(self, start_position: float, target_position: float,
                  delta: float, reason: str):
        """
        Enregistre un mouvement GOTO.

        Args:
            start_position: Position de départ
            target_position: Position cible
            delta: Déplacement en degrés
            reason: 'initial' ou 'large_correction'
        """
        self.drift_tracking['goto_log'].append({
            'timestamp': datetime.now().isoformat(),
            'start_position': round(start_position, 2),
            'target_position': round(target_position, 2),
            'delta': round(delta, 2),
            'reason': reason
        })

    def _update_mode_time(self, current_mode: str):
        """
        Met à jour le temps passé dans chaque mode.

        Appelé à chaque changement de mode ou périodiquement.
        """
        now = datetime.now()
        mode_key = current_mode.lower() if current_mode else 'normal'

        # Si c'est le premier appel, initialiser
        if self._mode_time_tracker['last_mode_time'] is None:
            self._mode_time_tracker['last_mode'] = mode_key
            self._mode_time_tracker['last_mode_time'] = now
            return

        # Calculer le temps écoulé dans le mode précédent
        elapsed = (now - self._mode_time_tracker['last_mode_time']).total_seconds()
        prev_mode = self._mode_time_tracker['last_mode']

        if prev_mode and prev_mode in self._mode_time_tracker:
            self._mode_time_tracker[prev_mode] += elapsed

        # Mettre à jour pour le prochain appel
        self._mode_time_tracker['last_mode'] = mode_key
        self._mode_time_tracker['last_mode_time'] = now

    def _track_correction_direction(self, correction_deg: float):
        """
        Comptabilise la direction des corrections (CW/CCW).

        Args:
            correction_deg: Correction en degrés (positif = CW, négatif = CCW)
        """
        if correction_deg > 0:
            self.clockwise_movement += abs(correction_deg)
        else:
            self.counterclockwise_movement += abs(correction_deg)

    def get_session_data(self) -> dict:
        """
        Retourne les données de session pour l'API.

        Returns:
            dict avec toutes les données de session pour affichage/sauvegarde
        """
        now = datetime.now()
        start_time = self.drift_tracking.get('start_time', now)
        duration_seconds = (now - start_time).total_seconds()

        # Finaliser le temps du mode courant
        self._update_mode_time(
            self.adaptive_manager.current_mode.value
            if hasattr(self, 'adaptive_manager') and self.adaptive_manager
            else 'normal'
        )

        return {
            'start_time': start_time.isoformat(),
            'duration_seconds': int(duration_seconds),
            'summary': {
                'total_corrections': self.total_corrections,
                'total_movement_deg': round(self.total_movement, 2),
                'clockwise_movement_deg': round(self.clockwise_movement, 2),
                'counterclockwise_movement_deg': round(self.counterclockwise_movement, 2),
                'avg_correction_deg': round(
                    self.total_movement / max(1, self.total_corrections), 2
                ),
                'mode_distribution': {
                    'normal': int(self._mode_time_tracker.get('normal', 0)),
                    'critical': int(self._mode_time_tracker.get('critical', 0)),
                    'continuous': int(self._mode_time_tracker.get('continuous', 0)),
                }
            },
            'corrections_log': self.drift_tracking.get('corrections_log', []),
            'position_log': self.drift_tracking.get('position_log', []),
            'goto_log': self.drift_tracking.get('goto_log', []),
        }

    # =========================================================================
    # BILAN DE SESSION
    # =========================================================================

    def _log_session_summary(self):
        """Affiche le bilan de la session."""
        if not self.drift_tracking.get('start_time'):
            return

        duration = datetime.now() - self.drift_tracking['start_time']
        duration_hours = duration.total_seconds() / 3600

        self.logger.info("=" * 60)
        self.logger.info("BILAN DE LA SESSION")
        self.logger.info("=" * 60)

        self._log_basic_stats(duration_hours, duration)
        self._log_rate_stats(duration_hours)
        self._log_additional_info()

        self.logger.info("=" * 60)

    def _log_basic_stats(self, duration_hours: float, duration):
        """Log les statistiques de base."""
        self.logger.info(f"Objet: {self.objet}")
        self.logger.info(f"Méthode: ABAQUE")
        self.logger.info(
            f"Durée: {duration_hours:.2f}h ({duration.total_seconds() / 60:.1f}min)"
        )
        self.logger.info(f"Corrections appliquées: {self.total_corrections}")
        self.logger.info(f"Mouvement total: {self.total_movement:.1f}°")

    def _log_rate_stats(self, duration_hours: float):
        """Log les statistiques de fréquence."""
        if duration_hours <= 0:
            return

        corrections_per_hour = self.total_corrections / duration_hours
        movement_per_hour = self.total_movement / duration_hours
        self.logger.info(f"Fréquence: {corrections_per_hour:.1f} corrections/h")
        self.logger.info(f"Mouvement moyen: {movement_per_hour:.1f}°/h")

    def _log_additional_info(self):
        """Log les informations additionnelles."""
        if hasattr(self.adaptive_manager, 'current_mode'):
            self.logger.info(f"Mode final: {self.adaptive_manager.current_mode.value}")

        if self.steps_correction_factor != 1.0:
            self.logger.info(f"Facteur de correction: {self.steps_correction_factor:.4f}")

        encoder_status = 'Actif' if self.encoder_available else 'Inactif'
        self.logger.info(f"Démon encodeur: {encoder_status}")
