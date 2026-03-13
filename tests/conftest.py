"""
Fixtures partagées pour les tests DriftApp.

Fournit des configurations de test, des chemins, et des mocks
pour éviter les dépendances hardware (GPIO, SPI, /dev/shm/).
"""

import json
import sys
from pathlib import Path

import pytest

# S'assurer que le répertoire racine est dans le path
PROJECT_ROOT = Path(__file__).parent.parent.resolve()
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))


@pytest.fixture
def project_root() -> Path:
    """Retourne le chemin racine du projet."""
    return PROJECT_ROOT


@pytest.fixture
def data_dir(project_root) -> Path:
    """Retourne le chemin du répertoire data/."""
    return project_root / "data"


@pytest.fixture
def config_json_path(data_dir) -> Path:
    """Retourne le chemin vers config.json."""
    return data_dir / "config.json"


@pytest.fixture
def sample_config_dict() -> dict:
    """Retourne un dictionnaire de configuration minimal pour les tests."""
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
        "simulation": False,
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
        "adaptive_tracking": {
            "altitudes": {"critical": 68.0, "zenith": 75.0},
            "movements": {"critical": 30.0, "extreme": 50.0, "min_for_continuous": 1.0},
            "modes": {
                "normal": {
                    "interval_sec": 60,
                    "threshold_deg": 0.5,
                    "motor_delay": 0.002,
                },
                "critical": {
                    "interval_sec": 30,
                    "threshold_deg": 0.35,
                    "motor_delay": 0.001,
                },
                "continuous": {
                    "interval_sec": 30,
                    "threshold_deg": 0.3,
                    "motor_delay": 0.00015,
                },
            },
            "critical_zones": [
                {
                    "name": "Zone Nord-Est haute",
                    "alt_min": 68.0,
                    "alt_max": 73.0,
                    "az_min": 50.0,
                    "az_max": 70.0,
                    "enabled": True,
                }
            ],
        },
        "logging": {
            "level": "INFO",
            "log_dir": "logs",
            "max_file_size_mb": 10,
            "backup_count": 5,
        },
    }


@pytest.fixture
def tmp_config_file(tmp_path, sample_config_dict) -> Path:
    """Crée un fichier config.json temporaire pour les tests."""
    config_file = tmp_path / "config.json"
    config_file.write_text(json.dumps(sample_config_dict, indent=2))
    return config_file
