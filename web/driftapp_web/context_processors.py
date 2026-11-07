"""Context processors pour DriftApp."""

import json
from datetime import datetime
from pathlib import Path

try:
    import tomllib
except ImportError:
    import tomli as tomllib  # Python < 3.11 fallback

_version_cache = None

# Écrit par scripts/update_driftapp.sh (lu aussi par /api/health/update/status/).
UPDATE_STATUS_FILE = Path(__file__).resolve().parent.parent.parent / "logs" / "update_status.json"


def _get_version():
    """Lit la version depuis pyproject.toml (cachée après premier appel)."""
    global _version_cache
    if _version_cache is None:
        pyproject = Path(__file__).resolve().parent.parent.parent / "pyproject.toml"
        try:
            with open(pyproject, "rb") as f:
                data = tomllib.load(f)
            _version_cache = data.get("project", {}).get("version", "unknown")
        except (FileNotFoundError, KeyError):
            _version_cache = "unknown"
    return _version_cache


def app_version(request):
    """Injecte APP_VERSION dans tous les templates."""
    return {"APP_VERSION": _get_version()}


def last_software_update(request):
    """Date de la dernière mise à jour réussie du logiciel (pied de page du dashboard).

    None si aucune mise à jour n'a abouti : jamais lancée (dev), en cours ou en
    échec (le fichier ne garde que la dernière tentative).
    """
    try:
        status = json.loads(UPDATE_STATUS_FILE.read_text())
        if status.get("phase") != "done" or status.get("success") is not True:
            raise ValueError("pas de mise à jour réussie")
        when = datetime.strptime(status["timestamp"], "%Y-%m-%d %H:%M:%S")
    except (OSError, ValueError, KeyError, TypeError):
        return {"LAST_SOFTWARE_UPDATE": None}
    return {"LAST_SOFTWARE_UPDATE": when.strftime("%d/%m/%Y à %H:%M")}


def site_coords(request):
    """Injecte les coordonnées du site (calcul solaire du mode nuit, theme.js)."""
    from core.config.config import SITE_LATITUDE, SITE_LONGITUDE

    return {"SITE_LAT": SITE_LATITUDE, "SITE_LON": SITE_LONGITUDE}
