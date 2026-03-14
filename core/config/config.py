"""
Configuration minimale, sans dépendance GPIO ni core.utils.

- Lit data/config.json s'il existe, sinon utilise des valeurs par défaut.
- Fournit les constantes attendues (CACHE_FILE, MOTOR_GEAR_RATIO, etc.).
- Calcule get_current_utc_offset() en pur Python (aucun import GPIO).
"""

from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Tuple

# Chemins
DATA_DIR: Path = Path("data")
LOGS_DIR: Path = Path("logs")
CONFIG_FILE: Path = DATA_DIR / "config.json"
CACHE_FILE: Path = DATA_DIR / "objets_cache.json"

# Valeurs par défaut (cohérentes avec ton projet)
DEFAULTS = {
    "site": {
        "latitude": 49.01,
        "longitude": 2.10,
        "tz_offset": None,         # si None: on calcule dynamiquement
        "encoder_mode": "relative",
        "simulation": False,
    },
    "motor": {
        "steps_per_revolution": 200,
        "microstepping": 4,
        "gear_ratio": 2230.0,      # 50×44.6 ≈ 2230
    },
    "gpio": {
        "dir_pin": 17,
        "step_pin": 18,
        "ms1_pin": 27,
        "ms2_pin": 22,
    },
    "dome_offsets": {
        "meridian_offset": 180.0,
        "zenith_offset": 180.0,
    },
}

# Lecture config.json (sans effets de bord)
def _load_json(path: Path) -> dict:
    if not path.exists():
        return {}
    try:
        with path.open("r", encoding="utf-8") as f:
            return json.load(f)
    except Exception:
        return {}

def _deep_update(base: dict, override: dict) -> dict:
    out = dict(base)
    for k, v in override.items():
        if isinstance(v, dict) and isinstance(out.get(k), dict):
            out[k] = _deep_update(out[k], v)
        else:
            out[k] = v
    return out

_config = _deep_update(DEFAULTS, _load_json(CONFIG_FILE))

def get_current_utc_offset() -> int:
    """Décalage local vs UTC en heures (pur Python, pas de GPIO)."""
    now = datetime.now().astimezone()
    off = now.utcoffset() or (now - datetime.now(timezone.utc))
    return int(round(off.total_seconds() / 3600.0))

# Expose a few top-level convenience values expected elsewhere
SITE_LATITUDE: float  = float(_config["site"]["latitude"])
SITE_LONGITUDE: float = float(_config["site"]["longitude"])
SITE_TZ_OFFSET = (
    int(_config["site"]["tz_offset"])
    if _config["site"]["tz_offset"] is not None
    else get_current_utc_offset()
)

ENCODER_MODE: str = str(_config["site"].get("encoder_mode", "relative")).lower()
SIMULATION: bool = bool(_config["site"].get("simulation", False))

MOTOR_STEPS_PER_REV: int = int(_config["motor"]["steps_per_revolution"])
MOTOR_MICROSTEPPING: int = int(_config["motor"]["microstepping"])
MOTOR_GEAR_RATIO: float  = float(_config["motor"]["gear_ratio"])

GPIO_PINS = dict(_config["gpio"])
DOME_OFFSETS = dict(_config["dome_offsets"])

# Helpers pour le reste de l’app (lecture simple et centralisée)
def get_site_config() -> Tuple[float, float, int, str, bool]:
    """
    Retourne (latitude, longitude, tz_offset, encoder_mode, simulation).
    """
    return SITE_LATITUDE, SITE_LONGITUDE, SITE_TZ_OFFSET, ENCODER_MODE, SIMULATION

def get_motor_config() -> dict:
    """
    steps_per_revolution, microstepping, gear_ratio
    """
    return {
        "steps_per_revolution": MOTOR_STEPS_PER_REV,
        "microstepping": MOTOR_MICROSTEPPING,
        "gear_ratio": MOTOR_GEAR_RATIO,
    }

def save_config() -> None:
    """Sauvegarde l'état courant (facultatif, utilisé si tu veux modifier à chaud)."""
    DATA_DIR.mkdir(parents=True, exist_ok=True)
    out = {
        "site": {
            "latitude": SITE_LATITUDE,
            "longitude": SITE_LONGITUDE,
            "tz_offset": SITE_TZ_OFFSET,
            "encoder_mode": ENCODER_MODE,
            "simulation": SIMULATION,
        },
        "motor": get_motor_config(),
        "gpio": GPIO_PINS,
        "dome_offsets": DOME_OFFSETS,
    }
    with CONFIG_FILE.open("w", encoding="utf-8") as f:
        json.dump(out, f, indent=2, ensure_ascii=False)
