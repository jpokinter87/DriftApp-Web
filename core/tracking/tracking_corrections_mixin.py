"""
Mixin pour la logique de correction du suivi.

Ce module contient les méthodes liées à:
- Vérification et application des corrections (check_and_correct)
- Correction avec feedback encodeur
- Correction sans feedback (fallback)
- Gestion des erreurs et mode dégradé

Date: Décembre 2025
Version: 4.5
"""

import time
from datetime import datetime, timedelta
from typing import Tuple


class TrackingCorrectionsMixin:
    """
    Mixin pour la logique de correction.

    Fournit les méthodes de vérification périodique
    et d'application des corrections de dérive.
    """

    # Seuil au-delà duquel on autorise les grands mouvements dans le FeedbackController
    # Correspond au seuil CONTINUOUS (30°) - évite que la protection 20° bloque les corrections post-méridien
    LARGE_MOVEMENT_THRESHOLD = 30.0

    # Seuil d'erreur acceptable même avec timeout (en degrés)
    # Si erreur < ce seuil, ne pas compter comme échec même si timeout atteint
    # Évite l'arrêt automatique lors de grands déplacements post-méridien
    ACCEPTABLE_ERROR_THRESHOLD = 2.0

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

        # Session milestone (toutes les 5 min)
        self._check_session_milestone()

        now = datetime.now()

        # Vérifier si c'est le moment de faire une correction
        # (respecte l'intervalle configuré, même si appelé plus fréquemment)
        if self.next_correction_time and now < self.next_correction_time:
            return False, ""  # Pas encore le moment

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


        # Détection explicite du transit méridien
        if abs(delta) > self.LARGE_MOVEMENT_THRESHOLD:
            self.logger.info(
                f"meridian_transit | delta={delta:+.1f} az={azimut:.1f} alt={altitude:.1f} "
                f"from={self.position_relative:.1f} to={position_cible:.1f}"
            )
            self._log_goto(self.position_relative, position_cible, delta, 'meridian_transit')

        # Vérifier si la correction dépasse le seuil
        if abs(delta) < tracking_params.correction_threshold:
            # Mise à jour du temps de prochaine vérification
            self.next_correction_time = now + timedelta(seconds=tracking_params.check_interval)
            self.logger.debug(
                f"correction_skip | delta={delta:+.2f} threshold={tracking_params.correction_threshold:.2f} "
                f"next_check={tracking_params.check_interval}s"
            )
            return False, f"correction_skip | delta={delta:+.2f} threshold={tracking_params.correction_threshold:.2f}"

        # === APPLIQUER LA CORRECTION ===
        self._apply_correction(delta, tracking_params.motor_delay)

        # === LOGS STRUCTURÉS ===
        mode_str = tracking_params.mode.value if hasattr(tracking_params.mode, 'value') else str(tracking_params.mode)
        log_message = (
            f"correction | delta={delta:+.2f} az={azimut:.1f} alt={altitude:.1f} "
            f"dome={position_cible:.1f} mode={mode_str} "
            f"interval={tracking_params.check_interval} threshold={tracking_params.correction_threshold:.2f}"
        )

        self.logger.info(log_message)

        # === Ajouter à l'historique de dérive ===
        self.drift_tracking['corrections_log'].append({
            'timestamp': now.isoformat(),
            'azimut': round(azimut, 2),
            'altitude': round(altitude, 2),
            'dome_position': round(position_cible, 2),
            'correction': round(delta, 2),
            'mode': mode_str
        })

        # === Tracking direction des corrections (CW/CCW) ===
        self._track_correction_direction(delta)

        # === Log position pour graphiques (sampling 30s) ===
        self._log_position_sample(azimut, altitude, position_cible, mode_str)

        # === Mise à jour temps par mode ===
        self._update_mode_time(mode_str)

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
            # Autoriser les grands mouvements si delta > seuil (ex: traversée méridien près du zénith)
            allow_large = abs(delta_deg) > self.LARGE_MOVEMENT_THRESHOLD

            if allow_large:
                self.is_large_movement_in_progress = True
                self.logger.info(
                    f"Grand mouvement en cours: {delta_deg:+.1f}° "
                    f"(position {self.position_relative:.1f}° → {position_cible_logique:.1f}°)"
                )

            try:
                result, duration = self._executer_rotation_feedback(
                    angle_cible_encodeur, motor_delay, allow_large_movement=allow_large
                )
                self._finaliser_correction(delta_deg, position_cible_logique)
                self._traiter_resultat_feedback(result, duration)

                # Re-sync encodeur après grand mouvement pour éviter dérive de l'offset
                if allow_large and self.encoder_available:
                    self._resync_encoder_offset(position_cible_logique)
            finally:
                if allow_large:
                    self.is_large_movement_in_progress = False

        except (RuntimeError, IOError, OSError) as e:
            # Erreurs de communication avec l'encodeur - fallback légitime
            self.logger.warning(
                f"Encodeur indisponible, fallback sans feedback: {e}"
            )
            self._notify_degraded_mode()
            self._apply_correction_sans_feedback(delta_deg, motor_delay)

        except (KeyboardInterrupt, SystemExit):
            # Ne pas capturer - laisser remonter pour arrêt propre
            raise

        except Exception as e:
            # Erreur inattendue - logger ET remonter (ne pas masquer)
            self.logger.error(
                f"Erreur critique dans correction feedback: {e}",
                exc_info=True
            )
            raise

    def _notify_degraded_mode(self):
        """Notifie l'utilisateur que le système fonctionne en mode dégradé."""
        if not hasattr(self, '_degraded_mode_notified'):
            self._degraded_mode_notified = False

        if not self._degraded_mode_notified:
            self.logger.warning(
                "Mode dégradé: correction sans feedback encodeur"
            )
            self._degraded_mode_notified = True

    def _calculer_cibles(self, delta_deg: float) -> tuple:
        """Calcule les positions cibles logique et encodeur."""
        position_cible_logique = (self.position_relative + delta_deg) % 360
        angle_cible_encodeur = (position_cible_logique - self.encoder_offset) % 360
        return position_cible_logique, angle_cible_encodeur

    def _executer_rotation_feedback(self, angle_cible: float,
                                     motor_delay: float,
                                     allow_large_movement: bool = False) -> tuple:
        """
        Exécute la rotation avec feedback et mesure la durée.

        Args:
            angle_cible: Angle cible absolu (0-360°)
            motor_delay: Délai moteur (secondes/pas)
            allow_large_movement: Si True, désactive la protection 20° du FeedbackController.
                                  Nécessaire pour les grands déplacements (traversée méridien).
        """
        start_time = time.time()
        result = self.moteur.rotation_avec_feedback(
            angle_cible=angle_cible,
            vitesse=motor_delay,
            tolerance=0.5,
            max_iterations=10,
            allow_large_movement=allow_large_movement
        )
        duration = time.time() - start_time
        return result, duration

    def _finaliser_correction(self, delta_deg: float, position_cible: float):
        """Met à jour la position et les statistiques."""
        self.position_relative = position_cible
        self.total_corrections += 1
        self.total_movement += abs(delta_deg)

    def _traiter_resultat_feedback(self, result: dict, duration: float):
        """
        Traite le résultat de la correction feedback.

        LOGIQUE AMÉLIORÉE (v4.6):
        - Succès complet → réinitialise le compteur d'échecs
        - Timeout MAIS erreur acceptable (< 2°) → avertissement, PAS un échec
          (évite l'arrêt automatique lors de grands déplacements post-méridien)
        - Échec réel (erreur > seuil) → incrémente le compteur
        """
        if result['success']:
            self._log_feedback_succes(result, duration)
        else:
            erreur_finale = abs(result.get('erreur_finale', 999))
            timeout_occurred = result.get('timeout', False)

            # Cas spécial: timeout mais erreur acceptable
            # La coupole a bien bougé, juste plus lentement que prévu
            if timeout_occurred and erreur_finale < self.ACCEPTABLE_ERROR_THRESHOLD:
                self._log_feedback_timeout_acceptable(result, duration)
                # NE PAS incrémenter failed_feedback_count
            else:
                self._log_feedback_echec(result, duration)
                if self._verifier_echecs_consecutifs():
                    return

        self._log_detail_iterations(result)

    def _log_feedback_succes(self, result: dict, duration: float):
        """Log une correction feedback réussie."""
        self.failed_feedback_count = 0
        self.logger.info(
            f"Correction feedback réussie: {result['position_initiale']:.1f}° -> "
            f"{result['position_finale']:.1f}° (erreur: {result['erreur_finale']:.2f}°, "
            f"AZCoupole: {result['position_cible']:.1f}°, "
            f"{result['iterations']}/10 iter, {duration:.1f}s)"
        )

    def _log_feedback_timeout_acceptable(self, result: dict, duration: float):
        """
        Log une correction avec timeout mais erreur acceptable.

        Ce cas se produit lors de grands déplacements (post-méridien)
        qui dépassent le timeout mais atteignent la cible.
        On NE réinitialise PAS le compteur d'échecs mais on NE l'incrémente PAS non plus.
        """
        self.logger.warning(
            f"Correction longue mais acceptable: "
            f"{result['position_initiale']:.1f}° -> {result['position_finale']:.1f}° "
            f"(erreur: {result['erreur_finale']:.2f}° < {self.ACCEPTABLE_ERROR_THRESHOLD}°, "
            f"AZCoupole: {result['position_cible']:.1f}°, "
            f"{result['iterations']}/10 iter, {duration:.1f}s, timeout OK)"
        )

    def _log_feedback_echec(self, result: dict, duration: float):
        """Log une correction feedback imprécise."""
        self.failed_feedback_count += 1
        self.logger.warning(
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
            self.logger.error(
                f"SUIVI ARRÊTÉ : {self.max_failed_feedback} corrections "
                f"consécutives ont échoué."
            )
            self.logger.error(
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

        self.logger.debug("  Détail corrections:")
        for corr in result['corrections']:
            correction = corr.get('correction_demandee', corr.get('correction_commandee', 0))
            erreur_avant = corr.get('erreur_avant', corr.get('erreur', 0))
            erreur_apres = corr.get('erreur_apres', 0)
            self.logger.debug(
                f"    Iter {corr['iteration']}: {correction:+.2f}° "
                f"(erreur avant: {erreur_avant:+.2f}°, après: {erreur_apres:+.2f}°)"
            )

    def _resync_encoder_offset(self, position_cible_logique: float):
        """
        Re-synchronise l'offset encodeur après un grand mouvement.

        Après un transit méridien, l'offset peut dériver si la rotation
        n'a pas atteint exactement la cible. La re-sync corrige cela.
        """
        try:
            from core.hardware.daemon_encoder_reader import get_daemon_reader
            real_position = get_daemon_reader().read_angle()
            old_offset = self.encoder_offset
            self.encoder_offset = position_cible_logique - real_position
            self.logger.info(
                f"Re-sync encodeur post-méridien: "
                f"offset {old_offset:.1f}° → {self.encoder_offset:.1f}° "
                f"(encodeur={real_position:.1f}°, logique={position_cible_logique:.1f}°)"
            )
        except Exception as e:
            self.logger.debug(f"Re-sync encodeur non critique: {e}")

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
        self.logger.debug(
            f"Déplacement (sans feedback): {steps} pas à {motor_delay}s/pas "
            f"(facteur: {self.steps_correction_factor:.4f}, "
            f"vitesse: {1 / motor_delay:.0f} pas/s)"
            f"DEBUG: steps_per_dome_revolution = {self.moteur.steps_per_dome_revolution}"
        )

        # Appliquer la rotation
        deg_per_step = 360.0 / self.moteur.steps_per_dome_revolution
        angle = steps * deg_per_step * direction
        self.moteur.rotation(angle, vitesse=motor_delay)

        # Mettre à jour la position relative (normalisée dans [0, 360[)
        self.position_relative = (self.position_relative + delta_deg) % 360

        # Statistiques
        self.total_corrections += 1
        self.total_movement += abs(delta_deg)
