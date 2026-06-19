# Chantier A — Noyau de résilience config.json — Plan d'implémentation

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Rendre `data/config.json` immunisé contre l'écrasement par git et la corruption : dé-tracker le fichier, migrer sa structure automatiquement en préservant les valeurs, et restaurer depuis une copie cachée en cas de corruption.

**Architecture:** Un module stdlib-pur `core/config/config_resilience.py` expose `ensure_config_ready(config, template, backup)` qui (1) bootstrap depuis un template tracké si absent, (2) restaure depuis `.config.lastgood.json` si illisible, (3) fait un merge structurel préservant les valeurs utilisateur vs le template. Appelé au démarrage de chaque process et en tête de `ConfigLoader.load()`. L'ancien mécanisme OTA de conflit `config.json` (diff-UI, stash/checkout) est retiré, remplacé par un rapport de migration automatique.

**Tech Stack:** Python 3 (stdlib : `json`, `os`, `pathlib`, `shutil`, `dataclasses`), pytest, Django (vues health), JS vanilla (dashboard).

**Spec de référence:** `docs/superpowers/specs/2026-06-19-config-resilience-design.md`

**Branche:** `feat/config-resilience` (déjà créée, spec committé).

**Règle de commit:** chaque tâche se termine par un commit. Les messages se terminent par `Co-Authored-By: Claude Opus 4.8 (1M context) <noreply@anthropic.com>`. **Pas de bump `pyproject.toml`** tant que le chantier A n'est pas terminé et validé (on bumpera au commit final de release).

---

## File Structure

| Fichier | Responsabilité | Action |
|---|---|---|
| `data/config.template.json` | Squelette + défauts tracké (= contenu repo actuel de config.json) | Créer |
| `data/config.json` | Valeurs terrain, dé-tracké | Untrack |
| `.gitignore` | Ignorer config.json, lastgood, tmp | Modifier |
| `core/config/config_resilience.py` | Bootstrap / restore / merge structurel / écriture atomique | Créer |
| `tests/test_config_resilience.py` | Tests unitaires du module | Créer |
| `core/config/config_loader.py` | Appel `ensure_config_ready` en tête de `load()` | Modifier (~458-474) |
| `services/motor_service.py` | Appel au démarrage + écriture IPC report | Modifier (main) |
| `services/cimier_service.py` | Appel au démarrage + écriture IPC report | Modifier (main) |
| `web/cimier/apps.py` (ou nouvelle AppConfig) | Appel Django `ready()` + écriture IPC report | Modifier |
| `web/health/views.py` | Exposer config_status ; retirer `config_diff_view` ; simplifier `apply_update` | Modifier |
| `web/health/urls.py` | Retirer route `update/config_diff/` | Modifier (~20) |
| `web/health/config_diff.py` | Diff-UI obsolète | Supprimer |
| `web/static/js/dashboard.js` | Retirer fetch config_diff + bannière config | Modifier (~2556-2620) |
| `web/templates/dashboard.html` | Retirer modale diff + ajouter bannière config | Modifier |
| `scripts/update_driftapp.sh` | Retirer la danse `CONFIG_STRATEGY=reset` sur config.json | Modifier (~48,66,77,170-188,449-489) |
| `tests/test_ota_uvlock.py` | Adapter aux suppressions | Modifier |

---

## Task 1: Migration git — dé-tracker config.json, créer le template, ignorer

**Files:**
- Create: `data/config.template.json`
- Modify: `.gitignore`
- Untrack: `data/config.json`

- [ ] **Step 1: Créer le template depuis le config.json actuel du dépôt**

Le template doit être le contenu **versionné** (origin/main) de config.json — le gabarit repo « propre » (hosts noop/vides), pas une éventuelle copie locale modifiée.

```bash
git show HEAD:data/config.json > data/config.template.json
```

- [ ] **Step 2: Vérifier que le template est du JSON valide**

Run: `python3 -c "import json; json.load(open('data/config.template.json')); print('OK template valide')"`
Expected: `OK template valide`

- [ ] **Step 3: Dé-tracker config.json (garde le fichier sur le disque)**

```bash
git rm --cached data/config.json
```
Expected: `rm 'data/config.json'` — et `ls data/config.json` montre que le fichier existe toujours sur le disque.

- [ ] **Step 4: Ajouter les entrées .gitignore**

Ajouter à la fin de `.gitignore` :

```gitignore

# Config terrain résiliente (chantier A) — voir docs/superpowers/specs/2026-06-19-config-resilience-design.md
data/config.json
data/.config.lastgood.json
data/config.json.tmp
```

- [ ] **Step 5: Vérifier l'état git**

Run: `git status --porcelain data/ .gitignore`
Expected : `config.template.json` en ajout (`A`), `config.json` en suppression de l'index (`D`) puis ignoré, `.gitignore` modifié (`M`). Vérifier ensuite :
Run: `git check-ignore data/config.json && echo IGNORED`
Expected: `data/config.json` puis `IGNORED`.

- [ ] **Step 6: Commit**

```bash
git add data/config.template.json .gitignore
git rm --cached data/config.json 2>/dev/null || true
git commit -m "build(config): dé-tracke config.json, ajoute config.template.json tracké

config.json devient un fichier terrain non versionné (.gitignore) ; le gabarit
repo vit dans config.template.json. git pull ne peut plus écraser les valeurs.

Co-Authored-By: Claude Opus 4.8 (1M context) <noreply@anthropic.com>"
```

---

## Task 2: Helpers purs — merge structurel + écriture atomique (TDD)

**Files:**
- Create: `core/config/config_resilience.py`
- Test: `tests/test_config_resilience.py`

- [ ] **Step 1: Écrire les tests des helpers purs**

Créer `tests/test_config_resilience.py` :

```python
"""Tests du noyau de résilience config (merge structurel + écriture atomique)."""
import json

from core.config.config_resilience import _structural_merge, _atomic_write_json


class TestStructuralMerge:
    def test_structure_identique_preserve_valeurs(self):
        user = {"a": 1, "b": {"c": 2}}
        template = {"a": 0, "b": {"c": 0}}
        merged, added, removed = _structural_merge(user, template)
        assert merged == {"a": 1, "b": {"c": 2}}  # valeurs user gardées
        assert added == []
        assert removed == []

    def test_nouvelle_cle_prend_le_defaut_template(self):
        user = {"a": 1}
        template = {"a": 0, "nouveau": 42}
        merged, added, removed = _structural_merge(user, template)
        assert merged == {"a": 1, "nouveau": 42}
        assert added == ["nouveau"]
        assert removed == []

    def test_cle_obsolete_retiree(self):
        user = {"a": 1, "vieux": 99}
        template = {"a": 0}
        merged, added, removed = _structural_merge(user, template)
        assert merged == {"a": 1}
        assert added == []
        assert removed == ["vieux"]

    def test_cles_imbriquees_chemins_pointes(self):
        user = {"cimier": {"motor_shelly": {"host_motor": "192.168.1.85"}}}
        template = {"cimier": {"motor_shelly": {"host_motor": "", "host_dir": ""}}}
        merged, added, removed = _structural_merge(user, template)
        assert merged["cimier"]["motor_shelly"]["host_motor"] == "192.168.1.85"
        assert merged["cimier"]["motor_shelly"]["host_dir"] == ""
        assert added == ["cimier.motor_shelly.host_dir"]
        assert removed == []

    def test_defaut_change_sur_cle_commune_valeur_user_conservee(self):
        # Verrou Option 1 : un changement de défaut n'est jamais propagé.
        user = {"motor_on_relay_state": True}
        template = {"motor_on_relay_state": False}
        merged, added, removed = _structural_merge(user, template)
        assert merged["motor_on_relay_state"] is True
        assert added == []
        assert removed == []


class TestAtomicWrite:
    def test_ecrit_via_tmp_puis_remplace(self, tmp_path):
        target = tmp_path / "config.json"
        _atomic_write_json(target, {"x": 1})
        assert json.loads(target.read_text()) == {"x": 1}
        # le .tmp ne doit pas subsister
        assert not (tmp_path / "config.json.tmp").exists()

    def test_remplace_un_fichier_existant(self, tmp_path):
        target = tmp_path / "config.json"
        target.write_text('{"old": true}')
        _atomic_write_json(target, {"new": True})
        assert json.loads(target.read_text()) == {"new": True}
```

- [ ] **Step 2: Lancer les tests, vérifier l'échec**

Run: `uv run --extra dev pytest tests/test_config_resilience.py -v`
Expected: FAIL — `ImportError` / `ModuleNotFoundError: core.config.config_resilience`.

- [ ] **Step 3: Implémenter les helpers purs**

Créer `core/config/config_resilience.py` :

```python
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


def _structural_merge(user: dict, template: dict, prefix: str = "") -> tuple[dict, list[str], list[str]]:
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
```

- [ ] **Step 4: Lancer les tests, vérifier qu'ils passent**

Run: `uv run --extra dev pytest tests/test_config_resilience.py -v`
Expected: PASS (7 tests).

- [ ] **Step 5: Format + lint**

Run: `uv run --extra dev ruff format core/config/config_resilience.py tests/test_config_resilience.py && uv run --extra dev ruff check core/config/config_resilience.py tests/test_config_resilience.py`
Expected: pas d'erreur.

- [ ] **Step 6: Commit**

```bash
git add core/config/config_resilience.py tests/test_config_resilience.py
git commit -m "feat(config): merge structurel + écriture atomique (helpers purs)

Co-Authored-By: Claude Opus 4.8 (1M context) <noreply@anthropic.com>"
```

---

## Task 3: Orchestration `ensure_config_ready` — bootstrap / restore / merge (TDD)

**Files:**
- Modify: `core/config/config_resilience.py`
- Test: `tests/test_config_resilience.py`

- [ ] **Step 1: Écrire les tests d'orchestration**

Ajouter à `tests/test_config_resilience.py` :

```python
import json as _json
from dataclasses import asdict

from core.config.config_resilience import ensure_config_ready, ConfigReport


def _write(p, data):
    p.write_text(_json.dumps(data), encoding="utf-8")


class TestEnsureConfigReady:
    def _paths(self, tmp_path):
        return (tmp_path / "config.json",
                tmp_path / "config.template.json",
                tmp_path / ".config.lastgood.json")

    def test_unchanged_ne_reecrit_pas_le_fichier(self, tmp_path):
        cfg, tpl, bak = self._paths(tmp_path)
        _write(tpl, {"a": 0})
        _write(cfg, {"a": 7})
        mtime_avant = cfg.stat().st_mtime_ns
        report = ensure_config_ready(cfg, tpl, bak, force=True)
        assert report.status == "unchanged"
        assert cfg.stat().st_mtime_ns == mtime_avant  # intact au bit près
        assert _json.loads(cfg.read_text()) == {"a": 7}

    def test_migrated_ajoute_nouvelle_cle_garde_valeurs(self, tmp_path):
        cfg, tpl, bak = self._paths(tmp_path)
        _write(tpl, {"a": 0, "nouveau": 42})
        _write(cfg, {"a": 7})
        report = ensure_config_ready(cfg, tpl, bak, force=True)
        assert report.status == "migrated"
        assert report.added == ["nouveau"]
        assert _json.loads(cfg.read_text()) == {"a": 7, "nouveau": 42}

    def test_bootstrap_depuis_template_si_absent(self, tmp_path):
        cfg, tpl, bak = self._paths(tmp_path)
        _write(tpl, {"a": 0, "b": 1})
        report = ensure_config_ready(cfg, tpl, bak, force=True)
        assert report.status == "bootstrapped_from_template"
        assert _json.loads(cfg.read_text()) == {"a": 0, "b": 1}

    def test_restore_depuis_backup_si_absent(self, tmp_path):
        cfg, tpl, bak = self._paths(tmp_path)
        _write(tpl, {"a": 0})
        _write(bak, {"a": 7})  # dernière config saine
        report = ensure_config_ready(cfg, tpl, bak, force=True)
        assert report.status == "restored_from_backup"
        assert _json.loads(cfg.read_text()) == {"a": 7}

    def test_recovered_corruption_restaure_backup(self, tmp_path):
        cfg, tpl, bak = self._paths(tmp_path)
        _write(tpl, {"a": 0})
        _write(bak, {"a": 7})
        cfg.write_text("{ ceci n'est pas du json", encoding="utf-8")
        report = ensure_config_ready(cfg, tpl, bak, force=True)
        assert report.status == "recovered_corruption"
        assert _json.loads(cfg.read_text()) == {"a": 7}

    def test_corruption_no_backup_regenere_template(self, tmp_path):
        cfg, tpl, bak = self._paths(tmp_path)
        _write(tpl, {"a": 0})
        cfg.write_text("CORROMPU", encoding="utf-8")
        report = ensure_config_ready(cfg, tpl, bak, force=True)
        assert report.status == "corruption_no_backup"
        assert _json.loads(cfg.read_text()) == {"a": 0}

    def test_lastgood_mis_a_jour_apres_chargement_valide(self, tmp_path):
        cfg, tpl, bak = self._paths(tmp_path)
        _write(tpl, {"a": 0})
        _write(cfg, {"a": 7})
        ensure_config_ready(cfg, tpl, bak, force=True)
        assert bak.exists()
        assert _json.loads(bak.read_text()) == {"a": 7}

    def test_report_est_un_dataclass_serialisable(self, tmp_path):
        cfg, tpl, bak = self._paths(tmp_path)
        _write(tpl, {"a": 0})
        _write(cfg, {"a": 7})
        report = ensure_config_ready(cfg, tpl, bak, force=True)
        assert isinstance(report, ConfigReport)
        d = asdict(report)
        assert set(d) >= {"status", "added", "removed", "backup_timestamp", "message"}
```

- [ ] **Step 2: Lancer, vérifier l'échec**

Run: `uv run --extra dev pytest tests/test_config_resilience.py::TestEnsureConfigReady -v`
Expected: FAIL — `ImportError: cannot import name 'ensure_config_ready'`.

- [ ] **Step 3: Implémenter l'orchestration**

Ajouter à `core/config/config_resilience.py` (en haut, après les imports : `from dataclasses import dataclass, field`) :

```python
from dataclasses import dataclass, field

_VALID_STATUSES = (
    "unchanged", "migrated", "bootstrapped_from_template",
    "restored_from_backup", "recovered_corruption", "corruption_no_backup",
)


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
        # Bug de packaging : le template tracké doit toujours être valide.
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
    #    - statut "unchanged" + aucune diff structurelle → NE PAS toucher.
    #    - sinon → écrire (bootstrap/restore/corruption ont déjà changé le contenu,
    #      ou le merge a modifié la structure).
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
        return (f"Configuration migrée : {len(added)} paramètre(s) ajouté(s) "
                f"à leur valeur par défaut. Tes réglages ont été conservés.")
    if status == "restored_from_backup":
        return f"config.json absent — restauré depuis la sauvegarde du {backup_ts}."
    if status == "recovered_corruption":
        return f"config.json illisible — restauré depuis la sauvegarde du {backup_ts}."
    if status == "bootstrapped_from_template":
        return "Première config générée depuis le gabarit — à renseigner."
    if status == "corruption_no_backup":
        return ("config.json corrompu et aucune sauvegarde — valeurs par défaut "
                "chargées, reconfiguration requise.")
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
```

- [ ] **Step 4: Lancer les tests, vérifier qu'ils passent**

Run: `uv run --extra dev pytest tests/test_config_resilience.py -v`
Expected: PASS (tous, ~15 tests).

- [ ] **Step 5: Format + lint**

Run: `uv run --extra dev ruff format core/config/config_resilience.py tests/test_config_resilience.py && uv run --extra dev ruff check core/config/config_resilience.py tests/test_config_resilience.py`
Expected: pas d'erreur.

- [ ] **Step 6: Commit**

```bash
git add core/config/config_resilience.py tests/test_config_resilience.py
git commit -m "feat(config): ensure_config_ready (bootstrap/restore/merge + rapport)

Co-Authored-By: Claude Opus 4.8 (1M context) <noreply@anthropic.com>"
```

---

## Task 4: Câbler `ensure_config_ready` dans le ConfigLoader (TDD)

**Files:**
- Modify: `core/config/config_loader.py` (~458-474)
- Test: `tests/test_config_loader.py`

- [ ] **Step 1: Écrire le test de câblage**

Ajouter à `tests/test_config_loader.py` une classe :

```python
import json
from pathlib import Path

from core.config.config_loader import ConfigLoader


class TestConfigLoaderResilience:
    def test_load_bootstrap_si_config_absent(self, tmp_path, monkeypatch):
        # template présent, config absent → load() ne doit pas lever, mais bootstrapper
        data_dir = tmp_path / "data"
        data_dir.mkdir()
        template = data_dir / "config.template.json"
        # contenu minimal valide pour les parsers (sections optionnelles → defaults)
        template.write_text(json.dumps({"site": {"latitude": 1.0, "longitude": 2.0}}),
                            encoding="utf-8")

        from core.config import config_resilience as cr
        cr._REPORT_CACHE.clear()
        monkeypatch.setattr(cr, "DEFAULT_TEMPLATE_PATH", template)
        monkeypatch.setattr(cr, "DEFAULT_BACKUP_PATH", data_dir / ".config.lastgood.json")

        cfg_path = data_dir / "config.json"
        loader = ConfigLoader(config_path=cfg_path)
        config = loader.load()  # ne doit plus lever FileNotFoundError
        assert cfg_path.exists()
        assert config.site.latitude == 1.0
```

- [ ] **Step 2: Lancer, vérifier l'échec**

Run: `uv run --extra dev pytest tests/test_config_loader.py::TestConfigLoaderResilience -v`
Expected: FAIL — `FileNotFoundError` levé par `_load_json` (config absent, pas encore bootstrappé).

- [ ] **Step 3: Modifier `ConfigLoader.load()` pour appeler ensure_config_ready**

Dans `core/config/config_loader.py`, modifier `load()` (actuellement lignes 458-463) :

```python
    def load(self) -> DriftAppConfig:
        """Charge et retourne la configuration complète."""
        self._ensure_ready()
        self._load_json()
        config = self._build_config()
        self._log_summary(config)
        return config

    def _ensure_ready(self) -> None:
        """Garantit un config.json valide/à jour avant lecture (chantier A).

        Le template/backup sont résolus côté config_resilience. Si le template
        n'existe pas (dev très ancien), on ne bloque pas la lecture classique.
        """
        try:
            from core.config.config_resilience import (
                DEFAULT_BACKUP_PATH,
                DEFAULT_TEMPLATE_PATH,
                ensure_config_ready,
            )
            ensure_config_ready(
                self.config_path, DEFAULT_TEMPLATE_PATH, DEFAULT_BACKUP_PATH
            )
        except Exception as exc:  # ne jamais empêcher le chargement à cause du filet
            self.logger.warning(f"ensure_config_ready a échoué (ignoré) : {exc}")
```

> Note : le test monkeypatch `DEFAULT_TEMPLATE_PATH`/`DEFAULT_BACKUP_PATH` mais `ensure_config_ready` reçoit `self.config_path` en 1er argument et les défauts mémoïsés pour les autres — l'import est fait dans `_ensure_ready` donc les attributs monkeypatchés du module sont bien lus.

- [ ] **Step 4: Lancer le test ciblé, vérifier qu'il passe**

Run: `uv run --extra dev pytest tests/test_config_loader.py::TestConfigLoaderResilience -v`
Expected: PASS.

- [ ] **Step 5: Lancer toute la suite config_loader (non-régression)**

Run: `uv run --extra dev pytest tests/test_config_loader.py -v`
Expected: PASS (aucune régression — `_REPORT_CACHE` peut nécessiter un `.clear()` entre tests si interférence ; sinon ajouter une fixture autouse qui vide le cache).

- [ ] **Step 6: Format, lint, commit**

```bash
uv run --extra dev ruff format core/config/config_loader.py tests/test_config_loader.py
uv run --extra dev ruff check core/config/config_loader.py tests/test_config_loader.py
git add core/config/config_loader.py tests/test_config_loader.py
git commit -m "feat(config): ConfigLoader appelle ensure_config_ready avant lecture

Co-Authored-By: Claude Opus 4.8 (1M context) <noreply@anthropic.com>"
```

---

## Task 5: Publier le rapport en IPC aux points d'entrée (TDD)

**Files:**
- Create: `core/config/config_status_writer.py`
- Modify: `services/motor_service.py` (main), `services/cimier_service.py` (main), `web/cimier/apps.py`
- Test: `tests/test_config_status_writer.py`

- [ ] **Step 1: Écrire le test du writer IPC**

Créer `tests/test_config_status_writer.py` :

```python
import json
from core.config.config_resilience import ConfigReport
from core.config.config_status_writer import write_config_status


def test_write_config_status_serialise_le_rapport(tmp_path):
    out = tmp_path / "config_status.json"
    report = ConfigReport(status="migrated", added=["x"], removed=[], message="m")
    write_config_status(report, path=out)
    data = json.loads(out.read_text())
    assert data["status"] == "migrated"
    assert data["added"] == ["x"]
    assert data["message"] == "m"


def test_write_config_status_jamais_levee(tmp_path):
    # chemin impossible → ne doit pas lever (le filet ne doit pas casser le boot)
    bad = tmp_path / "inexistant" / "sub" / "config_status.json"
    report = ConfigReport(status="unchanged")
    write_config_status(report, path=bad)  # pas d'exception
```

- [ ] **Step 2: Lancer, vérifier l'échec**

Run: `uv run --extra dev pytest tests/test_config_status_writer.py -v`
Expected: FAIL — module inexistant.

- [ ] **Step 3: Implémenter le writer**

Créer `core/config/config_status_writer.py` :

```python
"""Publie le ConfigReport en IPC (/dev/shm) pour surfaçage UI (chantier A)."""
from __future__ import annotations

import json
import logging
from dataclasses import asdict
from pathlib import Path

from core.config.config_resilience import ConfigReport

logger = logging.getLogger(__name__)

DEFAULT_STATUS_PATH = Path("/dev/shm/config_status.json")


def write_config_status(report: ConfigReport, path: Path = DEFAULT_STATUS_PATH) -> None:
    """Sérialise le rapport. Ne lève jamais (le filet ne doit pas casser le boot)."""
    try:
        tmp = path.parent / (path.name + ".tmp")
        with open(tmp, "w", encoding="utf-8") as f:
            json.dump(asdict(report), f, ensure_ascii=False)
        import os
        os.replace(tmp, path)
    except Exception as exc:
        logger.warning(f"Écriture config_status échouée (ignorée) : {exc}")
```

- [ ] **Step 4: Lancer le test, vérifier qu'il passe**

Run: `uv run --extra dev pytest tests/test_config_status_writer.py -v`
Expected: PASS.

- [ ] **Step 5: Câbler aux 3 points d'entrée**

Dans `services/motor_service.py`, au tout début de la fonction `main()` (avant la boucle / le chargement de config), ajouter :

```python
    # Chantier A : garantir un config.json valide + publier le rapport.
    from core.config.config_resilience import ensure_config_ready
    from core.config.config_status_writer import write_config_status
    write_config_status(ensure_config_ready(force=True))
```

Faire de même au début de `main()` dans `services/cimier_service.py`.

Dans `web/cimier/apps.py`, dans la méthode `ready()` de l'AppConfig (créer la méthode si absente — attention au guard `RUN_MAIN` pour éviter le double-run du autoreloader Django) :

```python
    def ready(self):
        import os
        if os.environ.get("RUN_MAIN") == "true" or not os.environ.get("RUN_MAIN"):
            try:
                from core.config.config_resilience import ensure_config_ready
                from core.config.config_status_writer import write_config_status
                write_config_status(ensure_config_ready(force=True))
            except Exception:
                pass
```

- [ ] **Step 6: Vérifier que les imports/wiring ne cassent rien**

Run: `uv run --extra dev pytest tests/test_config_status_writer.py tests/test_motor_service.py -v`
Expected: PASS (motor_service importable, pas de régression).

- [ ] **Step 7: Format, lint, commit**

```bash
uv run --extra dev ruff format core/config/config_status_writer.py tests/test_config_status_writer.py services/motor_service.py services/cimier_service.py web/cimier/apps.py
uv run --extra dev ruff check core/config/config_status_writer.py services/motor_service.py services/cimier_service.py web/cimier/apps.py
git add core/config/config_status_writer.py tests/test_config_status_writer.py services/motor_service.py services/cimier_service.py web/cimier/apps.py
git commit -m "feat(config): publie le rapport de résilience en IPC aux points d'entrée

Co-Authored-By: Claude Opus 4.8 (1M context) <noreply@anthropic.com>"
```

---

## Task 6: Exposer config_status via l'API health (TDD)

**Files:**
- Modify: `web/health/views.py`, `web/health/urls.py`
- Test: `tests/test_web_views.py`

- [ ] **Step 1: Écrire le test de l'endpoint**

Ajouter à `tests/test_web_views.py` (suivre le style des tests health existants — client DRF/Django) :

```python
def test_config_status_endpoint_lit_le_fichier_ipc(client, tmp_path, monkeypatch):
    import json
    from web.health import views as health_views
    status_file = tmp_path / "config_status.json"
    status_file.write_text(json.dumps({
        "status": "migrated", "added": ["x"], "removed": [],
        "backup_timestamp": None, "message": "Configuration migrée"
    }))
    monkeypatch.setattr(health_views, "CONFIG_STATUS_FILE", status_file)
    resp = client.get("/api/health/config_status/")
    assert resp.status_code == 200
    assert resp.json()["status"] == "migrated"


def test_config_status_endpoint_absent_renvoie_unchanged(client, tmp_path, monkeypatch):
    from web.health import views as health_views
    monkeypatch.setattr(health_views, "CONFIG_STATUS_FILE", tmp_path / "absent.json")
    resp = client.get("/api/health/config_status/")
    assert resp.status_code == 200
    assert resp.json()["status"] == "unchanged"
```

- [ ] **Step 2: Lancer, vérifier l'échec**

Run: `uv run --extra dev pytest tests/test_web_views.py -k config_status -v`
Expected: FAIL — 404 (route inexistante).

- [ ] **Step 3: Implémenter la vue + la route**

Dans `web/health/views.py`, ajouter près des autres constantes de chemins :

```python
CONFIG_STATUS_FILE = Path("/dev/shm/config_status.json")
```

Et une vue (style des autres vues `@api_view(['GET'])` du fichier) :

```python
@api_view(['GET'])
def config_status_view(request):
    """État du noyau de résilience config (chantier A). Lu depuis l'IPC."""
    import json
    try:
        with CONFIG_STATUS_FILE.open(encoding="utf-8") as f:
            return Response(json.load(f))
    except (OSError, json.JSONDecodeError):
        return Response({
            "status": "unchanged", "added": [], "removed": [],
            "backup_timestamp": None, "message": "",
        })
```

Dans `web/health/urls.py`, ajouter la route :

```python
    path('config_status/', views.config_status_view, name='config_status'),
```

- [ ] **Step 4: Lancer le test, vérifier qu'il passe**

Run: `uv run --extra dev pytest tests/test_web_views.py -k config_status -v`
Expected: PASS.

- [ ] **Step 5: Format, lint, commit**

```bash
uv run --extra dev ruff format web/health/views.py web/health/urls.py tests/test_web_views.py
uv run --extra dev ruff check web/health/views.py web/health/urls.py
git add web/health/views.py web/health/urls.py tests/test_web_views.py
git commit -m "feat(health): endpoint /api/health/config_status/ expose le rapport config

Co-Authored-By: Claude Opus 4.8 (1M context) <noreply@anthropic.com>"
```

---

## Task 7: Bannière config sur le dashboard (frontend)

**Files:**
- Modify: `web/templates/dashboard.html`, `web/static/js/dashboard.js`, `web/static/css/dashboard.css`

> Frontend pur, pas de test pytest. Vérification manuelle via `./start_dev.sh`.

- [ ] **Step 1: Ajouter le conteneur de bannière dans le HTML**

Dans `web/templates/dashboard.html`, ajouter en haut de la zone de contenu principal (à côté de la bannière de calibration existante — chercher `calibration` pour repérer le pattern) :

```html
<div id="config-banner" class="config-banner" style="display:none;">
  <span id="config-banner-msg"></span>
</div>
```

- [ ] **Step 2: Ajouter le style (réutiliser le ton des bannières existantes)**

Dans `web/static/css/dashboard.css`, ajouter :

```css
.config-banner {
  padding: 0.75rem 1rem;
  margin-bottom: 0.75rem;
  border-radius: 0.5rem;
  border: 1px solid #d4a055;
  background: rgba(212, 160, 85, 0.12);
  color: #e8c890;
  font-size: 0.9rem;
}
.config-banner.is-error {
  border-color: #d45555;
  background: rgba(212, 85, 85, 0.14);
  color: #f0a0a0;
}
```

- [ ] **Step 3: Récupérer et afficher le statut au chargement**

Dans `web/static/js/dashboard.js`, ajouter une fonction appelée au démarrage (près de l'init des autres polls) :

```javascript
async function refreshConfigBanner() {
  try {
    const resp = await fetch('/api/health/config_status/');
    if (!resp.ok) return;
    const data = await resp.json();
    const banner = document.getElementById('config-banner');
    const msg = document.getElementById('config-banner-msg');
    if (!banner || !msg) return;
    if (data.status === 'unchanged' || !data.message) {
      banner.style.display = 'none';
      return;
    }
    msg.textContent = data.message;
    banner.classList.toggle('is-error', data.status === 'corruption_no_backup');
    banner.style.display = 'block';
  } catch (e) { /* silencieux */ }
}
// Appel une fois au chargement
refreshConfigBanner();
```

- [ ] **Step 4: Vérification manuelle**

```bash
./start_dev.sh restart && ./start_dev.sh status
```
Ouvrir `http://localhost:8000`, recharger (Ctrl+F5). En cas nominal (config inchangée) : pas de bannière. Pour tester une migration : ajouter une clé bidon dans `data/config.template.json`, `./start_dev.sh restart`, recharger → bannière ambre « Configuration migrée… ». **Retirer ensuite la clé bidon du template.**

- [ ] **Step 5: Commit**

```bash
git add web/templates/dashboard.html web/static/js/dashboard.js web/static/css/dashboard.css
git commit -m "feat(ui): bannière dashboard du rapport de résilience config

Co-Authored-By: Claude Opus 4.8 (1M context) <noreply@anthropic.com>"
```

---

## Task 8: Retirer le diff-UI OTA et la danse config.json (TDD/nettoyage)

**Files:**
- Delete: `web/health/config_diff.py`
- Modify: `web/health/views.py` (~400-427 `config_diff_view`, ~449-489 `apply_update`), `web/health/urls.py` (~20)
- Modify: `web/static/js/dashboard.js` (~2556-2620), `web/templates/dashboard.html` (modale diff)
- Modify: `scripts/update_driftapp.sh` (~48,66-67,77,170,172-188,449... côté script)
- Modify: `tests/test_ota_uvlock.py`, et tout test ciblant `config_diff`

- [ ] **Step 1: Repérer les tests qui couvrent le code à retirer**

Run: `uv run --extra dev pytest --collect-only -q 2>/dev/null | grep -iE "config_diff|config_strategy|reset" ; grep -rln "config_diff\|config_strategy\|CONFIG_STRATEGY" tests/`
Noter les tests concernés — ils seront **adaptés ou retirés**, pas laissés cassés.

- [ ] **Step 2: Supprimer le module diff + la vue + la route**

```bash
git rm web/health/config_diff.py
```
Dans `web/health/views.py` : supprimer la fonction `config_diff_view` (≈ lignes 400-427) et l'import local `from .config_diff import get_config_diff`.
Dans `web/health/urls.py` : supprimer la ligne `path('update/config_diff/', ...)` (≈ ligne 20).

- [ ] **Step 3: Simplifier `apply_update` (retirer config_strategy)**

Dans `web/health/views.py`, `apply_update` (≈ 429-491) : retirer la lecture/validation de `config_strategy` (lignes 449-455), retirer `'--config-strategy', config_strategy` de `cmd` (≈ 472-473) → `cmd = ['sudo', '-n', str(UPDATE_SCRIPT)]`, et retirer `'config_strategy': config_strategy` de la réponse JSON (≈ 489). Adapter le docstring (retirer le bloc `config_strategy keep|reset`).

- [ ] **Step 4: Nettoyer le script OTA**

Dans `scripts/update_driftapp.sh` : retirer le bloc `if [ "$CONFIG_STRATEGY" = "reset" ]; then ... fi` (lignes 172-188), la variable `CONFIG_STRATEGY` (ligne 48), la validation `--config-strategy` (lignes 66-67), le passage `--config-strategy "$CONFIG_STRATEGY"` dans le ré-exec détaché (ligne 77), et la mention `config_strategy` du log (ligne 170). Le `git pull` et le stash des autres fichiers trackés restent inchangés (config.json étant désormais untracked, il n'apparaît plus dans `MODIFIED_FILES` ni dans le stash).

- [ ] **Step 5: Retirer la modale diff côté frontend**

Dans `web/static/js/dashboard.js` : retirer le `fetch('/api/health/update/config_diff/')` (≈ 2556) et la logique de modale de choix associée ; `applyUpdate()` n'accepte plus `configStrategy` (≈ 2604-2619) → le body POST devient `{}` ou sans `config_strategy`.
Dans `web/templates/dashboard.html` : retirer le bloc de la modale « Différences sur config.json / Choisissez quelle version garder » (chercher `config.json` / `upstream` / `user_backup`).

- [ ] **Step 6: Adapter les tests**

Dans `tests/test_ota_uvlock.py` et autres repérés au Step 1 : retirer/adapter les assertions sur `config_strategy`, `config.json.user_backup`, le checkout upstream de config.json. Conserver les guards `uv.lock --frozen` (hors périmètre, ne pas y toucher).

- [ ] **Step 7: Lancer les suites impactées**

Run: `uv run --extra dev pytest tests/test_ota_uvlock.py tests/test_web_views.py -v`
Expected: PASS (tests adaptés verts, plus aucune référence à config_diff).

- [ ] **Step 8: Vérifier qu'il ne reste aucune référence morte**

Run: `grep -rn "config_diff\|config_strategy\|CONFIG_STRATEGY\|configStrategy" web/ scripts/ tests/`
Expected: aucun résultat (ou seulement des commentaires historiques volontairement conservés).

- [ ] **Step 9: Format, lint, commit**

```bash
uv run --extra dev ruff format web/health/views.py web/health/urls.py tests/test_ota_uvlock.py
uv run --extra dev ruff check web/health/views.py web/health/urls.py
git add -A
git commit -m "refactor(ota): retire le diff-UI config.json au profit du rapport automatique

config.json étant dé-tracké, le pull ne le touche plus : suppression de
config_diff.py, de la vue/route config_diff, du paramètre config_strategy
(vue + script + frontend) et de la modale de choix. Tests adaptés.

Co-Authored-By: Claude Opus 4.8 (1M context) <noreply@anthropic.com>"
```

---

## Task 9: Validation d'ensemble + documentation déploiement

**Files:**
- Modify: `CLAUDE.md` (section déploiement — étape migration config + changelog)

- [ ] **Step 1: Suite de tests complète**

Run: `uv run --extra dev pytest -n auto -q`
Expected: tout vert (baseline + nouveaux tests config_resilience/status, OTA adaptés). Noter le total.

- [ ] **Step 2: Vérification fonctionnelle dev**

```bash
./start_dev.sh restart && ./start_dev.sh status
cat /dev/shm/config_status.json
```
Expected: les 4 process EN COURS ; `config_status.json` présent avec `status` cohérent (`unchanged` en nominal).

- [ ] **Step 3: Documenter la migration terrain dans CLAUDE.md**

Ajouter une sous-section « Migration config.json dé-tracké (chantier A) » dans la zone déploiement, décrivant l'étape one-shot sur le Pi :

```markdown
### Migration config.json dé-tracké (chantier A, juin 2026)

config.json n'est plus tracké. Au déploiement de cette version sur le Pi (one-shot) :

    ssh slenk@<pi-host>
    cd ~/DriftApp
    cp data/config.json data/config.json.bak      # filet manuel
    git fetch origin && git checkout origin/main -- . 2>/dev/null || git pull --ff-only origin main
    # config.json reste sur le disque (dé-tracking préserve le working tree).
    # Au premier boot, ensure_config_ready() crée .config.lastgood.json et migre
    # la structure si besoin (valeurs terrain préservées).
    ./start_dev.sh restart  # ou redémarrage des services systemd en prod
    cat /dev/shm/config_status.json   # vérifier le statut

Si `config.json` a des modifs locales non commitées qui bloquent le pull :
`git stash` les autres fichiers, pull, `git stash pop`. config.json (untracked)
n'est pas concerné.
```

- [ ] **Step 4: Commit doc**

```bash
git add CLAUDE.md
git commit -m "docs(config): procédure de migration config.json dé-tracké (chantier A)

Co-Authored-By: Claude Opus 4.8 (1M context) <noreply@anthropic.com>"
```

- [ ] **Step 5: Décision finale (hors plan automatique)**

Présenter à l'utilisateur : suite verte + diff complet. Décider du bump `pyproject.toml` (mineur, ex. 6.9.0) et du message de release au moment du merge — via le skill `pre-push`. **Ne pas bumper avant accord.**

---

## Self-Review (rempli par l'auteur du plan)

**Couverture spec :**
- §3 fichiers (template/gitignore/lastgood) → Task 1 ✓
- §4 module + algorithme (bootstrap/restore/merge/atomic/lastgood) → Tasks 2, 3 ✓
- §4 intégration ConfigLoader + entrypoints → Tasks 4, 5 ✓
- §5 surfaçage UI (IPC + endpoint + bannière) → Tasks 5, 6, 7 ✓
- §6 nettoyage OTA (script + config_diff + diff-UI + apply_update) → Task 8 ✓
- §7 tests → présents dans chaque task (TDD) ✓
- §8 critères de succès → Task 9 (suite verte + vérif fonctionnelle) ✓
- §3 migration terrain → Task 9 Step 3 (doc) ✓

**Placeholders :** aucun « TODO/TBD » ; code complet fourni pour le module cœur ; éditions OTA référencées par numéros de ligne réels.

**Cohérence des types :** `ConfigReport(status, added, removed, backup_timestamp, message)` cohérent entre Tasks 3/5/6/7. `ensure_config_ready(config_path, template_path, backup_path, *, force)` signature stable Tasks 3/4/5. `_structural_merge` retourne `(merged, added, removed)` partout. `write_config_status(report, path)` cohérent Tasks 5/6.

**Périmètre :** chantier A uniquement ; la page Configuration UI (chantier B) est explicitement hors plan (cycle ultérieur).
