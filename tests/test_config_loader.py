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
    BootCalibrationConfig,
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
    MotorShellyConfig,
    PowerSwitchConfig,
    SerialConfig,
    SiteConfig,
    SwitchReaderConfig,
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
            latitude=44.15, longitude=5.23, altitude=800, nom="Test", fuseau="Europe/Paris"
        )
        assert site.latitude == 44.15
        assert site.nom == "Test"
        assert site.tz_offset in (1, 2)  # DST-aware

    def test_str(self):
        site = SiteConfig(
            latitude=44.15, longitude=5.23, altitude=800, nom="Ubik", fuseau="Europe/Paris"
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
            steps_per_revolution=200,
            microsteps=4,
            gear_ratio=2230.0,
            steps_correction_factor=1.0,
            motor_delay_base=0.002,
            motor_delay_min=0.00001,
            motor_delay_max=0.01,
            max_speed_steps_per_sec=1000,
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
            abaque_file="data/Loi_coupole.xlsx",
        )
        assert tc.abaque_path == Path("data/Loi_coupole.xlsx")


class TestDriftAppConfig:
    def test_is_production(self):
        config = DriftAppConfig(
            site=SiteConfig(44.15, 5.23, 800, "Test", "UTC"),
            motor=MotorConfig(
                GPIOPins(17, 18), 200, 4, 2230.0, 1.0, 0.002, 0.00001, 0.01, 1000, 500
            ),
            motor_driver=MotorDriverConfig("gpio", SerialConfig("/dev/ttyACM0", 115200, 2.0)),
            tracking=TrackingConfig(0.5, 60, "data/Loi.xlsx"),
            encoder=EncoderConfig(
                True,
                EncoderSPIConfig(0, 0, 1000000, 0),
                EncoderMecaniqueConfig(50.0, 2303.0, 1024),
                0.01,
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
                False, EncoderSPIConfig(0, 0, 0, 0), EncoderMecaniqueConfig(0, 0, 0), 0
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
        assert not hasattr(config, "adaptive")

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

    def test_meridian_anticipation_enabled_false_explicit(self, tmp_path, sample_config_dict):
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
        assert config.cimier.cycle_timeout_s == 60.0
        assert config.cimier.boot_poll_timeout_s == 20.0
        assert config.cimier.post_off_quiet_s == 5.0
        assert config.cimier.power_switch.type == "shelly_gen2"
        assert config.cimier.power_switch.host == "10.0.0.43"
        assert config.cimier.power_switch.switch_id == 1

    def test_cimier_config_partial_section(self, tmp_path, sample_config_dict):
        """Section partielle → defaults pour clés absentes, override pour les autres."""
        cfg = dict(sample_config_dict)
        cfg["cimier"] = {"enabled": True}
        config_file = tmp_path / "config.json"
        config_file.write_text(json.dumps(cfg))
        config = ConfigLoader(config_file).load()
        assert config.cimier.enabled is True
        # Defaults pour les autres champs
        assert config.cimier.cycle_timeout_s == 90.0
        assert config.cimier.power_switch.type == "noop"

    def test_cimier_power_switch_nested_default(self, tmp_path, sample_config_dict):
        """Section cimier sans power_switch imbriqué → PowerSwitchConfig() par défaut."""
        cfg = dict(sample_config_dict)
        cfg["cimier"] = {"enabled": True}
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

    def test_cimier_shelly_settle_and_verbose_defaults(self, tmp_path, sample_config_dict):
        """shelly_settle_s et verbose_logging : defaults rétro-compatibles (section absente)."""
        cfg = dict(sample_config_dict)
        cfg.pop("cimier", None)
        config_file = tmp_path / "config.json"
        config_file.write_text(json.dumps(cfg))
        config = ConfigLoader(config_file).load()
        assert config.cimier.shelly_settle_s == 2.0
        assert config.cimier.dir_settle_s == 0.3
        assert config.cimier.verbose_logging is False

    def test_cimier_parse_shelly_settle_and_verbose(self, tmp_path, sample_config_dict):
        """Les deux clés sont lues depuis data/config.json."""
        cfg = dict(sample_config_dict)
        cfg["cimier"] = {"shelly_settle_s": 3.5, "verbose_logging": True}
        config_file = tmp_path / "config.json"
        config_file.write_text(json.dumps(cfg))
        config = ConfigLoader(config_file).load()
        assert config.cimier.shelly_settle_s == 3.5
        assert config.cimier.verbose_logging is True

    def test_cimier_parse_dir_settle_s(self, tmp_path, sample_config_dict):
        """dir_settle_s est lu depuis data/config.json (override du défaut 0.3)."""
        cfg = dict(sample_config_dict)
        cfg["cimier"] = {"dir_settle_s": 0.5}
        config_file = tmp_path / "config.json"
        config_file.write_text(json.dumps(cfg))
        config = ConfigLoader(config_file).load()
        assert config.cimier.dir_settle_s == 0.5

    def test_cimier_parse_cycle_poll_interval_s(self, tmp_path, sample_config_dict):
        """cycle_poll_interval_s est lu depuis data/config.json (override du défaut 0.5)."""
        cfg = dict(sample_config_dict)
        cfg["cimier"] = {"cycle_poll_interval_s": 0.1}
        config_file = tmp_path / "config.json"
        config_file.write_text(json.dumps(cfg))
        config = ConfigLoader(config_file).load()
        assert config.cimier.cycle_poll_interval_s == 0.1


@pytest.mark.parametrize("invalid", [-1.0, 0.0, 0])
def test_cimier_config_rejects_cycle_timeout_zero_or_negative(invalid):
    """cycle_timeout_s ≤ 0 → ValueError explicite au démarrage du service.

    Sans ce guard, le polling sortait immédiatement avec result=timeout
    trompeur (le moteur n'a pas tourné). On veut un refus net à la lecture
    de config, pas une dégénérescence silencieuse runtime (Bloc 3 dette T4).
    """
    with pytest.raises(ValueError, match="cycle_timeout_s"):
        CimierConfig(cycle_timeout_s=invalid)


# =============================================================================
# MotorShellyConfig (pivot v6.x — pilotage moteur via 2 relais Shelly)
# =============================================================================


class TestMotorShellyConfig:
    """Tests pour la section cimier.motor_shelly (pivot architectural v6.x).

    Section opt-in : absente du JSON → defaults appliqués, jamais d'exception.
    Validation default-safe sur erreurs typées (api invalide, timer négatif,
    types non parsables) → warning + fallback, pas de plantage du boot.
    Pas de validation `relay_motor != relay_dir` : les 2 Shellys ont des
    IPs distinctes, indice 0 partagé est légitime.
    """

    def _load_with_cimier(self, tmp_path, sample_config_dict, cimier_section):
        cfg = dict(sample_config_dict)
        cfg["cimier"] = cimier_section
        config_file = tmp_path / "config.json"
        config_file.write_text(json.dumps(cfg))
        return ConfigLoader(config_file).load()

    def test_motor_shelly_default_when_section_missing(self, tmp_path, sample_config_dict):
        """Section cimier.motor_shelly absente → MotorShellyConfig() par défaut."""
        config = self._load_with_cimier(tmp_path, sample_config_dict, {"enabled": True})
        ms = config.cimier.motor_shelly
        assert isinstance(ms, MotorShellyConfig)
        assert ms.host_motor == ""
        assert ms.host_dir == ""
        assert ms.relay_motor == 0
        assert ms.relay_dir == 0
        assert ms.open_dir_state is True
        assert ms.motor_on_relay_state is True
        assert ms.api == "rpc"
        assert ms.timer_safety_sec == 90.0

    def test_motor_shelly_full_section(self, tmp_path, sample_config_dict):
        """Section complète → toutes les valeurs reflétées dans la dataclass."""
        config = self._load_with_cimier(
            tmp_path,
            sample_config_dict,
            {
                "enabled": True,
                "motor_shelly": {
                    "host_motor": "10.0.0.85",
                    "host_dir": "10.0.0.86",
                    "relay_motor": 2,
                    "relay_dir": 3,
                    "open_dir_state": False,
                    "motor_on_relay_state": False,
                    "api": "legacy",
                    "timer_safety_sec": 60.0,
                },
            },
        )
        ms = config.cimier.motor_shelly
        assert ms.host_motor == "10.0.0.85"
        assert ms.host_dir == "10.0.0.86"
        assert ms.relay_motor == 2
        assert ms.relay_dir == 3
        assert ms.open_dir_state is False
        assert ms.motor_on_relay_state is False
        assert ms.api == "legacy"
        assert ms.timer_safety_sec == 60.0

    def test_motor_shelly_two_shellys_share_relay_index_zero(self, tmp_path, sample_config_dict):
        """Shelly 1 Gen 3 × 2 : chaque Shelly a son unique relais d'index 0,
        et c'est légitime. Pas de validation d'unicité côté config."""
        config = self._load_with_cimier(
            tmp_path,
            sample_config_dict,
            {
                "enabled": True,
                "motor_shelly": {
                    "host_motor": "10.0.0.85",
                    "host_dir": "10.0.0.86",
                    "relay_motor": 0,
                    "relay_dir": 0,
                },
            },
        )
        ms = config.cimier.motor_shelly
        assert ms.relay_motor == 0
        assert ms.relay_dir == 0
        assert ms.host_motor == "10.0.0.85"
        assert ms.host_dir == "10.0.0.86"

    def test_motor_shelly_serge_terrain_convention(self, tmp_path, sample_config_dict):
        """Cas terrain Serge : oscillateur NC + DIR ouvert=UP → conventions inversées
        sur les 2 champs paramétriques, sans recompiler la classe."""
        config = self._load_with_cimier(
            tmp_path,
            sample_config_dict,
            {
                "enabled": True,
                "motor_shelly": {
                    "open_dir_state": False,
                    "motor_on_relay_state": False,
                },
            },
        )
        assert config.cimier.motor_shelly.open_dir_state is False
        assert config.cimier.motor_shelly.motor_on_relay_state is False
        # Le reste reste par défaut
        assert config.cimier.motor_shelly.api == "rpc"
        assert config.cimier.motor_shelly.relay_motor == 0

    def test_motor_shelly_partial_section(self, tmp_path, sample_config_dict):
        """Section partielle → defaults pour clés absentes, override pour les autres."""
        config = self._load_with_cimier(
            tmp_path,
            sample_config_dict,
            {"enabled": True, "motor_shelly": {"host_motor": "10.0.0.85"}},
        )
        ms = config.cimier.motor_shelly
        assert ms.host_motor == "10.0.0.85"
        # Defaults pour le reste
        assert ms.host_dir == ""
        assert ms.relay_motor == 0
        assert ms.relay_dir == 0
        assert ms.api == "rpc"
        assert ms.timer_safety_sec == 90.0

    def test_motor_shelly_invalid_api_falls_back_to_rpc(self, tmp_path, sample_config_dict, caplog):
        """api='yolo' → warning + fallback sur 'rpc' (les autres champs préservés)."""
        import logging

        caplog.set_level(logging.WARNING)
        config = self._load_with_cimier(
            tmp_path,
            sample_config_dict,
            {
                "enabled": True,
                "motor_shelly": {"host_motor": "10.0.0.85", "api": "yolo"},
            },
        )
        assert config.cimier.motor_shelly.api == "rpc"
        assert config.cimier.motor_shelly.host_motor == "10.0.0.85"
        assert any("motor_shelly.api" in r.message for r in caplog.records)

    def test_motor_shelly_negative_timer_falls_back(self, tmp_path, sample_config_dict, caplog):
        """timer_safety_sec négatif → warning + fallback default (90.0)."""
        import logging

        caplog.set_level(logging.WARNING)
        config = self._load_with_cimier(
            tmp_path,
            sample_config_dict,
            {
                "enabled": True,
                "motor_shelly": {"host_motor": "10.0.0.85", "timer_safety_sec": -5.0},
            },
        )
        assert config.cimier.motor_shelly.timer_safety_sec == 90.0
        assert config.cimier.motor_shelly.host_motor == "10.0.0.85"
        assert any("timer_safety_sec" in r.message for r in caplog.records)

    def test_motor_shelly_invalid_types_fall_back_to_defaults(
        self, tmp_path, sample_config_dict, caplog
    ):
        """Type non parsable (relay_motor="abc") → warning + fallback MotorShellyConfig()."""
        import logging

        caplog.set_level(logging.WARNING)
        config = self._load_with_cimier(
            tmp_path,
            sample_config_dict,
            {
                "enabled": True,
                "motor_shelly": {"host_motor": "10.0.0.85", "relay_motor": "abc"},
            },
        )
        # Fallback total : host_motor repasse à default aussi
        assert config.cimier.motor_shelly.host_motor == ""
        assert config.cimier.motor_shelly.relay_motor == 0


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
        config = self._load_with_automation(tmp_path, sample_config_dict, {"enabled": True})
        assert config.cimier.automation.mode == "full"

    def test_legacy_enabled_false_maps_to_manual(self, tmp_path, sample_config_dict):
        """Rétro-compat v6.2 : enabled=false (sans mode) → mode='manual'."""
        config = self._load_with_automation(tmp_path, sample_config_dict, {"enabled": False})
        assert config.cimier.automation.mode == "manual"

    def test_explicit_mode_semi_loaded_directly(self, tmp_path, sample_config_dict):
        """Lecture directe : mode='semi' → mode='semi' (pas de fallback enabled)."""
        config = self._load_with_automation(tmp_path, sample_config_dict, {"mode": "semi"})
        assert config.cimier.automation.mode == "semi"

    def test_mode_takes_priority_over_legacy_enabled(self, tmp_path, sample_config_dict):
        """mode + enabled cohabitent → mode prime (warning log mais pas d'exception)."""
        config = self._load_with_automation(
            tmp_path, sample_config_dict, {"mode": "semi", "enabled": True}
        )
        assert config.cimier.automation.mode == "semi"

    def test_invalid_mode_falls_back_to_default_manual(self, tmp_path, sample_config_dict, caplog):
        """mode invalide ('yolo') → fallback default-safe sur 'manual', warning loggé."""
        import logging

        caplog.set_level(logging.WARNING)
        config = self._load_with_automation(tmp_path, sample_config_dict, {"mode": "yolo"})
        assert config.cimier.automation.mode == "manual"
        assert any("yolo" in record.message for record in caplog.records)

    def test_valid_modes_constant_exposes_all_three(self):
        """Sanity check : VALID_AUTOMATION_MODES doit contenir exactement les 3 niveaux."""
        assert set(VALID_AUTOMATION_MODES) == {"manual", "semi", "full"}


# =============================================================================
# BootCalibrationConfig (v6.6.0 — routine boot simplifiée)
# =============================================================================


class TestBootCalibrationConfig:
    """v6.6.0 : section `boot_calibration` rétro-compatible.

    Clés legacy (`overshoot_deg`, section `calibration`) sont ignorées
    silencieusement — pas de warning, juste défaut sans effet.
    """

    def _load_with_boot_calibration(self, tmp_path, sample_config_dict, boot_dict):
        cfg = dict(sample_config_dict)
        if boot_dict is not None:
            cfg["boot_calibration"] = boot_dict
        config_file = tmp_path / "config.json"
        config_file.write_text(json.dumps(cfg))
        return ConfigLoader(config_file).load()

    def test_boot_calibration_defaults_when_section_missing(self, tmp_path, sample_config_dict):
        """Section absente → defaults (rétro-compat stricte)."""
        config = self._load_with_boot_calibration(tmp_path, sample_config_dict, None)
        assert isinstance(config.boot_calibration, BootCalibrationConfig)
        assert config.boot_calibration.fallback_sweep_deg == 7.0
        assert config.boot_calibration.timeout_sec == 180.0
        assert config.boot_calibration.poll_interval_sec == 0.1

    def test_boot_calibration_partial_override(self, tmp_path, sample_config_dict):
        """Override partiel : seule la clé fournie est modifiée, les autres restent en défaut."""
        config = self._load_with_boot_calibration(
            tmp_path, sample_config_dict, {"fallback_sweep_deg": 12.0}
        )
        assert config.boot_calibration.fallback_sweep_deg == 12.0
        assert config.boot_calibration.timeout_sec == 180.0
        assert config.boot_calibration.poll_interval_sec == 0.1

    def test_boot_calibration_invalid_sweep_falls_back(self, tmp_path, sample_config_dict, caplog):
        """fallback_sweep_deg <= 0 → log WARNING + defaults."""
        import logging

        caplog.set_level(logging.WARNING)
        config = self._load_with_boot_calibration(
            tmp_path, sample_config_dict, {"fallback_sweep_deg": -1.0}
        )
        assert config.boot_calibration.fallback_sweep_deg == 7.0
        assert any("boot_calibration config invalide" in r.message for r in caplog.records)

    def test_boot_calibration_legacy_overshoot_ignored(self, tmp_path, sample_config_dict):
        """Clé legacy `overshoot_deg` dans la config est ignorée silencieusement."""
        config = self._load_with_boot_calibration(
            tmp_path, sample_config_dict, {"overshoot_deg": 5.0, "fallback_sweep_deg": 7.0}
        )
        # Pas d'erreur, valeurs explicites + defaults pour les autres clés
        assert config.boot_calibration.fallback_sweep_deg == 7.0
        assert not hasattr(config.boot_calibration, "overshoot_deg")

    def test_boot_calibration_invalid_timeout_falls_back(
        self, tmp_path, sample_config_dict, caplog
    ):
        """timeout_sec <= 0 → log WARNING + defaults."""
        import logging

        caplog.set_level(logging.WARNING)
        config = self._load_with_boot_calibration(tmp_path, sample_config_dict, {"timeout_sec": 0})
        assert config.boot_calibration.timeout_sec == 180.0
        assert any("boot_calibration config invalide" in r.message for r in caplog.records)

    def test_boot_calibration_invalid_poll_falls_back(self, tmp_path, sample_config_dict, caplog):
        """poll_interval_sec <= 0 → log WARNING + defaults."""
        import logging

        caplog.set_level(logging.WARNING)
        config = self._load_with_boot_calibration(
            tmp_path, sample_config_dict, {"poll_interval_sec": -0.5}
        )
        assert config.boot_calibration.poll_interval_sec == 0.1
        assert any("boot_calibration config invalide" in r.message for r in caplog.records)


# =============================================================================
# SwitchReaderConfig (V3 tout-Shelly — lecture fins de course via Shelly Uni+)
# =============================================================================


class TestSwitchReaderConfig:
    def test_defaults(self):
        c = SwitchReaderConfig()
        assert c.type == "noop"
        assert c.host == ""
        assert c.api == "rpc"
        assert c.open_input_id == 1
        assert c.closed_input_id == 0
        assert c.invert is True
        assert c.timeout_s == 3.0

    def test_parse_switch_reader_from_json(self, tmp_path):
        import json

        from core.config.config_loader import load_config

        cfg_path = tmp_path / "config.json"
        cfg_path.write_text(
            json.dumps(
                {
                    "cimier": {
                        "enabled": True,
                        "switch_reader": {
                            "type": "shelly_uni",
                            "host": "192.168.1.84",
                            "api": "rpc",
                            "open_input_id": 1,
                            "closed_input_id": 0,
                            "invert": True,
                        },
                    }
                }
            ),
            encoding="utf-8",
        )
        cfg = load_config(cfg_path)
        sr = cfg.cimier.switch_reader
        assert sr.type == "shelly_uni"
        assert sr.host == "192.168.1.84"
        assert sr.open_input_id == 1
        assert sr.closed_input_id == 0
        assert sr.invert is True

    def test_switch_reader_defaults_when_absent(self, tmp_path):
        import json

        from core.config.config_loader import load_config

        cfg_path = tmp_path / "config.json"
        cfg_path.write_text(json.dumps({"cimier": {"enabled": False}}), encoding="utf-8")
        cfg = load_config(cfg_path)
        assert cfg.cimier.switch_reader.type == "noop"

    def test_legacy_pico_keys_ignored(self, tmp_path):
        # Anciennes clés Pico host/port présentes : ne doivent PAS faire planter
        # le parse (rétro-compat lecture), mais ne sont plus exposées.
        import json

        from core.config.config_loader import load_config

        cfg_path = tmp_path / "config.json"
        cfg_path.write_text(
            json.dumps({"cimier": {"enabled": False, "host": "192.168.1.84", "port": 80}}),
            encoding="utf-8",
        )
        cfg = load_config(cfg_path)
        assert not hasattr(cfg.cimier, "host")
        assert not hasattr(cfg.cimier, "port")


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
