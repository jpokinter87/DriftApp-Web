"""
MODULE DE SUIVI ADAPTATIF - Gestion automatique des zones critiques.

Ce module permet d'adapter automatiquement :
1. La fréquence de vérification (jusqu'à 15s ou mode continu)
2. La vitesse du moteur (délai entre pas)
3. La vérification du chemin le plus court

VERSION 2.2 - Système adaptatif simplifié (3 modes)
- NORMAL: Conditions standard
- CRITICAL: Altitude >= 68° OU mouvement critique
- CONTINUOUS: Mouvement extrême OU (altitude >= 75° ET mouvement significatif)
              AUSSI utilisé pour les GOTO (vitesse max fluide)

CHANGEMENT v2.2: FAST_TRACK supprimé (redondant avec CONTINUOUS après calibration)
"""

from dataclasses import dataclass
from enum import Enum
from typing import Tuple, Dict
import logging


class TrackingMode(Enum):
    """Modes de suivi selon la zone du ciel."""
    NORMAL = "normal"           # Zone normale
    CRITICAL = "critical"       # Zone critique
    CONTINUOUS = "continuous"   # Correction continue + GOTO


@dataclass
class TrackingParameters:
    """Paramètres de suivi adaptatifs."""
    mode: TrackingMode
    check_interval: int         # Secondes entre vérifications
    correction_threshold: float # Seuil de correction (degrés)
    motor_delay: float         # Délai entre pas du moteur (secondes)
    description: str           # Description du mode


class AdaptiveTrackingManager:
    """
    Gestionnaire de suivi adaptatif.
    
    Adapte automatiquement les paramètres de suivi selon :
    - L'altitude de l'objet
    - L'azimut de l'objet
    - La vitesse de déplacement requise
    - L'historique des corrections
    """


    def __init__(self, base_interval: int = 60, base_threshold: float = 0.5, adaptive_config=None):
        """
        Args:
            base_interval: Intervalle de base (secondes)
            base_threshold: Seuil de correction de base (degrés)
            adaptive_config: Configuration adaptive depuis config.json
        """
        self.base_interval = base_interval
        self.base_threshold = base_threshold
        self.logger = logging.getLogger(__name__)

        # Charger depuis config ou valeurs par défaut
        if adaptive_config:
            self.ALTITUDE_CRITICAL = adaptive_config.altitudes.critical
            self.ALTITUDE_ZENITH = adaptive_config.altitudes.zenith

            self.MOVEMENT_CRITICAL = adaptive_config.movements.critical
            self.MOVEMENT_EXTREME = adaptive_config.movements.extreme

            # Seuil minimum de mouvement pour déclencher CONTINUOUS en haute altitude
            # Si le mouvement est inférieur à ce seuil, on reste en CRITICAL même proche du zénith
            self.MOVEMENT_MIN_FOR_CONTINUOUS = getattr(
                adaptive_config.movements, 'min_for_continuous', 1.0
            )

            self.CRITICAL_ZONE_1 = {
                'alt_min': adaptive_config.critical_zones[0].alt_min,
                'alt_max': adaptive_config.critical_zones[0].alt_max,
                'az_min': adaptive_config.critical_zones[0].az_min,
                'az_max': adaptive_config.critical_zones[0].az_max,
                'name': adaptive_config.critical_zones[0].name,
                'enabled': adaptive_config.critical_zones[0].enabled
            } if adaptive_config.critical_zones else None

            # Stocker config pour accès aux modes
            self.adaptive_config = adaptive_config
        else:
            # Valeurs par défaut
            self.ALTITUDE_CRITICAL = 68.0
            self.ALTITUDE_ZENITH = 75.0
            self.MOVEMENT_CRITICAL = 30.0
            self.MOVEMENT_EXTREME = 50.0
            self.MOVEMENT_MIN_FOR_CONTINUOUS = 1.0  # Seuil par défaut
            self.CRITICAL_ZONE_1 = None
            self.adaptive_config = None

        # Historique
        self.correction_history = []
        self.last_movement_speed = 0.0
        self.current_mode = TrackingMode.NORMAL
        self.current_params = self._get_normal_params()

    def _get_normal_params(self) -> TrackingParameters:
        if self.adaptive_config:
            mode = self.adaptive_config.modes.get('normal')
            return TrackingParameters(
                mode=TrackingMode.NORMAL,
                check_interval=mode.interval_sec,
                correction_threshold=mode.threshold_deg,
                motor_delay=mode.motor_delay,
                description="Zone normale - Suivi standard"
            )
        return TrackingParameters(
            mode=TrackingMode.NORMAL,
            check_interval=self.base_interval,
            correction_threshold=self.base_threshold,
            motor_delay=0.002,
            description="Zone normale - Suivi standard"
        )

    def _get_critical_params(self) -> TrackingParameters:
        if self.adaptive_config:
            mode = self.adaptive_config.modes.get('critical')
            return TrackingParameters(
                mode=TrackingMode.CRITICAL,
                check_interval=mode.interval_sec,
                correction_threshold=mode.threshold_deg,
                motor_delay=mode.motor_delay,
                description="Zone critique - Suivi rapproché"
            )
        return TrackingParameters(
            mode=TrackingMode.CRITICAL,
            check_interval=15,
            correction_threshold=self.base_threshold * 0.5,
            motor_delay=0.001,
            description="Zone critique - Suivi rapproché"
        )

    @staticmethod
    def _get_continuous_params_from_config(adaptive_config) -> TrackingParameters:
        if adaptive_config:
            mode = adaptive_config.modes.get('continuous')
            return TrackingParameters(
                mode=TrackingMode.CONTINUOUS,
                check_interval=mode.interval_sec,
                correction_threshold=mode.threshold_deg,
                motor_delay=mode.motor_delay,
                description="Mode continu - Corrections permanentes / GOTO"
            )
        return TrackingParameters(
            mode=TrackingMode.CONTINUOUS,
            check_interval=5,
            correction_threshold=0.1,
            motor_delay=0.00012,  # Ajusté 30/12/2025 sur retour terrain
            description="Mode continu - Corrections permanentes / GOTO"
        )

    def _get_continuous_params(self) -> TrackingParameters:
        return self._get_continuous_params_from_config(self.adaptive_config)

    def get_continuous_motor_delay(self) -> float:
        """
        Retourne le délai moteur pour le mode CONTINUOUS (vitesse max).

        Utilisé pour les GOTO initiaux et manuels pour garantir
        une vitesse rapide et fluide (~41°/min).

        Returns:
            Délai entre pas en secondes (ex: 0.00015)
        """
        return self._get_continuous_params().motor_delay

    # =========================================================================
    # PRÉDICATS D'ÉVALUATION
    # =========================================================================

    def _is_in_critical_zone(self, altitude: float, azimut: float) -> bool:
        """Vérifie si la position est dans une zone critique définie."""
        if not self.CRITICAL_ZONE_1:
            return False
        if not self.CRITICAL_ZONE_1.get('enabled', True):
            return False

        alt_ok = self.CRITICAL_ZONE_1['alt_min'] <= altitude <= self.CRITICAL_ZONE_1['alt_max']
        az_ok = self.CRITICAL_ZONE_1['az_min'] <= azimut <= self.CRITICAL_ZONE_1['az_max']
        return alt_ok and az_ok

    def _get_altitude_level(self, altitude: float) -> str:
        """Détermine le niveau d'altitude."""
        if altitude >= self.ALTITUDE_ZENITH:
            return "zenith"
        if altitude >= self.ALTITUDE_CRITICAL:
            return "critical"
        return "normal"

    def _get_movement_level(self, delta: float) -> str:
        """Détermine le niveau de mouvement."""
        abs_delta = abs(delta)
        if abs_delta >= self.MOVEMENT_EXTREME:
            return "extreme"
        if abs_delta >= self.MOVEMENT_CRITICAL:
            return "critical"
        return "normal"

    # =========================================================================
    # DÉCISION DU MODE
    # =========================================================================

    def _decide_mode(
        self,
        altitude_level: str,
        movement_level: str,
        in_critical_zone: bool,
        altitude: float,
        delta_required: float
    ) -> Tuple[TrackingMode, list]:
        """
        Décide du mode de suivi approprié.

        Priorité (du plus urgent au moins urgent):
        1. CONTINUOUS: mouvement extrême OU (zénith + mouvement significatif)
        2. CRITICAL: zone critique OU altitude critique OU mouvement critique
        3. NORMAL: conditions standard

        Returns:
            Tuple (mode, liste des raisons)
        """
        reasons = []

        # === CONTINUOUS ===
        # Mouvement extrême (> 50°)
        if movement_level == "extreme":
            reasons.append(f"Mouvement extrême ({abs(delta_required):.1f}°)")
            return TrackingMode.CONTINUOUS, reasons

        # Proche zénith ET mouvement significatif (> seuil minimum)
        if altitude_level == "zenith" and abs(delta_required) >= self.MOVEMENT_MIN_FOR_CONTINUOUS:
            reasons.append(f"Proche zénith ({altitude:.1f}°) + mouvement significatif ({abs(delta_required):.1f}°)")
            return TrackingMode.CONTINUOUS, reasons

        # === CRITICAL ===
        # Zone critique définie
        if in_critical_zone:
            reasons.append(f"Zone critique ({self.CRITICAL_ZONE_1['name']})")
            return TrackingMode.CRITICAL, reasons

        # Altitude critique OU proche zénith sans mouvement significatif
        if altitude_level in ["critical", "zenith"]:
            if altitude_level == "zenith":
                reasons.append(f"Proche zénith ({altitude:.1f}°) - mouvement faible, pas de CONTINUOUS")
            else:
                reasons.append(f"Altitude critique ({altitude:.1f}°)")
            return TrackingMode.CRITICAL, reasons

        # Mouvement critique
        if movement_level == "critical":
            reasons.append(f"Mouvement critique ({abs(delta_required):.1f}°)")
            return TrackingMode.CRITICAL, reasons

        # === NORMAL ===
        reasons.append("Conditions standard")
        return TrackingMode.NORMAL, reasons

    def _get_params_for_mode(self, mode: TrackingMode) -> TrackingParameters:
        """Retourne les paramètres pour un mode donné."""
        if mode == TrackingMode.CONTINUOUS:
            return self._get_continuous_params()
        elif mode == TrackingMode.CRITICAL:
            return self._get_critical_params()
        else:
            return self._get_normal_params()

    def _log_mode_change(
        self,
        old_mode: TrackingMode,
        new_mode: TrackingMode,
        reasons: list,
        params: TrackingParameters
    ):
        """Log le changement de mode."""
        reasons_str = ", ".join(reasons)
        self.logger.info(
            f"🔄 Changement de mode: {old_mode.value} → {new_mode.value}"
        )
        self.logger.info(f"   Raisons: {reasons_str}")
        self.logger.info(
            f"   Paramètres: intervalle={params.check_interval}s, "
            f"seuil={params.correction_threshold}°, "
            f"délai={params.motor_delay}s"
        )

    # =========================================================================
    # MÉTHODE PRINCIPALE
    # =========================================================================

    def evaluate_tracking_zone(
        self,
        altitude: float,
        azimut: float,
        delta_required: float
    ) -> TrackingParameters:
        """
        Évalue la zone de suivi et retourne les paramètres adaptés.

        Modes (priorité décroissante):
        - CONTINUOUS: Mouvement extrême OU (zénith + mouvement significatif)
        - CRITICAL: Zone critique OU altitude critique OU mouvement critique
        - NORMAL: Conditions standard

        Args:
            altitude: Altitude de l'objet (degrés)
            azimut: Azimut de l'objet (degrés)
            delta_required: Mouvement requis (degrés)

        Returns:
            Paramètres de suivi adaptés
        """
        # Évaluer les conditions
        in_critical_zone = self._is_in_critical_zone(altitude, azimut)
        altitude_level = self._get_altitude_level(altitude)
        movement_level = self._get_movement_level(delta_required)

        # Décider du mode
        mode, reasons = self._decide_mode(
            altitude_level, movement_level, in_critical_zone,
            altitude, delta_required
        )

        # Obtenir les paramètres
        params = self._get_params_for_mode(mode)

        # Logger si changement
        if mode != self.current_mode:
            self._log_mode_change(self.current_mode, mode, reasons, params)
            self.current_mode = mode
            self.current_params = params

        return params
    
    def verify_shortest_path(
        self,
        current_position: float,
        target_position: float
    ) -> Tuple[float, str]:
        """
        Vérifie et retourne le chemin le plus court.
        
        Args:
            current_position: Position actuelle (degrés)
            target_position: Position coupole (degrés)
        
        Returns:
            Tuple (delta, direction_description)
            - delta: Déplacement à effectuer (+ = horaire, - = anti-horaire)
            - direction_description: Description du chemin
        """
        # Normaliser les positions dans [0, 360[
        current = current_position % 360
        target = target_position % 360
        
        # Calculer les deux chemins possibles
        delta_direct = target - current
        
        # Chemin 1 : Direct
        if delta_direct >= 0:
            path1_angle = delta_direct
            path1_direction = "horaire"
        else:
            path1_angle = abs(delta_direct)
            path1_direction = "anti-horaire"
        
        # Chemin 2 : Par l'autre côté
        if delta_direct >= 0:
            path2_angle = 360 - delta_direct
            path2_direction = "anti-horaire"
        else:
            path2_angle = 360 - abs(delta_direct)
            path2_direction = "horaire"
        
        # Choisir le chemin le plus court
        if path1_angle <= path2_angle:
            chosen_angle = path1_angle if path1_direction == "horaire" else -path1_angle
            chosen_description = f"{path1_direction} ({path1_angle:.1f}°)"
            verification = f"Chemin le plus court: {chosen_description}"
        else:
            chosen_angle = path2_angle if path2_direction == "horaire" else -path2_angle
            chosen_description = f"{path2_direction} ({path2_angle:.1f}°)"
            verification = f"Chemin le plus court: {chosen_description}"
        
        # Logger la vérification pour les grands mouvements
        if abs(chosen_angle) > 30:
            self.logger.info(f"🔍 Vérification chemin:")
            self.logger.info(f"   Position actuelle: {current:.1f}°")
            self.logger.info(f"   Position coupole: {target:.1f}°")
            self.logger.info(f"   Chemin 1: {path1_direction} {path1_angle:.1f}°")
            self.logger.info(f"   Chemin 2: {path2_direction} {path2_angle:.1f}°")
            self.logger.info(f"   ✓ Choisi: {chosen_description}")
        
        return chosen_angle, verification
    
    def get_diagnostic_info(
        self,
        altitude: float,
        azimut: float,
        delta: float
    ) -> Dict:
        """
        Retourne des informations de diagnostic.
        
        Args:
            altitude: Altitude actuelle
            azimut: Azimut actuel
            delta: Delta de correction
        
        Returns:
            Dictionnaire d'informations
        """
        params = self.current_params
        
        # Déterminer les drapeaux d'alerte
        in_critical_zone = False
        if self.CRITICAL_ZONE_1:
            in_critical_zone = (
                self.CRITICAL_ZONE_1['alt_min'] <= altitude <= self.CRITICAL_ZONE_1['alt_max'] and
                self.CRITICAL_ZONE_1['az_min'] <= azimut <= self.CRITICAL_ZONE_1['az_max']
            )
        
        is_high_altitude = altitude >= self.ALTITUDE_CRITICAL
        is_large_movement = abs(delta) >= self.MOVEMENT_CRITICAL
        
        return {
            'mode': params.mode.value,
            'mode_description': params.description,
            'check_interval': params.check_interval,
            'correction_threshold': params.correction_threshold,
            'motor_delay': params.motor_delay,
            'in_critical_zone': in_critical_zone,
            'is_high_altitude': is_high_altitude,
            'is_large_movement': is_large_movement,
            'altitude_level': (
                "zenith" if altitude >= self.ALTITUDE_ZENITH else
                "critical" if altitude >= self.ALTITUDE_CRITICAL else
                "normal"
            ),
            'movement_level': (
                "extreme" if abs(delta) >= self.MOVEMENT_EXTREME else
                "critical" if abs(delta) >= self.MOVEMENT_CRITICAL else
                "normal"
            )
        }


# === EXEMPLE D'UTILISATION ===

if __name__ == "__main__":
    import logging
    logging.basicConfig(level=logging.INFO)
    
    # Créer le gestionnaire
    manager = AdaptiveTrackingManager(base_interval=60, base_threshold=0.5)
    
    # Test des différentes zones
    test_cases = [
        (45.0, 120.0, 0.3, "Zone normale"),
        (60.0, 120.0, 0.5, "Altitude moyenne"),
        (69.0, 60.0, 2.0, "Altitude critique (CRITICAL)"),
        (70.0, 60.0, 10.0, "Zone critique - mouvement modéré"),
        (70.5, 58.0, 31.0, "Zone critique - gros mouvement"),
        (71.0, 58.0, 70.0, "Zone critique - mouvement extrême (CONTINUOUS)"),
        (76.0, 180.0, 5.0, "Proche zénith (CONTINUOUS)"),
    ]
    
    print("\n" + "=" * 80)
    print("TEST DU SYSTÈME ADAPTATIF v2.2 (3 MODES - FAST_TRACK SUPPRIMÉ)")
    print("=" * 80)
    
    for alt, az, delta, description in test_cases:
        print(f"\n📍 Test: {description}")
        print(f"   Position: Alt={alt:.1f}° Az={az:.1f}° Delta={delta:.1f}°")
        
        params = manager.evaluate_tracking_zone(alt, az, delta)
        
        print(f"   → Mode: {params.mode.value}")
        print(f"   → Intervalle: {params.check_interval}s")
        print(f"   → Seuil: {params.correction_threshold:.2f}°")
        print(f"   → Délai moteur: {params.motor_delay}s")
    
    print("\n" + "=" * 80)
    print("TEST VÉRIFICATION CHEMIN LE PLUS COURT")
    print("=" * 80)
    
    path_tests = [
        (10.0, 350.0, "Traversée 0°"),
        (350.0, 10.0, "Traversée 0° inverse"),
        (45.0, 315.0, "Grand angle horaire"),
        (315.0, 45.0, "Grand angle anti-horaire"),
        (100.0, 280.0, "180° ambigü"),
    ]
    
    for current, target, description in path_tests:
        delta, verification = manager.verify_shortest_path(current, target)
        print(f"\n{description}:")
        print(f"   {current:.1f}° → {target:.1f}°")
        print(f"   {verification}")
        print(f"   Delta appliqué: {delta:+.1f}°")
