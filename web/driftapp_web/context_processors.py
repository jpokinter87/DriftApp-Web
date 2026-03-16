"""Context processors pour DriftApp."""

from pathlib import Path

try:
    import tomllib
except ImportError:
    import tomli as tomllib  # Python < 3.11 fallback

_version_cache = None


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
