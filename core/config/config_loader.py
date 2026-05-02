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
from dataclasses import dataclass, field
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
class MeridianAnticipationConfig:
    """Configuration de l'anticipation méridien (v5.9).

    Activé par défaut depuis v5.11.2 : retour terrain NGC 3690 (26-27/04) +
    re-scan glissant 1h (v5.11.1) → couverture sessions longues, gains
    théoriques −47% lag max au transit. Mettre `enabled=false` dans
    `data/config.json` pour repasser au comportement v5.10 strict.
    """
    enabled: bool = True


@dataclass
class PowerSwitchConfig:
    """Configuration du switch d'alimentation cimier (Shelly 220V).

    type:
      - "shelly_gen2"  → API moderne RPC `/rpc/Switch.Set?id=<id>&on=...`
      - "shelly_gen1"  → API legacy `/relay/<id>?turn=on|off`
      - "noop"         → no-op pour dev/tests sans hardware

    IP réelle uniquement dans `data/config.json` (terrain) — code Python neutre.
    """
    type: str = "noop"
    host: str = ""
    switch_id: int = 0


@dataclass
class WeatherProviderConfig:
    """Configuration du provider météo cimier (v6.0 Phase 2).

    Phase 2 ne livre que `type="noop"` (interface logique, pas de capteur).
    Les types réels (ex. `"pico_w_sensor"`) arriveront avec un milestone
    capteurs ultérieur (v6.4+). Aucun seuil dans la config tant qu'aucun
    capteur réel n'existe — le contrat figure dans `core.hardware.weather_provider`.
    """
    type: str = "noop"


@dataclass
class CimierAutomationConfig:
    """Configuration scheduler astropy cimier (v6.0 Phase 3).

    Opt-in (`enabled=False` par défaut). Quand actif, `cimier_service` polle
    toutes les `scheduler_interval_seconds` (60 s par défaut) pour déclencher
    automatiquement l'ouverture au crépuscule (sun_alt = `opening_sun_altitude_deg`
    descendant) et la fermeture à l'aube (~`closing_advance_minutes` +
    `clock_safety_margin_minutes` avant `closing_target_sun_altitude_deg` montant).

    `deparking_nudge_deg` : petit déplacement post-ouverture pour faire passer
    la couronne sur le microswitch de calibration à 45° (référence absolue
    encodeur EMS22A).

    `parking_target_azimuth_deg` : cible GOTO en fin de session (parallèle à
    la fermeture cimier).

    `retrigger_cooldown_hours` : idempotence intra-jour. Au reboot, l'état est
    perdu (mémoire seulement) → re-trigger si les conditions sont toujours
    remplies (état désiré, pas event-driven).
    """
    enabled: bool = False
    opening_sun_altitude_deg: float = -12.0
    closing_target_sun_altitude_deg: float = -6.0
    closing_advance_minutes: int = 10
    clock_safety_margin_minutes: int = 5
    parking_target_azimuth_deg: float = 45.0
    parking_timeout_minutes: int = 5
    deparking_nudge_deg: float = 1.0
    scheduler_interval_seconds: int = 60
    retrigger_cooldown_hours: int = 12


@dataclass
class CimierConfig:
    """Configuration du cimier motorisé (v6.0 Phase 1).

    Le service `cimier_service` orchestre un cycle complet (cascade Shelly
    220V/12V → polling Pico W ready → re-push invert si non-défaut → /open
    ou /close → polling final → turn_off → anti-bounce). IPs réelles
    uniquement dans `data/config.json` (terrain) — code Python neutre.

    Phase 2 ajoute `weather_provider` : interface logique no-op par défaut,
    consommée pour log structuré au démarrage de chaque cycle (pas de
    blocage runtime — Phase 3 décidera).

    Phase 3 ajoute `automation` : scheduler astropy opt-in qui déclenche
    automatiquement open/close selon les éphémérides solaires.
    """
    enabled: bool = False
    host: str = ""
    port: int = 80
    invert_direction: bool = False
    cycle_timeout_s: float = 90.0
    boot_poll_timeout_s: float = 30.0
    post_off_quiet_s: float = 10.0
    power_switch: PowerSwitchConfig = field(default_factory=PowerSwitchConfig)
    weather_provider: WeatherProviderConfig = field(default_factory=WeatherProviderConfig)
    automation: CimierAutomationConfig = field(default_factory=CimierAutomationConfig)


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
    meridian_anticipation: MeridianAnticipationConfig = field(
        default_factory=MeridianAnticipationConfig
    )
    cimier: CimierConfig = field(default_factory=CimierConfig)

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
            simulation=bool(self.cfg.get("simulation", False)),
            meridian_anticipation=self._parse_meridian_anticipation(),
            cimier=self._parse_cimier(),
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

    def _parse_meridian_anticipation(self) -> MeridianAnticipationConfig:
        """Parse la section meridian_anticipation (v5.9, activé par défaut depuis v5.11.2)."""
        c = self.cfg.get("meridian_anticipation", {})
        return MeridianAnticipationConfig(enabled=bool(c.get("enabled", True)))

    def _parse_cimier(self) -> CimierConfig:
        """Parse la section cimier (v6.0 Phase 1, opt-in : enabled=False par défaut)."""
        c = self.cfg.get("cimier", {})
        defaults = CimierConfig()
        ps_defaults = PowerSwitchConfig()
        wp_defaults = WeatherProviderConfig()
        au_defaults = CimierAutomationConfig()
        ps = c.get("power_switch", {}) if isinstance(c, dict) else {}
        wp = c.get("weather_provider", {}) if isinstance(c, dict) else {}
        au = c.get("automation", {}) if isinstance(c, dict) else {}
        return CimierConfig(
            enabled=bool(c.get("enabled", defaults.enabled)),
            host=str(c.get("host", defaults.host)),
            port=int(c.get("port", defaults.port)),
            invert_direction=bool(c.get("invert_direction", defaults.invert_direction)),
            cycle_timeout_s=float(c.get("cycle_timeout_s", defaults.cycle_timeout_s)),
            boot_poll_timeout_s=float(c.get("boot_poll_timeout_s", defaults.boot_poll_timeout_s)),
            post_off_quiet_s=float(c.get("post_off_quiet_s", defaults.post_off_quiet_s)),
            power_switch=PowerSwitchConfig(
                type=str(ps.get("type", ps_defaults.type)),
                host=str(ps.get("host", ps_defaults.host)),
                switch_id=int(ps.get("switch_id", ps_defaults.switch_id)),
            ),
            weather_provider=WeatherProviderConfig(
                type=str(wp.get("type", wp_defaults.type)),
            ),
            automation=CimierAutomationConfig(
                enabled=bool(au.get("enabled", au_defaults.enabled)),
                opening_sun_altitude_deg=float(au.get("opening_sun_altitude_deg", au_defaults.opening_sun_altitude_deg)),
                closing_target_sun_altitude_deg=float(au.get("closing_target_sun_altitude_deg", au_defaults.closing_target_sun_altitude_deg)),
                closing_advance_minutes=int(au.get("closing_advance_minutes", au_defaults.closing_advance_minutes)),
                clock_safety_margin_minutes=int(au.get("clock_safety_margin_minutes", au_defaults.clock_safety_margin_minutes)),
                parking_target_azimuth_deg=float(au.get("parking_target_azimuth_deg", au_defaults.parking_target_azimuth_deg)),
                parking_timeout_minutes=int(au.get("parking_timeout_minutes", au_defaults.parking_timeout_minutes)),
                deparking_nudge_deg=float(au.get("deparking_nudge_deg", au_defaults.deparking_nudge_deg)),
                scheduler_interval_seconds=int(au.get("scheduler_interval_seconds", au_defaults.scheduler_interval_seconds)),
                retrigger_cooldown_hours=int(au.get("retrigger_cooldown_hours", au_defaults.retrigger_cooldown_hours)),
            ),
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


