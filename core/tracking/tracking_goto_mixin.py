"""
Mixin pour la logique GOTO initial du suivi.

Ce module contient les méthodes liées à:
- Vérification si un GOTO initial est nécessaire
- Exécution du GOTO initial vers la position cible
- Recherche d'objets dans le catalogue
- Mise à jour des coordonnées planétaires
- Synchronisation de l'encodeur

Date: Décembre 2025
Version: 4.5
"""

from datetime import datetime
from typing import Tuple

from core.hardware.daemon_encoder_reader import get_daemon_reader
from core.observatoire import PlanetaryEphemerides
from core.observatoire.catalogue import GestionnaireCatalogue


class TrackingGotoMixin:
    """
    Mixin pour la logique GOTO initial.

    Fournit les méthodes de vérification et d'exécution
    du GOTO initial lors du démarrage du suivi.
    """

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
            encoder_status = get_daemon_reader().read_status()
            if not encoder_status:
                self.logger.debug("Daemon encodeur non disponible")
                return False, 0.0

            is_calibrated = encoder_status.get('calibrated', False)
            if not is_calibrated:
                self.logger.info(
                    "Encodeur non calibré - Pas de GOTO initial "
                    "(passez par le switch pour activer le mode absolu)"
                )
                return False, 0.0

            # Lire la position réelle
            real_position = get_daemon_reader().read_angle()

            # Calculer le delta via le chemin le plus court
            delta, path_info = self.adaptive_manager.verify_shortest_path(
                real_position, position_cible
            )

            # Si le delta est significatif (> seuil de correction), GOTO nécessaire
            if abs(delta) > self.seuil:
                self.logger.info(
                    f"🔄 Encodeur calibré - Position réelle: {real_position:.1f}° | "
                    f"Position cible: {position_cible:.1f}° | Delta: {delta:+.1f}°"
                )
                # Notifier le callback avec les infos du GOTO avant exécution
                if self.goto_callback:
                    goto_info = {
                        'current_position': real_position,
                        'target_position': position_cible,
                        'delta': delta
                    }
                    self.goto_callback(goto_info)

                # Logger le GOTO pour le rapport de session
                self._log_goto(real_position, position_cible, delta, 'initial')

                return True, delta

            self.logger.info(
                f"Position OK - Réelle: {real_position:.1f}° ≈ Cible: {position_cible:.1f}° "
                f"(delta={delta:+.2f}° < seuil={self.seuil}°)"
            )
            return False, 0.0

        except Exception as e:
            self.logger.debug(f"Daemon non accessible: {e}")
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
            encoder_status = get_daemon_reader().read_status()
            if encoder_status:
                is_calibrated = encoder_status.get('calibrated', False)
                if is_calibrated:
                    self.logger.info("Encodeur calibré - Mode absolu disponible")
                else:
                    self.logger.warning(
                        "Encodeur non calibré - Mode relatif. "
                        "Passez par le switch (45°) pour le mode absolu."
                    )

            real_position = get_daemon_reader().read_angle()
            self.encoder_offset = position_cible - real_position
            self.logger.info(
                f"SYNC: Coupole={position_cible:.1f}° | "
                f"Encodeur={real_position:.1f}° | Offset={self.encoder_offset:.1f}°"
            )
        except Exception as e:
            self.logger.warning(f"Encodeur: {e}")
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
            position_actuelle = get_daemon_reader().read_angle()

            self.logger.info(
                f"GOTO initial: {position_actuelle:.1f}° → {position_cible:.1f}° "
                f"(vitesse: {motor_delay}s/pas)"
            )

            # Utiliser rotation_avec_feedback si l'encodeur est disponible
            if self.encoder_available:
                # Calculer l'angle cible pour l'encodeur (sans offset car GOTO initial)
                # Pour le GOTO initial, on cible directement position_cible
                # allow_large_movement=True car le GOTO initial peut être > 180°
                result = self.moteur.rotation_avec_feedback(
                    angle_cible=position_cible,
                    vitesse=motor_delay,
                    tolerance=0.5,
                    max_iterations=10,
                    allow_large_movement=True  # IMPORTANT: Autorise grands déplacements
                )

                if result['success']:
                    self.logger.info(
                        f"GOTO initial réussi: {result['position_initiale']:.1f}° → "
                        f"{result['position_finale']:.1f}° "
                        f"(erreur: {result['erreur_finale']:.2f}°, {result['iterations']} iter)"
                    )
                else:
                    self.logger.warning(
                        f"GOTO initial imprécis: erreur finale = {result['erreur_finale']:.2f}°"
                    )

                # Mettre à jour l'offset encodeur après le GOTO
                try:
                    position_finale = get_daemon_reader().read_angle()
                    self.encoder_offset = position_cible - position_finale
                    self.logger.info(
                        f"Offset encodeur recalculé: {self.encoder_offset:.1f}°"
                    )
                except Exception as e:
                    self.logger.debug(f"Erreur recalcul offset encodeur (non critique): {e}")

            else:
                # Sans feedback, utiliser rotation simple
                delta, _ = self.adaptive_manager.verify_shortest_path(
                    position_actuelle, position_cible
                )
                self.moteur.rotation(delta, motor_delay)
                self.logger.info(f"GOTO initial (sans feedback): {delta:+.1f}°")

            # NE PAS modifier position_relative - elle est déjà correcte !
            # position_relative = position_cible (mise par _setup_initial_position)

        except Exception as e:
            self.logger.error(f"Erreur GOTO initial: {e}")
            # En cas d'erreur, position_relative reste à position_cible
            # ce qui est l'hypothèse de départ
