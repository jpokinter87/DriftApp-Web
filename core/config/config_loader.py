"""
Core Configuration Module - DriftApp

Architecture propre avec dataclasses pour remplacer le tuple de 12 valeurs.
Centralise tout le chargement de configuration en dehors de l'UI.

Usage:
    from core.config.config_loader import load_config
    
    config = load_config()
    print(config.site.latitude)
    print(config.motor.steps_per_revolution)
    print(config.adaptive.modes.critical.motor_delay)
"""

from __future__ import annotations

import json
import logging
from dataclasses import dataclass
from pathlib import Path
from typing import Dict, List, Optional

# ============================================================================
# CHEMINS PROJET (absolus, basés sur la racine du projet)
# ============================================================================

PROJECT_ROOT: Path = Path(__file__).parent.parent.parent.resolve()
DATA_DIR: Path = PROJECT_ROOT / "data"
CACHE_FILE: Path = DATA_DIR / "objets_cache.json"


def get_version() -> str:
    """Lit la version depuis pyproject.toml."""
    try:
        toml_path = PROJECT_ROOT / "pyproject.toml"
        for line in toml_path.read_text().splitlines():
            if line.startswith("version"):
                return line.split('"')[1]
    except Exception:
        pass
    return "unknown"


# ============================================================================
# DATACLASSES POUR LA CONFIGURATION
# ============================================================================

@dataclass
class SiteConfig:
    """Configuration du site d'observation."""
    latitude: float
    longitude: float
    altitude: float
    nom: str
    fuseau: str
    tz_offset: int
    
    def __str__(self) -> str:
        return (f"{self.nom} (lat={self.latitude}°, lon={self.longitude}°, "
                f"alt={self.altitude}m, TZ={self.fuseau})")


@dataclass
class GPIOPins:
    """Configuration des pins GPIO."""
    dir: int
    step: int


@dataclass
class MotorConfig:
    """Configuration du moteur pas-à-pas."""
    gpio_pins: GPIOPins
    steps_per_revolution: int
    microsteps: int
    gear_ratio: float
    steps_correction_factor: float
    motor_delay_base: float
    motor_delay_min: float
    motor_delay_max: float
    max_speed_steps_per_sec: int
    acceleration_steps_per_sec2: int
    
    @property
    def steps_per_dome_revolution(self) -> int:
        """Calcule le nombre total de pas pour un tour complet de coupole."""
        return int(
            self.steps_per_revolution *
            self.microsteps *
            self.gear_ratio *
            self.steps_correction_factor
        )
    
    def __str__(self) -> str:
        return (f"Motor(steps/rev={self.steps_per_revolution}, "
                f"MS={self.microsteps}, GR={self.gear_ratio}, "
                f"correction={self.steps_correction_factor:.4f}, "
                f"total={self.steps_per_dome_revolution} steps/360°)")


@dataclass
class TrackingConfig:
    """Configuration du suivi de base (méthode abaque uniquement)."""
    seuil_correction_deg: float
    intervalle_verification_sec: int
    abaque_file: str

    @property
    def abaque_path(self) -> Path:
        """Retourne le Path absolu du fichier abaque."""
        return Path(self.abaque_file)


@dataclass
class TrackingModeParams:
    """Paramètres d'un mode de suivi."""
    interval_sec: int
    threshold_deg: float
    motor_delay: float
    
    def calculate_speed(self, steps_per_dome_revolution: int) -> float:
        """
        Calcule la vitesse en °/min pour ce mode.
        
        Args:
            steps_per_dome_revolution: Nombre de pas pour 360°
            
        Returns:
            Vitesse en degrés par minute
        """
        if self.motor_delay <= 0:
            return 0.0
        steps_per_degree = steps_per_dome_revolution / 360.0
        degrees_per_second = 1.0 / (self.motor_delay * steps_per_degree)
        return degrees_per_second * 60.0


@dataclass
class AltitudeThresholds:
    """Seuils d'altitude pour les modes adaptatifs (3 modes)."""
    critical: float
    zenith: float


@dataclass
class MovementThresholds:
    """Seuils de mouvement pour les modes adaptatifs (3 modes)."""
    critical: float
    extreme: float


@dataclass
class CriticalZone:
    """Définition d'une zone critique du ciel."""
    name: str
    alt_min: float
    alt_max: float
    az_min: float
    az_max: float
    enabled: bool


@dataclass
class AdaptiveConfig:
    """Configuration du système adaptatif."""
    altitudes: AltitudeThresholds
    movements: MovementThresholds
    modes: Dict[str, TrackingModeParams]
    critical_zones: List[CriticalZone]
    
    def get_mode(self, mode_name: str) -> Optional[TrackingModeParams]:
        """Récupère les paramètres d'un mode."""
        return self.modes.get(mode_name)


@dataclass
class EncoderSPIConfig:
    """Configuration SPI de l'encodeur."""
    bus: int
    device: int
    speed_hz: int
    mode: int


@dataclass
class EncoderMecaniqueConfig:
    """Configuration mécanique de l'encodeur."""
    wheel_diameter_mm: float
    ring_diameter_mm: float
    counts_per_rev: int


@dataclass
class EncoderConfig:
    """Configuration de l'encodeur magnétique."""
    enabled: bool
    spi: EncoderSPIConfig
    mecanique: EncoderMecaniqueConfig
    calibration_factor: float


@dataclass
class DriftAppConfig:
    """
    Configuration complète de DriftApp.

    Usage:
        config = load_config()
        moteur = MoteurCoupole(config.motor)
        tracker = Tracker(config.site, config.tracking, config.adaptive)
    """
    site: SiteConfig
    motor: MotorConfig
    tracking: TrackingConfig
    adaptive: AdaptiveConfig
    encoder: EncoderConfig
    simulation: bool

    def __str__(self) -> str:
        return (
            f"DriftAppConfig(\n"
            f"  Site: {self.site}\n"
            f"  Motor: {self.motor}\n"
            f"  Adaptive: {len(self.adaptive.modes)} modes\n"
            f"  Encoder: {'ON' if self.encoder.enabled else 'OFF'}\n"
            f"  Simulation: {self.simulation}\n"
            f")"
        )
    
    @property
    def is_production(self) -> bool:
        """True si mode production (pas simulation)."""
        return not self.simulation


# ============================================================================
# CHARGEMENT DE LA CONFIGURATION
# ============================================================================

class ConfigLoader:
    """Chargeur de configuration modulaire."""

    def __init__(self, config_path: Path = DATA_DIR / "config.json"):
        self.logger = logging.getLogger("config_loader")
        self.config_path = config_path
        self.cfg: dict = {}

    def load(self) -> DriftAppConfig:
        """Charge et retourne la configuration complète."""
        self._load_json()
        config = self._build_config()
        self._log_summary(config)
        return config

    def _load_json(self):
        """Charge le fichier JSON."""
        if not self.config_path.exists():
            raise FileNotFoundError(
                f"Fichier de configuration introuvable : {self.config_path}\n"
                f"Créez-le à partir de config_TEMPLATE.json"
            )
        self.logger.info(f"Chargement configuration depuis {self.config_path}")
        with open(self.config_path, "r", encoding="utf-8") as f:
            self.cfg = json.load(f)

    def _build_config(self) -> DriftAppConfig:
        """Construit l'objet de configuration."""
        return DriftAppConfig(
            site=self._parse_site(),
            motor=self._parse_motor(),
            tracking=self._parse_tracking(),
            adaptive=self._parse_adaptive(),
            encoder=self._parse_encoder(),
            simulation=bool(self.cfg.get("simulation", False))
        )

    # =========================================================================
    # PARSERS DE SECTIONS
    # =========================================================================

    def _parse_site(self) -> SiteConfig:
        """Parse la section site."""
        c = self.cfg.get("site", {})
        return SiteConfig(
            latitude=float(c.get("latitude", 0.0)),
            longitude=float(c.get("longitude", 0.0)),
            altitude=float(c.get("altitude", 0.0)),
            nom=str(c.get("nom", "Observatoire")),
            fuseau=str(c.get("fuseau", "UTC")),
            tz_offset=int(c.get("tz_offset", 0))
        )

    def _parse_motor(self) -> MotorConfig:
        """Parse la section moteur."""
        c = self.cfg.get("moteur", {})
        gpio_cfg = c.get("gpio_pins", {})
        return MotorConfig(
            gpio_pins=GPIOPins(
                dir=int(gpio_cfg.get("dir", 17)),
                step=int(gpio_cfg.get("step", 18))
            ),
            steps_per_revolution=int(c.get("steps_per_revolution", 200)),
            microsteps=int(c.get("microsteps", 4)),
            gear_ratio=float(c.get("gear_ratio", 2230.0)),
            steps_correction_factor=float(c.get("steps_correction_factor", 1.0)),
            motor_delay_base=float(c.get("motor_delay_base", 0.002)),
            motor_delay_min=float(c.get("motor_delay_min", 0.00001)),
            motor_delay_max=float(c.get("motor_delay_max", 0.01)),
            max_speed_steps_per_sec=int(c.get("max_speed_steps_per_sec", 10000)),
            acceleration_steps_per_sec2=int(c.get("acceleration_steps_per_sec2", 5000))
        )

    def _parse_tracking(self) -> TrackingConfig:
        """Parse la section suivi."""
        c = self.cfg.get("suivi", {})
        return TrackingConfig(
            seuil_correction_deg=float(c.get("seuil_correction_deg", 0.5)),
            intervalle_verification_sec=int(c.get("intervalle_verification_sec", 60)),
            abaque_file=str(c.get("abaque_file", "data/Loi_coupole.xlsx"))
        )

    def _parse_adaptive(self) -> AdaptiveConfig:
        """Parse la section adaptive_tracking."""
        c = self.cfg.get("adaptive_tracking", {})
        return AdaptiveConfig(
            altitudes=self._parse_altitudes(c.get("altitudes", {})),
            movements=self._parse_movements(c.get("movements", {})),
            modes=self._parse_modes(c.get("modes", {})),
            critical_zones=self._parse_critical_zones(c.get("critical_zones", []))
        )

    def _parse_altitudes(self, c: dict) -> AltitudeThresholds:
        """Parse les seuils d'altitude."""
        return AltitudeThresholds(
            critical=float(c.get("critical", 68.0)),
            zenith=float(c.get("zenith", 75.0))
        )

    def _parse_movements(self, c: dict) -> MovementThresholds:
        """Parse les seuils de mouvement."""
        return MovementThresholds(
            critical=float(c.get("critical", 30.0)),
            extreme=float(c.get("extreme", 50.0))
        )

    def _parse_modes(self, modes_cfg: dict) -> Dict[str, TrackingModeParams]:
        """Parse les modes de tracking."""
        modes = {}
        for mode_name in ["normal", "critical", "continuous"]:
            c = modes_cfg.get(mode_name, {})
            modes[mode_name] = TrackingModeParams(
                interval_sec=int(c.get("interval_sec", 60)),
                threshold_deg=float(c.get("threshold_deg", 0.5)),
                motor_delay=float(c.get("motor_delay", 0.002))
            )
        return modes

    def _parse_critical_zones(self, zones_cfg: list) -> List[CriticalZone]:
        """Parse les zones critiques."""
        zones = []
        for c in zones_cfg:
            if isinstance(c, dict):
                zones.append(CriticalZone(
                    name=str(c.get("name", "Zone")),
                    alt_min=float(c.get("alt_min", 0.0)),
                    alt_max=float(c.get("alt_max", 90.0)),
                    az_min=float(c.get("az_min", 0.0)),
                    az_max=float(c.get("az_max", 360.0)),
                    enabled=bool(c.get("enabled", True))
                ))
        return zones

    def _parse_encoder(self) -> EncoderConfig:
        """Parse la section encodeur."""
        c = self.cfg.get("encodeur", {})
        spi = c.get("spi", {})
        meca = c.get("mecanique", {})

        return EncoderConfig(
            enabled=bool(c.get("enabled", False)),
            spi=EncoderSPIConfig(
                bus=int(spi.get("bus", 0)),
                device=int(spi.get("device", 0)),
                speed_hz=int(spi.get("speed_hz", 1000000)),
                mode=int(spi.get("mode", 0))
            ),
            mecanique=EncoderMecaniqueConfig(
                wheel_diameter_mm=float(meca.get("wheel_diameter_mm", 50.0)),
                ring_diameter_mm=float(meca.get("ring_diameter_mm", 2303.0)),
                counts_per_rev=int(meca.get("counts_per_rev", 1024))
            ),
            calibration_factor=float(c.get("calibration_factor", 0.031354))
        )

    def _log_summary(self, config: DriftAppConfig):
        """Log le résumé de la configuration."""
        self.logger.info("Configuration chargée avec succès")
        self.logger.info(f"  Site: {config.site.nom}")
        self.logger.info(f"  Moteur: {config.motor.steps_per_dome_revolution} steps/tour")
        self.logger.info(f"  Modes adaptatifs: {len(config.adaptive.modes)}")
        self.logger.info(f"  Encodeur: {'ON' if config.encoder.enabled else 'OFF'}")
        self.logger.info(f"  Mode: {'SIMULATION' if config.simulation else 'PRODUCTION'}")


def load_config(config_path: Path = DATA_DIR / "config.json") -> DriftAppConfig:
    """
    Charge la configuration complète depuis config.json.

    Args:
        config_path: Chemin vers le fichier config.json

    Returns:
        DriftAppConfig: Objet de configuration complet et structuré

    Raises:
        FileNotFoundError: Si config.json n'existe pas
        json.JSONDecodeError: Si le JSON est invalide

    Example:
        config = load_config()
        print(f"Site: {config.site.nom}")
    """
    return ConfigLoader(config_path).load()
