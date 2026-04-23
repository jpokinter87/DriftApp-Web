"""
Core Configuration Module - DriftApp

Architecture propre avec dataclasses pour remplacer le tuple de 12 valeurs.
Centralise tout le chargement de configuration en dehors de l'UI.

Usage:
    from core.config.config_loader import load_config

    config = load_config()
    print(config.site.latitude)
    print(config.motor.steps_per_revolution)
"""

from __future__ import annotations

import json
import logging
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from zoneinfo import ZoneInfo


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

    @property
    def tz_offset(self) -> int:
        """Offset UTC actuel, DST-aware (calculé dynamiquement)."""
        tz = ZoneInfo(self.fuseau)
        off = datetime.now(tz).utcoffset()
        return int(round(off.total_seconds() / 3600.0))

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
class ThresholdsConfig:
    """Seuils de mouvement centralisés (remplace les constantes magiques)."""
    feedback_min_deg: float      # Delta min pour feedback (en-dessous = rotation directe)
    large_movement_deg: float    # Au-delà = mode CONTINUOUS/FAST_TRACK
    feedback_protection_deg: float  # Protection contre mouvements anormaux
    default_tolerance_deg: float    # Tolérance par défaut pour feedback


@dataclass
class SerialConfig:
    """Configuration du port serie pour RP2040."""
    port: str
    baudrate: int
    timeout: float


@dataclass
class MotorDriverConfig:
    """Configuration du pilote moteur (GPIO direct ou RP2040 serie)."""
    type: str  # "rp2040"
    serial: SerialConfig


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
        moteur = MoteurRP2040(config.motor, serial_port)
    """
    site: SiteConfig
    motor: MotorConfig
    motor_driver: MotorDriverConfig
    tracking: TrackingConfig
    encoder: EncoderConfig
    thresholds: ThresholdsConfig
    simulation: bool

    def __str__(self) -> str:
        return (
            f"DriftAppConfig(\n"
            f"  Site: {self.site}\n"
            f"  Motor: {self.motor}\n"
            f"  Driver: {self.motor_driver.type}\n"
            f"  Encoder: {'ON' if self.encoder.enabled else 'OFF'}\n"
            f"  Simulation: {self.simulation}\n"
            f")"
        )
    
    @property
    def is_production(self) -> bool:
        """True si mode production (pas simulation)."""
        return not self.simulation
    
    def to_dict(self) -> dict:
        """Convertit la config en dictionnaire (pour sauvegarde JSON)."""
        from dataclasses import asdict
        return asdict(self)


# ============================================================================
# CHARGEMENT DE LA CONFIGURATION
# ============================================================================

class ConfigLoader:
    """Chargeur de configuration modulaire."""

    def __init__(self, config_path: Path = Path(__file__).resolve().parent.parent.parent / "data" / "config.json"):
        self.logger = logging.getLogger(__name__)
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
            motor_driver=self._parse_motor_driver(),
            tracking=self._parse_tracking(),
            encoder=self._parse_encoder(),
            thresholds=self._parse_thresholds(),
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
            fuseau=str(c.get("fuseau", "Europe/Paris")),
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

    def _parse_motor_driver(self) -> MotorDriverConfig:
        """Parse la section motor_driver."""
        c = self.cfg.get("motor_driver", {})
        serial_cfg = c.get("serial", {})
        return MotorDriverConfig(
            type=str(c.get("type", "rp2040")).lower(),
            serial=SerialConfig(
                port=str(serial_cfg.get("port", "/dev/ttyACM0")),
                baudrate=int(serial_cfg.get("baudrate", 115200)),
                timeout=float(serial_cfg.get("timeout", 2.0)),
            ),
        )

    def _parse_tracking(self) -> TrackingConfig:
        """Parse la section suivi."""
        c = self.cfg.get("suivi", {})
        return TrackingConfig(
            seuil_correction_deg=float(c.get("seuil_correction_deg", 0.5)),
            intervalle_verification_sec=int(c.get("intervalle_verification_sec", 60)),
            abaque_file=str(c.get("abaque_file", "data/Loi_coupole.xlsx"))
        )

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

    def _parse_thresholds(self) -> ThresholdsConfig:
        """Parse la section thresholds (seuils de mouvement centralisés)."""
        c = self.cfg.get("thresholds", {})
        return ThresholdsConfig(
            feedback_min_deg=float(c.get("feedback_min_deg", 3.0)),
            large_movement_deg=float(c.get("large_movement_deg", 30.0)),
            feedback_protection_deg=float(c.get("feedback_protection_deg", 20.0)),
            default_tolerance_deg=float(c.get("default_tolerance_deg", 0.5))
        )

    def _log_summary(self, config: DriftAppConfig):
        """Log le résumé de la configuration."""
        self.logger.info("Configuration chargée avec succès")
        self.logger.info(f"  Site: {config.site.nom}")
        self.logger.info(f"  Moteur: {config.motor.steps_per_dome_revolution} steps/tour")
        self.logger.info(f"  Encodeur: {'ON' if config.encoder.enabled else 'OFF'}")
        self.logger.info(f"  Driver: {config.motor_driver.type}")
        self.logger.info(f"  Mode: {'SIMULATION' if config.simulation else 'PRODUCTION'}")


def load_config(config_path: Path = Path(__file__).resolve().parent.parent.parent / "data" / "config.json") -> DriftAppConfig:
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


