"""
Fixtures partagées pour les tests DriftApp.

Ce fichier contient les fixtures pytest utilisées par plusieurs fichiers de test.
"""

import json
import time as _real_time
from datetime import datetime, timezone
from pathlib import Path
from typing import Dict, Any
from unittest.mock import MagicMock, patch

import pytest


# =============================================================================
# FIXTURES CONFIGURATION
# =============================================================================


@pytest.fixture
def sample_config() -> Dict[str, Any]:
    """Configuration de test minimale."""
    return {
        "site": {
            "latitude": 44.15,
            "longitude": 5.23,
            "fuseau": "Europe/Paris",
            "encoder_mode": "relative",
            "simulation": True,
        },
        "motor": {"steps_per_revolution": 200, "microstepping": 4, "gear_ratio": 2230.0},
        "gpio": {"dir_pin": 17, "step_pin": 18, "ms1_pin": 27, "ms2_pin": 22},
        "dome_offsets": {"meridian_offset": 180.0, "zenith_offset": 180.0},
    }


@pytest.fixture
def temp_config_file(sample_config, tmp_path) -> Path:
    """Crée un fichier config.json temporaire."""
    config_file = tmp_path / "config.json"
    with open(config_file, "w", encoding="utf-8") as f:
        json.dump(sample_config, f)
    return config_file


# =============================================================================
# FIXTURES ASTRONOMIQUES
# =============================================================================


@pytest.fixture
def observation_datetime() -> datetime:
    """Date/heure d'observation fixe pour tests reproductibles."""
    return datetime(2025, 6, 21, 22, 0, 0, tzinfo=timezone.utc)


@pytest.fixture
def known_objects() -> Dict[str, Dict[str, float]]:
    """Objets célestes avec coordonnées connues pour tests."""
    return {
        "M13": {"ra_deg": 250.42, "dec_deg": 36.46, "description": "Amas globulaire d'Hercule"},
        "Vega": {"ra_deg": 279.23, "dec_deg": 38.78, "description": "Etoile brillante de la Lyre"},
        "Polaris": {"ra_deg": 37.95, "dec_deg": 89.26, "description": "Etoile polaire"},
        "NGC6826": {"ra_deg": 296.20, "dec_deg": 50.53, "description": "Nebuleuse du Clin d'Oeil"},
    }


@pytest.fixture
def site_location() -> Dict[str, float]:
    """Coordonnées du site d'observation."""
    return {"latitude": 44.15, "longitude": 5.23, "altitude_m": 800, "fuseau": "Europe/Paris"}


# =============================================================================
# FIXTURES ABAQUE
# =============================================================================


@pytest.fixture
def sample_abaque_data() -> Dict[float, Dict[str, list]]:
    """Données d'abaque simulées pour tests."""
    return {
        30.0: {
            "az_astre": [0, 45, 90, 135, 180, 225, 270, 315],
            "az_coupole": [2, 47, 95, 138, 182, 227, 272, 317],
        },
        45.0: {
            "az_astre": [0, 45, 90, 135, 180, 225, 270, 315],
            "az_coupole": [3, 48, 96, 139, 183, 228, 273, 318],
        },
        60.0: {
            "az_astre": [0, 45, 90, 135, 180, 225, 270, 315],
            "az_coupole": [4, 49, 97, 140, 184, 229, 274, 319],
        },
        75.0: {
            "az_astre": [0, 45, 90, 135, 180, 225, 270, 315],
            "az_coupole": [5, 50, 98, 141, 185, 230, 275, 320],
        },
    }


# =============================================================================
# FIXTURES SIMULATION (ISOLATION)
# =============================================================================


@pytest.fixture(autouse=True)
def reset_simulation_state():
    """
    Reset automatique de l'état de simulation avant chaque test.

    Garantit l'isolation des tests en remettant toutes les positions
    simulées à zéro et en réinitialisant le lecteur daemon global.
    """
    from core.hardware.moteur_simule import reset_all_simulated_positions
    from core.hardware.daemon_encoder_reader import reset_daemon_reader

    reset_all_simulated_positions()
    reset_daemon_reader()
    yield
    reset_all_simulated_positions()
    reset_daemon_reader()


class _NoSleepTime:
    """Proxy du module ``time`` dont seul ``sleep()`` est neutralisé.

    Tout le reste (``time()``, ``monotonic()``…) est délégué au vrai module.
    """

    @staticmethod
    def sleep(*_args, **_kwargs):
        return None

    def __getattr__(self, name):
        return getattr(_real_time, name)


# Modules de SIMULATION dont les ``time.sleep`` ne servent qu'à mimer la durée
# réelle d'un mouvement (timing réaliste voulu en dev, inutile en test). Leurs
# boucles sont toutes à ``elapsed`` manuel ou single-shot → un sleep no-op les
# rend instantanées sans changer la position/les pas vérifiés. AUCUN test
# n'assert sur la durée de ces mouvements.
_SIMULATION_SLEEP_MODULES = (
    "core.hardware.moteur_simule",
    "core.hardware.serial_simulator",
    "services.simulation",
)
# NB : core.hardware.feedback_controller est volontairement EXCLU — son
# time.sleep accompagne un vrai timeout horloge-murale vérifié par
# test_rotation_timeout_global (un sleep no-op le ferait spinner jusqu'au
# plafond d'itérations). Son coût est négligeable (sleep 0.01 s).


@pytest.fixture(autouse=True)
def _neutralize_simulation_sleeps(monkeypatch):
    """Neutralise les ``time.sleep`` des simulateurs moteur/encodeur en test.

    Patch CIBLÉ : on rebinde le nom ``time`` au niveau de chaque module de
    simulation (pas le module ``time`` global). Les modules dépendant du temps
    réel (simulateur cimier, watchdog, synchro threads) ne sont PAS touchés.

    Gain mesuré : la suite passe de ~513 s à quelques dizaines de secondes
    (ex. ``test_rotation_full_circle`` : 145 s → instantané).
    """
    import importlib

    shim = _NoSleepTime()
    for mod_name in _SIMULATION_SLEEP_MODULES:
        try:
            mod = importlib.import_module(mod_name)
        except Exception:
            continue
        if getattr(mod, "time", None) is not None:
            monkeypatch.setattr(mod, "time", shim, raising=False)
    yield


# =============================================================================
# FIXTURES HARDWARE (MOCKS)
# =============================================================================


@pytest.fixture
def mock_gpio():
    """Mock pour les bibliothèques GPIO."""
    with patch.dict(
        "sys.modules",
        {"RPi": MagicMock(), "RPi.GPIO": MagicMock(), "lgpio": MagicMock(), "spidev": MagicMock()},
    ):
        yield


@pytest.fixture
def mock_daemon_encoder_data() -> Dict[str, Any]:
    """Données simulées du daemon encodeur."""
    return {
        "angle": 45.5,
        "raw": 512,
        "total_counts": 47104,
        "timestamp": "2025-06-21T22:00:00",
        "age_ms": 10,
        "calibrated": True,
    }


@pytest.fixture
def mock_encoder_json_file(mock_daemon_encoder_data, tmp_path) -> Path:
    """Crée un fichier JSON daemon simulé."""
    json_file = tmp_path / "ems22_position.json"
    with open(json_file, "w") as f:
        json.dump(mock_daemon_encoder_data, f)
    return json_file


# =============================================================================
# FIXTURES MOTEUR
# =============================================================================


@pytest.fixture
def motor_config() -> Dict[str, Any]:
    """Configuration moteur pour tests."""
    return {
        "steps_per_revolution": 200,
        "microstepping": 4,
        "gear_ratio": 2230.0,
        "steps_correction_factor": 1.08849,
        "dir_pin": 17,
        "step_pin": 18,
        "min_delay": 0.00005,  # 50 microseconds
        "max_delay": 0.01,  # 10 milliseconds
    }


# =============================================================================
# HELPERS
# =============================================================================


def approx_angle(expected: float, rel: float = 1e-3, abs: float = 0.01):
    """Helper pour comparaison d'angles avec tolérance."""
    return pytest.approx(expected, rel=rel, abs=abs)
