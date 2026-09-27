"""
Configuration minimale, sans dépendance GPIO ni core.utils.

- Lit data/config.json s'il existe, sinon utilise des valeurs par défaut.
- Fournit les constantes attendues (CACHE_FILE, MOTOR_GEAR_RATIO, etc.).
- Calcule get_current_utc_offset() en pur Python (aucun import GPIO).
"""

from __future__ import annotations

import json
from datetime import datetime
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

# Vitesse unique du suivi (v5.10), reconfigurable depuis v6.16 via la clé
# `motor_driver.delay_us` de config.json (page Configuration → Avancé).
#
# Le défaut 260 µs (≈ 43°/min) reproduit à l'identique le comportement v5.10.
# Ce n'était pas une limite du driver : les campagnes de décembre 2025 (GPIO) et
# de mars 2026 (firmware RP2040 v1) ont toutes deux mesuré le plafond de la
# couche logicielle de l'époque — 121 µs/pas de surcoût Python pour la première,
# le coût par pas de MicroPython pour la seconde. Depuis que le PIO génère la
# croisière en autonome (v5.4), plus rien ne borne la vitesse côté logiciel.
# Bornes : 100 µs (au-delà de l'UPAN mesuré à 96°/min, garde-fou anti-faute de
# frappe) et 3000 µs (RAMP_START_DELAY_US — au-dessus, la rampe s'inverserait).
DEFAULT_MOTOR_DELAY_US: float = 260.0
MOTOR_DELAY_US_MIN: float = 100.0
MOTOR_DELAY_US_MAX: float = 3000.0


def _resolve_borne(
    motor_driver_cfg: dict, key: str, default: float, vmin: float, vmax: float, unite: str
) -> float:
    """Valeur numérique de `motor_driver.<key>`, bornée à [vmin, vmax].

    La valeur étant éditable depuis l'interface web, une saisie absente,
    non numérique ou hors bornes retombe sur une valeur sûre plutôt que
    d'être transmise telle quelle au moteur.
    """
    import logging

    raw = motor_driver_cfg.get(key, default)
    try:
        value = float(raw)
    except (TypeError, ValueError):
        logging.getLogger(__name__).warning(
            f"motor_driver.{key} invalide ({raw!r}) — repli sur {default} {unite}"
        )
        return default

    if not vmin <= value <= vmax:
        clamped = min(max(value, vmin), vmax)
        logging.getLogger(__name__).warning(
            f"motor_driver.{key}={value} {unite} hors bornes "
            f"[{vmin}, {vmax}] — borné à {clamped} {unite}"
        )
        return clamped

    return value


def resolve_motor_delay_us(
    motor_driver_cfg: dict,
    key: str = "delay_us",
    default: float = DEFAULT_MOTOR_DELAY_US,
) -> float:
    """Délai moteur en µs/pas issu de `motor_driver.<key>`, borné.

    Args:
        motor_driver_cfg: Section `motor_driver` de config.json.
        key: Clé lue (`delay_us` ou `fast_delay_us`).
        default: Valeur si la clé est absente ou invalide.

    Returns:
        Délai en microsecondes par pas.
    """
    return _resolve_borne(
        motor_driver_cfg, key, default, MOTOR_DELAY_US_MIN, MOTOR_DELAY_US_MAX, "µs"
    )


SINGLE_SPEED_MOTOR_DELAY: float = (
    resolve_motor_delay_us(_config.get("motor_driver", {})) / 1_000_000
)

# Deux vitesses (v6.18). Depuis le flash du firmware v6.16, la coupole tient
# 90°/min (mesuré à l'encodeur le 27/09/2026, 124 µs). Mais sous 1° la rampe
# domine la durée (0,3° : 1,79 s à 260 µs, 1,64 s à 124 µs), et c'est là que
# le firmware raccourcit la rampe (< 1000 pas) ou la supprime (< 200 pas) —
# seule la rampe complète a été validée à haute vitesse. D'où :
#   - SINGLE_SPEED_MOTOR_DELAY (`delay_us`) : déplacements < 3° (corrections
#     de suivi, itérations finales de la boucle de retour) ;
#   - FAST_MOTOR_DELAY (`fast_delay_us`) : déplacements ≥ 3° (GOTO, bascule
#     méridien, parking, JOG ±10°) et mode continu.
# Clé absente → même valeur que `delay_us` : comportement v6.17 inchangé.
# 3° reprend la frontière GOTO direct / GOTO avec boucle de retour (v4.4).
FAST_SPEED_MIN_DEG: float = 3.0
FAST_MOTOR_DELAY: float = (
    resolve_motor_delay_us(
        _config.get("motor_driver", {}),
        key="fast_delay_us",
        default=SINGLE_SPEED_MOTOR_DELAY * 1_000_000,
    )
    / 1_000_000
)


# Rampe à accélération constante (v6.19) : vitesse rapide atteinte en
# `motor_driver.ramp_time_s` (défaut 2 s). L'accélération est transmise au
# Pico en 6e jeton de MOVE et vaut pour tous les mouvements (v6.19.1) : un
# mouvement à 260 µs atteint sa vitesse en ~0,9 s. STOP doux sous 260 µs
# seulement.
DEFAULT_RAMP_TIME_S: float = 2.0
RAMP_TIME_S_MIN: float = 0.5
RAMP_TIME_S_MAX: float = 10.0


def resolve_ramp_time_s(motor_driver_cfg: dict) -> float:
    """Durée (s) de la rampe jusqu'à la vitesse rapide, bornée."""
    return _resolve_borne(
        motor_driver_cfg, "ramp_time_s", DEFAULT_RAMP_TIME_S,
        RAMP_TIME_S_MIN, RAMP_TIME_S_MAX, "s",
    )


def fast_accel_steps_s2(fast_delay_s: float, ramp_time_s: float) -> int:
    """Accélération (pas/s²) pour atteindre la vitesse rapide en `ramp_time_s`."""
    return round((1.0 / fast_delay_s) / ramp_time_s)


RAMP_TIME_S: float = resolve_ramp_time_s(_config.get("motor_driver", {}))
FAST_ACCEL_STEPS_S2: int = fast_accel_steps_s2(FAST_MOTOR_DELAY, RAMP_TIME_S)


def motor_delay_for(delta_deg: float, slow: float = None, fast: float = None) -> float:
    """Délai moteur (s/pas) adapté à l'amplitude d'une rotation.

    `slow`/`fast` par défaut : les constantes du module, lues à l'appel.
    """
    if abs(delta_deg) >= FAST_SPEED_MIN_DEG:
        return FAST_MOTOR_DELAY if fast is None else fast
    return SINGLE_SPEED_MOTOR_DELAY if slow is None else slow

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
