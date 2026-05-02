"""
Tests exhaustifs pour core/config/config_loader.py

Couvre :
- Toutes les dataclasses (SiteConfig, MotorConfig, etc.)
- ConfigLoader : chargement, parsing, validation
- load_config() : fonction publique
- Gestion d'erreurs (fichier manquant, JSON invalide, clés manquantes)
- Valeurs par défaut silencieuses
"""

import json
from pathlib import Path

import pytest

from core.config.config_loader import (
    VALID_AUTOMATION_MODES,
    CimierAutomationConfig,
    CimierConfig,
    ConfigLoader,
    DriftAppConfig,
    EncoderConfig,
    EncoderMecaniqueConfig,
    EncoderSPIConfig,
    GPIOPins,
    MeridianAnticipationConfig,
    MotorConfig,
    MotorDriverConfig,
    PowerSwitchConfig,
    SerialConfig,
    SiteConfig,
    ThresholdsConfig,
    TrackingConfig,
    load_config,
)


# =============================================================================
# Fixtures locales
# =============================================================================

@pytest.fixture
def sample_config_dict():
    """Dict JSON complet pour un config.json de test."""
    return {
        "site": {
            "latitude": 44.15,
            "longitude": 5.23,
            "altitude": 800,
            "nom": "Observatoire Test",
            "fuseau": "Europe/Paris",
        },
        "moteur": {
            "gpio_pins": {"dir": 17, "step": 18},
            "steps_per_revolution": 200,
            "microsteps": 4,
            "gear_ratio": 2230,
            "steps_correction_factor": 1.08849,
            "motor_delay_base": 0.002,
            "motor_delay_min": 0.00001,
            "motor_delay_max": 0.01,
            "max_speed_steps_per_sec": 1000,
            "acceleration_steps_per_sec2": 500,
        },
        "suivi": {
            "seuil_correction_deg": 0.5,
            "intervalle_verification_sec": 60,
            "abaque_file": "data/Loi_coupole.xlsx",
        },
        "encodeur": {
            "enabled": True,
            "spi": {"bus": 0, "device": 0, "speed_hz": 1000000, "mode": 0},
            "mecanique": {
                "wheel_diameter_mm": 50.0,
                "ring_diameter_mm": 2303.0,
                "counts_per_rev": 1024,
            },
            "calibration_factor": 0.010851,
        },
        "thresholds": {
            "feedback_min_deg": 3.0,
            "large_movement_deg": 30.0,
            "feedback_protection_deg": 20.0,
            "default_tolerance_deg": 0.5,
        },
        "simulation": False,
    }


@pytest.fixture
def tmp_config_file(tmp_path, sample_config_dict):
    """Fichier config.json temporaire."""
    config_file = tmp_path / "config.json"
    config_file.write_text(json.dumps(sample_config_dict, indent=2))
    return config_file


@pytest.fixture
def config_json_path():
    """Chemin vers le vrai config.json du projet."""
    return Path(__file__).resolve().parent.parent / "data" / "config.json"


# =============================================================================
# Dataclasses — Tests de construction et propriétés
# =============================================================================

class TestSiteConfig:
    def test_construction(self):
        site = SiteConfig(
            latitude=44.15, longitude=5.23, altitude=800,
            nom="Test", fuseau="Europe/Paris"
        )
        assert site.latitude == 44.15
        assert site.nom == "Test"
        assert site.tz_offset in (1, 2)  # DST-aware

    def test_str(self):
        site = SiteConfig(
            latitude=44.15, longitude=5.23, altitude=800,
            nom="Ubik", fuseau="Europe/Paris"
        )
        s = str(site)
        assert "Ubik" in s
        assert "44.15" in s


class TestGPIOPins:
    def test_construction(self):
        pins = GPIOPins(dir=17, step=18)
        assert pins.dir == 17
        assert pins.step == 18


class TestMotorConfig:
    def test_steps_per_dome_revolution(self):
        motor = MotorConfig(
            gpio_pins=GPIOPins(dir=17, step=18),
            steps_per_revolution=200,
            microsteps=4,
            gear_ratio=2230.0,
            steps_correction_factor=1.08849,
            motor_delay_base=0.002,
            motor_delay_min=0.00001,
            motor_delay_max=0.01,
            max_speed_steps_per_sec=1000,
            acceleration_steps_per_sec2=500,
        )
        expected = int(200 * 4 * 2230.0 * 1.08849)
        assert motor.steps_per_dome_revolution == expected

    def test_str(self):
        motor = MotorConfig(
            gpio_pins=GPIOPins(dir=17, step=18),
            steps_per_revolution=200, microsteps=4,
            gear_ratio=2230.0, steps_correction_factor=1.0,
            motor_delay_base=0.002, motor_delay_min=0.00001,
            motor_delay_max=0.01, max_speed_steps_per_sec=1000,
            acceleration_steps_per_sec2=500,
        )
        s = str(motor)
        assert "200" in s
        assert "2230" in s


class TestTrackingConfig:
    def test_abaque_path(self):
        tc = TrackingConfig(
            seuil_correction_deg=0.5,
            intervalle_verification_sec=60,
            abaque_file="data/Loi_coupole.xlsx"
        )
        assert tc.abaque_path == Path("data/Loi_coupole.xlsx")


class TestDriftAppConfig:
    def test_is_production(self):
        config = DriftAppConfig(
            site=SiteConfig(44.15, 5.23, 800, "Test", "UTC"),
            motor=MotorConfig(
                GPIOPins(17, 18), 200, 4, 2230.0, 1.0,
                0.002, 0.00001, 0.01, 1000, 500
            ),
            motor_driver=MotorDriverConfig("gpio", SerialConfig("/dev/ttyACM0", 115200, 2.0)),
            tracking=TrackingConfig(0.5, 60, "data/Loi.xlsx"),
            encoder=EncoderConfig(
                True, EncoderSPIConfig(0, 0, 1000000, 0),
                EncoderMecaniqueConfig(50.0, 2303.0, 1024), 0.01
            ),
            thresholds=ThresholdsConfig(3.0, 30.0, 20.0, 0.5),
            simulation=False,
        )
        assert config.is_production is True

    def test_is_simulation(self):
        config = DriftAppConfig(
            site=SiteConfig(0, 0, 0, "", "UTC"),
            motor=MotorConfig(GPIOPins(0, 0), 200, 4, 2230, 1, 0, 0, 0, 0, 0),
            motor_driver=MotorDriverConfig("gpio", SerialConfig("/dev/ttyACM0", 115200, 2.0)),
            tracking=TrackingConfig(0.5, 60, ""),
            encoder=EncoderConfig(
                False, EncoderSPIConfig(0, 0, 0, 0),
                EncoderMecaniqueConfig(0, 0, 0), 0
            ),
            thresholds=ThresholdsConfig(3.0, 30.0, 20.0, 0.5),
            simulation=True,
        )
        assert config.is_production is False


# =============================================================================
# ConfigLoader — Tests de chargement
# =============================================================================

class TestConfigLoader:
    def test_load_valid_config(self, tmp_config_file):
        """Chargement d'un fichier config valide."""
        loader = ConfigLoader(tmp_config_file)
        config = loader.load()
        assert isinstance(config, DriftAppConfig)
        assert config.site.latitude == 44.15
        assert config.site.nom == "Observatoire Test"

    def test_load_missing_file(self, tmp_path):
        """Fichier manquant → FileNotFoundError."""
        loader = ConfigLoader(tmp_path / "nonexistent.json")
        with pytest.raises(FileNotFoundError):
            loader.load()

    def test_load_invalid_json(self, tmp_path):
        """JSON invalide → JSONDecodeError."""
        bad_file = tmp_path / "bad.json"
        bad_file.write_text("{invalid json")
        loader = ConfigLoader(bad_file)
        with pytest.raises(json.JSONDecodeError):
            loader.load()

    def test_load_empty_json(self, tmp_path):
        """JSON vide {} → utilise les valeurs par défaut."""
        empty_file = tmp_path / "empty.json"
        empty_file.write_text("{}")
        loader = ConfigLoader(empty_file)
        config = loader.load()
        assert config.site.latitude == 0.0
        assert config.site.nom == "Observatoire"

    def test_parse_site(self, tmp_config_file):
        loader = ConfigLoader(tmp_config_file)
        config = loader.load()
        assert config.site.latitude == 44.15
        assert config.site.longitude == 5.23
        assert config.site.altitude == 800
        assert config.site.fuseau == "Europe/Paris"
        assert config.site.tz_offset in (1, 2)  # DST-aware

    def test_parse_motor(self, tmp_config_file):
        loader = ConfigLoader(tmp_config_file)
        config = loader.load()
        assert config.motor.gpio_pins.dir == 17
        assert config.motor.gpio_pins.step == 18
        assert config.motor.steps_per_revolution == 200
        assert config.motor.microsteps == 4
        assert config.motor.gear_ratio == 2230
        assert config.motor.steps_correction_factor == 1.08849

    def test_parse_tracking(self, tmp_config_file):
        loader = ConfigLoader(tmp_config_file)
        config = loader.load()
        assert config.tracking.seuil_correction_deg == 0.5
        assert config.tracking.intervalle_verification_sec == 60
        assert config.tracking.abaque_file == "data/Loi_coupole.xlsx"

    def test_parse_encoder(self, tmp_config_file):
        loader = ConfigLoader(tmp_config_file)
        config = loader.load()
        assert config.encoder.enabled is True
        assert config.encoder.spi.bus == 0
        assert config.encoder.mecanique.ring_diameter_mm == 2303.0
        assert config.encoder.calibration_factor == 0.010851

    def test_legacy_adaptive_section_ignored(self, tmp_path, sample_config_dict):
        """v5.10 : présence d'une section legacy adaptive_tracking ne casse pas le load."""
        legacy = dict(sample_config_dict)
        legacy["adaptive_tracking"] = {
            "modes": {"normal": {"interval_sec": 60, "motor_delay": 0.002}},
            "force_continuous": True,
        }
        config_file = tmp_path / "config.json"
        config_file.write_text(json.dumps(legacy))
        config = ConfigLoader(config_file).load()
        assert isinstance(config, DriftAppConfig)
        assert not hasattr(config, 'adaptive')

    def test_parse_simulation_flag(self, tmp_config_file):
        loader = ConfigLoader(tmp_config_file)
        config = loader.load()
        assert config.simulation is False

    def test_simulation_true(self, tmp_path, sample_config_dict):
        sample_config_dict["simulation"] = True
        config_file = tmp_path / "config.json"
        config_file.write_text(json.dumps(sample_config_dict))
        config = ConfigLoader(config_file).load()
        assert config.simulation is True

    def test_missing_section_uses_defaults(self, tmp_path):
        """Section manquante → valeurs par défaut silencieuses."""
        minimal = {"site": {"latitude": 44.15, "longitude": 5.23}}
        config_file = tmp_path / "config.json"
        config_file.write_text(json.dumps(minimal))
        config = ConfigLoader(config_file).load()
        assert config.site.latitude == 44.15
        assert config.site.altitude == 0.0
        assert config.motor.steps_per_revolution == 200
        assert config.motor.gpio_pins.dir == 17

    def test_parse_thresholds(self, tmp_config_file):
        """Thresholds section is parsed correctly."""
        config = ConfigLoader(tmp_config_file).load()
        assert config.thresholds.feedback_min_deg == 3.0
        assert config.thresholds.large_movement_deg == 30.0
        assert config.thresholds.feedback_protection_deg == 20.0
        assert config.thresholds.default_tolerance_deg == 0.5


# =============================================================================
# MeridianAnticipationConfig (v5.9) — flag opt-in
# =============================================================================

class TestMeridianAnticipationConfig:
    """Tests pour le flag meridian_anticipation (v5.9 Phase 2 Plan 01)."""

    def test_meridian_anticipation_default_true_when_section_missing(
        self, tmp_path, sample_config_dict
    ):
        """Section absente du JSON → enabled=True (défaut depuis v5.11.2), pas d'exception."""
        cfg = dict(sample_config_dict)
        cfg.pop("meridian_anticipation", None)
        config_file = tmp_path / "config.json"
        config_file.write_text(json.dumps(cfg))
        config = ConfigLoader(config_file).load()
        assert isinstance(config.meridian_anticipation, MeridianAnticipationConfig)
        assert config.meridian_anticipation.enabled is True

    def test_meridian_anticipation_enabled_true(self, tmp_path, sample_config_dict):
        """Section avec enabled=true → flag à True."""
        cfg = dict(sample_config_dict)
        cfg["meridian_anticipation"] = {"enabled": True}
        config_file = tmp_path / "config.json"
        config_file.write_text(json.dumps(cfg))
        config = ConfigLoader(config_file).load()
        assert config.meridian_anticipation.enabled is True

    def test_meridian_anticipation_enabled_false_explicit(
        self, tmp_path, sample_config_dict
    ):
        """Section avec enabled=false explicitement → flag à False."""
        cfg = dict(sample_config_dict)
        cfg["meridian_anticipation"] = {"enabled": False}
        config_file = tmp_path / "config.json"
        config_file.write_text(json.dumps(cfg))
        config = ConfigLoader(config_file).load()
        assert config.meridian_anticipation.enabled is False

    def test_meridian_anticipation_on_production_config(self, config_json_path):
        """Le data/config.json versionné doit avoir enabled=True depuis v5.11.2."""
        if not config_json_path.exists():
            pytest.skip("config.json non trouvé")
        config = load_config(config_json_path)
        assert config.meridian_anticipation.enabled is True


# =============================================================================
# CimierConfig (v6.0 Phase 1) — opt-in + rétro-compat stricte
# =============================================================================

class TestCimierConfig:
    """Tests pour la section cimier (v6.0 Phase 1, sub-plan 02)."""

    def test_cimier_config_default_when_missing(self, tmp_path, sample_config_dict):
        """Section absente du JSON → defaults appliqués, pas d'exception (rétro-compat)."""
        cfg = dict(sample_config_dict)
        cfg.pop("cimier", None)
        config_file = tmp_path / "config.json"
        config_file.write_text(json.dumps(cfg))
        config = ConfigLoader(config_file).load()
        assert isinstance(config.cimier, CimierConfig)
        assert config.cimier.enabled is False
        assert config.cimier.host == ""
        assert config.cimier.port == 80
        assert config.cimier.invert_direction is False
        assert config.cimier.cycle_timeout_s == 90.0
        assert config.cimier.boot_poll_timeout_s == 30.0
        assert config.cimier.post_off_quiet_s == 10.0
        assert isinstance(config.cimier.power_switch, PowerSwitchConfig)
        assert config.cimier.power_switch.type == "noop"
        assert config.cimier.power_switch.host == ""
        assert config.cimier.power_switch.switch_id == 0

    def test_cimier_config_full_section(self, tmp_path, sample_config_dict):
        """Section complète → toutes les valeurs reflétées dans la dataclass."""
        cfg = dict(sample_config_dict)
        cfg["cimier"] = {
            "enabled": True,
            "host": "10.0.0.42",
            "port": 8080,
            "invert_direction": True,
            "cycle_timeout_s": 60.0,
            "boot_poll_timeout_s": 20.0,
            "post_off_quiet_s": 5.0,
            "power_switch": {
                "type": "shelly_gen2",
                "host": "10.0.0.43",
                "switch_id": 1,
            },
        }
        config_file = tmp_path / "config.json"
        config_file.write_text(json.dumps(cfg))
        config = ConfigLoader(config_file).load()
        assert config.cimier.enabled is True
        assert config.cimier.host == "10.0.0.42"
        assert config.cimier.port == 8080
        assert config.cimier.invert_direction is True
        assert config.cimier.cycle_timeout_s == 60.0
        assert config.cimier.boot_poll_timeout_s == 20.0
        assert config.cimier.post_off_quiet_s == 5.0
        assert config.cimier.power_switch.type == "shelly_gen2"
        assert config.cimier.power_switch.host == "10.0.0.43"
        assert config.cimier.power_switch.switch_id == 1

    def test_cimier_config_partial_section(self, tmp_path, sample_config_dict):
        """Section partielle → defaults pour clés absentes, override pour les autres."""
        cfg = dict(sample_config_dict)
        cfg["cimier"] = {"enabled": True, "host": "10.0.0.99"}
        config_file = tmp_path / "config.json"
        config_file.write_text(json.dumps(cfg))
        config = ConfigLoader(config_file).load()
        assert config.cimier.enabled is True
        assert config.cimier.host == "10.0.0.99"
        # Defaults pour les autres champs
        assert config.cimier.port == 80
        assert config.cimier.invert_direction is False
        assert config.cimier.cycle_timeout_s == 90.0
        assert config.cimier.power_switch.type == "noop"

    def test_cimier_power_switch_nested_default(self, tmp_path, sample_config_dict):
        """Section cimier sans power_switch imbriqué → PowerSwitchConfig() par défaut."""
        cfg = dict(sample_config_dict)
        cfg["cimier"] = {"enabled": True, "host": "10.0.0.99"}
        config_file = tmp_path / "config.json"
        config_file.write_text(json.dumps(cfg))
        config = ConfigLoader(config_file).load()
        assert config.cimier.power_switch.type == "noop"
        assert config.cimier.power_switch.host == ""
        assert config.cimier.power_switch.switch_id == 0

    def test_cimier_power_switch_shelly_gen2(self, tmp_path, sample_config_dict):
        """type=shelly_gen2 + host renseigné → reflété dans la dataclass."""
        cfg = dict(sample_config_dict)
        cfg["cimier"] = {
            "enabled": False,
            "power_switch": {
                "type": "shelly_gen2",
                "host": "10.0.0.43",
                "switch_id": 2,
            },
        }
        config_file = tmp_path / "config.json"
        config_file.write_text(json.dumps(cfg))
        config = ConfigLoader(config_file).load()
        assert config.cimier.power_switch.type == "shelly_gen2"
        assert config.cimier.power_switch.host == "10.0.0.43"
        assert config.cimier.power_switch.switch_id == 2


# =============================================================================
# CimierAutomationConfig modes (v6.0 Phase 4) — enum mode + rétro-compat
# =============================================================================


class TestCimierAutomationMode:
    """AC-1 du sub-plan v6.0-04-01.

    Couvre la migration `enabled: bool` → `mode: str` (manual|semi|full) avec
    rétro-compat stricte sur la clé legacy `enabled` (v6.2).
    """

    def _load_with_automation(self, tmp_path, sample_config_dict, automation_dict):
        cfg = dict(sample_config_dict)
        cfg["cimier"] = {"enabled": True, "automation": automation_dict}
        config_file = tmp_path / "config.json"
        config_file.write_text(json.dumps(cfg))
        return ConfigLoader(config_file).load()

    def test_default_mode_is_manual_when_section_absent(self, tmp_path, sample_config_dict):
        """Section automation absente → mode='manual' (default-safe)."""
        cfg = dict(sample_config_dict)
        cfg["cimier"] = {"enabled": True}  # pas de section automation
        config_file = tmp_path / "config.json"
        config_file.write_text(json.dumps(cfg))
        config = ConfigLoader(config_file).load()
        assert isinstance(config.cimier.automation, CimierAutomationConfig)
        assert config.cimier.automation.mode == "manual"

    def test_legacy_enabled_true_maps_to_full(self, tmp_path, sample_config_dict):
        """Rétro-compat v6.2 : enabled=true (sans mode) → mode='full'."""
        config = self._load_with_automation(
            tmp_path, sample_config_dict, {"enabled": True}
        )
        assert config.cimier.automation.mode == "full"

    def test_legacy_enabled_false_maps_to_manual(self, tmp_path, sample_config_dict):
        """Rétro-compat v6.2 : enabled=false (sans mode) → mode='manual'."""
        config = self._load_with_automation(
            tmp_path, sample_config_dict, {"enabled": False}
        )
        assert config.cimier.automation.mode == "manual"

    def test_explicit_mode_semi_loaded_directly(self, tmp_path, sample_config_dict):
        """Lecture directe : mode='semi' → mode='semi' (pas de fallback enabled)."""
        config = self._load_with_automation(
            tmp_path, sample_config_dict, {"mode": "semi"}
        )
        assert config.cimier.automation.mode == "semi"

    def test_mode_takes_priority_over_legacy_enabled(self, tmp_path, sample_config_dict):
        """mode + enabled cohabitent → mode prime (warning log mais pas d'exception)."""
        config = self._load_with_automation(
            tmp_path, sample_config_dict, {"mode": "semi", "enabled": True}
        )
        assert config.cimier.automation.mode == "semi"

    def test_invalid_mode_falls_back_to_default_manual(
        self, tmp_path, sample_config_dict, caplog
    ):
        """mode invalide ('yolo') → fallback default-safe sur 'manual', warning loggé."""
        import logging
        caplog.set_level(logging.WARNING)
        config = self._load_with_automation(
            tmp_path, sample_config_dict, {"mode": "yolo"}
        )
        assert config.cimier.automation.mode == "manual"
        assert any("yolo" in record.message for record in caplog.records)

    def test_valid_modes_constant_exposes_all_three(self):
        """Sanity check : VALID_AUTOMATION_MODES doit contenir exactement les 3 niveaux."""
        assert set(VALID_AUTOMATION_MODES) == {"manual", "semi", "full"}


# =============================================================================
# load_config() — fonction publique
# =============================================================================

class TestLoadConfig:
    def test_load_real_config(self, config_json_path):
        """Charge le vrai config.json du projet."""
        if not config_json_path.exists():
            pytest.skip("config.json non trouvé")
        config = load_config(config_json_path)
        assert isinstance(config, DriftAppConfig)
        assert config.site.nom == "Observatoire Ubik"

    def test_load_with_custom_path(self, tmp_config_file):
        config = load_config(tmp_config_file)
        assert config.site.nom == "Observatoire Test"
