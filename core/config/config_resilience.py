"""Noyau de résilience de data/config.json (chantier A).

Stdlib-pur (aucun import projet) pour pouvoir tourner avant tout chargement de
configuration. Voir docs/superpowers/specs/2026-06-19-config-resilience-design.md.
"""

from __future__ import annotations

import json
import os
from pathlib import Path

_PROJECT_ROOT = Path(__file__).resolve().parent.parent.parent
DEFAULT_CONFIG_PATH = _PROJECT_ROOT / "data" / "config.json"
DEFAULT_TEMPLATE_PATH = _PROJECT_ROOT / "data" / "config.template.json"
DEFAULT_BACKUP_PATH = _PROJECT_ROOT / "data" / ".config.lastgood.json"


def _atomic_write_json(path: Path, data: dict) -> None:
    """Écrit `data` en JSON de façon atomique (tmp + os.replace)."""
    tmp = path.parent / (path.name + ".tmp")
    with open(tmp, "w", encoding="utf-8") as f:
        json.dump(data, f, indent=2, ensure_ascii=False)
        f.write("\n")
    os.replace(tmp, path)


def _collect_leaf_paths(value, prefix: str, out: list[str]) -> None:
    """Ajoute à `out` tous les chemins de feuilles sous `value`."""
    if isinstance(value, dict) and value:
        for k, v in value.items():
            _collect_leaf_paths(v, f"{prefix}.{k}" if prefix else k, out)
    else:
        out.append(prefix)


def _structural_merge(
    user: dict, template: dict, prefix: str = ""
) -> tuple[dict, list[str], list[str]]:
    """Merge la STRUCTURE du template dans `user`, en préservant les VALEURS user.

    Retourne (merged, added_paths, removed_paths).
    - clé des deux côtés, dicts → récursion ; sinon → valeur user gardée (Option 1)
    - clé template seule → défaut du template (added)
    - clé user seule → retirée (removed)
    """
    added: list[str] = []
    removed: list[str] = []
    merged: dict = {}
    for key, tmpl_val in template.items():
        path = f"{prefix}.{key}" if prefix else key
        if key in user:
            user_val = user[key]
            if isinstance(tmpl_val, dict) and isinstance(user_val, dict):
                sub, sub_add, sub_rem = _structural_merge(user_val, tmpl_val, path)
                merged[key] = sub
                added.extend(sub_add)
                removed.extend(sub_rem)
            else:
                merged[key] = user_val  # valeur user sacrée
        else:
            merged[key] = tmpl_val
            _collect_leaf_paths(tmpl_val, path, added)
    for key in user:
        if key not in template:
            removed.append(f"{prefix}.{key}" if prefix else key)
    return merged, added, removed
