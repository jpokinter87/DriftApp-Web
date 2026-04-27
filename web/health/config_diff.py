"""
Utilitaire de diff `data/config.json` local vs upstream (origin/main).

Sert à présenter à l'utilisateur les changements de config avant la MAJ OTA,
pour qu'il choisisse explicitement entre garder son config local ou prendre
celui du dépôt (v5.12.0).

API publique :
- `diff_config(local, upstream)` → liste de diffs structurés (clé par clé)
- `fetch_upstream_config(project_root)` → dict, contenu de data/config.json
                                          sur origin/main (fait `git fetch`)
- `get_config_diff(project_root)` → dict {has_diff, diffs, error}
"""

from __future__ import annotations

import json
import logging
import subprocess
from pathlib import Path
from typing import Any

logger = logging.getLogger(__name__)


def diff_config(local: dict, upstream: dict, prefix: str = "") -> list[dict]:
    """Compare deux dicts de config et renvoie la liste des différences.

    Format du résultat : list[{path, op, local, upstream}] où :
    - path : chemin pointé (ex. "meridian_anticipation.enabled")
    - op : "added" (clé absente en local), "removed" (absente upstream), "modified"
    - local, upstream : valeurs (None pour clé absente)

    Les clés commençant par `_comment` sont ignorées (commentaires inline JSON).
    Les sous-dicts sont parcourus récursivement.
    """
    diffs: list[dict] = []
    all_keys = set(local.keys()) | set(upstream.keys())
    for key in sorted(all_keys):
        if key.startswith("_comment"):
            continue
        path = f"{prefix}.{key}" if prefix else key
        in_local = key in local
        in_upstream = key in upstream
        if not in_local:
            diffs.append({
                "path": path, "op": "added",
                "local": None, "upstream": upstream[key],
            })
        elif not in_upstream:
            diffs.append({
                "path": path, "op": "removed",
                "local": local[key], "upstream": None,
            })
        elif isinstance(local[key], dict) and isinstance(upstream[key], dict):
            diffs.extend(diff_config(local[key], upstream[key], path))
        elif local[key] != upstream[key]:
            diffs.append({
                "path": path, "op": "modified",
                "local": local[key], "upstream": upstream[key],
            })
    return diffs


def fetch_upstream_config(project_root: Path,
                          relative_path: str = "data/config.json") -> dict[str, Any]:
    """Renvoie le contenu de `<relative_path>` sur origin/main.

    Effectue un `git fetch origin main` au préalable. Lève `RuntimeError` si
    git échoue ou si le fichier upstream n'est pas du JSON valide.
    """
    try:
        subprocess.run(
            ["git", "fetch", "origin", "main"],
            cwd=str(project_root),
            check=True,
            capture_output=True,
            timeout=30,
        )
    except (subprocess.CalledProcessError, subprocess.TimeoutExpired) as e:
        raise RuntimeError(f"git fetch a échoué : {e}") from e

    try:
        result = subprocess.run(
            ["git", "show", f"origin/main:{relative_path}"],
            cwd=str(project_root),
            check=True,
            capture_output=True,
            text=True,
            timeout=10,
        )
    except subprocess.CalledProcessError as e:
        raise RuntimeError(
            f"git show origin/main:{relative_path} a échoué : {e.stderr}"
        ) from e

    try:
        return json.loads(result.stdout)
    except json.JSONDecodeError as e:
        raise RuntimeError(
            f"config upstream non parsable : {e}"
        ) from e


def get_config_diff(project_root: Path,
                    relative_path: str = "data/config.json") -> dict[str, Any]:
    """Renvoie le diff entre config local et upstream, au format API.

    Format : {has_diff: bool, diffs: list, local_exists: bool, error: str|None}
    """
    local_path = project_root / relative_path
    if not local_path.exists():
        return {
            "has_diff": False,
            "diffs": [],
            "local_exists": False,
            "error": f"Fichier local introuvable : {relative_path}",
        }

    try:
        with local_path.open() as fh:
            local = json.load(fh)
    except (OSError, json.JSONDecodeError) as e:
        return {
            "has_diff": False,
            "diffs": [],
            "local_exists": True,
            "error": f"config local non parsable : {e}",
        }

    try:
        upstream = fetch_upstream_config(project_root, relative_path)
    except RuntimeError as e:
        return {
            "has_diff": False,
            "diffs": [],
            "local_exists": True,
            "error": str(e),
        }

    diffs = diff_config(local, upstream)
    return {
        "has_diff": len(diffs) > 0,
        "diffs": diffs,
        "local_exists": True,
        "error": None,
    }
