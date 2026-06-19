"""Noyau de résilience de data/config.json (chantier A).

Stdlib-pur (aucun import projet) pour pouvoir tourner avant tout chargement de
configuration. Voir docs/superpowers/specs/2026-06-19-config-resilience-design.md.
"""

from __future__ import annotations

import json
import os
from dataclasses import dataclass, field
from pathlib import Path

_PROJECT_ROOT = Path(__file__).resolve().parent.parent.parent
DEFAULT_CONFIG_PATH = _PROJECT_ROOT / "data" / "config.json"
DEFAULT_TEMPLATE_PATH = _PROJECT_ROOT / "data" / "config.template.json"
DEFAULT_BACKUP_PATH = _PROJECT_ROOT / "data" / ".config.lastgood.json"


def _atomic_write_json(path: Path, data: dict) -> None:
    """Écrit `data` en JSON de façon atomique (tmp unique par process + os.replace)."""
    tmp = path.parent / f"{path.name}.{os.getpid()}.tmp"
    try:
        with open(tmp, "w", encoding="utf-8") as f:
            json.dump(data, f, indent=2, ensure_ascii=False)
            f.write("\n")
        os.replace(tmp, path)
    finally:
        if tmp.exists():
            tmp.unlink(missing_ok=True)


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
            if not key.startswith("_"):
                _collect_leaf_paths(tmpl_val, path, added)
    for key in user:
        if key not in template and not key.startswith("_"):
            removed.append(f"{prefix}.{key}" if prefix else key)
    return merged, added, removed


@dataclass
class ConfigReport:
    status: str
    added: list[str] = field(default_factory=list)
    removed: list[str] = field(default_factory=list)
    backup_timestamp: str | None = None
    message: str = ""


_REPORT_CACHE: dict[str, ConfigReport] = {}


def _load_json_or_none(path: Path) -> dict | None:
    try:
        with path.open("r", encoding="utf-8") as f:
            return json.load(f)
    except (OSError, json.JSONDecodeError):
        return None


def _backup_mtime_iso(path: Path) -> str | None:
    if not path.exists():
        return None
    import datetime

    ts = path.stat().st_mtime
    return datetime.datetime.fromtimestamp(ts, datetime.timezone.utc).isoformat()


def _run_ensure(config_path: Path, template_path: Path, backup_path: Path) -> ConfigReport:
    template = _load_json_or_none(template_path)
    if template is None:
        raise RuntimeError(f"Template introuvable ou invalide : {template_path}")

    backup_ts = _backup_mtime_iso(backup_path)

    # 1. Déterminer la config de base + le statut primaire.
    if not config_path.exists():
        backup = _load_json_or_none(backup_path)
        if backup is not None:
            user, status = backup, "restored_from_backup"
        else:
            user, status = dict(template), "bootstrapped_from_template"
    else:
        parsed = _load_json_or_none(config_path)
        if parsed is not None:
            user, status = parsed, "unchanged"
        else:
            backup = _load_json_or_none(backup_path)
            if backup is not None:
                user, status = backup, "recovered_corruption"
            else:
                user, status = dict(template), "corruption_no_backup"

    # 2. Merge structurel vs template.
    merged, added, removed = _structural_merge(user, template)

    # 3. Décider d'écrire config.json.
    structural_change = bool(added or removed)
    if status == "unchanged":
        if structural_change:
            status = "migrated"
            _atomic_write_json(config_path, merged)
        # sinon : on ne réécrit rien (intact au bit près)
    else:
        _atomic_write_json(config_path, merged)

    # 4. lastgood = config valide finale.
    _atomic_write_json(backup_path, merged)

    return ConfigReport(
        status=status,
        added=added,
        removed=removed,
        backup_timestamp=backup_ts,
        message=_message_for(status, added, removed, backup_ts),
    )


def _message_for(status, added, removed, backup_ts) -> str:
    if status == "unchanged":
        return "Configuration inchangée."
    if status == "migrated":
        return (
            f"Configuration migrée : {len(added)} paramètre(s) ajouté(s) "
            f"à leur valeur par défaut. Tes réglages ont été conservés."
        )
    if status == "restored_from_backup":
        return f"config.json absent — restauré depuis la sauvegarde du {backup_ts}."
    if status == "recovered_corruption":
        return f"config.json illisible — restauré depuis la sauvegarde du {backup_ts}."
    if status == "bootstrapped_from_template":
        return "Première config générée depuis le gabarit — à renseigner."
    if status == "corruption_no_backup":
        return (
            "config.json corrompu et aucune sauvegarde — valeurs par défaut "
            "chargées, reconfiguration requise."
        )
    return ""


def ensure_config_ready(
    config_path: Path = DEFAULT_CONFIG_PATH,
    template_path: Path = DEFAULT_TEMPLATE_PATH,
    backup_path: Path = DEFAULT_BACKUP_PATH,
    *,
    force: bool = False,
) -> ConfigReport:
    """Garantit un config.json valide et à jour structurellement. Mémoïsé par process."""
    key = str(config_path)
    if not force and key in _REPORT_CACHE:
        return _REPORT_CACHE[key]
    report = _run_ensure(config_path, template_path, backup_path)
    _REPORT_CACHE[key] = report
    return report
