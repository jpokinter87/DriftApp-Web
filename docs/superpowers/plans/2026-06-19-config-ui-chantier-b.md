# Page Configuration UI (chantier B) — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Fournir une page web qui édite `data/config.json` en sécurité (formulaire accordéon auto-généré depuis le template), en écrivant **à travers** le noyau de résilience du chantier A.

**Architecture:** Deux ajouts purs au noyau A (`build_config_schema`, `write_user_config`) réutilisant le `_structural_merge` et `_atomic_write_json` existants. Une app Django dédiée `configuration` (GET schema+values, POST save). Un frontend Alpine.js en accordéon (sections terrain dépliées, « Avancé » replié), notice « redémarrage requis » après sauvegarde.

**Tech Stack:** Python (stdlib pur pour le noyau), Django REST Framework, Alpine.js 3 (CDN), Tailwind (CSS déjà compilé).

**Spec:** `docs/superpowers/specs/2026-06-19-config-ui-chantier-b-design.md`

---

## File Structure

**Modifié :**
- `core/config/config_resilience.py` — ajoute `ADVANCED_SECTIONS`, `ENUM_REGISTRY`, `_infer_type`, `build_config_schema`, `ConfigValidationError`, `validate_and_coerce`, `write_user_config`, `_message_for` (cas `saved`).
- `web/driftapp_web/settings.py` — `INSTALLED_APPS += ["configuration"]`.
- `web/driftapp_web/urls.py` — route API `api/configuration/` + route page `configuration/`.
- `web/templates/base.html` — onglet nav « Configuration ».

**Créé :**
- `web/configuration/__init__.py`
- `web/configuration/urls.py`
- `web/configuration/views.py`
- `web/templates/configuration.html`
- `web/static/js/configuration.js`
- `tests/test_configuration_views.py`

**Tests étendus :**
- `tests/test_config_resilience.py` — schema + validation + write_user_config.

**Commande de test de référence (périmètre) :**
```
uv run --extra dev pytest tests/test_config_resilience.py tests/test_configuration_views.py -v
```

---

## Task 1: `build_config_schema` — génération du schéma depuis le template (pur)

**Files:**
- Modify: `core/config/config_resilience.py`
- Test: `tests/test_config_resilience.py`

- [ ] **Step 1: Write the failing tests**

Ajouter en fin de `tests/test_config_resilience.py` :

```python
from core.config.config_resilience import (
    ADVANCED_SECTIONS,
    build_config_schema,
)


class TestBuildConfigSchema:
    def test_infere_les_types_et_ignore_les_underscore(self):
        template = {
            "_comment": "global",
            "site": {"latitude": 44.15, "altitude": 800, "nom": "Ubik"},
            "simulation": False,
        }
        schema = build_config_schema(template)
        sections = {s["key"]: s for s in schema}

        # 'simulation' (scalaire top-level) regroupé sous la section synthétique 'Général'
        assert "_general" in sections
        gen_fields = {f["key"]: f for f in sections["_general"]["fields"]}
        assert gen_fields["simulation"]["type"] == "bool"

        site_fields = {f["path"]: f for f in sections["site"]["fields"]}
        assert site_fields["site.latitude"]["type"] == "float"
        assert site_fields["site.altitude"]["type"] == "int"
        assert site_fields["site.nom"]["type"] == "str"
        # aucune clé _-préfixée n'est devenue un champ
        assert all(not f["key"].startswith("_") for f in site_fields.values())

    def test_bool_avant_int(self):
        # isinstance(True, int) is True → bool doit être testé en premier
        template = {"flags": {"enabled": True}}
        schema = build_config_schema(template)
        field = schema[0]["fields"][0]
        assert field["type"] == "bool"

    def test_section_avancee_marquee(self):
        template = {
            "site": {"latitude": 44.0},
            "moteur": {"microsteps": 4},
        }
        schema = {s["key"]: s for s in build_config_schema(template)}
        assert schema["site"]["advanced"] is False
        assert schema["moteur"]["advanced"] is True
        assert "moteur" in ADVANCED_SECTIONS

    def test_aide_extraite_du_comment_voisin(self):
        template = {
            "motor_driver": {
                "serial": {"port": "/dev/ttyACM0", "_port_comment": "Port USB CDC"}
            }
        }
        schema = build_config_schema(template)
        fields = {f["path"]: f for f in schema[0]["fields"]}
        assert fields["motor_driver.serial.port"]["help"] == "Port USB CDC"

    def test_enum_detecte_depuis_le_registre(self):
        template = {"cimier": {"automation": {"mode": "full"}}}
        schema = build_config_schema(template)
        field = schema[0]["fields"][0]
        assert field["path"] == "cimier.automation.mode"
        assert field["enum"] == ["manual", "semi", "full"]

    def test_groupe_sous_section_renseigne(self):
        template = {"cimier": {"motor_shelly": {"host_motor": ""}}}
        schema = build_config_schema(template)
        field = schema[0]["fields"][0]
        assert field["group"] == "motor_shelly"
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `uv run --extra dev pytest tests/test_config_resilience.py::TestBuildConfigSchema -v`
Expected: FAIL avec `ImportError: cannot import name 'build_config_schema'`.

- [ ] **Step 3: Write minimal implementation**

Ajouter dans `core/config/config_resilience.py` (après les imports, avant `ConfigReport`) :

```python
# --- Chantier B : génération du schéma de formulaire depuis le template ---

ADVANCED_SECTIONS = {
    "moteur",
    "encodeur",
    "motor_driver",
    "boot_calibration",
    "thresholds",
}

# Énumérations connues : chemin pointé → options proposées (menu déroulant UI).
ENUM_REGISTRY: dict[str, list[str]] = {
    "cimier.automation.mode": ["manual", "semi", "full"],
    "logging.level": ["DEBUG", "INFO", "WARNING", "ERROR"],
    "motor_driver.type": ["gpio", "rp2040"],
    "cimier.switch_reader.type": ["shelly_uni", "noop"],
    "cimier.power_switch.type": ["shelly_gen1", "shelly_gen2", "noop"],
    "cimier.weather_provider.type": ["noop"],
    "cimier.motor_shelly.api": ["legacy", "rpc"],
    "cimier.switch_reader.api": ["legacy", "rpc"],
}


def _infer_type(value) -> str:
    # bool AVANT int : isinstance(True, int) is True.
    if isinstance(value, bool):
        return "bool"
    if isinstance(value, int):
        return "int"
    if isinstance(value, float):
        return "float"
    return "str"


def _collect_fields(node: dict, prefix: str, group: str | None, out: list[dict]) -> None:
    """Collecte récursivement les feuilles éditables (hors clés _-préfixées)."""
    for key, value in node.items():
        if key.startswith("_"):
            continue
        path = f"{prefix}.{key}" if prefix else key
        if isinstance(value, dict):
            _collect_fields(value, path, key, out)
        else:
            out.append(
                {
                    "path": path,
                    "key": key,
                    "label": key,
                    "group": group,
                    "type": _infer_type(value),
                    "help": node.get(f"_{key}_comment", ""),
                    "enum": ENUM_REGISTRY.get(path),
                }
            )


def build_config_schema(template: dict) -> list[dict]:
    """Produit la liste des sections (accordéon) depuis le squelette du template.

    Les scalaires de premier niveau (ex. `simulation`) sont regroupés sous une
    section synthétique « Général » (`key="_general"`).
    """
    sections: list[dict] = []
    general_fields: list[dict] = []

    for key, value in template.items():
        if key.startswith("_"):
            continue
        if isinstance(value, dict):
            fields: list[dict] = []
            _collect_fields(value, key, None, fields)
            sections.append(
                {
                    "key": key,
                    "label": key,
                    "help": value.get("_comment", ""),
                    "advanced": key in ADVANCED_SECTIONS,
                    "fields": fields,
                }
            )
        else:
            general_fields.append(
                {
                    "path": key,
                    "key": key,
                    "label": key,
                    "group": None,
                    "type": _infer_type(value),
                    "help": template.get(f"_{key}_comment", ""),
                    "enum": ENUM_REGISTRY.get(key),
                }
            )

    if general_fields:
        sections.insert(
            0,
            {
                "key": "_general",
                "label": "Général",
                "help": "",
                "advanced": False,
                "fields": general_fields,
            },
        )
    return sections
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `uv run --extra dev pytest tests/test_config_resilience.py::TestBuildConfigSchema -v`
Expected: PASS (6 tests).

- [ ] **Step 5: Commit**

```bash
git add core/config/config_resilience.py tests/test_config_resilience.py
git commit -m "feat(config): build_config_schema — schéma de formulaire depuis le template"
```

---

## Task 2: `validate_and_coerce` — validation de types + `ConfigValidationError` (pur)

**Files:**
- Modify: `core/config/config_resilience.py`
- Test: `tests/test_config_resilience.py`

- [ ] **Step 1: Write the failing tests**

Ajouter dans `tests/test_config_resilience.py` :

```python
import pytest

from core.config.config_resilience import (
    ConfigValidationError,
    validate_and_coerce,
)


class TestValidateAndCoerce:
    def test_types_corrects_preserves(self):
        template = {"site": {"latitude": 44.0, "altitude": 800, "nom": "x"}}
        values = {"site": {"latitude": 45.1, "altitude": 810, "nom": "Ubik"}}
        out = validate_and_coerce(values, template)
        assert out == {"site": {"latitude": 45.1, "altitude": 810, "nom": "Ubik"}}
        assert isinstance(out["site"]["altitude"], int)

    def test_int_vers_float_si_champ_float(self):
        template = {"site": {"latitude": 44.0}}
        out = validate_and_coerce({"site": {"latitude": 45}}, template)
        assert out["site"]["latitude"] == 45.0
        assert isinstance(out["site"]["latitude"], float)

    def test_chaine_vide_autorisee_pour_str(self):
        template = {"cimier": {"motor_shelly": {"host_motor": "192.168.1.85"}}}
        out = validate_and_coerce({"cimier": {"motor_shelly": {"host_motor": ""}}}, template)
        assert out["cimier"]["motor_shelly"]["host_motor"] == ""

    def test_texte_dans_champ_numerique_rejete(self):
        template = {"site": {"altitude": 800}}
        with pytest.raises(ConfigValidationError) as exc:
            validate_and_coerce({"site": {"altitude": "abc"}}, template)
        assert exc.value.path == "site.altitude"

    def test_bool_non_accepte_pour_int(self):
        template = {"site": {"altitude": 800}}
        with pytest.raises(ConfigValidationError) as exc:
            validate_and_coerce({"site": {"altitude": True}}, template)
        assert exc.value.path == "site.altitude"
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `uv run --extra dev pytest tests/test_config_resilience.py::TestValidateAndCoerce -v`
Expected: FAIL avec `ImportError: cannot import name 'ConfigValidationError'`.

- [ ] **Step 3: Write minimal implementation**

Ajouter dans `core/config/config_resilience.py` (après `build_config_schema`) :

```python
class ConfigValidationError(ValueError):
    """Type incohérent pour une clé lors d'une sauvegarde UI."""

    def __init__(self, path: str, message: str = "") -> None:
        self.path = path
        super().__init__(message or f"Type invalide pour « {path} »")


def validate_and_coerce(values: dict, template: dict, prefix: str = "") -> dict:
    """Vérifie/coerce les feuilles de `values` selon le type des feuilles du template.

    Ne valide que les chemins présents des deux côtés (le merge structurel gère le
    reste). Lève ConfigValidationError(path) au premier type incohérent.
    """
    out: dict = {}
    for key, val in values.items():
        if key.startswith("_"):
            continue
        path = f"{prefix}.{key}" if prefix else key
        if key not in template:
            continue  # clé inconnue : ignorée ici, retirée par le merge
        tmpl_val = template[key]
        if isinstance(tmpl_val, dict) and isinstance(val, dict):
            out[key] = validate_and_coerce(val, tmpl_val, path)
            continue
        expected = _infer_type(tmpl_val)
        if expected == "bool":
            if not isinstance(val, bool):
                raise ConfigValidationError(path)
            out[key] = val
        elif expected == "int":
            if isinstance(val, bool) or not isinstance(val, int):
                raise ConfigValidationError(path)
            out[key] = val
        elif expected == "float":
            if isinstance(val, bool) or not isinstance(val, (int, float)):
                raise ConfigValidationError(path)
            out[key] = float(val)
        else:  # str
            if not isinstance(val, str):
                raise ConfigValidationError(path)
            out[key] = val
    return out
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `uv run --extra dev pytest tests/test_config_resilience.py::TestValidateAndCoerce -v`
Expected: PASS (5 tests).

- [ ] **Step 5: Commit**

```bash
git add core/config/config_resilience.py tests/test_config_resilience.py
git commit -m "feat(config): validate_and_coerce — garde-fou de types pour la sauvegarde UI"
```

---

## Task 3: `write_user_config` — écriture à travers le noyau A (pur)

**Files:**
- Modify: `core/config/config_resilience.py`
- Test: `tests/test_config_resilience.py`

- [ ] **Step 1: Write the failing tests**

Ajouter dans `tests/test_config_resilience.py` :

```python
from core.config.config_resilience import (
    _REPORT_CACHE,
    ensure_config_ready,
    write_user_config,
)


class TestWriteUserConfig:
    def _paths(self, tmp_path):
        return (
            tmp_path / "config.json",
            tmp_path / "config.template.json",
            tmp_path / ".config.lastgood.json",
        )

    def test_ecrit_valeurs_et_reinjecte_comment(self, tmp_path):
        cfg, tmpl, backup = self._paths(tmp_path)
        _atomic_write_json(
            tmpl,
            {
                "_comment": "gabarit",
                "site": {"_comment": "le site", "latitude": 44.0, "nom": "x"},
            },
        )
        report = write_user_config(
            {"site": {"latitude": 45.5, "nom": "Ubik"}},
            config_path=cfg,
            template_path=tmpl,
            backup_path=backup,
        )
        written = json.loads(cfg.read_text())
        assert written["site"]["latitude"] == 45.5
        assert written["site"]["nom"] == "Ubik"
        assert written["site"]["_comment"] == "le site"   # _comment réinjecté
        assert written["_comment"] == "gabarit"
        assert report.status == "saved"
        # lastgood rafraîchi à l'identique
        assert json.loads(backup.read_text()) == written

    def test_type_invalide_leve_et_n_ecrit_pas(self, tmp_path):
        cfg, tmpl, backup = self._paths(tmp_path)
        _atomic_write_json(tmpl, {"site": {"altitude": 800}})
        with pytest.raises(ConfigValidationError):
            write_user_config(
                {"site": {"altitude": "haut"}},
                config_path=cfg,
                template_path=tmpl,
                backup_path=backup,
            )
        assert not cfg.exists()  # rien écrit

    def test_invalide_le_cache_report(self, tmp_path):
        cfg, tmpl, backup = self._paths(tmp_path)
        _atomic_write_json(tmpl, {"site": {"nom": "x"}})
        _atomic_write_json(cfg, {"site": {"nom": "ancien"}})
        ensure_config_ready(cfg, tmpl, backup)          # peuple _REPORT_CACHE
        assert str(cfg) in _REPORT_CACHE
        write_user_config(
            {"site": {"nom": "neuf"}},
            config_path=cfg,
            template_path=tmpl,
            backup_path=backup,
        )
        assert str(cfg) not in _REPORT_CACHE            # cache invalidé
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `uv run --extra dev pytest tests/test_config_resilience.py::TestWriteUserConfig -v`
Expected: FAIL avec `ImportError: cannot import name 'write_user_config'`.

- [ ] **Step 3: Write minimal implementation**

Dans `core/config/config_resilience.py`, ajouter le cas `saved` comme **branche sœur** dans `_message_for` (au même niveau d'indentation que `if status == "unchanged":`, juste avant son `return` — c'est une nouvelle clause `if` indépendante, PAS imbriquée) :

```python
def _message_for(status, added, removed, backup_ts) -> str:
    if status == "saved":
        return "Configuration enregistrée. Redémarre les services pour l'appliquer."
    if status == "unchanged":
        return "Configuration inchangée."
    # ... (branches existantes inchangées en dessous)
```

Puis ajouter à la fin du module :

```python
def write_user_config(
    values: dict,
    config_path: Path = DEFAULT_CONFIG_PATH,
    template_path: Path = DEFAULT_TEMPLATE_PATH,
    backup_path: Path = DEFAULT_BACKUP_PATH,
) -> ConfigReport:
    """Persiste les valeurs éditées par l'UI, à travers le noyau A.

    Valide les types vs template, merge la structure (réinjecte les _comment et
    écarte toute clé inconnue), écrit atomiquement, rafraîchit lastgood, invalide
    la mémoïsation. Lève ConfigValidationError(path) si un type est incohérent.
    """
    template = _load_json_or_none(template_path)
    if template is None:
        raise RuntimeError(f"Template introuvable ou invalide : {template_path}")

    coerced = validate_and_coerce(values, template)
    merged, added, removed = _structural_merge(coerced, template)

    _atomic_write_json(config_path, merged)
    _atomic_write_json(backup_path, merged)
    _REPORT_CACHE.pop(str(config_path), None)

    return ConfigReport(
        status="saved",
        added=added,
        removed=removed,
        backup_timestamp=_backup_mtime_iso(backup_path),
        message=_message_for("saved", added, removed, None),
    )
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `uv run --extra dev pytest tests/test_config_resilience.py -v`
Expected: PASS (tous les tests du fichier, anciens + nouveaux).

- [ ] **Step 5: Commit**

```bash
git add core/config/config_resilience.py tests/test_config_resilience.py
git commit -m "feat(config): write_user_config — sauvegarde UI atomique via le noyau A"
```

---

## Task 4: App Django `configuration` + endpoint `GET /api/configuration/`

**Files:**
- Create: `web/configuration/__init__.py`, `web/configuration/urls.py`, `web/configuration/views.py`
- Modify: `web/driftapp_web/settings.py`, `web/driftapp_web/urls.py`
- Test: `tests/test_configuration_views.py`

- [ ] **Step 1: Write the failing test**

Créer `tests/test_configuration_views.py` :

```python
"""Tests des vues de l'app configuration (GET schema+values, POST save)."""

import json
import os
import sys
from pathlib import Path

import pytest

PROJECT_ROOT = Path(__file__).parent.parent.resolve()
sys.path.insert(0, str(PROJECT_ROOT))
sys.path.insert(0, str(PROJECT_ROOT / "web"))
os.environ.setdefault("DJANGO_SETTINGS_MODULE", "driftapp_web.settings")
os.environ.setdefault("DRIFTAPP_DEBUG", "1")

import django

django.setup()

from rest_framework.test import APIClient

from core.config import config_resilience


@pytest.fixture
def api_client():
    return APIClient()


@pytest.fixture
def tmp_config(tmp_path, monkeypatch):
    """Redirige les chemins config du module vue vers des fichiers temporaires."""
    cfg = tmp_path / "config.json"
    tmpl = tmp_path / "config.template.json"
    backup = tmp_path / ".config.lastgood.json"
    template = {
        "_comment": "gabarit",
        "site": {"_comment": "le site", "latitude": 44.0, "nom": "x"},
        "moteur": {"microsteps": 4},
        "simulation": False,
    }
    config_resilience._atomic_write_json(tmpl, template)
    config_resilience._atomic_write_json(
        cfg, {"site": {"latitude": 45.5, "nom": "Ubik"}, "moteur": {"microsteps": 4}, "simulation": False}
    )
    from configuration import views as cfg_views

    monkeypatch.setattr(cfg_views, "CONFIG_PATH", cfg)
    monkeypatch.setattr(cfg_views, "TEMPLATE_PATH", tmpl)
    monkeypatch.setattr(cfg_views, "BACKUP_PATH", backup)
    return cfg, tmpl, backup


class TestConfigurationGet:
    def test_get_renvoie_schema_et_valeurs(self, api_client, tmp_config):
        resp = api_client.get("/api/configuration/")
        assert resp.status_code == 200
        body = resp.json()
        assert "schema" in body and "values" in body
        section_keys = {s["key"] for s in body["schema"]}
        assert {"site", "moteur", "_general"} <= section_keys
        assert body["values"]["site"]["nom"] == "Ubik"
```

- [ ] **Step 2: Run test to verify it fails**

Run: `uv run --extra dev pytest tests/test_configuration_views.py::TestConfigurationGet -v`
Expected: FAIL (app `configuration` introuvable / 404).

- [ ] **Step 3: Write minimal implementation**

Créer `web/configuration/__init__.py` (vide).

Créer `web/configuration/views.py` :

```python
"""Vues de la page Configuration (chantier B) : lecture/écriture via le noyau A."""

import json

from rest_framework import status
from rest_framework.decorators import api_view
from rest_framework.response import Response

from core.config.config_resilience import (
    DEFAULT_BACKUP_PATH,
    DEFAULT_CONFIG_PATH,
    DEFAULT_TEMPLATE_PATH,
    ConfigValidationError,
    build_config_schema,
    write_user_config,
)

# Chemins du noyau A (surchargés dans les tests).
CONFIG_PATH = DEFAULT_CONFIG_PATH
TEMPLATE_PATH = DEFAULT_TEMPLATE_PATH
BACKUP_PATH = DEFAULT_BACKUP_PATH


def _load(path):
    with path.open(encoding="utf-8") as f:
        return json.load(f)


@api_view(["GET", "POST"])
def configuration_view(request):
    if request.method == "GET":
        template = _load(TEMPLATE_PATH)
        values = _load(CONFIG_PATH)
        return Response({"schema": build_config_schema(template), "values": values})

    # POST : sauvegarde
    values = request.data
    if not isinstance(values, dict):
        return Response({"error": "Corps JSON attendu (objet)."}, status=status.HTTP_400_BAD_REQUEST)
    try:
        report = write_user_config(
            values,
            config_path=CONFIG_PATH,
            template_path=TEMPLATE_PATH,
            backup_path=BACKUP_PATH,
        )
    except ConfigValidationError as exc:
        return Response(
            {"error": str(exc), "path": exc.path}, status=status.HTTP_400_BAD_REQUEST
        )
    return Response(
        {
            "status": report.status,
            "message": report.message,
            "added": report.added,
            "removed": report.removed,
            "restart_required": True,
        }
    )
```

Créer `web/configuration/urls.py` :

```python
"""URLs de l'app configuration."""

from django.urls import path

from . import views

urlpatterns = [
    path("", views.configuration_view, name="configuration-api"),
]
```

Modifier `web/driftapp_web/settings.py` — ajouter `"configuration"` à la fin de `INSTALLED_APPS` :

```python
    "cimier",
    "configuration",
]
```

Modifier `web/driftapp_web/urls.py` — ajouter la route API dans `urlpatterns`, après la ligne `api/cimier/` :

```python
    path('api/configuration/', include('configuration.urls')),
```

- [ ] **Step 4: Run test to verify it passes**

Run: `uv run --extra dev pytest tests/test_configuration_views.py::TestConfigurationGet -v`
Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add web/configuration/ web/driftapp_web/settings.py web/driftapp_web/urls.py tests/test_configuration_views.py
git commit -m "feat(config): app Django configuration + endpoint GET /api/configuration/"
```

---

## Task 5: Endpoint `POST /api/configuration/` (sauvegarde + 400)

**Files:**
- Test: `tests/test_configuration_views.py` (la vue POST existe déjà depuis Task 4 ; on la couvre par des tests)

- [ ] **Step 1: Write the failing tests**

Ajouter dans `tests/test_configuration_views.py` :

```python
class TestConfigurationPost:
    def test_post_valide_persiste(self, api_client, tmp_config):
        cfg, _tmpl, _backup = tmp_config
        payload = {
            "site": {"latitude": 46.2, "nom": "Nouveau"},
            "moteur": {"microsteps": 8},
            "simulation": True,
        }
        resp = api_client.post("/api/configuration/", payload, format="json")
        assert resp.status_code == 200
        assert resp.json()["status"] == "saved"
        assert resp.json()["restart_required"] is True
        written = json.loads(cfg.read_text())
        assert written["site"]["latitude"] == 46.2
        assert written["site"]["nom"] == "Nouveau"
        assert written["simulation"] is True
        # _comment du template réinjecté
        assert written["site"]["_comment"] == "le site"

    def test_post_type_invalide_400_et_inchange(self, api_client, tmp_config):
        cfg, _tmpl, _backup = tmp_config
        avant = cfg.read_text()
        resp = api_client.post(
            "/api/configuration/", {"site": {"latitude": "haut"}}, format="json"
        )
        assert resp.status_code == 400
        assert resp.json()["path"] == "site.latitude"
        assert cfg.read_text() == avant  # config.json intact
```

- [ ] **Step 2: Run tests to verify they fail/pass**

Run: `uv run --extra dev pytest tests/test_configuration_views.py::TestConfigurationPost -v`
Expected: PASS (la vue POST a été écrite en Task 4 ; ces tests la verrouillent). Si un test échoue, corriger `web/configuration/views.py` jusqu'au vert.

- [ ] **Step 3: Commit**

```bash
git add tests/test_configuration_views.py
git commit -m "test(config): couverture POST /api/configuration/ (save + 400 type invalide)"
```

---

## Task 6: Route page `/configuration/` + onglet de navigation

**Files:**
- Modify: `web/driftapp_web/urls.py`, `web/templates/base.html`
- Test: `tests/test_configuration_views.py`

- [ ] **Step 1: Write the failing test**

Ajouter dans `tests/test_configuration_views.py` :

```python
class TestConfigurationPage:
    def test_page_configuration_rend_200(self, api_client):
        from django.test import Client

        resp = Client().get("/configuration/")
        assert resp.status_code == 200
        assert b"configuration.js" in resp.content
```

- [ ] **Step 2: Run test to verify it fails**

Run: `uv run --extra dev pytest tests/test_configuration_views.py::TestConfigurationPage -v`
Expected: FAIL (404 : route page absente).

- [ ] **Step 3: Write minimal implementation**

Modifier `web/driftapp_web/urls.py` — ajouter la route page après la route `session/` :

```python
    path('configuration/', TemplateView.as_view(template_name='configuration.html', extra_context={'active_tab': 'config'}), name='configuration'),
```

Créer le squelette minimal `web/templates/configuration.html` (étoffé en Task 7, mais doit charger `configuration.js` pour que le test passe) :

```html
{% extends "base.html" %}
{% block title %}Configuration{% endblock %}
{% block content %}
<div id="config-root"></div>
{% endblock %}
{% block extra_js %}
<script src="/static/js/configuration.js?v={{ APP_VERSION }}"></script>
{% endblock %}
```

Créer un `web/static/js/configuration.js` vide (étoffé en Task 8) :

```javascript
// Page Configuration (chantier B) — implémenté en Task 8.
```

Modifier `web/templates/base.html` — ajouter l'onglet « Configuration » dans le bloc `nav_items`, juste après le `<a href="/session/">…</a>` (avant `{% endblock %}` du nav) :

```html
                <a href="/configuration/"
                   class="nav-tab px-3 py-1.5 rounded-button text-sm font-medium transition-colors duration-200
                          {% if active_tab == 'config' %}
                          bg-accent-amber/15 text-accent-amber
                          {% else %}
                          text-obs-text-secondary hover:text-obs-text hover:bg-obs-hover
                          {% endif %}">
                    Configuration
                </a>
```

- [ ] **Step 4: Run test to verify it passes**

Run: `uv run --extra dev pytest tests/test_configuration_views.py::TestConfigurationPage -v`
Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add web/driftapp_web/urls.py web/templates/base.html web/templates/configuration.html web/static/js/configuration.js
git commit -m "feat(config): route page /configuration/ + onglet de navigation"
```

---

## Task 7: Template accordéon `configuration.html`

**Files:**
- Modify: `web/templates/configuration.html`

> Frontend pur : pas de test pytest (cohérent avec les chantiers UI précédents).
> Vérification = chargement de la page (Task 9).

- [ ] **Step 1: Remplacer `web/templates/configuration.html` par la version complète**

```html
{% extends "base.html" %}
{% block title %}Configuration{% endblock %}

{% block extra_css %}
<style>
  [x-cloak] { display: none !important; }
  .cfg-section { border: 1px solid var(--color-border, #2a2a31); border-radius: 8px; margin-bottom: 0.6rem; overflow: hidden; }
  .cfg-head { display: flex; align-items: center; justify-content: space-between; padding: 0.7rem 1rem; cursor: pointer; background: rgba(255,255,255,0.02); }
  .cfg-head:hover { background: rgba(255,255,255,0.04); }
  .cfg-title { font-weight: 600; color: var(--color-accent-amber); text-transform: capitalize; }
  .cfg-advanced { border-color: rgba(212,160,85,0.4); }
  .cfg-body { padding: 0.4rem 1rem 0.9rem; }
  .cfg-group { font-size: 0.72rem; text-transform: uppercase; letter-spacing: 0.05em; color: var(--color-text-muted, #8a8a92); margin: 0.7rem 0 0.3rem; }
  .cfg-field { display: flex; align-items: center; gap: 0.6rem; padding: 0.3rem 0; }
  .cfg-label { width: 230px; flex: none; font-family: var(--font-mono); font-size: 0.82rem; color: var(--color-text-secondary, #c8c8d0); display: flex; align-items: center; gap: 0.3rem; }
  .cfg-input { flex: 1; background: #101013; border: 1px solid #33333b; border-radius: 5px; padding: 0.35rem 0.5rem; color: #e8e8ee; font-family: var(--font-mono); font-size: 0.82rem; }
  .cfg-help { cursor: help; color: var(--color-text-muted, #8a8a92); }
  .cfg-warn { background: rgba(212,160,85,0.1); color: var(--color-accent-amber); padding: 0.5rem 0.8rem; border-radius: 6px; font-size: 0.8rem; margin-bottom: 0.6rem; }
  .cfg-savebar { position: sticky; bottom: 0; background: var(--color-bg, #16161a); border-top: 1px solid #2a2a31; padding: 0.8rem 0; display: flex; align-items: center; gap: 1rem; margin-top: 0.5rem; }
  .cfg-save-btn { background: var(--color-accent-amber); color: #16161a; font-weight: 700; border: none; border-radius: 6px; padding: 0.55rem 1.4rem; cursor: pointer; }
  .cfg-save-btn:disabled { opacity: 0.4; cursor: default; }
  .cfg-notice { padding: 0.5rem 0.9rem; border-radius: 6px; font-size: 0.85rem; }
  .cfg-notice-ok { background: rgba(0,210,106,0.12); color: var(--color-accent-green); }
  .cfg-notice-err { background: rgba(255,71,87,0.12); color: var(--color-accent-red); }
</style>
{% endblock %}

{% block content %}
<div class="max-w-4xl mx-auto px-4 py-6" x-data="configPage()" x-init="load()" x-cloak>
  <h1 class="text-xl font-semibold mb-1">Configuration</h1>
  <p class="text-sm text-obs-text-muted mb-4">Édition de <code>data/config.json</code>. Les valeurs sont préservées ; un redémarrage des services applique les changements.</p>

  <template x-if="error"><div class="cfg-notice cfg-notice-err mb-4" x-text="error"></div></template>
  <template x-if="loading"><p class="text-sm text-obs-text-muted">Chargement…</p></template>

  <!-- Sections terrain (non avancées) -->
  <template x-for="section in normalSections" :key="section.key">
    <div class="cfg-section">
      <div class="cfg-head" @click="toggle(section.key)">
        <span class="cfg-title" x-text="section.label"></span>
        <span x-text="open[section.key] ? '▾' : '▸'"></span>
      </div>
      <div class="cfg-body" x-show="open[section.key]">
        <template x-if="section.help"><div class="cfg-warn" x-text="section.help"></div></template>
        <template x-for="field in section.fields" :key="field.path">
          <div>
            <template x-if="field.group && field.group !== lastGroup(section, field)">
              <div class="cfg-group" x-text="field.group"></div>
            </template>
            <div class="cfg-field" x-html="renderField(field)"></div>
          </div>
        </template>
      </div>
    </div>
  </template>

  <!-- Panneau Avancé (replié) -->
  <template x-if="advancedSections.length">
    <div class="cfg-section cfg-advanced">
      <div class="cfg-head" @click="toggle('__advanced__')">
        <span class="cfg-title">⚠ Avancé — paramètres matériels</span>
        <span x-text="open['__advanced__'] ? '▾' : '▸'"></span>
      </div>
      <div class="cfg-body" x-show="open['__advanced__']">
        <div class="cfg-warn">Modifier ces paramètres peut empêcher le moteur ou l'encodeur de fonctionner. Ne touche que si tu sais ce que tu fais.</div>
        <template x-for="section in advancedSections" :key="section.key">
          <div class="mb-3">
            <div class="cfg-group" x-text="section.label"></div>
            <template x-for="field in section.fields" :key="field.path">
              <div class="cfg-field" x-html="renderField(field)"></div>
            </template>
          </div>
        </template>
      </div>
    </div>
  </template>

  <div class="cfg-savebar" x-show="!loading">
    <button class="cfg-save-btn" :disabled="!dirty || saving" @click="save()" x-text="saving ? 'Enregistrement…' : 'Sauvegarder'"></button>
    <span x-show="dirty && !notice" class="text-sm text-obs-text-muted">Modifications non enregistrées</span>
    <template x-if="notice"><span class="cfg-notice cfg-notice-ok" x-text="notice"></span></template>
  </div>
</div>
{% endblock %}

{% block extra_js %}
<script src="/static/js/configuration.js?v={{ APP_VERSION }}"></script>
{% endblock %}
```

- [ ] **Step 2: Commit**

```bash
git add web/templates/configuration.html
git commit -m "feat(config): template accordéon de la page Configuration"
```

---

## Task 8: Composant Alpine `configuration.js`

**Files:**
- Modify: `web/static/js/configuration.js`

> Frontend pur : vérification manuelle en Task 9.

- [ ] **Step 1: Remplacer `web/static/js/configuration.js` par la version complète**

```javascript
// Page Configuration (chantier B) — formulaire accordéon auto-généré.
// Charge {schema, values} depuis /api/configuration/, édite localement, POST au save.

function getCookie(name) {
  const m = document.cookie.match('(^|;)\\s*' + name + '\\s*=\\s*([^;]+)');
  return m ? m.pop() : '';
}

function deepGet(obj, path) {
  return path.split('.').reduce((o, k) => (o == null ? undefined : o[k]), obj);
}

function deepSet(obj, path, value) {
  const keys = path.split('.');
  let cur = obj;
  for (let i = 0; i < keys.length - 1; i++) {
    if (typeof cur[keys[i]] !== 'object' || cur[keys[i]] === null) cur[keys[i]] = {};
    cur = cur[keys[i]];
  }
  cur[keys[keys.length - 1]] = value;
}

function configPage() {
  return {
    schema: [],
    values: {},
    open: {},
    dirty: false,
    saving: false,
    loading: true,
    error: '',
    notice: '',

    get normalSections() { return this.schema.filter((s) => !s.advanced); },
    get advancedSections() { return this.schema.filter((s) => s.advanced); },

    async load() {
      try {
        const resp = await fetch('/api/configuration/');
        if (!resp.ok) throw new Error('HTTP ' + resp.status);
        const body = await resp.json();
        this.schema = body.schema;
        this.values = body.values;
        // Sections terrain ouvertes par défaut, Avancé fermé.
        this.normalSections.forEach((s) => { this.open[s.key] = true; });
        this.open['__advanced__'] = false;
      } catch (e) {
        this.error = 'Impossible de charger la configuration : ' + e.message;
      } finally {
        this.loading = false;
      }
    },

    toggle(key) { this.open[key] = !this.open[key]; },

    lastGroup(section, field) {
      // Renvoie le group du champ précédent pour n'afficher l'en-tête qu'au changement.
      const idx = section.fields.indexOf(field);
      return idx > 0 ? section.fields[idx - 1].group : null;
    },

    renderField(field) {
      const val = deepGet(this.values, field.path);
      const help = field.help
        ? `<span class="cfg-help" title="${field.help.replace(/"/g, '&quot;')}">ⓘ</span>`
        : '';
      const label = `<span class="cfg-label">${field.label}${help}</span>`;
      const onChange = `onchange="window.__configSet('${field.path}', this, '${field.type}')"`;
      let input;
      if (field.type === 'bool') {
        input = `<input type="checkbox" class="cfg-input" style="flex:none;width:auto" ${val ? 'checked' : ''} ${onChange}>`;
      } else if (field.enum) {
        const opts = field.enum
          .map((o) => `<option value="${o}" ${o === val ? 'selected' : ''}>${o}</option>`)
          .join('');
        input = `<select class="cfg-input" ${onChange}>${opts}</select>`;
      } else if (field.type === 'int' || field.type === 'float') {
        const step = field.type === 'int' ? '1' : 'any';
        input = `<input type="number" step="${step}" class="cfg-input" value="${val}" ${onChange}>`;
      } else {
        const safe = (val == null ? '' : String(val)).replace(/"/g, '&quot;');
        input = `<input type="text" class="cfg-input" value="${safe}" ${onChange}>`;
      }
      return label + input;
    },

    async save() {
      this.saving = true;
      this.notice = '';
      this.error = '';
      try {
        const resp = await fetch('/api/configuration/', {
          method: 'POST',
          headers: { 'Content-Type': 'application/json', 'X-CSRFToken': getCookie('csrftoken') },
          body: JSON.stringify(this.values),
        });
        const body = await resp.json();
        if (!resp.ok) {
          this.error = body.path ? `${body.error} (${body.path})` : body.error || 'Erreur';
          return;
        }
        this.notice = body.message || 'Configuration enregistrée — redémarrage requis.';
        this.dirty = false;
      } catch (e) {
        this.error = 'Échec de la sauvegarde : ' + e.message;
      } finally {
        this.saving = false;
      }
    },

    init() {
      // Pont pour les inputs rendus via x-html (hors portée Alpine).
      window.__configSet = (path, el, type) => {
        let v;
        if (type === 'bool') v = el.checked;
        else if (type === 'int') v = parseInt(el.value, 10);
        else if (type === 'float') v = parseFloat(el.value);
        else v = el.value;
        if ((type === 'int' || type === 'float') && Number.isNaN(v)) v = el.value; // laisse le backend rejeter
        deepSet(this.values, path, v);
        this.dirty = true;
        this.notice = '';
      };
    },
  };
}
```

- [ ] **Step 2: Commit**

```bash
git add web/static/js/configuration.js
git commit -m "feat(config): composant Alpine de la page Configuration (édition + save)"
```

---

## Task 9: Vérification manuelle + suite complète

**Files:** aucun (vérification).

- [ ] **Step 1: Lancer la suite ciblée**

Run: `uv run --extra dev pytest tests/test_config_resilience.py tests/test_configuration_views.py -v`
Expected: PASS (tous).

- [ ] **Step 2: Format + lint**

Run: `uv run --extra dev ruff format core/config/config_resilience.py web/configuration/ tests/test_configuration_views.py`
Puis: `uv run --extra dev ruff check core/config/config_resilience.py web/configuration/ tests/test_configuration_views.py`
Expected: aucune erreur (corriger sinon).

- [ ] **Step 3: Vérification visuelle dans le navigateur**

```bash
./start_dev.sh start 8000
```
Ouvrir `http://localhost:8000/configuration/` et vérifier :
- Les sections terrain (Site, Cimier, Suivi, Logging, Général…) sont dépliées.
- Le panneau « ⚠ Avancé » est replié ; le déplier montre Moteur/Encodeur/etc. avec l'avertissement.
- Les bulles ⓘ affichent les `_comment` au survol.
- Modifier un champ active le bouton « Sauvegarder » ; cliquer affiche la notice « redémarrage requis ».
- Recharger la page : la valeur modifiée est persistée (`cat data/config.json`).
- Saisir du texte dans un champ numérique avancé → la sauvegarde renvoie une erreur 400 ciblée.

Puis: `./start_dev.sh stop`

- [ ] **Step 4: Régression complète**

Run: `uv run --extra dev pytest -n auto -q`
Expected: vert (baseline + nouveaux). Noter le flake parallèle pré-existant connu `TestMotorHealth::test_healthy` (passe en isolation) si rencontré.

- [ ] **Step 5: Bump de version + commit final**

Mettre à jour `pyproject.toml` (`version`) : `6.9.0` → `6.10.0` (feature). (cf. règle de versionnement projet — sans bump, la MAJ OTA n'est pas proposée.)

```bash
git add pyproject.toml
git commit -m "chore(release): bump 6.10.0 — chantier B page Configuration UI"
```

---

## Notes d'intégration / déploiement

- **Aucune migration terrain particulière** : la page lit/écrit `data/config.json` (déjà dé-tracké au chantier A). Le merge structurel garantit que les `_comment` du template sont réinjectés à chaque sauvegarde.
- **Le push** : suivre le skill `pre-push` (le chantier cimier en cours est l'exception « pas de bump » ; ici on bumpe car c'est une feature config hors cimier).
- **Branche** : `feat/config-resilience` (où vit le chantier A non encore mergé). Chantier B s'empile dessus ; A + B peuvent être mergés ensemble.
