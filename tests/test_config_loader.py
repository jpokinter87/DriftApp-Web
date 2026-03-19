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
    AdaptiveConfig,
    AltitudeThresholds,
    ConfigLoader,
    DriftAppConfig,
    EncoderConfig,
    EncoderMecaniqueConfig,
    EncoderSPIConfig,
    GPIOPins,
    MotorConfig,
    MotorDriverConfig,
    MovementThresholds,
    SerialConfig,
    SiteConfig,
    ThresholdsConfig,
    TrackingConfig,
    TrackingModeParams,
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
            "tz_offset": 1,
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
        "adaptive_tracking": {
            "altitudes": {"critical": 68.0, "zenith": 75.0},
            "movements": {"critical": 30.0, "extreme": 50.0},
            "modes": {
                "normal": {"interval_sec": 60, "threshold_deg": 0.5, "motor_delay": 0.002},
                "critical": {"interval_sec": 15, "threshold_deg": 0.3, "motor_delay": 0.001},
                "continuous": {"interval_sec": 5, "threshold_deg": 0.2, "motor_delay": 0.00015},
            },
            "critical_zones": [
                {
                    "name": "Zone Nord-Est haute",
                    "alt_min": 68.0,
                    "alt_max": 90.0,
                    "az_min": 0.0,
                    "az_max": 90.0,
                    "enabled": True,
                }
            ],
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
            nom="Test", fuseau="Europe/Paris", tz_offset=1
        )
        assert site.latitude == 44.15
        assert site.nom == "Test"

    def test_str(self):
        site = SiteConfig(
            latitude=44.15, longitude=5.23, altitude=800,
            nom="Ubik", fuseau="Europe/Paris", tz_offset=1
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


class TestTrackingModeParams:
    def test_calculate_speed(self):
        params = TrackingModeParams(
            interval_sec=60, threshold_deg=0.5, motor_delay=0.002
        )
        speed = params.calculate_speed(1941866)
        assert speed > 0

    def test_calculate_speed_zero_delay(self):
        params = TrackingModeParams(
            interval_sec=60, threshold_deg=0.5, motor_delay=0.0
        )
        assert params.calculate_speed(1941866) == 0.0

    def test_calculate_speed_negative_delay(self):
        params = TrackingModeParams(
            interval_sec=60, threshold_deg=0.5, motor_delay=-0.001
        )
        assert params.calculate_speed(1941866) == 0.0


class TestDriftAppConfig:
    def test_is_production(self):
        config = DriftAppConfig(
            site=SiteConfig(44.15, 5.23, 800, "Test", "UTC", 1),
            motor=MotorConfig(
                GPIOPins(17, 18), 200, 4, 2230.0, 1.0,
                0.002, 0.00001, 0.01, 1000, 500
            ),
            motor_driver=MotorDriverConfig("gpio", SerialConfig("/dev/ttyACM0", 115200, 2.0)),
            tracking=TrackingConfig(0.5, 60, "data/Loi.xlsx"),
            adaptive=AdaptiveConfig(
                AltitudeThresholds(68.0, 75.0),
                MovementThresholds(30.0, 50.0),
                {}, []
            ),
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
            site=SiteConfig(0, 0, 0, "", "", 0),
            motor=MotorConfig(GPIOPins(0, 0), 200, 4, 2230, 1, 0, 0, 0, 0, 0),
            motor_driver=MotorDriverConfig("gpio", SerialConfig("/dev/ttyACM0", 115200, 2.0)),
            tracking=TrackingConfig(0.5, 60, ""),
            adaptive=AdaptiveConfig(
                AltitudeThresholds(68, 75), MovementThresholds(30, 50), {}, []
            ),
            encoder=EncoderConfig(
                False, EncoderSPIConfig(0, 0, 0, 0),
                EncoderMecaniqueConfig(0, 0, 0), 0
            ),
            thresholds=ThresholdsConfig(3.0, 30.0, 20.0, 0.5),
            simulation=True,
        )
        assert config.is_production is False

class TestAdaptiveConfig:
    def test_get_mode_exists(self):
        modes = {"normal": TrackingModeParams(60, 0.5, 0.002)}
        ac = AdaptiveConfig(
            AltitudeThresholds(68, 75), MovementThresholds(30, 50),
            modes, []
        )
        assert ac.get_mode("normal") is not None

    def test_get_mode_not_exists(self):
        ac = AdaptiveConfig(
            AltitudeThresholds(68, 75), MovementThresholds(30, 50),
            {}, []
        )
        assert ac.get_mode("nonexistent") is None


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
        assert config.site.tz_offset == 1

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

    def test_parse_adaptive_modes(self, tmp_config_file):
        loader = ConfigLoader(tmp_config_file)
        config = loader.load()
        assert "normal" in config.adaptive.modes
        assert "critical" in config.adaptive.modes
        assert "continuous" in config.adaptive.modes
        assert config.adaptive.modes["normal"].motor_delay == 0.002
        assert config.adaptive.modes["continuous"].motor_delay == 0.00015

    def test_parse_adaptive_thresholds(self, tmp_config_file):
        loader = ConfigLoader(tmp_config_file)
        config = loader.load()
        assert config.adaptive.altitudes.critical == 68.0
        assert config.adaptive.altitudes.zenith == 75.0
        assert config.adaptive.movements.critical == 30.0
        assert config.adaptive.movements.extreme == 50.0

    def test_parse_critical_zones(self, tmp_config_file):
        loader = ConfigLoader(tmp_config_file)
        config = loader.load()
        assert len(config.adaptive.critical_zones) == 1
        zone = config.adaptive.critical_zones[0]
        assert zone.name == "Zone Nord-Est haute"
        assert zone.alt_min == 68.0
        assert zone.enabled is True

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

    def test_modes_include_fast_track(self, tmp_config_file):
        """Parser inclut fast_track même si absent du JSON (valeur par défaut)."""
        config = ConfigLoader(tmp_config_file).load()
        assert "fast_track" in config.adaptive.modes


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
