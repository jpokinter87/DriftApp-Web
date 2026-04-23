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
from zoneinfo import ZoneInfo

# Chemins (absolus depuis la racine du projet)
_PROJECT_ROOT: Path = Path(__file__).resolve().parent.parent.parent
DATA_DIR: Path = _PROJECT_ROOT / "data"
LOGS_DIR: Path = _PROJECT_ROOT / "logs"
CONFIG_FILE: Path = DATA_DIR / "config.json"
CACHE_FILE: Path = DATA_DIR / "objets_cache.json"

# Valeurs par défaut (cohérentes avec ton projet)
DEFAULTS = {
    "site": {
        "latitude": 49.01,
        "longitude": 2.10,
        "fuseau": "Europe/Paris",
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
    except (json.JSONDecodeError, FileNotFoundError, OSError) as e:
        import logging
        logging.getLogger(__name__).warning(f"Erreur chargement config {path}: {e}")
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

def get_current_utc_offset(fuseau: str | None = None) -> int:
    """Décalage UTC en heures pour le fuseau donné, à l'instant présent.

    Gère automatiquement l'heure d'été/hiver via zoneinfo.
    """
    if fuseau:
        tz = ZoneInfo(fuseau)
    else:
        tz = datetime.now().astimezone().tzinfo
    now = datetime.now(tz)
    off = now.utcoffset()
    return int(round(off.total_seconds() / 3600.0))

# Expose a few top-level convenience values expected elsewhere
SITE_LATITUDE: float  = float(_config["site"]["latitude"])
SITE_LONGITUDE: float = float(_config["site"]["longitude"])
SITE_FUSEAU: str = str(_config["site"].get("fuseau", "Europe/Paris"))

def get_site_tz_offset() -> int:
    """Offset UTC actuel pour le fuseau du site (DST-aware)."""
    return get_current_utc_offset(SITE_FUSEAU)

# Rétro-compatibilité : les appelants qui lisent SITE_TZ_OFFSET obtiennent
# la valeur correcte au moment de l'import. Pour un calcul précis en cours
# de session (transit méridien etc.), utiliser get_site_tz_offset().
SITE_TZ_OFFSET: int = get_site_tz_offset()

ENCODER_MODE: str = str(_config["site"].get("encoder_mode", "relative")).lower()
SIMULATION: bool = bool(_config["site"].get("simulation", False))

# Vitesse unique du suivi (v5.10) : ex-mode CONTINUOUS validé terrain 22/03/2026.
# En dur dans le code — si un jour reconfigurable, ajouter une clé
# `motor_driver.delay_us` dans config.json.
SINGLE_SPEED_MOTOR_DELAY: float = 0.00026   # 260 µs / pas ≈ 40°/min (limite DM860T)
SINGLE_SPEED_CHECK_INTERVAL_S: int = 30     # secondes entre deux corrections
SINGLE_SPEED_CORRECTION_THRESHOLD_DEG: float = 0.3  # seuil au-delà duquel on corrige

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
    return SITE_LATITUDE, SITE_LONGITUDE, get_site_tz_offset(), ENCODER_MODE, SIMULATION

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
            "fuseau": SITE_FUSEAU,
            "encoder_mode": ENCODER_MODE,
            "simulation": SIMULATION,
        },
        "motor": get_motor_config(),
        "gpio": GPIO_PINS,
        "dome_offsets": DOME_OFFSETS,
    }
    with CONFIG_FILE.open("w", encoding="utf-8") as f:
        json.dump(out, f, indent=2, ensure_ascii=False)
