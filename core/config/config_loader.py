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
        return (
            f"{self.nom} (lat={self.latitude}°, lon={self.longitude}°, "
            f"alt={self.altitude}m, TZ={self.fuseau})"
        )


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
            self.steps_per_revolution
            * self.microsteps
            * self.gear_ratio
            * self.steps_correction_factor
        )

    def __str__(self) -> str:
        return (
            f"Motor(steps/rev={self.steps_per_revolution}, "
            f"MS={self.microsteps}, GR={self.gear_ratio}, "
            f"correction={self.steps_correction_factor:.4f}, "
            f"total={self.steps_per_dome_revolution} steps/360°)"
        )


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

    feedback_min_deg: float  # Delta min pour feedback (en-dessous = rotation directe)
    large_movement_deg: float  # Au-delà = mode CONTINUOUS/FAST_TRACK
    feedback_protection_deg: float  # Protection contre mouvements anormaux
    default_tolerance_deg: float  # Tolérance par défaut pour feedback


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
    """Configuration du switch d'alimentation cimier (Shelly 24V).

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
class MotorShellyConfig:
    """Configuration du Shelly pilotant le moteur cimier (pivot v6.x).

    Archi V3 : pilotage moteur via 2 Shelly Gen 1 (contact sec)
    distincts (1 relais chacun, contact sec) qui automatisent le circuit
    de commande manuel de Serge (interrupteur ON/OFF moteur + DPDT
    direction). Cf. `core/hardware/motor_shelly.py`.

    Champs :
      - ``host_motor``            : IP du Shelly MOTOR (ON/OFF moteur) ;
                                    vide → section inactive. IP réelle
                                    uniquement dans ``data/config.json``.
      - ``host_dir``              : IP du Shelly DIR (pilote le DPDT
                                    externe du sens moteur).
      - ``relay_motor``           : index relais du Shelly MOTOR (défaut 0,
                                    seul relais d'un Shelly 1).
      - ``relay_dir``             : index relais du Shelly DIR (défaut 0).
                                    Les 2 indices peuvent valoir 0 puisque
                                    les Shellys sont distincts.
      - ``open_dir_state``        : convention sens. True → relais DIR ON =
                                    ouverture cimier. False = inversé (cas
                                    Serge : ouvert = UP = ouverture).
      - ``motor_on_relay_state``  : convention moteur. False (défaut,
                                    convention validée terrain 17-18/06,
                                    oscillateur câblé NC : le moteur tourne
                                    quand le relais MOTOR est ouvert) →
                                    turn_on met le relais à OFF (turn=off).
                                    True (NO intuitive, non utilisée en V3) →
                                    turn_on met le relais à ON.
      - ``api``                   : "rpc" (Shelly Gen 2/3/Plus/Pro, défaut)
                                    ou "legacy" (Gen 1).
      - ``timer_safety_sec``      : filet hardware (Shelly toggle_after).
                                    Auto-OFF moteur après N secondes en cas
                                    de WiFi-drop. 0 = pas de timer.

    IPs réelles uniquement dans ``data/config.json`` (terrain) — code Python
    neutre.
    """

    host_motor: str = ""
    host_dir: str = ""
    relay_motor: int = 0
    relay_dir: int = 0
    open_dir_state: bool = True
    motor_on_relay_state: bool = False
    api: str = "rpc"
    timer_safety_sec: float = 90.0


@dataclass
class SwitchReaderConfig:
    """Configuration de la lecture des fins de course cimier (Shelly Uni+, V3).

    Archi V3 : les 2 microswitches Haut/Bas sont lus via les
    2 entrées du Shelly Uni+ (RPC Gen 2 ``Input.GetStatus``).

    type:
      - "shelly_uni" → lit via ``core.hardware.shelly_switch_reader.ShellySwitchReader``
      - "noop"       → reader inerte (dev/tests sans hardware)

    ``open_input_id`` / ``closed_input_id`` : index d'entrée Shelly Uni+ pour
    les microswitches HAUT et BAS. ``invert`` : True → butée atteinte = input
    False (contact ouvert : les switches sont NC, ils s'ouvrent à l'actionnement ;
    state=True = contact fermé = repos. Convention NC validée au banc).

    IP réelle uniquement dans ``data/config.json`` (terrain) — code Python neutre.
    """

    type: str = "noop"
    host: str = ""
    api: str = "rpc"
    open_input_id: int = 1
    closed_input_id: int = 0
    invert: bool = True
    timeout_s: float = 3.0


@dataclass
class WeatherProviderConfig:
    """Configuration du provider météo cimier (v6.0 Phase 2).

    Phase 2 ne livre que `type="noop"` (interface logique, pas de capteur).
    Les types réels (ex. `"pico_w_sensor"`) arriveront avec un milestone
    capteurs ultérieur (v6.4+). Aucun seuil dans la config tant qu'aucun
    capteur réel n'existe — le contrat figure dans `core.hardware.weather_provider`.
    """

    type: str = "noop"


VALID_AUTOMATION_MODES = ("manual", "semi", "full")


@dataclass
class CimierAutomationConfig:
    """Configuration scheduler astropy cimier (v6.0 Phase 3 + Phase 4).

    Trois niveaux d'automatisation (v6.0 Phase 4) :
      - `manual` : aucune automatisation cimier (équivalent v6.2 `enabled=False`).
      - `semi`   : démarrage manuel par l'utilisateur, fermeture auto en fin de
                   nuit. Le scheduler ne déclenche QUE l'événement CLOSE.
      - `full`   : ouverture auto au crépuscule + fermeture auto avant l'aube
                   (équivalent v6.2 `enabled=True`).

    Quand le mode est `semi` ou `full`, `cimier_service` polle toutes les
    `scheduler_interval_seconds` (60 s par défaut) pour évaluer les triggers.
    Ouverture (mode `full` uniquement) : `sun_alt <= opening_sun_altitude_deg`
    en descente. Fermeture (modes `semi` et `full`) : ~`closing_advance_minutes`
    + `clock_safety_margin_minutes` avant `closing_target_sun_altitude_deg` en
    montée.

    `deparking_nudge_deg` : petit déplacement post-ouverture pour faire passer
    la couronne sur le microswitch de calibration à 45° (référence absolue
    encodeur EMS22A).

    `parking_target_azimuth_deg` : cible GOTO en fin de session (parallèle à
    la fermeture cimier). Aussi consommé par l'endpoint manuel
    `POST /api/cimier/parking-session/`.

    `retrigger_cooldown_hours` : idempotence intra-jour. Au reboot, l'état est
    perdu (mémoire seulement) → re-trigger si les conditions sont toujours
    remplies (état désiré, pas event-driven).

    Rétro-compat (v6.2 → v6.3) : la clé legacy `enabled: bool` est lue par le
    parser si `mode` est absent (`enabled=true` → `mode="full"`,
    `enabled=false` ou absent → `mode="manual"`). Cf. `_parse_cimier()`.
    """

    mode: str = "manual"
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
    alim 24V → settle WiFi Shelly → set_direction → motor_on → poll butées
    ou /close → polling final → turn_off → anti-bounce). IPs réelles
    uniquement dans `data/config.json` (terrain) — code Python neutre.

    Phase 2 ajoute `weather_provider` : interface logique no-op par défaut,
    consommée pour log structuré au démarrage de chaque cycle (pas de
    blocage runtime — Phase 3 décidera).

    Phase 3 ajoute `automation` : scheduler astropy opt-in qui déclenche
    automatiquement open/close selon les éphémérides solaires.
    """

    enabled: bool = False
    cycle_timeout_s: float = 90.0
    boot_poll_timeout_s: float = 30.0  # legacy (boot Pico) — dette, non utilisé en V3
    post_off_quiet_s: float = 10.0
    shelly_settle_s: float = 2.0  # attente appairage WiFi Shelly MOT/UPDN (synoptique "à mesurer")
    dir_settle_s: float = (
        0.3  # attente commutation DPDT entre set_direction et turn_on (anti-course sens)
    )
    cycle_poll_interval_s: float = (
        0.5  # cadence lecture butées pendant un cycle (0.1 = debug 100ms)
    )
    verbose_logging: bool = False  # true → logs DEBUG par itération (debug à distance)
    switch_reader: SwitchReaderConfig = field(default_factory=SwitchReaderConfig)
    power_switch: PowerSwitchConfig = field(default_factory=PowerSwitchConfig)
    weather_provider: WeatherProviderConfig = field(default_factory=WeatherProviderConfig)
    automation: CimierAutomationConfig = field(default_factory=CimierAutomationConfig)
    motor_shelly: MotorShellyConfig = field(default_factory=MotorShellyConfig)

    def __post_init__(self) -> None:
        if self.cycle_timeout_s <= 0:
            raise ValueError(f"cimier.cycle_timeout_s doit être > 0, reçu {self.cycle_timeout_s}")


@dataclass(frozen=True)
class BootCalibrationConfig:
    """Configuration de la routine de calibration au boot motor_service (v6.6.0).

    Au démarrage du `motor_service` (production uniquement), une routine ramène
    la coupole sur le microswitch à 45° avant d'accepter des commandes. Elle
    effectue un sweep court autour de la position courante (`-fallback_sweep_deg`
    puis `+2×fallback_sweep_deg`). À 40°/min (single-speed) et avec
    `fallback_sweep_deg=7°`, les deux branches durent ≈ 10s puis ≈ 20s.
    `timeout_sec` borne la durée totale (mode dégradé après expiration).
    `poll_interval_sec` cadence le watcher qui poll `last_calibration_at`
    dans le payload IPC encodeur.
    """

    fallback_sweep_deg: float = 7.0
    timeout_sec: float = 180.0
    poll_interval_sec: float = 0.1


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
    boot_calibration: BootCalibrationConfig = field(default_factory=BootCalibrationConfig)

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

    def __init__(
        self,
        config_path: Path = Path(__file__).resolve().parent.parent.parent / "data" / "config.json",
    ):
        self.logger = logging.getLogger(__name__)
        self.config_path = config_path
        self.cfg: dict = {}

    def load(self) -> DriftAppConfig:
        """Charge et retourne la configuration complète."""
        self._ensure_ready()
        self._load_json()
        config = self._build_config()
        self._log_summary(config)
        return config

    def _ensure_ready(self) -> None:
        """Garantit un config.json valide/à jour avant lecture (chantier A).

        Le template/backup sont résolus côté config_resilience. Si le template
        n'existe pas (dev très ancien), on ne bloque pas la lecture classique.
        """
        try:
            from core.config.config_resilience import (
                DEFAULT_BACKUP_PATH,
                DEFAULT_TEMPLATE_PATH,
                ensure_config_ready,
            )

            ensure_config_ready(self.config_path, DEFAULT_TEMPLATE_PATH, DEFAULT_BACKUP_PATH)
        except Exception as exc:  # ne jamais empêcher le chargement à cause du filet
            self.logger.warning(f"ensure_config_ready a échoué (ignoré) : {exc}")

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
            boot_calibration=self._parse_boot_calibration(),
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
                dir=int(gpio_cfg.get("dir", 17)), step=int(gpio_cfg.get("step", 18))
            ),
            steps_per_revolution=int(c.get("steps_per_revolution", 200)),
            microsteps=int(c.get("microsteps", 4)),
            gear_ratio=float(c.get("gear_ratio", 2230.0)),
            steps_correction_factor=float(c.get("steps_correction_factor", 1.0)),
            motor_delay_base=float(c.get("motor_delay_base", 0.002)),
            motor_delay_min=float(c.get("motor_delay_min", 0.00001)),
            motor_delay_max=float(c.get("motor_delay_max", 0.01)),
            max_speed_steps_per_sec=int(c.get("max_speed_steps_per_sec", 10000)),
            acceleration_steps_per_sec2=int(c.get("acceleration_steps_per_sec2", 5000)),
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
            abaque_file=str(c.get("abaque_file", "data/Loi_coupole.xlsx")),
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
                mode=int(spi.get("mode", 0)),
            ),
            mecanique=EncoderMecaniqueConfig(
                wheel_diameter_mm=float(meca.get("wheel_diameter_mm", 50.0)),
                ring_diameter_mm=float(meca.get("ring_diameter_mm", 2303.0)),
                counts_per_rev=int(meca.get("counts_per_rev", 1024)),
            ),
            calibration_factor=float(c.get("calibration_factor", 0.031354)),
        )

    def _parse_thresholds(self) -> ThresholdsConfig:
        """Parse la section thresholds (seuils de mouvement centralisés)."""
        c = self.cfg.get("thresholds", {})
        return ThresholdsConfig(
            feedback_min_deg=float(c.get("feedback_min_deg", 3.0)),
            large_movement_deg=float(c.get("large_movement_deg", 30.0)),
            feedback_protection_deg=float(c.get("feedback_protection_deg", 20.0)),
            default_tolerance_deg=float(c.get("default_tolerance_deg", 0.5)),
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
        ms_defaults = MotorShellyConfig()
        ps = c.get("power_switch", {}) if isinstance(c, dict) else {}
        wp = c.get("weather_provider", {}) if isinstance(c, dict) else {}
        au = c.get("automation", {}) if isinstance(c, dict) else {}
        ms = c.get("motor_shelly", {}) if isinstance(c, dict) else {}
        if not isinstance(ms, dict):
            ms = {}
        sr = c.get("switch_reader", {}) if isinstance(c, dict) else {}
        if not isinstance(sr, dict):
            sr = {}
        sr_defaults = SwitchReaderConfig()
        return CimierConfig(
            enabled=bool(c.get("enabled", defaults.enabled)),
            cycle_timeout_s=float(c.get("cycle_timeout_s", defaults.cycle_timeout_s)),
            boot_poll_timeout_s=float(c.get("boot_poll_timeout_s", defaults.boot_poll_timeout_s)),
            post_off_quiet_s=float(c.get("post_off_quiet_s", defaults.post_off_quiet_s)),
            shelly_settle_s=float(c.get("shelly_settle_s", defaults.shelly_settle_s)),
            dir_settle_s=float(c.get("dir_settle_s", defaults.dir_settle_s)),
            cycle_poll_interval_s=float(
                c.get("cycle_poll_interval_s", defaults.cycle_poll_interval_s)
            ),
            verbose_logging=bool(c.get("verbose_logging", defaults.verbose_logging)),
            switch_reader=SwitchReaderConfig(
                type=str(sr.get("type", sr_defaults.type)),
                host=str(sr.get("host", sr_defaults.host)),
                api=str(sr.get("api", sr_defaults.api)),
                open_input_id=int(sr.get("open_input_id", sr_defaults.open_input_id)),
                closed_input_id=int(sr.get("closed_input_id", sr_defaults.closed_input_id)),
                invert=bool(sr.get("invert", sr_defaults.invert)),
                timeout_s=float(sr.get("timeout_s", sr_defaults.timeout_s)),
            ),
            power_switch=PowerSwitchConfig(
                type=str(ps.get("type", ps_defaults.type)),
                host=str(ps.get("host", ps_defaults.host)),
                switch_id=int(ps.get("switch_id", ps_defaults.switch_id)),
            ),
            weather_provider=WeatherProviderConfig(
                type=str(wp.get("type", wp_defaults.type)),
            ),
            automation=CimierAutomationConfig(
                mode=self._resolve_automation_mode(au, au_defaults.mode),
                opening_sun_altitude_deg=float(
                    au.get("opening_sun_altitude_deg", au_defaults.opening_sun_altitude_deg)
                ),
                closing_target_sun_altitude_deg=float(
                    au.get(
                        "closing_target_sun_altitude_deg",
                        au_defaults.closing_target_sun_altitude_deg,
                    )
                ),
                closing_advance_minutes=int(
                    au.get("closing_advance_minutes", au_defaults.closing_advance_minutes)
                ),
                clock_safety_margin_minutes=int(
                    au.get("clock_safety_margin_minutes", au_defaults.clock_safety_margin_minutes)
                ),
                parking_target_azimuth_deg=float(
                    au.get("parking_target_azimuth_deg", au_defaults.parking_target_azimuth_deg)
                ),
                parking_timeout_minutes=int(
                    au.get("parking_timeout_minutes", au_defaults.parking_timeout_minutes)
                ),
                deparking_nudge_deg=float(
                    au.get("deparking_nudge_deg", au_defaults.deparking_nudge_deg)
                ),
                scheduler_interval_seconds=int(
                    au.get("scheduler_interval_seconds", au_defaults.scheduler_interval_seconds)
                ),
                retrigger_cooldown_hours=int(
                    au.get("retrigger_cooldown_hours", au_defaults.retrigger_cooldown_hours)
                ),
            ),
            motor_shelly=self._build_motor_shelly_config(ms, ms_defaults),
        )

    def _build_motor_shelly_config(
        self, ms: dict, defaults: MotorShellyConfig
    ) -> MotorShellyConfig:
        """Construit MotorShellyConfig avec validation default-safe.

        Erreurs typées (api invalide, timer négatif, types non parsables) →
        warning + fallback sur defaults pour ne pas casser le boot du
        service à cause d'une config terrain mal saisie.

        Pas de validation `relay_motor != relay_dir` : les 2 Shellys ayant
        des hôtes distincts, les relais peuvent légitimement avoir le même
        index (cas Shelly 1 où l'unique relais est d'index 0).
        """
        try:
            host_motor = str(ms.get("host_motor", defaults.host_motor))
            host_dir = str(ms.get("host_dir", defaults.host_dir))
            relay_motor = int(ms.get("relay_motor", defaults.relay_motor))
            relay_dir = int(ms.get("relay_dir", defaults.relay_dir))
            open_dir_state = bool(ms.get("open_dir_state", defaults.open_dir_state))
            motor_on_relay_state = bool(
                ms.get("motor_on_relay_state", defaults.motor_on_relay_state)
            )
            api = str(ms.get("api", defaults.api))
            timer_safety_sec = float(ms.get("timer_safety_sec", defaults.timer_safety_sec))
        except (TypeError, ValueError):
            self.logger.warning(
                "motor_shelly config invalide (types non parsables) — utilisation des defaults"
            )
            return MotorShellyConfig()
        if api not in ("rpc", "legacy"):
            self.logger.warning("motor_shelly.api invalide (%s) — fallback sur 'rpc'", api)
            api = defaults.api
        if timer_safety_sec < 0:
            self.logger.warning(
                "motor_shelly.timer_safety_sec négatif (%s) — fallback sur default",
                timer_safety_sec,
            )
            timer_safety_sec = defaults.timer_safety_sec
        return MotorShellyConfig(
            host_motor=host_motor,
            host_dir=host_dir,
            relay_motor=relay_motor,
            relay_dir=relay_dir,
            open_dir_state=open_dir_state,
            motor_on_relay_state=motor_on_relay_state,
            api=api,
            timer_safety_sec=timer_safety_sec,
        )

    def _parse_boot_calibration(self) -> BootCalibrationConfig:
        """Parse la section boot_calibration (opt-in : section absente = defaults).

        Clés inconnues ignorées silencieusement (rétro-compat avec
        `overshoot_deg`/`persist_path` des configs terrain pré-v6.6).
        """
        section = self.cfg.get("boot_calibration", {})
        if not isinstance(section, dict):
            section = {}
        defaults = BootCalibrationConfig()
        try:
            fallback_sweep_deg = float(
                section.get("fallback_sweep_deg", defaults.fallback_sweep_deg)
            )
            timeout_sec = float(section.get("timeout_sec", defaults.timeout_sec))
            poll_interval_sec = float(section.get("poll_interval_sec", defaults.poll_interval_sec))
        except (TypeError, ValueError):
            self.logger.warning(
                "boot_calibration config invalide (types non numériques) — utilisation des defaults"
            )
            return BootCalibrationConfig()
        if fallback_sweep_deg <= 0 or timeout_sec <= 0 or poll_interval_sec <= 0:
            self.logger.warning(
                "boot_calibration config invalide (sweep=%s, timeout=%s, poll=%s) — "
                "utilisation des defaults",
                fallback_sweep_deg,
                timeout_sec,
                poll_interval_sec,
            )
            return BootCalibrationConfig()
        return BootCalibrationConfig(
            fallback_sweep_deg=fallback_sweep_deg,
            timeout_sec=timeout_sec,
            poll_interval_sec=poll_interval_sec,
        )

    def _resolve_automation_mode(self, au: dict, default_mode: str) -> str:
        """Résout `cimier.automation.mode` avec rétro-compat sur la clé legacy `enabled` (v6.0 Phase 4).

        Règles (testées par AC-1 du sub-plan v6.0-04-01) :
          - Si `mode` présent et valide (∈ VALID_AUTOMATION_MODES) → retourne `mode`.
          - Si `mode` présent ET `enabled` aussi → `mode` prime ; warning si incohérent
            (ex. `mode="manual"` avec `enabled=true`).
          - Si `mode` présent mais invalide (ex. "yolo") → warning + fallback `default_mode`
            (default-safe : "manual").
          - Si `mode` absent et `enabled` présent → `enabled=True` → "full",
            `enabled=False` → "manual".
          - Si `mode` ET `enabled` absents → `default_mode`.
        """
        mode = au.get("mode")
        legacy_enabled = au.get("enabled")
        if mode is not None:
            mode = str(mode)
            if mode not in VALID_AUTOMATION_MODES:
                self.logger.warning(
                    "cimier.automation.mode invalide '%s' — fallback sur '%s' "
                    "(valeurs valides : %s)",
                    mode,
                    default_mode,
                    list(VALID_AUTOMATION_MODES),
                )
                return default_mode
            if legacy_enabled is not None:
                expected_enabled = mode == "full"
                if bool(legacy_enabled) != expected_enabled:
                    self.logger.warning(
                        "cimier.automation : mode='%s' et enabled=%s incohérents — "
                        "mode prime sur enabled (la clé enabled est legacy v6.2)",
                        mode,
                        legacy_enabled,
                    )
            return mode
        # mode absent → rétro-compat sur enabled
        if legacy_enabled is not None:
            return "full" if bool(legacy_enabled) else "manual"
        return default_mode

    def _log_summary(self, config: DriftAppConfig):
        """Log le résumé de la configuration."""
        self.logger.info("Configuration chargée avec succès")
        self.logger.info(f"  Site: {config.site.nom}")
        self.logger.info(f"  Moteur: {config.motor.steps_per_dome_revolution} steps/tour")
        self.logger.info(f"  Encodeur: {'ON' if config.encoder.enabled else 'OFF'}")
        self.logger.info(f"  Driver: {config.motor_driver.type}")
        self.logger.info(f"  Mode: {'SIMULATION' if config.simulation else 'PRODUCTION'}")


def load_config(
    config_path: Path = Path(__file__).resolve().parent.parent.parent / "data" / "config.json",
) -> DriftAppConfig:
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
