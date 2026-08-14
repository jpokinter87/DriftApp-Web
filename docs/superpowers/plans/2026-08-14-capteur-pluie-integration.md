# Intégration capteur de pluie cimier — plan d'implémentation

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** brancher le capteur de pluie MH-RD (Shelly Plus Uni `.87`, entrée `id=0`) sur le cimier — refus d'ouverture et fermeture d'urgence — derrière une case « Protection pluie » décochée par défaut, et restituer chaque nuit sous forme de frise dans l'UI.

**Architecture:** un provider implémentant le contrat `WeatherProvider` existant lit le Shelly par RPC ; un objet `RainProtection` l'enveloppe et porte la politique (armement, verrou anti-réouverture) ; une veille cadencée dans `cimier_service.tick()` le sonde et déclenche la séquence de fermeture, elle-même factorisée en un module unique partagé avec le scheduler et le parking manuel. Les transitions sont écrites dans un journal de nuit sur disque, restitué par une frise SVG sur la page Session.

**Tech Stack:** Python 3.12, `urllib` (stdlib), Django REST Framework, Alpine.js, SVG inline, pytest (+ `pytest-xdist`).

**Spec de référence :** `docs/superpowers/specs/2026-08-14-capteur-pluie-integration-design.md`

---

## Contexte pour qui découvre le projet

- Toutes les commandes Python passent par `uv run --extra dev …`. Jamais `python` nu, jamais `source .venv/bin/activate`.
- Le dépôt tourne sur une machine de dev **à 800 km du Raspberry Pi de production**. Rien ne peut être testé sur le matériel réel depuis ici : la simulation n'est pas un confort, c'est le seul moyen de vérifier.
- `data/config.json` n'est **pas** suivi par git (valeurs terrain). Le gabarit suivi est `data/config.template.json`. Toute nouvelle clé va dans le **template**.
- Aucune IP, aucun host, aucune valeur terrain en dur dans le code Python : tout vit dans la configuration.
- L'écran de l'observatoire est **tactile** : aucune information ne doit dépendre d'un survol (`title=`, `:hover`).
- `web/static/css/dashboard.css` est du CSS **brut**, pas du Tailwind compilé — on peut l'éditer sans recompiler. Les classes utilitaires Tailwind présentes dans les templates, elles, exigeraient `./scripts/build_css.sh` si on en introduisait de nouvelles : ce plan n'en introduit pas.

### Cartographie des fichiers

| Fichier | Responsabilité | Statut |
|---|---|---|
| `core/hardware/shelly_rpc.py` | dialogue RPC `Input.GetStatus` — parsing, erreurs, timeout | **créé** (T1) |
| `core/hardware/shelly_switch_reader.py` | butées cimier ; délègue le transport à `shelly_rpc` | modifié (T1) |
| `core/config/config_loader.py` | `WeatherProviderConfig` étendu + parser | modifié (T2) |
| `data/config.template.json` | gabarit de la section `weather_provider` | modifié (T2) |
| `core/hardware/weather_provider.py` | `ShellyRainWeatherProvider` + `RainProtection` + factory | modifié (T3, T4) |
| `services/night_journal.py` | journal de nuit sur disque (écriture, lecture, purge) | **créé** (T5) |
| `services/session_close_sequence.py` | séquence `tracking_stop → goto → close`, une seule fois | **créé** (T6) |
| `services/cimier_scheduler.py` | consomme la séquence factorisée | modifié (T6) |
| `web/cimier/views.py` | `ParkingSessionView` consomme la séquence ; `AutomationView` porte la case | modifié (T6, T9) |
| `services/cimier_service.py` | veille pluie, publication d'état, journalisation | modifié (T7, T8) |
| `web/templates/dashboard.html` | case, pastille, avertissement | modifié (T10) |
| `web/static/js/dashboard.js` | état de la case, libellés, timeline | modifié (T10) |
| `web/static/css/dashboard.css` | styles de la pastille | modifié (T10) |
| `core/hardware/cimier_simulator.py` | entrée pluie simulée + bascule `/dev/rain` | modifié (T11) |
| `web/session/views.py`, `urls.py` | endpoint `night` | modifié (T13) |
| `web/static/js/night_frieze.js` | rendu SVG de la frise | **créé** (T14) |
| `web/templates/session.html`, `web/static/js/session.js` | carte « Nuit » | modifié (T14) |

**Lot 1 (T1 → T12)** livre la protection et le journal — déployable seul.
**Lot 2 (T13 → T15)** livre la restitution graphique.

---

## Task 1 : extraire le dialogue RPC Shelly

Le provider pluie doit faire exactement le même appel HTTP que le lecteur de butées. Plutôt que de le réécrire, on l'extrait. Refactor à comportement constant : les tests existants de `ShellySwitchReader` doivent rester verts **sans modification**.

**Files:**
- Create: `core/hardware/shelly_rpc.py`
- Modify: `core/hardware/shelly_switch_reader.py:69-87`
- Test: `tests/test_shelly_rpc.py` (créé), `tests/test_shelly_switch_reader.py` (inchangé, sert de filet)

- [ ] **Step 1 : écrire les tests du nouveau module**

Créer `tests/test_shelly_rpc.py` :

```python
"""Tests du dialogue RPC Shelly partagé (Input.GetStatus)."""

from __future__ import annotations

import json
import urllib.error

import pytest

from core.hardware.shelly_rpc import ShellyRpcError, read_input_state


class FakeResponse:
    """Contexte minimal mimant ce que renvoie urlopen()."""

    def __init__(self, body: bytes, status: int = 200):
        self._body = body
        self.status = status

    def read(self):
        return self._body

    def __enter__(self):
        return self

    def __exit__(self, *exc):
        return False


def make_urlopen(body, status=200, captured=None):
    def _urlopen(url, timeout=None):
        if captured is not None:
            captured.append((url, timeout))
        return FakeResponse(body, status)

    return _urlopen


def test_returns_state_true_and_payload():
    state, payload = read_input_state(
        "1.2.3.4", 0, urlopen=make_urlopen(b'{"id":0,"state":true}')
    )
    assert state is True
    assert payload == {"id": 0, "state": True}


def test_returns_state_false():
    state, _ = read_input_state("1.2.3.4", 0, urlopen=make_urlopen(b'{"id":0,"state":false}'))
    assert state is False


def test_builds_expected_url_and_passes_timeout():
    captured = []
    read_input_state(
        "1.2.3.4", 2, timeout_s=1.5, urlopen=make_urlopen(b'{"state":true}', captured=captured)
    )
    assert captured == [("http://1.2.3.4/rpc/Input.GetStatus?id=2", 1.5)]


def test_raises_on_network_error():
    def _urlopen(url, timeout=None):
        raise urllib.error.URLError("boom")

    with pytest.raises(ShellyRpcError):
        read_input_state("1.2.3.4", 0, urlopen=_urlopen)


def test_raises_on_http_error_status():
    with pytest.raises(ShellyRpcError):
        read_input_state("1.2.3.4", 0, urlopen=make_urlopen(b"{}", status=500))


def test_raises_on_invalid_json():
    with pytest.raises(ShellyRpcError):
        read_input_state("1.2.3.4", 0, urlopen=make_urlopen(b"pas du json"))


def test_raises_on_payload_without_state():
    with pytest.raises(ShellyRpcError):
        read_input_state("1.2.3.4", 0, urlopen=make_urlopen(json.dumps({"id": 0}).encode()))
```

- [ ] **Step 2 : lancer les tests et vérifier qu'ils échouent**

Run: `uv run --extra dev pytest tests/test_shelly_rpc.py -v`
Expected: FAIL — `ModuleNotFoundError: No module named 'core.hardware.shelly_rpc'`

- [ ] **Step 3 : créer le module**

Créer `core/hardware/shelly_rpc.py` :

```python
"""Dialogue RPC Gen 2 partagé avec les Shelly (``Input.GetStatus``).

Un seul endroit où vivent la construction d'URL, le timeout, le typage des
erreurs et la validation du payload. Consommé par :

  - ``ShellySwitchReader`` — butées HAUT/BAS du cimier (Shelly Uni+ .84) ;
  - ``ShellyRainWeatherProvider`` — capteur de pluie (Shelly Plus Uni .87).

L'argument ``urlopen`` permet d'injecter un double dans les tests.
Aucune valeur terrain ici : host, id et timeout viennent de l'appelant.
"""

from __future__ import annotations

import json
import urllib.error
import urllib.request
from typing import Any, Dict, Optional, Tuple


class ShellyRpcError(Exception):
    """Échec de lecture d'une entrée Shelly (réseau, HTTP, payload)."""


def read_input_state(
    host: str,
    input_id: int,
    timeout_s: float = 3.0,
    urlopen: Optional[Any] = None,
) -> Tuple[bool, Dict[str, Any]]:
    """Lit ``GET http://<host>/rpc/Input.GetStatus?id=<n>``.

    Returns:
        ``(state, payload)`` — ``state`` est le booléen brut rapporté par le
        Shelly, sans interprétation métier (l'inversion éventuelle appartient
        à l'appelant, qui seul connaît son câblage).

    Raises:
        ShellyRpcError: hôte injoignable, HTTP ≠ 200, JSON invalide, ou
            payload sans clé ``state``.
    """
    opener = urlopen or urllib.request.urlopen
    url = "http://" + host + "/rpc/Input.GetStatus?id=" + str(int(input_id))
    try:
        with opener(url, timeout=float(timeout_s)) as resp:
            status = getattr(resp, "status", 200)
            raw = resp.read()
    except urllib.error.URLError as exc:
        raise ShellyRpcError("Shelly unreachable: " + str(exc.reason)) from exc
    except OSError as exc:
        raise ShellyRpcError("Shelly socket error: " + str(exc)) from exc
    if status != 200:
        raise ShellyRpcError("Shelly HTTP " + str(status))
    try:
        payload = json.loads(raw.decode("utf-8"))
    except (ValueError, UnicodeDecodeError) as exc:
        raise ShellyRpcError("Shelly JSON invalide: " + str(exc)) from exc
    if not isinstance(payload, dict) or "state" not in payload:
        raise ShellyRpcError("Shelly payload sans 'state': " + repr(payload))
    return bool(payload["state"]), payload
```

- [ ] **Step 4 : vérifier que les tests passent**

Run: `uv run --extra dev pytest tests/test_shelly_rpc.py -v`
Expected: PASS — 7 tests.

- [ ] **Step 5 : brancher `ShellySwitchReader` dessus**

Dans `core/hardware/shelly_switch_reader.py`, remplacer intégralement la méthode `_read_input` (lignes 69-87) par :

```python
    def _read_input(self, input_id: int):
        try:
            return read_input_state(
                self._host, input_id, self._timeout_s, self._urlopen
            )
        except ShellyRpcError as exc:
            raise SwitchReaderError("Shelly Uni+ : " + str(exc)) from exc
```

Ajouter l'import en tête de fichier, après `from dataclasses import dataclass` :

```python
from core.hardware.shelly_rpc import ShellyRpcError, read_input_state
```

Supprimer les imports devenus inutilisés par ce changement : `import json`, `import urllib.error`, `import urllib.request`.

- [ ] **Step 6 : vérifier la non-régression du lecteur de butées**

Run: `uv run --extra dev pytest tests/test_shelly_switch_reader.py tests/test_shelly_rpc.py tests/test_cimier_service.py -v`
Expected: PASS — aucun test modifié, tous verts.

- [ ] **Step 7 : format, lint, commit**

```bash
uv run --extra dev ruff format core/hardware/shelly_rpc.py core/hardware/shelly_switch_reader.py tests/test_shelly_rpc.py
uv run --extra dev ruff check core/hardware/shelly_rpc.py core/hardware/shelly_switch_reader.py tests/test_shelly_rpc.py
git add core/hardware/shelly_rpc.py core/hardware/shelly_switch_reader.py tests/test_shelly_rpc.py
git commit -m "refactor(shelly): extrait le dialogue RPC Input.GetStatus dans un module partagé"
```

---

## Task 2 : configuration du provider pluie

**Files:**
- Modify: `core/config/config_loader.py:228-239` (dataclass), `core/config/config_loader.py:643-645` (parser)
- Modify: `data/config.template.json` (section `cimier.weather_provider`)
- Modify: `.gitignore`
- Test: `tests/test_config_loader.py`

- [ ] **Step 1 : écrire les tests de parsing**

Ajouter à la fin de `tests/test_config_loader.py`. Le fichier fournit déjà la fixture `sample_config_dict` (config complète valide) et charge via `ConfigLoader(config_file).load()` — on suit ce motif, utilisé par exemple par `test_legacy_adaptive_section_ignored` :

```python
class TestWeatherProviderConfig:
    """Section cimier.weather_provider étendue (capteur de pluie, 2026-08)."""

    def test_defaults_are_noop_and_disarmed(self):
        cfg = WeatherProviderConfig()
        assert cfg.type == "noop"
        assert cfg.host == ""
        assert cfg.input_id == 0
        assert cfg.invert is False
        assert cfg.timeout_s == 3.0
        assert cfg.protection_enabled is False
        assert cfg.watch_interval_s == 10.0
        assert cfg.confirm_reads == 2

    def test_parses_full_section(self, tmp_path, sample_config_dict):
        payload = dict(sample_config_dict)
        payload["cimier"] = {
            "weather_provider": {
                "type": "shelly_rain",
                "host": "10.0.0.9",
                "input_id": 1,
                "invert": True,
                "timeout_s": 1.5,
                "protection_enabled": True,
                "watch_interval_s": 5.0,
                "confirm_reads": 3,
            }
        }
        config_file = tmp_path / "config.json"
        config_file.write_text(json.dumps(payload))
        wp = ConfigLoader(config_file).load().cimier.weather_provider
        assert wp.type == "shelly_rain"
        assert wp.host == "10.0.0.9"
        assert wp.input_id == 1
        assert wp.invert is True
        assert wp.timeout_s == 1.5
        assert wp.protection_enabled is True
        assert wp.watch_interval_s == 5.0
        assert wp.confirm_reads == 3

    def test_missing_section_stays_retro_compatible(self, tmp_path, sample_config_dict):
        # Une config antérieure (sans la section) doit se charger et rester noop.
        payload = dict(sample_config_dict)
        payload["cimier"] = {"enabled": True}
        config_file = tmp_path / "config.json"
        config_file.write_text(json.dumps(payload))
        wp = ConfigLoader(config_file).load().cimier.weather_provider
        assert wp.type == "noop"
        assert wp.protection_enabled is False

    def test_non_dict_section_falls_back_to_defaults(self, tmp_path, sample_config_dict):
        # Config terrain mal saisie : ne doit pas casser le boot du service.
        payload = dict(sample_config_dict)
        payload["cimier"] = {"weather_provider": "oui"}
        config_file = tmp_path / "config.json"
        config_file.write_text(json.dumps(payload))
        assert ConfigLoader(config_file).load().cimier.weather_provider.type == "noop"
```

Ajouter `WeatherProviderConfig` à l'import `from core.config.config_loader import (…)` en tête du fichier s'il n'y figure pas.

- [ ] **Step 2 : lancer les tests et vérifier qu'ils échouent**

Run: `uv run --extra dev pytest tests/test_config_loader.py::TestWeatherProviderConfig -v`
Expected: FAIL — `AttributeError: 'WeatherProviderConfig' object has no attribute 'host'`

- [ ] **Step 3 : étendre la dataclass**

Dans `core/config/config_loader.py`, remplacer le corps de `WeatherProviderConfig` (la ligne `type: str = "noop"` et sa docstring) par :

```python
@dataclass
class WeatherProviderConfig:
    """Configuration du provider météo cimier.

    ``type="noop"`` (défaut) : provider inerte, toujours OK — comportement
    historique, aucune régression pour une config non migrée.

    ``type="shelly_rain"`` : capteur de pluie MH-RD lu via un Shelly Plus Uni
    dédié (RPC ``Input.GetStatus``). Valeurs mesurées sur le terrain le
    14/08/2026 : D0 sur l'entrée ``id=0``, ``state=true`` = pluie, donc
    ``invert=false``.

    ``protection_enabled`` est la case « Protection pluie » du dashboard.
    Désarmée, le capteur est lu, publié et journalisé mais ne commande rien —
    c'est le mode d'observation qui permet d'éprouver le comportement sous un
    orage réel sans risque.

    ``confirm_reads`` : nombre de lectures concordantes exigées avant de
    changer d'état (anti-rebond). ``watch_interval_s`` : cadence de la veille
    dans ``cimier_service``.

    IP réelle uniquement dans ``data/config.json`` (terrain) — code neutre.
    """

    type: str = "noop"
    host: str = ""
    input_id: int = 0
    invert: bool = False
    timeout_s: float = 3.0
    protection_enabled: bool = False
    watch_interval_s: float = 10.0
    confirm_reads: int = 2
```

- [ ] **Step 4 : étendre le parser**

Dans `core/config/config_loader.py`, méthode `_parse_cimier`, remplacer le bloc :

```python
            weather_provider=WeatherProviderConfig(
                type=str(wp.get("type", wp_defaults.type)),
            ),
```

par :

```python
            weather_provider=WeatherProviderConfig(
                type=str(wp.get("type", wp_defaults.type)),
                host=str(wp.get("host", wp_defaults.host)),
                input_id=int(wp.get("input_id", wp_defaults.input_id)),
                invert=bool(wp.get("invert", wp_defaults.invert)),
                timeout_s=float(wp.get("timeout_s", wp_defaults.timeout_s)),
                protection_enabled=bool(
                    wp.get("protection_enabled", wp_defaults.protection_enabled)
                ),
                watch_interval_s=float(
                    wp.get("watch_interval_s", wp_defaults.watch_interval_s)
                ),
                confirm_reads=int(wp.get("confirm_reads", wp_defaults.confirm_reads)),
            ),
```

Vérifier au passage que `wp` est bien protégé contre une valeur non-dict, comme `ms` et `sr` le sont juste au-dessus. Si la ligne `wp = c.get("weather_provider", {}) if isinstance(c, dict) else {}` n'est pas suivie d'un garde, ajouter :

```python
        if not isinstance(wp, dict):
            wp = {}
```

- [ ] **Step 5 : vérifier que les tests passent**

Run: `uv run --extra dev pytest tests/test_config_loader.py -v`
Expected: PASS — toute la classe, plus les tests préexistants.

- [ ] **Step 6 : mettre à jour le gabarit**

Dans `data/config.template.json`, remplacer la section `cimier.weather_provider` par :

```json
  "weather_provider": {
    "_comment": "Capteur de pluie MH-RD sur Shelly Plus Uni (.87), D0 câblé sur l'entrée id=0. type ∈ {noop, shelly_rain} — mettre shelly_rain dans le config.json terrain. Valeurs mesurées le 14/08/2026 : state=true = pluie (invert=false), séchage ≤ 1 min 51 s. protection_enabled=false : le capteur est lu et affiché mais ne commande rien (mode observation).",
    "type": "noop",
    "host": "192.168.1.87",
    "input_id": 0,
    "invert": false,
    "timeout_s": 3.0,
    "protection_enabled": false,
    "watch_interval_s": 10.0,
    "confirm_reads": 2
  },
```

- [ ] **Step 7 : ignorer les journaux de nuit**

Ajouter à la fin de `.gitignore` :

```
# Journaux de nuit cimier (données terrain, cf. data/sessions/)
data/nights/*.jsonl
!data/nights/.gitkeep
```

Puis créer le répertoire suivi :

```bash
mkdir -p data/nights && touch data/nights/.gitkeep
```

- [ ] **Step 8 : vérifier que la page Configuration reste complète**

La page `/configuration/` impose une aide sur chaque champ, verrouillée par un test de complétude.

Run: `uv run --extra dev pytest tests/ -k "configuration or config_schema" -v`
Expected: PASS. En cas d'échec sur un champ sans aide, l'aide provient du `_comment` de la section — vérifier que le `_comment` du Step 6 est bien présent, ou compléter `HELP_REGISTRY` dans le module de schéma de configuration comme le font les champs existants.

- [ ] **Step 9 : format, lint, commit**

```bash
uv run --extra dev ruff format core/config/config_loader.py tests/test_config_loader.py
uv run --extra dev ruff check core/config/config_loader.py tests/test_config_loader.py
git add core/config/config_loader.py data/config.template.json .gitignore data/nights/.gitkeep tests/test_config_loader.py
git commit -m "feat(pluie): configuration du provider capteur de pluie (defaults rétro-compatibles)"
```

---

## Task 3 : `ShellyRainWeatherProvider`

**Files:**
- Modify: `core/hardware/weather_provider.py`
- Test: `tests/test_weather_provider.py`

- [ ] **Step 1 : écrire les tests du provider**

Ajouter à `tests/test_weather_provider.py` (garder les imports existants, ajouter ceux nécessaires en tête) :

```python
from core.hardware.weather_provider import (
    RAIN_DRY,
    RAIN_UNREACHABLE,
    RAIN_WET,
    ShellyRainWeatherProvider,
)


class FakeRainShelly:
    """urlopen programmable : ``script`` = liste de bool ou d'exceptions."""

    def __init__(self, script):
        self._script = list(script)
        self.calls = []

    def __call__(self, url, timeout=None):
        self.calls.append(url)
        idx = min(len(self.calls) - 1, len(self._script) - 1)
        item = self._script[idx]
        if isinstance(item, Exception):
            raise item
        return _FakeResp(('{"id":0,"state":%s}' % ("true" if item else "false")).encode())


class _FakeResp:
    def __init__(self, body, status=200):
        self._body = body
        self.status = status

    def read(self):
        return self._body

    def __enter__(self):
        return self

    def __exit__(self, *exc):
        return False


def make_provider(script, **kwargs):
    return ShellyRainWeatherProvider(
        host="1.2.3.4", urlopen=FakeRainShelly(script), **kwargs
    )


class TestShellyRainProviderReading:
    def test_initial_state_is_unreachable_before_any_read(self):
        p = make_provider([False])
        assert p.state == RAIN_UNREACHABLE

    def test_two_dry_reads_confirm_dry(self):
        p = make_provider([False, False])
        p.read_now()
        assert p.read_now() == RAIN_DRY

    def test_two_wet_reads_confirm_wet(self):
        p = make_provider([True, True])
        p.read_now()
        assert p.read_now() == RAIN_WET

    def test_single_wet_read_does_not_flip_confirmed_state(self):
        # sec confirmé, puis UNE lecture humide isolée : l'état ne bascule pas.
        p = make_provider([False, False, True, False])
        p.read_now()
        p.read_now()
        assert p.state == RAIN_DRY
        assert p.read_now() == RAIN_DRY
        assert p.read_now() == RAIN_DRY

    def test_invert_flips_interpretation(self):
        p = make_provider([True, True], invert=True)
        p.read_now()
        assert p.read_now() == RAIN_DRY

    def test_confirm_reads_one_flips_immediately(self):
        p = make_provider([True], confirm_reads=1)
        assert p.read_now() == RAIN_WET


class TestShellyRainProviderDecisions:
    def test_dry_is_safe_for_both(self):
        p = make_provider([False, False])
        p.read_now()
        p.read_now()
        assert p.is_safe_to_open() is True
        assert p.is_safe_to_keep_open() is True

    def test_wet_blocks_both(self):
        p = make_provider([True, True])
        p.read_now()
        p.read_now()
        assert p.is_safe_to_open() is False
        assert p.is_safe_to_keep_open() is False

    def test_unreachable_blocks_opening_but_never_closes(self):
        # Décision terrain : on n'ouvre pas à l'aveugle, mais on ne ferme
        # jamais une session sur une absence de donnée.
        import urllib.error

        p = make_provider([urllib.error.URLError("down"), urllib.error.URLError("down")])
        p.read_now()
        p.read_now()
        assert p.state == RAIN_UNREACHABLE
        assert p.is_safe_to_open() is False
        assert p.is_safe_to_keep_open() is True

    def test_never_raises_on_network_error(self):
        import urllib.error

        p = make_provider([urllib.error.URLError("down")])
        assert p.read_now() == RAIN_UNREACHABLE


class TestShellyRainProviderDescribe:
    def test_describe_is_json_serializable_and_complete(self):
        p = make_provider([True, True])
        p.read_now()
        p.read_now()
        d = p.describe()
        assert d["provider"] == "shelly_rain"
        assert d["state"] == RAIN_WET
        assert d["host"] == "1.2.3.4"
        assert d["input_id"] == 0
        assert d["last_read_at"] is not None
        # Le service logge describe() inline dans cimier_event=cycle_start.
        json.dumps(d, sort_keys=True)

    def test_describe_carries_error_when_unreachable(self):
        import urllib.error

        p = make_provider([urllib.error.URLError("down")])
        p.read_now()
        assert p.describe()["error"]

    def test_protocol_conformance(self):
        assert isinstance(make_provider([False]), WeatherProvider)


class TestMakeWeatherProviderRain:
    def test_shelly_rain_type_builds_rain_provider_wrapped(self):
        from core.config.config_loader import WeatherProviderConfig
        from core.hardware.weather_provider import RainProtection

        p = make_weather_provider(
            WeatherProviderConfig(type="shelly_rain", host="1.2.3.4")
        )
        assert isinstance(p, RainProtection)

    def test_shelly_rain_without_host_raises(self):
        from core.config.config_loader import WeatherProviderConfig

        with pytest.raises(ValueError, match="host"):
            make_weather_provider(WeatherProviderConfig(type="shelly_rain", host=""))
```

- [ ] **Step 2 : lancer les tests et vérifier qu'ils échouent**

Run: `uv run --extra dev pytest tests/test_weather_provider.py -v`
Expected: FAIL — `ImportError: cannot import name 'ShellyRainWeatherProvider'`

- [ ] **Step 3 : implémenter le provider**

Dans `core/hardware/weather_provider.py`, ajouter après la classe `NoopWeatherProvider` :

```python
# États confirmés du capteur de pluie.
RAIN_WET = "wet"
RAIN_DRY = "dry"
RAIN_UNREACHABLE = "unreachable"


class ShellyRainWeatherProvider:
    """Capteur de pluie MH-RD lu via un Shelly Plus Uni dédié.

    La sortie D0 du comparateur LM393 est câblée sur une entrée digitale du
    Shelly, lue en RPC (``Input.GetStatus``). Le seuil pluie/sec est réglé en
    **matériel** par le trimpot du module : ce provider ne fait que lire un
    état déjà comparé.

    **Aucune I/O dans les méthodes du contrat.** ``read_now()`` fait la
    requête et met à jour l'état ; ``is_safe_to_*`` et ``describe()`` lisent le
    dernier état connu. Ainsi la veille de ``cimier_service`` et le scheduler
    partagent une lecture unique, sans se marcher dessus ni doubler le trafic.

    **Anti-rebond** : il faut ``confirm_reads`` lectures concordantes pour
    changer d'état. Une lecture aberrante isolée ne doit pas mettre fin à une
    nuit d'observation.

    **Asymétrie du fail-safe** — capteur injoignable :
      - ``is_safe_to_open()`` → False : on n'ouvre pas à l'aveugle (refuser est
        réversible et sans coût) ;
      - ``is_safe_to_keep_open()`` → True : on ne ferme **jamais** sur une
        absence de donnée. La fiabilité des Shelly est un sujet connu du
        projet ; une coupure Wi-Fi passagère ne doit pas tuer une session.

    Ne lève jamais vers ses consommateurs.
    """

    def __init__(
        self,
        host: str,
        input_id: int = 0,
        invert: bool = False,
        timeout_s: float = 3.0,
        confirm_reads: int = 2,
        urlopen=None,
        clock=None,
    ) -> None:
        import time as _time

        self._host = host
        self._input_id = int(input_id)
        self._invert = bool(invert)
        self._timeout_s = float(timeout_s)
        self._confirm_reads = max(1, int(confirm_reads))
        self._urlopen = urlopen
        self._clock = clock or _time.time

        self._state = RAIN_UNREACHABLE
        self._pending = None
        self._pending_count = 0
        self._last_read_ts = None
        self._last_error = ""

    @property
    def state(self) -> str:
        """Dernier état confirmé : ``wet`` | ``dry`` | ``unreachable``."""
        return self._state

    def read_now(self) -> str:
        """Interroge le Shelly, applique l'anti-rebond, retourne l'état confirmé."""
        from core.hardware.shelly_rpc import ShellyRpcError, read_input_state

        try:
            raw, _payload = read_input_state(
                self._host, self._input_id, self._timeout_s, self._urlopen
            )
        except ShellyRpcError as exc:
            observed = RAIN_UNREACHABLE
            self._last_error = str(exc)
        else:
            # Convention mesurée le 14/08/2026 : state=true = pluie
            # (invert=false). `invert` reste offert si le câblage change.
            observed = RAIN_WET if raw != self._invert else RAIN_DRY
            self._last_error = ""

        if observed == self._pending:
            self._pending_count += 1
        else:
            self._pending = observed
            self._pending_count = 1
        if self._pending_count >= self._confirm_reads:
            self._state = observed

        self._last_read_ts = self._clock()
        return self._state

    def is_safe_to_open(self) -> bool:
        return self._state == RAIN_DRY

    def is_safe_to_keep_open(self) -> bool:
        return self._state != RAIN_WET

    def describe(self) -> Dict[str, Any]:
        from datetime import datetime

        last_read_at = None
        if self._last_read_ts is not None:
            last_read_at = datetime.fromtimestamp(self._last_read_ts).isoformat(
                timespec="seconds"
            )
        return {
            "provider": "shelly_rain",
            "state": self._state,
            "host": self._host,
            "input_id": self._input_id,
            "last_read_at": last_read_at,
            "error": self._last_error,
        }
```

- [ ] **Step 4 : enrichir la factory**

Remplacer `make_weather_provider` par :

```python
def make_weather_provider(cfg: "WeatherProviderConfig") -> WeatherProvider:
    """Factory : instancie le provider d'après la config.

    type ∈ {noop, shelly_rain}. Un type inconnu lève — jamais d'inférence
    silencieuse sur un composant de protection.

    Le provider pluie est toujours renvoyé **enveloppé dans RainProtection**,
    qui porte l'armement : sans armement explicite (case décochée), il ne
    commande rien.
    """
    t = (cfg.type or "noop").lower()
    if t == "noop":
        return NoopWeatherProvider()
    if t == "shelly_rain":
        if not cfg.host:
            raise ValueError("WeatherProviderConfig.host vide pour shelly_rain")
        inner = ShellyRainWeatherProvider(
            host=cfg.host,
            input_id=cfg.input_id,
            invert=cfg.invert,
            timeout_s=cfg.timeout_s,
            confirm_reads=cfg.confirm_reads,
        )
        return RainProtection(inner, armed=cfg.protection_enabled)
    raise ValueError("WeatherProviderConfig.type inconnu: " + repr(cfg.type))
```

`RainProtection` est écrite à la Task 4 : les tests de cette task échoueront tant qu'elle n'existe pas. C'est volontaire — les deux tasks se commitent ensemble à la fin de la Task 4.

- [ ] **Step 5 : enchaîner sur la Task 4 sans commit**

Les tests `TestShellyRainProviderReading`, `…Decisions` et `…Describe` doivent déjà passer :

Run: `uv run --extra dev pytest tests/test_weather_provider.py -k "not MakeWeatherProviderRain" -v`
Expected: PASS.

`TestMakeWeatherProviderRain` échoue encore (`RainProtection` absente) — c'est attendu.

---

## Task 4 : `RainProtection` — armement et verrou

**Files:**
- Modify: `core/hardware/weather_provider.py`
- Test: `tests/test_weather_provider.py`

- [ ] **Step 1 : écrire les tests**

Ajouter à `tests/test_weather_provider.py` :

```python
class StubRainProvider:
    """Provider minimal pour tester la politique sans réseau."""

    def __init__(self, state=RAIN_DRY):
        self.state = state
        self.read_calls = 0

    def read_now(self):
        self.read_calls += 1
        return self.state

    def is_safe_to_open(self):
        return self.state == RAIN_DRY

    def is_safe_to_keep_open(self):
        return self.state != RAIN_WET

    def describe(self):
        return {"provider": "stub", "state": self.state}


class TestRainProtectionDisarmed:
    def test_disarmed_allows_everything_even_under_rain(self):
        from core.hardware.weather_provider import RainProtection

        p = RainProtection(StubRainProvider(RAIN_WET), armed=False)
        assert p.is_safe_to_open() is True
        assert p.is_safe_to_keep_open() is True

    def test_disarmed_still_exposes_real_state(self):
        # C'est tout l'intérêt du mode observation : on voit sans agir.
        from core.hardware.weather_provider import RainProtection

        p = RainProtection(StubRainProvider(RAIN_WET), armed=False)
        assert p.state == RAIN_WET
        assert p.describe()["state"] == RAIN_WET
        assert p.describe()["armed"] is False

    def test_disarmed_still_reads(self):
        from core.hardware.weather_provider import RainProtection

        inner = StubRainProvider(RAIN_WET)
        RainProtection(inner, armed=False).read_now()
        assert inner.read_calls == 1


class TestRainProtectionArmed:
    def test_armed_relays_provider_under_rain(self):
        from core.hardware.weather_provider import RainProtection

        p = RainProtection(StubRainProvider(RAIN_WET), armed=True)
        assert p.is_safe_to_open() is False
        assert p.is_safe_to_keep_open() is False

    def test_armed_allows_when_dry(self):
        from core.hardware.weather_provider import RainProtection

        p = RainProtection(StubRainProvider(RAIN_DRY), armed=True)
        assert p.is_safe_to_open() is True
        assert p.is_safe_to_keep_open() is True

    def test_armed_can_be_toggled_at_runtime(self):
        # Hot-reload de la case à cocher, sans redémarrer le service.
        from core.hardware.weather_provider import RainProtection

        p = RainProtection(StubRainProvider(RAIN_WET), armed=False)
        assert p.is_safe_to_keep_open() is True
        p.armed = True
        assert p.is_safe_to_keep_open() is False


class TestRainProtectionLatch:
    def test_latch_blocks_reopening_even_once_dry(self):
        from core.hardware.weather_provider import RainProtection

        inner = StubRainProvider(RAIN_WET)
        p = RainProtection(inner, armed=True)
        p.latch()
        inner.state = RAIN_DRY
        assert p.is_safe_to_open() is False

    def test_release_lifts_the_latch(self):
        from core.hardware.weather_provider import RainProtection

        inner = StubRainProvider(RAIN_DRY)
        p = RainProtection(inner, armed=True)
        p.latch()
        p.release()
        assert p.is_safe_to_open() is True

    def test_latch_does_not_block_keeping_open_when_dry(self):
        # Le verrou porte sur l'ouverture, pas sur le maintien.
        from core.hardware.weather_provider import RainProtection

        p = RainProtection(StubRainProvider(RAIN_DRY), armed=True)
        p.latch()
        assert p.is_safe_to_keep_open() is True

    def test_latch_is_reported_in_describe(self):
        from core.hardware.weather_provider import RainProtection

        p = RainProtection(StubRainProvider(RAIN_DRY), armed=True)
        p.latch()
        assert p.describe()["latched"] is True

    def test_disarmed_ignores_latch(self):
        from core.hardware.weather_provider import RainProtection

        p = RainProtection(StubRainProvider(RAIN_DRY), armed=False)
        p.latch()
        assert p.is_safe_to_open() is True
```

- [ ] **Step 2 : lancer les tests et vérifier qu'ils échouent**

Run: `uv run --extra dev pytest tests/test_weather_provider.py -k "RainProtection" -v`
Expected: FAIL — `ImportError: cannot import name 'RainProtection'`

- [ ] **Step 3 : implémenter la politique**

Dans `core/hardware/weather_provider.py`, ajouter après `ShellyRainWeatherProvider` :

```python
class RainProtection:
    """Politique d'armement autour d'un provider pluie.

    Le provider mesure ; cet objet décide si la mesure a le droit de commander
    quoi que ce soit. Implémente le même contrat, donc transparent pour le
    scheduler.

    - **Désarmé** (défaut) : ``is_safe_to_*`` renvoient True sans condition. Le
      capteur est lu, publié, affiché, journalisé — et strictement inerte.
      C'est le mode qui permet d'observer un orage réel sans risque avant de
      confier la protection au système.
    - **Armé** : relaie le provider. Refus d'ouverture *et* fermeture
      d'urgence — la case gouverne tout le comportement pluie.

    ``latched`` est le **verrou anti-réouverture** : une fermeture pluie le
    pose, et plus aucune ouverture automatique n'est autorisée, même si le
    capteur redevient sec. Décision produit : on ne rouvre pas sur une
    éclaircie, la monture n'a pas à être re-exposée en pleine nuit. Seule une
    commande d'ouverture humaine (ou un redémarrage) le lève.

    ``armed`` est mutable : ``cimier_service`` le rafraîchit depuis
    ``config.json`` à chaque tour de veille, ce qui fait prendre effet la case
    en quelques secondes sans redémarrage.
    """

    def __init__(self, provider, armed: bool = False) -> None:
        self._inner = provider
        self.armed = bool(armed)
        self.latched = False

    @property
    def inner(self):
        return self._inner

    @property
    def state(self):
        return getattr(self._inner, "state", None)

    def read_now(self):
        """Délègue la lecture — l'observation a lieu même désarmée."""
        return self._inner.read_now()

    def latch(self) -> None:
        self.latched = True

    def release(self) -> None:
        self.latched = False

    def is_safe_to_open(self) -> bool:
        if not self.armed:
            return True
        if self.latched:
            return False
        return self._inner.is_safe_to_open()

    def is_safe_to_keep_open(self) -> bool:
        if not self.armed:
            return True
        return self._inner.is_safe_to_keep_open()

    def describe(self) -> Dict[str, Any]:
        payload = dict(self._inner.describe())
        payload["armed"] = self.armed
        payload["latched"] = self.latched
        return payload
```

- [ ] **Step 4 : vérifier que tout le module passe**

Run: `uv run --extra dev pytest tests/test_weather_provider.py -v`
Expected: PASS — y compris `TestMakeWeatherProviderRain` de la Task 3.

- [ ] **Step 5 : format, lint, commit**

```bash
uv run --extra dev ruff format core/hardware/weather_provider.py tests/test_weather_provider.py
uv run --extra dev ruff check core/hardware/weather_provider.py tests/test_weather_provider.py
git add core/hardware/weather_provider.py tests/test_weather_provider.py
git commit -m "feat(pluie): provider Shelly + politique d'armement avec verrou anti-réouverture"
```

---

## Task 5 : journal de nuit

**Files:**
- Create: `services/night_journal.py`
- Test: `tests/test_night_journal.py`

- [ ] **Step 1 : écrire les tests**

Créer `tests/test_night_journal.py` :

```python
"""Tests du journal de nuit cimier (transitions pluie + événements cimier)."""

from __future__ import annotations

import json
from datetime import datetime, timedelta

from services import night_journal


class TestNightKey:
    def test_evening_belongs_to_its_own_date(self):
        assert night_journal.night_key(datetime(2026, 8, 14, 22, 30)) == "2026-08-14"

    def test_after_midnight_belongs_to_the_previous_date(self):
        # Une nuit ne doit pas être coupée en deux à minuit.
        assert night_journal.night_key(datetime(2026, 8, 15, 3, 15)) == "2026-08-14"

    def test_noon_starts_a_new_night(self):
        assert night_journal.night_key(datetime(2026, 8, 15, 12, 0)) == "2026-08-15"

    def test_just_before_noon_still_previous_night(self):
        assert night_journal.night_key(datetime(2026, 8, 15, 11, 59)) == "2026-08-14"


class TestAppendAndRead:
    def test_append_then_read_roundtrip(self, tmp_path):
        night_journal.append_event(
            "rain",
            at=datetime(2026, 8, 14, 22, 30),
            nights_dir=tmp_path,
            state="wet",
            armed=False,
        )
        events = night_journal.read_night("2026-08-14", nights_dir=tmp_path)
        assert len(events) == 1
        assert events[0]["event"] == "rain"
        assert events[0]["state"] == "wet"
        assert events[0]["armed"] is False
        assert events[0]["ts"].startswith("2026-08-14T22:30")

    def test_appends_accumulate_in_order(self, tmp_path):
        for minute, state in ((0, "wet"), (5, "dry"), (9, "wet")):
            night_journal.append_event(
                "rain",
                at=datetime(2026, 8, 14, 23, minute),
                nights_dir=tmp_path,
                state=state,
            )
        events = night_journal.read_night("2026-08-14", nights_dir=tmp_path)
        assert [e["state"] for e in events] == ["wet", "dry", "wet"]

    def test_events_after_midnight_land_in_the_same_file(self, tmp_path):
        night_journal.append_event(
            "rain", at=datetime(2026, 8, 14, 23, 50), nights_dir=tmp_path, state="wet"
        )
        night_journal.append_event(
            "rain", at=datetime(2026, 8, 15, 0, 10), nights_dir=tmp_path, state="dry"
        )
        assert len(night_journal.read_night("2026-08-14", nights_dir=tmp_path)) == 2

    def test_read_unknown_night_returns_empty(self, tmp_path):
        assert night_journal.read_night("1999-01-01", nights_dir=tmp_path) == []

    def test_corrupted_line_is_skipped_not_fatal(self, tmp_path):
        night_journal.append_event(
            "rain", at=datetime(2026, 8, 14, 22, 0), nights_dir=tmp_path, state="wet"
        )
        path = tmp_path / "2026-08-14.jsonl"
        with open(path, "a", encoding="utf-8") as fh:
            fh.write("{ceci n'est pas du json\n")
        assert len(night_journal.read_night("2026-08-14", nights_dir=tmp_path)) == 1

    def test_append_never_raises_on_io_error(self, tmp_path):
        # Un disque plein ne doit jamais empêcher une fermeture d'urgence.
        unwritable = tmp_path / "fichier"
        unwritable.write_text("", encoding="utf-8")
        assert (
            night_journal.append_event(
                "rain", at=datetime(2026, 8, 14, 22, 0), nights_dir=unwritable, state="wet"
            )
            is False
        )


class TestListAndPurge:
    def test_list_nights_is_sorted_most_recent_first(self, tmp_path):
        for day in (12, 14, 13):
            night_journal.append_event(
                "rain", at=datetime(2026, 8, day, 22, 0), nights_dir=tmp_path, state="wet"
            )
        assert night_journal.list_nights(nights_dir=tmp_path) == [
            "2026-08-14",
            "2026-08-13",
            "2026-08-12",
        ]

    def test_purge_removes_files_older_than_retention(self, tmp_path):
        now = datetime(2026, 8, 14, 12, 0)
        old = now - timedelta(days=40)
        recent = now - timedelta(days=3)
        for moment in (old, recent):
            night_journal.append_event(
                "rain", at=moment, nights_dir=tmp_path, state="wet"
            )
        removed = night_journal.purge_old(nights_dir=tmp_path, retention_days=30, now=now)
        assert removed == 1
        remaining = night_journal.list_nights(nights_dir=tmp_path)
        assert remaining == [night_journal.night_key(recent)]

    def test_purge_keeps_everything_within_retention(self, tmp_path):
        now = datetime(2026, 8, 14, 12, 0)
        night_journal.append_event(
            "rain", at=now - timedelta(days=2), nights_dir=tmp_path, state="wet"
        )
        assert night_journal.purge_old(nights_dir=tmp_path, retention_days=30, now=now) == 0


class TestEventShapes:
    def test_decision_event(self, tmp_path):
        night_journal.append_event(
            "decision",
            at=datetime(2026, 8, 14, 23, 0),
            nights_dir=tmp_path,
            action="would_close",
            reason="rain",
        )
        e = night_journal.read_night("2026-08-14", nights_dir=tmp_path)[0]
        assert e["event"] == "decision"
        assert e["action"] == "would_close"

    def test_cimier_event(self, tmp_path):
        night_journal.append_event(
            "cimier",
            at=datetime(2026, 8, 14, 21, 0),
            nights_dir=tmp_path,
            action="open",
            result="ok",
        )
        e = night_journal.read_night("2026-08-14", nights_dir=tmp_path)[0]
        assert e["event"] == "cimier"
        assert e["result"] == "ok"

    def test_lines_are_valid_jsonl(self, tmp_path):
        night_journal.append_event(
            "rain", at=datetime(2026, 8, 14, 22, 0), nights_dir=tmp_path, state="dry"
        )
        raw = (tmp_path / "2026-08-14.jsonl").read_text(encoding="utf-8")
        assert raw.endswith("\n")
        json.loads(raw.strip())
```

- [ ] **Step 2 : lancer les tests et vérifier qu'ils échouent**

Run: `uv run --extra dev pytest tests/test_night_journal.py -v`
Expected: FAIL — `ModuleNotFoundError: No module named 'services.night_journal'`

- [ ] **Step 3 : implémenter le journal**

Créer `services/night_journal.py` :

```python
"""Journal de nuit cimier — trace persistante des transitions.

La timeline du dashboard est un buffer mémoire de 50 entrées, perdu au
rechargement de la page : inutilisable pour relire une nuit le lendemain. Ce
module écrit sur disque ce qu'il faut pour reconstituer la nuit — les
transitions du capteur de pluie, les décisions de la protection, les cycles
cimier.

**Transitions, pas échantillons.** Une ligne n'est écrite que quand quelque
chose change. Échantillonner l'état toutes les 10 s produirait 8 640 points
par nuit pour la même information.

**Découpage midi → midi.** Une nuit d'observation traverse minuit : la
découper à minuit scinderait chaque session en deux fichiers. La nuit
``2026-08-14`` couvre donc du 14/08 12:00 au 15/08 11:59, heure locale.

Écriture en append avec ``flush`` immédiat : une coupure ne doit rien perdre.
Aucune erreur d'E/S n'est propagée — un disque plein ne doit jamais empêcher
une fermeture d'urgence.
"""

from __future__ import annotations

import json
import logging
from datetime import datetime, timedelta
from pathlib import Path
from typing import Any, Dict, List, Optional

logger = logging.getLogger(__name__)

DEFAULT_NIGHTS_DIR = Path(__file__).resolve().parents[1] / "data" / "nights"

# Heure locale à laquelle une nuit de journal commence.
NIGHT_BOUNDARY_HOUR = 12

# Les fichiers pèsent quelques kilo-octets : 30 jours couvrent une saison
# d'essais et permettent de comparer plusieurs épisodes de pluie entre eux.
RETENTION_DAYS = 30


def night_key(moment: datetime) -> str:
    """Nuit à laquelle appartient un instant, au format ``AAAA-MM-JJ``."""
    if moment.hour < NIGHT_BOUNDARY_HOUR:
        moment = moment - timedelta(days=1)
    return moment.strftime("%Y-%m-%d")


def _resolve_dir(nights_dir: Optional[Path]) -> Path:
    return Path(nights_dir) if nights_dir is not None else DEFAULT_NIGHTS_DIR


def append_event(
    event: str,
    *,
    at: Optional[datetime] = None,
    nights_dir: Optional[Path] = None,
    **fields: Any,
) -> bool:
    """Ajoute une ligne au journal de la nuit courante.

    Args:
        event: ``"rain"`` | ``"decision"`` | ``"cimier"``.
        at: instant de l'événement (heure locale). ``datetime.now()`` si absent.
        **fields: champs propres au type d'événement (``state``, ``armed``,
            ``action``, ``reason``, ``result``…).

    Returns:
        True si la ligne a été écrite, False si l'écriture a échoué (l'échec
        est journalisé, jamais propagé).
    """
    moment = at or datetime.now()
    directory = _resolve_dir(nights_dir)
    payload: Dict[str, Any] = {"ts": moment.isoformat(timespec="seconds"), "event": event}
    payload.update(fields)
    try:
        directory.mkdir(parents=True, exist_ok=True)
        target = directory / (night_key(moment) + ".jsonl")
        with open(target, "a", encoding="utf-8") as fh:
            fh.write(json.dumps(payload, ensure_ascii=False) + "\n")
            fh.flush()
        return True
    except (OSError, TypeError, ValueError) as exc:
        logger.warning("night_journal_event=append_failed event=%s exc=%s", event, exc)
        return False


def read_night(date_key: str, nights_dir: Optional[Path] = None) -> List[Dict[str, Any]]:
    """Lit les événements d'une nuit. Liste vide si le fichier n'existe pas.

    Une ligne corrompue est ignorée : un journal partiellement lisible reste
    plus utile qu'une erreur.
    """
    target = _resolve_dir(nights_dir) / (str(date_key) + ".jsonl")
    events: List[Dict[str, Any]] = []
    try:
        with open(target, "r", encoding="utf-8") as fh:
            for line in fh:
                line = line.strip()
                if not line:
                    continue
                try:
                    parsed = json.loads(line)
                except ValueError:
                    continue
                if isinstance(parsed, dict):
                    events.append(parsed)
    except OSError:
        return []
    return events


def list_nights(nights_dir: Optional[Path] = None) -> List[str]:
    """Nuits disponibles, de la plus récente à la plus ancienne."""
    directory = _resolve_dir(nights_dir)
    try:
        keys = [p.stem for p in directory.glob("*.jsonl")]
    except OSError:
        return []
    return sorted(keys, reverse=True)


def purge_old(
    nights_dir: Optional[Path] = None,
    retention_days: int = RETENTION_DAYS,
    now: Optional[datetime] = None,
) -> int:
    """Supprime les journaux au-delà de la rétention. Retourne le nombre supprimé."""
    directory = _resolve_dir(nights_dir)
    reference = now or datetime.now()
    cutoff = (reference - timedelta(days=int(retention_days))).strftime("%Y-%m-%d")
    removed = 0
    for key in list_nights(nights_dir=directory):
        if key >= cutoff:
            continue
        try:
            (directory / (key + ".jsonl")).unlink()
            removed += 1
        except OSError as exc:
            logger.warning("night_journal_event=purge_failed night=%s exc=%s", key, exc)
    return removed
```

- [ ] **Step 4 : vérifier que les tests passent**

Run: `uv run --extra dev pytest tests/test_night_journal.py -v`
Expected: PASS — 17 tests.

- [ ] **Step 5 : format, lint, commit**

```bash
uv run --extra dev ruff format services/night_journal.py tests/test_night_journal.py
uv run --extra dev ruff check services/night_journal.py tests/test_night_journal.py
git add services/night_journal.py tests/test_night_journal.py
git commit -m "feat(pluie): journal de nuit persistant (transitions, découpage midi-midi, purge 30j)"
```

---

## Task 6 : factoriser la séquence de fermeture de session

La séquence `tracking_stop → attente → goto 45° → close` existe en deux copies. C'est leur divergence qui a produit le bug de parking corrigé en 6.11.3 : le correctif de mai n'avait été appliqué qu'à `ParkingSessionView`, laissant `CimierScheduler._trigger_close` cassé trois mois. La fermeture pluie serait une troisième copie — on unifie d'abord.

**Files:**
- Create: `services/session_close_sequence.py`
- Modify: `services/cimier_scheduler.py:375-395`
- Modify: `web/cimier/views.py:342-381`
- Test: `tests/test_session_close_sequence.py`

- [ ] **Step 1 : écrire les tests de la séquence**

Créer `tests/test_session_close_sequence.py` :

```python
"""Tests de la séquence unique de fermeture de session.

Elle existait en deux copies divergentes (bug de parking 6.11.3) : ces tests
verrouillent l'ordre des opérations pour les trois appelants.
"""

from __future__ import annotations

from services.session_close_sequence import close_session


class RecordingMotorIpc:
    def __init__(self, tracking_stop_confirmed=True):
        self.calls = []
        self._confirmed = tracking_stop_confirmed

    def send_tracking_stop(self):
        self.calls.append("tracking_stop")
        return True

    def wait_tracking_stopped(self):
        self.calls.append("wait")
        return self._confirmed

    def send_goto(self, angle):
        self.calls.append("goto:%s" % angle)
        return True


def test_order_is_stop_then_wait_then_goto():
    # L'attente entre les deux est le cœur du fix 6.11.3 : motor_command.json
    # n'a qu'un slot, un goto émis trop tôt écrase le tracking_stop.
    motor = RecordingMotorIpc()
    close_session(motor, lambda: True, 45.0, reason="rain")
    assert motor.calls == ["tracking_stop", "wait", "goto:45.0"]


def test_close_callable_is_invoked():
    called = []
    close_session(RecordingMotorIpc(), lambda: called.append(True) or True, 45.0, reason="auto")
    assert called == [True]


def test_returns_outcome_of_each_step():
    result = close_session(RecordingMotorIpc(), lambda: True, 45.0, reason="rain")
    assert result["tracking_stop_sent"] is True
    assert result["tracking_stop_confirmed"] is True
    assert result["goto_sent"] is True
    assert result["cimier_close_sent"] is True
    assert result["parking_target_deg"] == 45.0


def test_timeout_on_confirmation_does_not_stop_the_sequence():
    # Best-effort : mieux vaut un parking imparfait qu'un cimier resté ouvert.
    motor = RecordingMotorIpc(tracking_stop_confirmed=False)
    result = close_session(motor, lambda: True, 45.0, reason="rain")
    assert motor.calls == ["tracking_stop", "wait", "goto:45.0"]
    assert result["tracking_stop_confirmed"] is False
    assert result["cimier_close_sent"] is True


def test_failing_close_is_reported_not_raised():
    result = close_session(RecordingMotorIpc(), lambda: False, 45.0, reason="rain")
    assert result["cimier_close_sent"] is False


def test_raising_close_is_caught():
    def _boom():
        raise RuntimeError("IPC mort")

    result = close_session(RecordingMotorIpc(), _boom, 45.0, reason="rain")
    assert result["cimier_close_sent"] is False


def test_logs_reason(caplog):
    import logging

    with caplog.at_level(logging.INFO, logger="services.session_close_sequence"):
        close_session(RecordingMotorIpc(), lambda: True, 45.0, reason="rain")
    assert "reason=rain" in caplog.text
```

- [ ] **Step 2 : lancer les tests et vérifier qu'ils échouent**

Run: `uv run --extra dev pytest tests/test_session_close_sequence.py -v`
Expected: FAIL — `ModuleNotFoundError: No module named 'services.session_close_sequence'`

- [ ] **Step 3 : créer le module**

Créer `services/session_close_sequence.py` :

```python
"""Séquence unique de fermeture d'une session d'observation.

``tracking_stop`` → attente de sa consommation → ``goto`` parking → fermeture
du cimier. Trois appelants la partagent :

  - ``CimierScheduler._trigger_close``  — fin de nuit sur éphémérides ;
  - ``ParkingSessionView``              — bouton « Parking » du dashboard ;
  - la veille pluie de ``cimier_service`` — fermeture d'urgence.

**Pourquoi un module et pas trois copies.** Elle a vécu en deux exemplaires
jusqu'en août 2026. Le correctif du 02/05 (attendre la consommation du
``tracking_stop`` avant d'émettre le ``goto``) n'avait été appliqué qu'à l'un
des deux : ``motor_command.json`` n'ayant qu'un seul slot lu à 20 Hz, le
``goto`` écrasait le ``tracking_stop``, le suivi restait actif et la coupole
dérivait hors du parking pendant des heures — bug terrain des 08 et 09/08,
corrigé en 6.11.3. Une troisième copie rejouerait la même histoire.

La fermeture du cimier est passée en **callable** : le scheduler écrit dans
``cimier_command.json`` via ``CimierIpcManager``, Django passe par son propre
client. Le module n'a pas à connaître les deux.

Tout est **best-effort** : aucune étape n'interrompt les suivantes. Un parking
imparfait vaut mieux qu'un cimier resté ouvert.
"""

from __future__ import annotations

import logging
from typing import Any, Callable, Dict

logger = logging.getLogger(__name__)


def close_session(
    motor_ipc: Any,
    send_close: Callable[[], bool],
    parking_target_deg: float,
    reason: str,
) -> Dict[str, Any]:
    """Exécute la séquence complète et retourne le détail de chaque étape.

    Args:
        motor_ipc: writer exposant ``send_tracking_stop``, ``wait_tracking_stopped``
            et ``send_goto``.
        send_close: callable sans argument déclenchant la fermeture du cimier,
            retournant une valeur vraie en cas de succès.
        parking_target_deg: azimut de parking de la coupole.
        reason: motif journalisé (``auto``, ``manual``, ``rain``).
    """
    tracking_stop_sent = bool(motor_ipc.send_tracking_stop())
    tracking_stop_confirmed = bool(motor_ipc.wait_tracking_stopped())
    goto_sent = bool(motor_ipc.send_goto(float(parking_target_deg)))
    try:
        cimier_close_sent = bool(send_close())
    except Exception as exc:  # noqa: BLE001 — best-effort, jamais de propagation
        logger.error("cimier_event=session_close_cimier_failed reason=%s exc=%s", reason, exc)
        cimier_close_sent = False

    logger.info(
        "cimier_event=session_close reason=%s parking_target_deg=%.2f "
        "tracking_stop_sent=%s tracking_stop_confirmed=%s goto_sent=%s cimier_close_sent=%s",
        reason,
        float(parking_target_deg),
        tracking_stop_sent,
        tracking_stop_confirmed,
        goto_sent,
        cimier_close_sent,
    )
    return {
        "tracking_stop_sent": tracking_stop_sent,
        "tracking_stop_confirmed": tracking_stop_confirmed,
        "goto_sent": goto_sent,
        "cimier_close_sent": cimier_close_sent,
        "parking_target_deg": float(parking_target_deg),
        "reason": reason,
    }
```

- [ ] **Step 4 : vérifier que les tests passent**

Run: `uv run --extra dev pytest tests/test_session_close_sequence.py -v`
Expected: PASS — 7 tests.

- [ ] **Step 5 : brancher le scheduler**

Dans `services/cimier_scheduler.py`, remplacer intégralement `_trigger_close` par :

```python
    def _trigger_close(self) -> None:
        """Fin de nuit : arrêt du suivi, parking coupole, fermeture cimier.

        Délègue à ``services.session_close_sequence`` — séquence partagée avec
        le parking manuel et la fermeture pluie (cf. sa docstring pour le bug
        de parking 6.11.3 qui a motivé la factorisation).
        """
        cimier_cmd_id = str(uuid.uuid4())

        def _send_close() -> bool:
            self._cimier_ipc.write_command({"id": cimier_cmd_id, "action": "close"})
            return True

        close_session(
            self._motor_ipc,
            _send_close,
            self._cfg.parking_target_azimuth_deg,
            reason="auto",
        )
        logger.info(
            "cimier_event=automation_close_triggered cimier_cmd_id=%s",
            cimier_cmd_id,
        )
```

Ajouter l'import en tête du fichier, à côté des autres imports `services` :

```python
from services.session_close_sequence import close_session
```

- [ ] **Step 6 : brancher la vue de parking manuel**

Dans `web/cimier/views.py`, remplacer le corps de `ParkingSessionView.post` (à partir de la construction de `motor_writer` jusqu'au `return`) par :

```python
        motor_writer = MotorIpcWriter(
            command_file=Path(settings.MOTOR_SERVICE_IPC["COMMAND_FILE"]),
            status_file=Path(settings.MOTOR_SERVICE_IPC["STATUS_FILE"]),
        )
        outcome = close_session(
            motor_writer,
            lambda: cimier_client.send_command("close"),
            parking_deg,
            reason="manual",
        )
        body = {
            "applied": outcome["tracking_stop_sent"]
            and outcome["goto_sent"]
            and outcome["cimier_close_sent"],
            "tracking_stopped": outcome["tracking_stop_sent"],
            "goto_parking_sent": outcome["goto_sent"],
            "cimier_close_sent": outcome["cimier_close_sent"],
            "parking_target_deg": outcome["parking_target_deg"],
        }
        if body["applied"]:
            return Response(body)
        body["error"] = "Une ou plusieurs commandes IPC ont échoué"
        return Response(body, status=status.HTTP_503_SERVICE_UNAVAILABLE)
```

Ajouter l'import local dans la méthode, à côté de `from services.motor_ipc_writer import MotorIpcWriter` :

```python
        from services.session_close_sequence import close_session
```

Les clés de la réponse JSON sont **inchangées** — le dashboard les consomme.

- [ ] **Step 7 : vérifier la non-régression des deux appelants**

Run: `uv run --extra dev pytest tests/test_cimier_scheduler.py tests/test_cimier_parking_sequence.py tests/test_web_views.py tests/test_session_close_sequence.py -v`
Expected: PASS — en particulier `tests/test_cimier_parking_sequence.py`, qui mime la boucle 20 Hz réelle et garde le bug 6.11.3.

- [ ] **Step 8 : format, lint, commit**

```bash
uv run --extra dev ruff format services/session_close_sequence.py services/cimier_scheduler.py web/cimier/views.py tests/test_session_close_sequence.py
uv run --extra dev ruff check services/session_close_sequence.py services/cimier_scheduler.py web/cimier/views.py tests/test_session_close_sequence.py
git add services/session_close_sequence.py services/cimier_scheduler.py web/cimier/views.py tests/test_session_close_sequence.py
git commit -m "refactor(cimier): séquence de fermeture de session unifiée (fin des deux copies)"
```

---

## Task 7 : veille pluie dans `cimier_service`

**Files:**
- Modify: `services/cimier_service.py` (constructeur, `tick`, `_publish_status`, `execute_command`, `_build_service_from_config`)
- Test: `tests/test_cimier_service.py`

- [ ] **Step 1 : écrire les tests de la veille**

Ajouter à `tests/test_cimier_service.py` :

```python
# ======================================================================
# Veille pluie (2026-08)
# ======================================================================


class StubRainProtection:
    """Double de RainProtection : état pilotable, appels comptés."""

    def __init__(self, state="dry", armed=False):
        self.state = state
        self.armed = armed
        self.latched = False
        self.read_calls = 0

    def read_now(self):
        self.read_calls += 1
        return self.state

    def latch(self):
        self.latched = True

    def release(self):
        self.latched = False

    def is_safe_to_open(self):
        if not self.armed:
            return True
        return (not self.latched) and self.state == "dry"

    def is_safe_to_keep_open(self):
        if not self.armed:
            return True
        return self.state != "wet"

    def describe(self):
        return {
            "provider": "stub",
            "state": self.state,
            "armed": self.armed,
            "latched": self.latched,
        }


class RecordingCloser:
    """Capture les appels à la séquence de fermeture."""

    def __init__(self):
        self.calls = []

    def __call__(self, reason):
        self.calls.append(reason)
        return {"cimier_close_sent": True}


def make_rain_service(tmp_path, rain, cimier_open=True, watch_interval_s=0.0):
    """Service prêt pour la veille, avec un cimier observé ouvert ou fermé."""
    from core.config.config_loader import WeatherProviderConfig

    cfg = CimierConfig(
        enabled=True,
        weather_provider=WeatherProviderConfig(
            type="shelly_rain", host="1.2.3.4", watch_interval_s=watch_interval_s
        ),
    )
    ipc = CimierIpcManager(
        command_file=tmp_path / "cmd.json", status_file=tmp_path / "status.json"
    )
    service = CimierService(
        cimier_config=cfg,
        power_switch=NoopPowerSwitch(),
        motor_shelly=NoopMotorShelly(),
        switch_reader=FakeSwitchReader([(cimier_open, not cimier_open)]),
        ipc_manager=ipc,
        weather_provider=rain,
    )
    service._last_open_switch = cimier_open
    service._last_closed_switch = not cimier_open
    return service


class TestRainWatch:
    def test_reads_the_sensor_on_each_tick(self, tmp_path):
        rain = StubRainProtection(state="dry")
        service = make_rain_service(tmp_path, rain)
        service.tick()
        assert rain.read_calls == 1

    def test_armed_rain_on_open_cimier_triggers_close(self, tmp_path):
        rain = StubRainProtection(state="wet", armed=True)
        service = make_rain_service(tmp_path, rain, cimier_open=True)
        closer = RecordingCloser()
        service._close_session_fn = closer
        service.tick()
        assert closer.calls == ["rain"]

    def test_armed_rain_latches_against_reopening(self, tmp_path):
        rain = StubRainProtection(state="wet", armed=True)
        service = make_rain_service(tmp_path, rain, cimier_open=True)
        service._close_session_fn = RecordingCloser()
        service.tick()
        assert rain.latched is True

    def test_disarmed_rain_does_not_close(self, tmp_path):
        rain = StubRainProtection(state="wet", armed=False)
        service = make_rain_service(tmp_path, rain, cimier_open=True)
        closer = RecordingCloser()
        service._close_session_fn = closer
        service.tick()
        assert closer.calls == []

    def test_disarmed_rain_logs_would_close(self, tmp_path, caplog):
        import logging

        rain = StubRainProtection(state="wet", armed=False)
        service = make_rain_service(tmp_path, rain, cimier_open=True)
        service._close_session_fn = RecordingCloser()
        with caplog.at_level(logging.INFO, logger="services.cimier_service"):
            service.tick()
        assert "rain_would_close" in caplog.text

    def test_closed_cimier_is_not_closed_again(self, tmp_path):
        rain = StubRainProtection(state="wet", armed=True)
        service = make_rain_service(tmp_path, rain, cimier_open=False)
        closer = RecordingCloser()
        service._close_session_fn = closer
        service.tick()
        assert closer.calls == []

    def test_unreachable_sensor_never_closes(self, tmp_path):
        rain = StubRainProtection(state="unreachable", armed=True)
        service = make_rain_service(tmp_path, rain, cimier_open=True)
        closer = RecordingCloser()
        service._close_session_fn = closer
        service.tick()
        assert closer.calls == []

    def test_rain_state_is_published_in_status(self, tmp_path):
        rain = StubRainProtection(state="wet", armed=False)
        service = make_rain_service(tmp_path, rain, cimier_open=True)
        service._close_session_fn = RecordingCloser()
        service.tick()
        payload = json.loads((tmp_path / "status.json").read_text())
        assert payload["rain"]["state"] == "wet"
        assert payload["rain"]["armed"] is False

    def test_rain_transition_is_written_to_night_journal(self, tmp_path, monkeypatch):
        from services import night_journal

        recorded = []
        monkeypatch.setattr(
            night_journal,
            "append_event",
            lambda event, **kw: recorded.append((event, kw)) or True,
        )
        rain = StubRainProtection(state="wet", armed=False)
        service = make_rain_service(tmp_path, rain, cimier_open=True)
        service._close_session_fn = RecordingCloser()
        service.tick()
        assert any(e == "rain" and kw.get("state") == "wet" for e, kw in recorded)

    def test_stable_state_is_not_journaled_twice(self, tmp_path, monkeypatch):
        from services import night_journal

        recorded = []
        monkeypatch.setattr(
            night_journal,
            "append_event",
            lambda event, **kw: recorded.append((event, kw)) or True,
        )
        rain = StubRainProtection(state="dry", armed=False)
        service = make_rain_service(tmp_path, rain, cimier_open=True)
        service.tick()
        service.tick()
        assert len([e for e, _ in recorded if e == "rain"]) == 1

    def test_noop_provider_disables_the_watch_entirely(self, tmp_path):
        # Rétro-compat : une config non migrée ne doit rien changer.
        from core.hardware.weather_provider import NoopWeatherProvider

        cfg = CimierConfig(enabled=True)
        ipc = CimierIpcManager(
            command_file=tmp_path / "cmd.json", status_file=tmp_path / "status.json"
        )
        service = CimierService(
            cimier_config=cfg,
            power_switch=NoopPowerSwitch(),
            motor_shelly=NoopMotorShelly(),
            switch_reader=FakeSwitchReader([(False, True)]),
            ipc_manager=ipc,
            weather_provider=NoopWeatherProvider(),
        )
        service.tick()
        payload = json.loads((tmp_path / "status.json").read_text())
        assert payload.get("rain") is None

    def test_manual_open_command_releases_the_latch(self, tmp_path):
        rain = StubRainProtection(state="dry", armed=True)
        service = make_rain_service(tmp_path, rain, cimier_open=False)
        rain.latch()
        service.execute_command({"id": "x1", "action": "open"})
        assert rain.latched is False
```

- [ ] **Step 2 : lancer les tests et vérifier qu'ils échouent**

Run: `uv run --extra dev pytest tests/test_cimier_service.py -k "RainWatch" -v`
Expected: FAIL — `AttributeError: 'CimierService' object has no attribute '_close_session_fn'`

- [ ] **Step 3 : préparer le service dans le constructeur**

Dans `services/cimier_service.py`, à la fin de `__init__` et **avant** l'appel final à `self._publish_status(...)`, insérer :

```python
        # ---- Veille pluie (2026-08) ----
        # Active uniquement si le provider sait lire un capteur (RainProtection).
        # Un provider noop laisse tout ce bloc inerte : rétro-compat stricte.
        self._rain_enabled = hasattr(self._weather_provider, "read_now")
        self._rain_watch_interval_s = float(cimier_config.weather_provider.watch_interval_s)
        self._last_rain_watch_ts: Optional[float] = None
        self._last_rain_state: Optional[str] = None
        # Indirection pour les tests : la séquence réelle est branchée à la
        # première utilisation (elle a besoin des writers IPC).
        self._close_session_fn: Optional[Callable[[str], Dict[str, Any]]] = None
        self._motor_ipc = motor_ipc
```

Attention : `motor_ipc` est aujourd'hui une variable locale réassignée dans la branche scheduler. Remonter sa résolution **avant** le bloc scheduler, en remplaçant la ligne `motor_ipc = motor_ipc or MotorIpcWriter()` (à l'intérieur du `else:`) par une initialisation en amont :

```python
        motor_ipc = motor_ipc or MotorIpcWriter()
```
placée juste avant `self._scheduler: Optional[CimierScheduler] = scheduler`, et supprimer la réassignation devenue redondante dans la branche `else:`.

- [ ] **Step 4 : écrire la veille**

Toujours dans `services/cimier_service.py`, ajouter ces méthodes à `CimierService` (après `_derive_current_cimier_state`) :

```python
    # ------------------------------------------------------------------
    # Veille pluie
    # ------------------------------------------------------------------

    def _refresh_rain_armed_from_config(self) -> None:
        """Relit la case « Protection pluie » depuis data/config.json.

        Même mécanique que le hot-reload du mode d'automatisation : la case
        cochée dans l'UI prend effet au tour de veille suivant, sans qu'on ait
        à redémarrer le service. Un échec de lecture laisse l'état courant.
        """
        provider = self._weather_provider
        if not hasattr(provider, "armed"):
            return
        try:
            config_path = Path(__file__).resolve().parents[1] / "data" / "config.json"
            with open(config_path, "r") as fh:
                cfg = json.load(fh)
        except (IOError, OSError, ValueError) as exc:
            logger.debug("cimier_event=rain_armed_refresh_skip exc=%s", exc)
            return
        section = cfg.get("cimier", {}).get("weather_provider", {})
        if not isinstance(section, dict) or "protection_enabled" not in section:
            return
        armed = bool(section.get("protection_enabled"))
        if armed != provider.armed:
            logger.info(
                "cimier_event=rain_protection_changed from=%s to=%s source=config_hot_reload",
                provider.armed,
                armed,
            )
            provider.armed = armed

    def _close_session_for_rain(self, reason: str) -> Dict[str, Any]:
        """Fermeture d'urgence : séquence partagée avec le scheduler et le parking."""
        from services.session_close_sequence import close_session

        cimier_cmd_id = str(uuid.uuid4())

        def _send_close() -> bool:
            self._ipc.write_command({"id": cimier_cmd_id, "action": "close"})
            return True

        return close_session(
            self._motor_ipc,
            _send_close,
            self._config.automation.parking_target_azimuth_deg,
            reason=reason,
        )

    def _rain_watch_tick(self) -> None:
        """Un tour de veille pluie : rafraîchit l'armement, lit, publie, décide."""
        self._refresh_rain_armed_from_config()
        provider = self._weather_provider
        state = provider.read_now()

        if state != self._last_rain_state:
            logger.info(
                "cimier_event=rain_transition from=%s to=%s armed=%s",
                self._last_rain_state or "unknown",
                state,
                getattr(provider, "armed", False),
            )
            night_journal.append_event(
                "rain", state=state, armed=bool(getattr(provider, "armed", False))
            )
            self._last_rain_state = state

        # Décision : le cimier doit être observé ouvert. En cooldown ou en
        # cycle, l'état dérivé n'est pas "open" et on réessaie au tour suivant
        # — nécessaire, le service étant en mode Drop (une commande écrite
        # pendant le cooldown serait consommée puis jetée).
        if self._derive_current_cimier_state() != CIMIER_STATE_OPEN:
            return
        if provider.is_safe_to_keep_open():
            return

        if not getattr(provider, "armed", False):
            # Décision à blanc : ce qu'on aurait fait, sans le faire. C'est ce
            # qui permet de valider le déclenchement avant d'armer.
            logger.info("cimier_event=rain_would_close state=%s armed=false", state)
            night_journal.append_event("decision", action="would_close", reason="rain")
            return

        logger.warning("cimier_event=rain_emergency_close state=%s", state)
        night_journal.append_event("decision", action="close", reason="rain")
        closer = self._close_session_fn or self._close_session_for_rain
        closer("rain")
        if hasattr(provider, "latch"):
            provider.latch()
```

Ajouter en tête de fichier, avec les autres imports :

```python
import uuid

from services import night_journal
```

- [ ] **Step 5 : brancher la veille dans `tick()`**

Dans `tick()`, insérer **tout en haut de la méthode**, avant le bloc scheduler (commentaire `# 0. Phase 3 : scheduler astropy`) :

```python
        # Veille pluie — placée AVANT le scheduler pour qu'une décision
        # d'ouverture ne s'appuie jamais sur un état capteur non encore lu.
        if self._rain_enabled:
            now_mono = self._clock()
            if (
                self._last_rain_watch_ts is None
                or (now_mono - self._last_rain_watch_ts) >= self._rain_watch_interval_s
            ):
                try:
                    self._rain_watch_tick()
                except Exception as exc:  # noqa: BLE001 — la veille ne tue jamais le service
                    logger.error("cimier_event=rain_watch_exception exc=%s", exc)
                self._last_rain_watch_ts = now_mono
```

- [ ] **Step 6 : publier l'état pluie**

Dans `_publish_status`, juste avant `if remaining_quiet_s is not None:`, ajouter :

```python
        if self._rain_enabled:
            payload["rain"] = self._weather_provider.describe()
```

- [ ] **Step 7 : lever le verrou sur une ouverture humaine**

Dans `execute_command`, juste après l'affectation de `self._last_command_id_value = cmd_id`, ajouter :

```python
        if action == ACTION_OPEN and hasattr(self._weather_provider, "release"):
            # Une ouverture décidée par un humain lève le verrou anti-réouverture :
            # c'est le seul geste qui vaut consentement explicite.
            if getattr(self._weather_provider, "latched", False):
                logger.info("cimier_event=rain_latch_released source=manual_open")
            self._weather_provider.release()
```

- [ ] **Step 8 : purger les vieux journaux au démarrage**

Dans `main()`, juste après `write_config_status(ensure_config_ready(force=True))` :

```python
    night_journal.purge_old()
```

- [ ] **Step 9 : vérifier que les tests passent**

Run: `uv run --extra dev pytest tests/test_cimier_service.py -v`
Expected: PASS — les 12 nouveaux tests plus tous les préexistants.

- [ ] **Step 10 : format, lint, commit**

```bash
uv run --extra dev ruff format services/cimier_service.py tests/test_cimier_service.py
uv run --extra dev ruff check services/cimier_service.py tests/test_cimier_service.py
git add services/cimier_service.py tests/test_cimier_service.py
git commit -m "feat(pluie): veille capteur dans cimier_service (fermeture d'urgence, décision à blanc)"
```

---

## Task 8 : journaliser les cycles cimier

Sans les ouvertures et fermetures, la frise ne montrerait que la moitié de l'histoire — on veut lire « il a plu à 2 h 13, **le cimier était ouvert** ».

**Files:**
- Modify: `services/cimier_service.py` (fin de `_run_cycle`)
- Test: `tests/test_cimier_service.py`

- [ ] **Step 1 : écrire le test**

Ajouter à `tests/test_cimier_service.py`, dans la classe `TestRainWatch` ou juste après :

```python
class TestCimierCycleJournaling:
    def test_cycle_end_is_written_to_night_journal(self, tmp_path, monkeypatch):
        from services import night_journal

        recorded = []
        monkeypatch.setattr(
            night_journal,
            "append_event",
            lambda event, **kw: recorded.append((event, kw)) or True,
        )
        cfg = CimierConfig(enabled=True)
        ipc = CimierIpcManager(
            command_file=tmp_path / "cmd.json", status_file=tmp_path / "status.json"
        )
        service = CimierService(
            cimier_config=cfg,
            power_switch=NoopPowerSwitch(),
            motor_shelly=NoopMotorShelly(),
            # Déjà fermé → preflight noop, cycle court sans matériel.
            switch_reader=FakeSwitchReader([(False, True)]),
            ipc_manager=ipc,
        )
        service.execute_command({"id": "c1", "action": "close"})
        cimier_events = [kw for e, kw in recorded if e == "cimier"]
        assert cimier_events
        assert cimier_events[-1]["action"] == "close"
        assert cimier_events[-1]["result"] == "noop"
```

- [ ] **Step 2 : lancer le test et vérifier qu'il échoue**

Run: `uv run --extra dev pytest tests/test_cimier_service.py::TestCimierCycleJournaling -v`
Expected: FAIL — `assert []` (aucun événement `cimier` journalisé).

- [ ] **Step 3 : journaliser les trois sorties de cycle**

Dans `services/cimier_service.py`, méthode `_run_cycle`, ajouter un appel après **chacun** des trois `logger.info("cimier_event=cycle_end …")` existants.

Après celui de la branche `noop` (juste avant le `return`) :

```python
            night_journal.append_event("cimier", action=action, result="noop", reason=reason)
```

Après celui de la branche `error`/`unreachable` (juste avant le `return`) :

```python
            night_journal.append_event("cimier", action=action, result=decision, reason=reason)
```

Après celui du bloc `finally` (dernière instruction avant l'établissement du cooldown) :

```python
            night_journal.append_event("cimier", action=action, result=result)
```

- [ ] **Step 4 : vérifier que les tests passent**

Run: `uv run --extra dev pytest tests/test_cimier_service.py -v`
Expected: PASS.

- [ ] **Step 5 : format, lint, commit**

```bash
uv run --extra dev ruff format services/cimier_service.py tests/test_cimier_service.py
uv run --extra dev ruff check services/cimier_service.py tests/test_cimier_service.py
git add services/cimier_service.py tests/test_cimier_service.py
git commit -m "feat(pluie): journalise les cycles cimier dans le journal de nuit"
```

---

## Task 9 : la case côté API

Pas de nouvelle URL : `AutomationView` sait déjà lire, modifier et réécrire `config.json`, et le dashboard la sonde déjà. On y rattache `rain_protection`.

**Files:**
- Modify: `web/cimier/views.py` (`AutomationView.get`, `AutomationView.post`)
- Test: `tests/test_web_cimier_views.py`

- [ ] **Step 1 : écrire les tests**

Ajouter à `tests/test_web_cimier_views.py`, juste après la classe `TestAutomationView`. Les fixtures `api_client`, `writable_config_file` et `mock_cimier_ipc` existent déjà dans ce fichier :

```python
class TestAutomationViewRainProtection:
    """La case « Protection pluie » voyage sur l'endpoint automation existant."""

    def test_get_returns_rain_protection_false_by_default(
        self, api_client, mock_cimier_ipc, writable_config_file
    ):
        response = api_client.get("/api/cimier/automation/")
        assert response.status_code == 200
        assert response.json()["rain_protection"] is False

    def test_get_reflects_configured_value(
        self, api_client, mock_cimier_ipc, writable_config_file
    ):
        cfg = json.loads(writable_config_file.read_text())
        cfg.setdefault("cimier", {})["weather_provider"] = {"protection_enabled": True}
        writable_config_file.write_text(json.dumps(cfg))
        response = api_client.get("/api/cimier/automation/")
        assert response.json()["rain_protection"] is True

    def test_post_persists_rain_protection(self, api_client, writable_config_file):
        response = api_client.post(
            "/api/cimier/automation/", {"rain_protection": True}, format="json"
        )
        assert response.status_code == 200
        assert response.json()["rain_protection"] is True
        cfg = json.loads(writable_config_file.read_text())
        assert cfg["cimier"]["weather_provider"]["protection_enabled"] is True

    def test_post_rain_protection_preserves_rest_of_config(
        self, api_client, writable_config_file
    ):
        api_client.post("/api/cimier/automation/", {"rain_protection": True}, format="json")
        cfg = json.loads(writable_config_file.read_text())
        assert cfg["site"]["nom"] == "Test"
        assert cfg["moteur"]["gear_ratio"] == 2230

    def test_post_mode_alone_leaves_rain_protection_untouched(
        self, api_client, writable_config_file
    ):
        api_client.post("/api/cimier/automation/", {"rain_protection": True}, format="json")
        api_client.post("/api/cimier/automation/", {"mode": "full"}, format="json")
        cfg = json.loads(writable_config_file.read_text())
        assert cfg["cimier"]["weather_provider"]["protection_enabled"] is True
        assert cfg["cimier"]["automation"]["mode"] == "full"

    def test_post_rain_protection_alone_leaves_mode_untouched(
        self, api_client, writable_config_file
    ):
        api_client.post("/api/cimier/automation/", {"mode": "semi"}, format="json")
        api_client.post("/api/cimier/automation/", {"rain_protection": True}, format="json")
        cfg = json.loads(writable_config_file.read_text())
        assert cfg["cimier"]["automation"]["mode"] == "semi"

    def test_post_both_fields_at_once(self, api_client, writable_config_file):
        response = api_client.post(
            "/api/cimier/automation/", {"mode": "semi", "rain_protection": True}, format="json"
        )
        assert response.status_code == 200
        cfg = json.loads(writable_config_file.read_text())
        assert cfg["cimier"]["automation"]["mode"] == "semi"
        assert cfg["cimier"]["weather_provider"]["protection_enabled"] is True

    def test_post_can_disarm(self, api_client, writable_config_file):
        api_client.post("/api/cimier/automation/", {"rain_protection": True}, format="json")
        api_client.post("/api/cimier/automation/", {"rain_protection": False}, format="json")
        cfg = json.loads(writable_config_file.read_text())
        assert cfg["cimier"]["weather_provider"]["protection_enabled"] is False

    def test_post_invalid_mode_still_rejected(self, api_client, writable_config_file):
        response = api_client.post("/api/cimier/automation/", {"mode": "yolo"}, format="json")
        assert response.status_code == 400
```

- [ ] **Step 2 : lancer les tests et vérifier qu'ils échouent**

Run: `uv run --extra dev pytest tests/test_web_cimier_views.py -k "RainProtection" -v`
Expected: FAIL — `KeyError: 'rain_protection'`

- [ ] **Step 3 : lire la case dans le GET**

Dans `web/cimier/views.py`, classe `AutomationView`, ajouter cette méthode à côté de `_read_configured_mode` :

```python
    @staticmethod
    def _read_rain_protection() -> bool:
        """Lit `cimier.weather_provider.protection_enabled`, défaut False.

        Défaut prudent : une configuration muette laisse la protection
        désarmée. C'est un armement, il doit être explicite.
        """
        config_path = Path(settings.DRIFTAPP_CONFIG)
        try:
            with open(config_path, "r") as f:
                cfg = json.load(f)
        except (IOError, json.JSONDecodeError):
            return False
        section = cfg.get("cimier", {}).get("weather_provider", {})
        if not isinstance(section, dict):
            return False
        return bool(section.get("protection_enabled", False))
```

Puis, dans `get`, ajouter la clé au dictionnaire de la `Response` :

```python
                "rain_protection": self._read_rain_protection(),
```

- [ ] **Step 4 : accepter la case dans le POST**

Remplacer le début de `AutomationView.post` (jusqu'à l'ouverture du fichier de config incluse) par :

```python
    def post(self, request):
        """Persiste `mode` et/ou `rain_protection` dans data/config.json.

        Les deux champs sont optionnels et indépendants : un POST ne portant
        que l'un des deux laisse l'autre intact. Un corps vide est une erreur —
        on ne réécrit pas la configuration pour rien.
        """
        mode = request.data.get("mode")
        rain_protection = request.data.get("rain_protection")

        if mode is None and rain_protection is None:
            return Response(
                {"error": "aucun champ à appliquer", "fields": ["mode", "rain_protection"]},
                status=status.HTTP_400_BAD_REQUEST,
            )
        if mode is not None and mode not in VALID_AUTOMATION_MODES:
            return Response(
                {"error": "mode invalide", "valid": list(VALID_AUTOMATION_MODES)},
                status=status.HTTP_400_BAD_REQUEST,
            )

        config_path = Path(settings.DRIFTAPP_CONFIG)
        try:
            with open(config_path, "r") as f:
                cfg = json.load(f)
        except (IOError, json.JSONDecodeError) as exc:
            return Response(
                {"error": f"Lecture config.json impossible : {exc}"},
                status=status.HTTP_503_SERVICE_UNAVAILABLE,
            )
        cimier_section = cfg.setdefault("cimier", {})
        if mode is not None:
            automation_section = cimier_section.setdefault("automation", {})
            automation_section["mode"] = mode
            # Nettoyage : `mode` est la source de vérité, la clé legacy
            # `enabled` n'est plus perpétuée en écriture.
            automation_section.pop("enabled", None)
        if rain_protection is not None:
            weather_section = cimier_section.setdefault("weather_provider", {})
            weather_section["protection_enabled"] = bool(rain_protection)
        try:
            self._write_atomic(config_path, cfg)
        except OSError as exc:
            return Response(
                {"error": f"Écriture config.json impossible : {exc}"},
                status=status.HTTP_503_SERVICE_UNAVAILABLE,
            )
        return Response(
            {
                "mode": mode if mode is not None else self._read_configured_mode(),
                "rain_protection": (
                    bool(rain_protection)
                    if rain_protection is not None
                    else self._read_rain_protection()
                ),
                "applied": True,
                "apply_pending": True,
            }
        )
```

Mettre à jour la docstring de classe pour mentionner `rain_protection`, et le commentaire d'en-tête de `web/cimier/urls.py`.

- [ ] **Step 5 : réparer l'assertion d'égalité stricte préexistante**

`tests/test_web_cimier_views.py::TestAutomationView::test_post_valid_mode_persists_to_config_json` compare la réponse **par égalité de dictionnaire** :

```python
        assert body == {"mode": "semi", "applied": True, "apply_pending": True}
```

La nouvelle clé la fait échouer. Remplacer cette ligne par :

```python
        assert body["mode"] == "semi"
        assert body["applied"] is True
        assert body["apply_pending"] is True
        # La réponse porte désormais aussi l'état de la protection pluie (2026-08).
        assert body["rain_protection"] is False
```

C'est le seul test préexistant que ce changement casse — l'égalité stricte le rendait sensible à toute extension de la réponse.

- [ ] **Step 6 : vérifier que les tests passent**

Run: `uv run --extra dev pytest tests/test_web_cimier_views.py -v`
Expected: PASS — les 9 nouveaux et tous les préexistants sur `AutomationView` et `ParkingSessionView`.

- [ ] **Step 7 : format, lint, commit**

```bash
uv run --extra dev ruff format web/cimier/views.py tests/test_web_cimier_views.py
uv run --extra dev ruff check web/cimier/views.py tests/test_web_cimier_views.py
git add web/cimier/views.py web/cimier/urls.py tests/test_web_cimier_views.py
git commit -m "feat(pluie): case Protection pluie portée par l'endpoint automation existant"
```

---

## Task 10 : la case et la pastille sur le dashboard

Frontend pur. Aucune classe Tailwind nouvelle : les styles vont dans `dashboard.css`, qui est du CSS brut (pas de recompilation).

**Files:**
- Modify: `web/templates/dashboard.html` (bloc automatisation cimier, ~ligne 368)
- Modify: `web/static/js/dashboard.js` (store, `fetchAutomationState`, nouvelles fonctions)
- Modify: `web/static/css/dashboard.css`

- [ ] **Step 1 : ajouter l'état au store**

Dans `web/static/js/dashboard.js`, après la ligne `automationCountdownLabel: '',` :

```javascript
        // Protection pluie (2026-08) — case décochée par défaut. Le capteur
        // est lu et affiché en permanence ; la case n'arme que l'action.
        rainProtection: false,                     // reflet de config.json
        rainProtectionInFlight: false,             // anti-double-clic POST
```

- [ ] **Step 2 : hydrater depuis l'API**

Dans `fetchAutomationState`, juste avant `store.automationNextOpenAt = …` :

```javascript
        if (typeof data.rain_protection === 'boolean' && !store.rainProtectionInFlight) {
            store.rainProtection = data.rain_protection;
        }
```

- [ ] **Step 3 : écrire les helpers d'affichage et le POST**

Ajouter à `web/static/js/dashboard.js`, juste après `updateAutomationMode` :

```javascript
// Libellé de la pastille capteur de pluie. Source : cimier_status.json,
// publié par la veille de cimier_service (clé `rain`). Absent = provider noop
// ou service arrêté.
function rainStateLabel() {
    const rain = Alpine.store('dashboard').cimier?.rain;
    if (!rain) return '';
    if (rain.state === 'wet') return 'PLUIE';
    if (rain.state === 'dry') return 'SEC';
    return 'CAPTEUR ?';
}
window.rainStateLabel = rainStateLabel;

function rainStateClass() {
    const rain = Alpine.store('dashboard').cimier?.rain;
    if (!rain) return '';
    if (rain.state === 'wet') return 'rain-pill rain-pill-wet';
    if (rain.state === 'dry') return 'rain-pill rain-pill-dry';
    return 'rain-pill rain-pill-unknown';
}
window.rainStateClass = rainStateClass;

// Avertissement : décochée, la case n'empêche pas le scheduler d'ouvrir au
// crépuscule. Une campagne d'observation sous orage se mène en manual ou semi.
function rainModeWarning() {
    const store = Alpine.store('dashboard');
    if (store.automationMode === 'full' && !store.rainProtection) {
        return '⚠ Mode full auto : le cimier s\'ouvrira au crépuscule malgré la pluie';
    }
    return '';
}
window.rainModeWarning = rainModeWarning;

// Persiste la case via l'endpoint automation (pas d'URL dédiée).
async function updateRainProtection(enabled) {
    const store = Alpine.store('dashboard');
    const previous = store.rainProtection;
    store.rainProtection = enabled;
    store.rainProtectionInFlight = true;

    const result = await apiCall('/api/cimier/automation/', 'POST', { rain_protection: enabled });

    store.rainProtectionInFlight = false;
    if (result && result.applied) {
        const label = enabled ? 'armée' : 'désarmée';
        pushCimierTimeline('INFO', `Protection pluie ${label} (prise en compte sous 10 s)`);
        log(`Cimier : protection pluie ${label}`, 'info');
    } else {
        const err = (result && (result.error || result.detail)) || 'erreur inconnue';
        pushCimierTimeline('ERROR', `Protection pluie : échec (${err})`);
        log(`Cimier : changement protection pluie échoué (${err})`, 'error');
        store.rainProtection = previous;
    }
}
window.updateRainProtection = updateRainProtection;
```

- [ ] **Step 4 : alimenter la timeline sur les transitions du capteur**

`pollCimierStatus` détecte déjà les changements d'état cimier pour la timeline, juste avant `store.cimier = status;` (bloc commenté « Détection changement d'état cimier pour timeline »). Ajouter la détection pluie **dans ce même bloc**, avant l'assignation :

```javascript
    // Transitions du capteur de pluie → timeline. Comparé avant assignation,
    // comme l'état cimier juste au-dessus.
    const prevRain = store.cimier?.rain?.state;
    const nextRain = status.rain?.state;
    if (prevRain && nextRain && prevRain !== nextRain) {
        if (nextRain === 'wet') {
            pushCimierTimeline('WARNING', 'Capteur de pluie : PLUIE détectée');
        } else if (nextRain === 'unreachable') {
            pushCimierTimeline('ERROR', 'Capteur de pluie injoignable — protection aveugle');
        } else {
            pushCimierTimeline('INFO', 'Capteur de pluie : retour au sec');
        }
    }
    // Verrou anti-réouverture posé par une fermeture pluie.
    if (!store.cimier?.rain?.latched && status.rain?.latched) {
        pushCimierTimeline('WARNING', 'Fermeture pluie — réouverture auto verrouillée');
    }
```

- [ ] **Step 5 : ajouter la case au template**

Dans `web/templates/dashboard.html`, à l'intérieur du bloc `<div class="flex items-center gap-2 flex-wrap text-xs">` du panneau Cimier, insérer **avant** le bouton de bascule de la timeline (celui portant `class="ml-auto …"`) :

```html
                    <!-- Protection pluie (2026-08) : décochée par défaut. Le capteur
                         est lu et affiché en permanence ; la case n'arme que l'action
                         (refus d'ouverture + fermeture d'urgence). -->
                    <label class="flex items-center gap-1.5 whitespace-nowrap cursor-pointer">
                        <input type="checkbox" id="cimier-rain-protection"
                               class="accent-accent-amber w-4 h-4"
                               :checked="$store.dashboard.rainProtection"
                               @change="window.updateRainProtection &&
                                        window.updateRainProtection($event.target.checked)"
                               aria-label="Armer la protection pluie">
                        <span class="text-obs-text-muted uppercase tracking-wider">Protection pluie</span>
                    </label>
                    <span id="cimier-rain-state" class="font-mono"
                          :class="window.rainStateClass ? window.rainStateClass() : ''"
                          x-text="window.rainStateLabel ? window.rainStateLabel() : ''"
                          x-show="$store.dashboard.cimier?.rain" x-cloak
                          role="status" aria-live="polite"
                          aria-label="État du capteur de pluie"></span>
```

Puis, juste après le `<div id="cimier-automation-hint" …></div>` :

```html
                <div id="cimier-rain-warning"
                     class="text-[0.7rem] font-mono text-accent-amber-light min-h-[1rem]"
                     x-text="window.rainModeWarning ? window.rainModeWarning() : ''"
                     x-cloak></div>
```

- [ ] **Step 6 : styler la pastille**

Ajouter à la fin de `web/static/css/dashboard.css` :

```css
/* ── Pastille capteur de pluie (2026-08) ─────────────────────────────────
   Lisible sans survol : l'écran de l'observatoire est tactile. */
.rain-pill {
    padding: 0.1rem 0.5rem;
    border-radius: 999px;
    font-weight: 700;
    letter-spacing: 0.05em;
    border: 1px solid transparent;
}
.rain-pill-dry {
    color: #00d26a;
    border-color: rgba(0, 210, 106, 0.4);
    background: rgba(0, 210, 106, 0.08);
}
.rain-pill-wet {
    color: #4aa3ff;
    border-color: rgba(74, 163, 255, 0.5);
    background: rgba(74, 163, 255, 0.12);
}
.rain-pill-unknown {
    color: #ffa502;
    border-color: rgba(255, 165, 2, 0.4);
    background: rgba(255, 165, 2, 0.08);
}
```

- [ ] **Step 7 : vérifier la non-régression des tests web**

Run: `uv run --extra dev pytest tests/test_web_views.py -v`
Expected: PASS.

- [ ] **Step 8 : commit**

```bash
git add web/templates/dashboard.html web/static/js/dashboard.js web/static/css/dashboard.css
git commit -m "feat(pluie): case Protection pluie + pastille capteur sur le dashboard"
```

Le rendu réel est vérifié à la Task 12, une fois le simulateur capable de produire de la pluie.

---

## Task 11 : simuler la pluie

Sans cela, rien de tout ce qui précède n'est vérifiable depuis la machine de dev.

Le simulateur émule **un seul** Shelly sur le port 8001, dont les entrées `id=0` et `id=1` sont déjà les butées BAS et HAUT. Le capteur de pluie y prend donc l'entrée **`id=2`**, et la configuration de dev-mode pointe `input_id=2`. Sur le terrain, c'est bien `id=0` d'un Shelly distinct — la divergence est confinée aux overrides de dev.

**Files:**
- Modify: `core/hardware/cimier_simulator.py`
- Modify: `services/cimier_service.py` (`_apply_dev_mode_overrides`)
- Test: `tests/test_cimier_simulator.py` (créer si absent)

- [ ] **Step 1 : écrire les tests du simulateur**

Ajouter à `tests/test_cimier_simulator.py` (créer le fichier avec cet en-tête s'il n'existe pas) :

```python
"""Tests du simulateur Shelly unifié — entrée pluie (2026-08)."""

from __future__ import annotations

import json
import urllib.request

import pytest

from core.hardware.cimier_simulator import INPUT_RAIN, CimierSimulator


@pytest.fixture
def sim():
    simulator = CimierSimulator(port=0)
    simulator.start()
    assert simulator.wait_ready(timeout=5.0)
    yield simulator
    simulator.stop()


def get_json(sim, path):
    with urllib.request.urlopen(sim.url + path, timeout=2.0) as resp:
        return json.loads(resp.read().decode("utf-8"))


def test_rain_input_is_dry_by_default(sim):
    assert get_json(sim, "/rpc/Input.GetStatus?id=%d" % INPUT_RAIN)["state"] is False


def test_dev_rain_on_makes_it_wet(sim):
    get_json(sim, "/dev/rain?on=1")
    assert get_json(sim, "/rpc/Input.GetStatus?id=%d" % INPUT_RAIN)["state"] is True


def test_dev_rain_off_makes_it_dry_again(sim):
    get_json(sim, "/dev/rain?on=1")
    get_json(sim, "/dev/rain?on=0")
    assert get_json(sim, "/rpc/Input.GetStatus?id=%d" % INPUT_RAIN)["state"] is False


def test_dev_rain_returns_current_state(sim):
    assert get_json(sim, "/dev/rain?on=1") == {"raining": True}


def test_rain_input_does_not_disturb_the_limit_switches(sim):
    before = get_json(sim, "/rpc/Input.GetStatus?id=0")["state"]
    get_json(sim, "/dev/rain?on=1")
    assert get_json(sim, "/rpc/Input.GetStatus?id=0")["state"] == before
```

- [ ] **Step 2 : lancer les tests et vérifier qu'ils échouent**

Run: `uv run --extra dev pytest tests/test_cimier_simulator.py -v`
Expected: FAIL — `ImportError: cannot import name 'INPUT_RAIN'`

- [ ] **Step 3 : ajouter l'entrée pluie au simulateur**

Dans `core/hardware/cimier_simulator.py` :

Après `INPUT_HAUT = 1`, ajouter :

```python
# Le simulateur n'émule qu'un seul Shelly : la pluie y prend une 3ᵉ entrée
# libre. Sur le terrain elle est sur l'entrée id=0 d'un Shelly distinct (.87) —
# la divergence est absorbée par les overrides de dev-mode.
INPUT_RAIN = 2
```

Dans `CimierSimulator.__init__`, après `self._power_on = False  # relais 24V` :

```python
        self._raining = False  # entrée pluie simulée (bascule via /dev/rain)
```

Dans `CimierSimulator.input_state`, avant `return None` :

```python
            if input_id == INPUT_RAIN:
                # Convention terrain mesurée le 14/08/2026 : state=true = pluie.
                return self._raining
```

Ajouter la méthode, après `set_relay` :

```python
    def set_rain(self, raining):
        """Bascule l'averse simulée. Retourne l'état courant."""
        with self._lock:
            self._raining = bool(raining)
            return self._raining
```

Dans `_SilentHandler.do_GET`, avant le `self._send_json(404, …)` final :

```python
        if parsed.path == "/dev/rain":
            raw = qs.get("on", ["1"])[0].strip().lower()
            raining = raw in ("1", "true", "yes", "on")
            self._send_json(200, {"raining": sim.set_rain(raining)})
            return
```

Enfin, compléter la docstring de module en listant `/dev/rain?on=0|1` à côté des autres routes.

- [ ] **Step 4 : vérifier que les tests passent**

Run: `uv run --extra dev pytest tests/test_cimier_simulator.py -v`
Expected: PASS — 5 tests.

- [ ] **Step 5 : pointer le dev-mode sur le simulateur**

Dans `services/cimier_service.py`, fonction `_apply_dev_mode_overrides`, ajouter avant la ligne `cimier_cfg.power_switch.type = "shelly_gen1"` :

```python
    # Capteur de pluie simulé : 3ᵉ entrée du Shelly unifié (id=2), basculée
    # par GET /dev/rain?on=1. Désarmé par défaut, comme en production — c'est
    # l'UI qui arme, et on veut exercer le mode observation en priorité.
    cimier_cfg.weather_provider.type = "shelly_rain"
    cimier_cfg.weather_provider.host = "127.0.0.1:8001"
    cimier_cfg.weather_provider.input_id = 2
    cimier_cfg.weather_provider.invert = False
    cimier_cfg.weather_provider.watch_interval_s = 2.0
    cimier_cfg.weather_provider.confirm_reads = 2
```

`watch_interval_s=2.0` en dev : une averse déclenchée à la main doit produire un effet observable en quelques secondes, pas en dix.

- [ ] **Step 6 : vérifier la non-régression du dev-mode**

Run: `uv run --extra dev pytest tests/test_cimier_service.py -k "DevMode" -v`
Expected: PASS.

- [ ] **Step 7 : format, lint, commit**

```bash
uv run --extra dev ruff format core/hardware/cimier_simulator.py services/cimier_service.py tests/test_cimier_simulator.py
uv run --extra dev ruff check core/hardware/cimier_simulator.py services/cimier_service.py tests/test_cimier_simulator.py
git add core/hardware/cimier_simulator.py services/cimier_service.py tests/test_cimier_simulator.py
git commit -m "feat(pluie): averse simulée dans le simulateur cimier (/dev/rain) + overrides dev"
```

---

## Task 12 : vérification bout en bout du lot 1

Aucun test unitaire ne remplace le fait de voir la chaîne complète fonctionner. Tout se passe sur la machine de dev.

**Files:** aucun code — vérification, puis `pyproject.toml` et `CLAUDE.md`.

- [ ] **Step 1 : suite complète**

Run: `uv run --extra dev pytest -q`
Expected: PASS, aucun échec. Noter le total (référence : 1180 avant ce chantier).

- [ ] **Step 2 : lint global sur le périmètre touché**

```bash
uv run --extra dev ruff format --check core/ services/ web/ tests/
uv run --extra dev ruff check core/ services/ web/ tests/
```
Expected: aucune erreur.

- [ ] **Step 3 : démarrer la stack de développement**

```bash
./start_dev.sh stop; ./start_dev.sh start
./start_dev.sh status
```
Expected: les 4 processus « EN COURS ».

- [ ] **Step 4 : vérifier que le capteur est lu au repos**

```bash
sleep 5 && cat /dev/shm/cimier_status.json | python3 -m json.tool | grep -A 8 '"rain"'
```
Expected: un bloc `rain` avec `"state": "dry"`, `"armed": false`, `"latched": false`, `"provider": "shelly_rain"`.

- [ ] **Step 5 : déclencher une averse, protection désarmée**

```bash
curl -s "http://127.0.0.1:8001/relay/0?turn=on" >/dev/null   # ouvre le cimier simulé
curl -s "http://127.0.0.1:8001/relay/2?turn=on" >/dev/null
curl -s "http://127.0.0.1:8001/relay/1?turn=on" >/dev/null
sleep 65                                                      # laisse le cimier s'ouvrir
curl -s "http://127.0.0.1:8001/dev/rain?on=1"
sleep 8
grep -E "rain_transition|rain_would_close" logs/cimier_service.log | tail -5
```
Expected: une ligne `rain_transition from=dry to=wet armed=False`, puis une ligne `rain_would_close` — **et aucune fermeture**. Vérifier que le cimier est toujours ouvert dans le status.

- [ ] **Step 6 : vérifier le journal de nuit**

```bash
cat data/nights/$(date -d 'today 06:00' +%Y-%m-%d 2>/dev/null || date +%Y-%m-%d).jsonl
```
Expected: des lignes JSON avec `"event": "rain"` et `"event": "decision"` / `"action": "would_close"`. Si la commande de date échoue, lister `ls data/nights/` et lire le fichier présent.

- [ ] **Step 7 : armer la protection et vérifier la fermeture**

Ouvrir `http://127.0.0.1:8000/`, cocher « Protection pluie ». Puis :

```bash
sleep 12
grep -E "rain_emergency_close|session_close" logs/cimier_service.log | tail -5
```
Expected: `cimier_event=rain_emergency_close`, puis `cimier_event=session_close reason=rain` avec `tracking_stop_sent=True` et `cimier_close_sent=True`.

- [ ] **Step 8 : vérifier le verrou anti-réouverture**

```bash
curl -s "http://127.0.0.1:8001/dev/rain?on=0"
sleep 8
cat /dev/shm/cimier_status.json | python3 -m json.tool | grep -A 8 '"rain"'
```
Expected: `"state": "dry"` mais `"latched": true` — le retour au beau ne rouvre rien.

- [ ] **Step 9 : vérifier le rendu du dashboard**

Sur `http://127.0.0.1:8000/`, contrôler à l'œil :
- la case « Protection pluie » et la pastille sont sur la même ligne que « Mode auto », sans faire déborder le panneau ;
- la pastille passe de `SEC` (vert) à `PLUIE` (bleu) quand on rebascule `/dev/rain?on=1` ;
- en passant le Mode auto sur « Full auto » avec la case décochée, l'avertissement ambre apparaît ;
- rien de tout cela n'exige un survol.

Contrôler aussi à 1280×720 (fenêtre réduite ou outils de développement) : l'écran de l'observatoire fait 720 p et la v6.11.0 vient d'y dégraisser le dashboard.

- [ ] **Step 10 : arrêter la stack, bumper la version, documenter**

```bash
./start_dev.sh stop
```

Dans `pyproject.toml`, passer `version = "6.11.3"` à `version = "6.12.0"` (jalon).

Dans `CLAUDE.md`, ajouter une ligne en tête du tableau « Changelog Resume » résumant : capteur de pluie intégré (Shelly Plus Uni `.87`, entrée `id=0`, `state=true`=pluie mesuré le 14/08), protection armable décochée par défaut, verrou anti-réouverture, séquence de fermeture unifiée, journal de nuit 30 jours, averse simulée `/dev/rain`.

- [ ] **Step 11 : commit**

```bash
git add pyproject.toml CLAUDE.md
git commit -m "chore(pluie): v6.12.0 — protection pluie armable et journal de nuit"
```

---

## Task 13 : endpoint de restitution d'une nuit

Début du lot 2.

**Files:**
- Modify: `web/session/views.py`, `web/session/urls.py`
- Test: `tests/test_session_views.py`

- [ ] **Step 1 : écrire les tests**

Ajouter à `tests/test_session_views.py`. Les fixtures `api_client` et `mock_sessions` (qui repointe `session_storage.SESSIONS_DIR` vers un `tmp_path/sessions`) existent déjà dans ce fichier ; on ajoute une fixture sœur pour le journal :

```python
@pytest.fixture
def mock_nights(tmp_path, monkeypatch):
    """Repointe le journal de nuit vers un répertoire temporaire."""
    from services import night_journal

    nights_dir = tmp_path / "nights"
    nights_dir.mkdir()
    monkeypatch.setattr(night_journal, "DEFAULT_NIGHTS_DIR", nights_dir)
    return nights_dir


def write_night_event(nights_dir, moment, event="rain", **fields):
    from services import night_journal

    night_journal.append_event(event, at=moment, nights_dir=nights_dir, **fields)


class TestNightView:
    """GET /api/session/night/ — données de la frise de nuit."""

    def test_returns_available_nights(self, api_client, mock_nights, mock_sessions):
        from datetime import datetime

        write_night_event(mock_nights, datetime(2026, 8, 14, 22, 0), state="wet")
        data = api_client.get("/api/session/night/").json()
        assert "2026-08-14" in data["available_nights"]

    def test_returns_events_of_requested_night(self, api_client, mock_nights, mock_sessions):
        from datetime import datetime

        write_night_event(mock_nights, datetime(2026, 8, 14, 22, 0), state="wet")
        data = api_client.get("/api/session/night/?date=2026-08-14").json()
        assert data["night"] == "2026-08-14"
        assert data["events"][0]["state"] == "wet"

    def test_unknown_night_returns_empty_not_404(self, api_client, mock_nights, mock_sessions):
        response = api_client.get("/api/session/night/?date=1999-01-01")
        assert response.status_code == 200
        assert response.json()["events"] == []

    def test_malformed_date_is_rejected(self, api_client, mock_nights, mock_sessions):
        assert api_client.get("/api/session/night/?date=pas-une-date").status_code == 400

    def test_no_journal_at_all_returns_empty_payload(
        self, api_client, mock_nights, mock_sessions
    ):
        data = api_client.get("/api/session/night/").json()
        assert data["night"] is None
        assert data["available_nights"] == []

    def test_defaults_to_most_recent_night(self, api_client, mock_nights, mock_sessions):
        from datetime import datetime

        for day in (12, 14):
            write_night_event(mock_nights, datetime(2026, 8, day, 22, 0), state="wet")
        assert api_client.get("/api/session/night/").json()["night"] == "2026-08-14"

    def test_includes_tracking_sessions_of_the_night(
        self, api_client, mock_nights, mock_sessions
    ):
        # 3ᵉ ligne de la frise : lue des sessions déjà persistées, sans
        # coupler cimier_service et motor_service.
        from datetime import datetime

        write_night_event(mock_nights, datetime(2026, 8, 14, 22, 0), state="wet")
        session_storage.save_session(
            {
                "session_id": "20260814_213000_M31",
                "object": {"name": "M31"},
                "timing": {
                    "start_time": "2026-08-14T21:30:00",
                    "end_time": "2026-08-15T02:00:00",
                },
            }
        )
        data = api_client.get("/api/session/night/?date=2026-08-14").json()
        assert data["tracking"][0]["object_name"] == "M31"

    def test_excludes_sessions_of_other_nights(self, api_client, mock_nights, mock_sessions):
        from datetime import datetime

        write_night_event(mock_nights, datetime(2026, 8, 14, 22, 0), state="wet")
        session_storage.save_session(
            {
                "session_id": "20260801_213000_M13",
                "object": {"name": "M13"},
                "timing": {
                    "start_time": "2026-08-01T21:30:00",
                    "end_time": "2026-08-02T02:00:00",
                },
            }
        )
        assert api_client.get("/api/session/night/?date=2026-08-14").json()["tracking"] == []

    def test_session_started_after_midnight_belongs_to_the_night(
        self, api_client, mock_nights, mock_sessions
    ):
        # Une session démarrée à 1 h du matin appartient à la nuit de la veille.
        from datetime import datetime

        write_night_event(mock_nights, datetime(2026, 8, 14, 22, 0), state="wet")
        session_storage.save_session(
            {
                "session_id": "20260815_010000_NGC7640",
                "object": {"name": "NGC 7640"},
                "timing": {
                    "start_time": "2026-08-15T01:00:00",
                    "end_time": "2026-08-15T04:00:00",
                },
            }
        )
        data = api_client.get("/api/session/night/?date=2026-08-14").json()
        assert data["tracking"][0]["object_name"] == "NGC 7640"

    def test_night_bounds_are_noon_to_noon(self, api_client, mock_nights, mock_sessions):
        from datetime import datetime

        write_night_event(mock_nights, datetime(2026, 8, 14, 22, 0), state="wet")
        data = api_client.get("/api/session/night/?date=2026-08-14").json()
        assert data["night_start"].startswith("2026-08-14T12:00")
        assert data["night_end"].startswith("2026-08-15T12:00")
```

- [ ] **Step 2 : lancer les tests et vérifier qu'ils échouent**

Run: `uv run --extra dev pytest tests/test_session_views.py -k "NightView" -v`
Expected: FAIL — 404 sur `/api/session/night/`.

- [ ] **Step 3 : écrire la vue**

Ajouter à `web/session/views.py` :

```python
@api_view(["GET"])
def night_report(request):
    """Données de la frise d'une nuit d'observation.

    Query params:
        date: nuit au format AAAA-MM-JJ (défaut : la plus récente disponible).

    Une nuit couvre midi → midi, découpage propre au journal cimier : une nuit
    d'observation traverse minuit et ne doit pas être scindée.

    Retourne :
        - `events`   : journal cimier (pluie, décisions, cycles) ;
        - `tracking` : sessions de suivi recouvrant la nuit, lues des fichiers
          déjà persistés — aucun couplage nouveau entre les services ;
        - `available_nights` : pour peupler le sélecteur de date.
    """
    from datetime import datetime, timedelta

    from services import night_journal
    from web.session import session_storage

    available = night_journal.list_nights()
    requested = request.query_params.get("date")
    if requested:
        try:
            night_start = datetime.strptime(requested, "%Y-%m-%d")
        except ValueError:
            return Response(
                {"error": "date invalide, format attendu AAAA-MM-JJ"},
                status=status.HTTP_400_BAD_REQUEST,
            )
    elif available:
        requested = available[0]
        night_start = datetime.strptime(requested, "%Y-%m-%d")
    else:
        return Response({"night": None, "events": [], "tracking": [], "available_nights": []})

    night_start = night_start.replace(hour=night_journal.NIGHT_BOUNDARY_HOUR)
    night_end = night_start + timedelta(days=1)

    tracking = []
    for summary in session_storage.list_sessions(limit=200):
        start_iso = summary.get("start_time")
        if not start_iso:
            continue
        try:
            started = datetime.fromisoformat(start_iso)
        except (TypeError, ValueError):
            continue
        if not (night_start <= started < night_end):
            continue
        tracking.append(
            {
                "session_id": summary.get("session_id"),
                "object_name": summary.get("object_name"),
                "start_time": start_iso,
                "end_time": summary.get("end_time"),
                "duration_seconds": summary.get("duration_seconds", 0),
            }
        )

    return Response(
        {
            "night": requested,
            "night_start": night_start.isoformat(),
            "night_end": night_end.isoformat(),
            "events": night_journal.read_night(requested),
            "tracking": tracking,
            "available_nights": available,
        }
    )
```

- [ ] **Step 4 : router l'endpoint**

Dans `web/session/urls.py`, ajouter à `urlpatterns` :

```python
    path('night/', views.night_report, name='session-night'),
```

et compléter la docstring du module.

- [ ] **Step 5 : vérifier que les tests passent**

Run: `uv run --extra dev pytest tests/test_session_views.py -v`
Expected: PASS — les 10 nouveaux et tous les préexistants.

- [ ] **Step 6 : format, lint, commit**

```bash
uv run --extra dev ruff format web/session/views.py web/session/urls.py tests/test_session_views.py
uv run --extra dev ruff check web/session/views.py web/session/urls.py tests/test_session_views.py
git add web/session/views.py web/session/urls.py tests/test_session_views.py
git commit -m "feat(pluie): endpoint de restitution d'une nuit (journal + sessions recouvrantes)"
```

---

## Task 14 : frise de la nuit

SVG inline plutôt que Chart.js : un diagramme de bandes s'y exprime mal, le SVG donne un contrôle exact, reste net à toute largeur et se lit **sans tooltip** — l'écran de l'observatoire est tactile.

**Files:**
- Create: `web/static/js/night_frieze.js`
- Modify: `web/templates/session.html`, `web/static/js/session.js`, `web/static/css/session.css` (ou le bloc `<style>` de `session.html`)

- [ ] **Step 1 : écrire le module de rendu**

Créer `web/static/js/night_frieze.js` :

```javascript
/**
 * Frise de nuit — restitution graphique d'une nuit d'observation.
 *
 * Trois lignes sur un axe horaire commun (midi → midi) :
 *   1. Pluie  — bande = pluie, hachures = capteur injoignable
 *   2. Cimier — bande = ouvert, marqueurs verticaux aux décisions
 *   3. Suivi  — bandes des sessions, étiquetées du nom d'objet
 *
 * SVG inline, sans dépendance. Aucune information ne dépend d'un survol :
 * l'écran de l'observatoire est tactile.
 */

const FRIEZE = {
    height: 190,
    rowHeight: 30,
    rowGap: 14,
    marginLeft: 74,
    marginRight: 14,
    marginTop: 16,
    axisHeight: 22,
    colors: {
        wet: '#4aa3ff',
        dry: 'rgba(255,255,255,0.05)',
        unreachable: '#ffa502',
        cimierOpen: '#00d26a',
        tracking: '#d4a055',
        closeMarker: '#ff4757',
        wouldCloseMarker: '#ffa502',
        axis: 'rgba(255,255,255,0.25)',
        text: '#9aa0a6',
    },
};

const ROWS = [
    { key: 'rain', label: 'Pluie' },
    { key: 'cimier', label: 'Cimier' },
    { key: 'tracking', label: 'Suivi' },
];

function parseIso(value) {
    const ms = Date.parse(value);
    return Number.isFinite(ms) ? ms : null;
}

/**
 * Convertit la liste d'événements en segments d'état continus.
 * Un état vaut jusqu'au prochain événement du même type, ou jusqu'à la fin.
 */
function toSegments(events, predicate, valueOf, startMs, endMs) {
    const points = events
        .filter(predicate)
        .map((e) => ({ ts: parseIso(e.ts), value: valueOf(e) }))
        .filter((p) => p.ts !== null)
        .sort((a, b) => a.ts - b.ts);

    const segments = [];
    for (let i = 0; i < points.length; i += 1) {
        const from = Math.max(points[i].ts, startMs);
        const to = i + 1 < points.length ? Math.min(points[i + 1].ts, endMs) : endMs;
        if (to > from) segments.push({ from, to, value: points[i].value });
    }
    return segments;
}

function svgEl(name, attrs) {
    const el = document.createElementNS('http://www.w3.org/2000/svg', name);
    Object.entries(attrs || {}).forEach(([k, v]) => el.setAttribute(k, String(v)));
    return el;
}

/**
 * Dessine la frise dans le conteneur fourni.
 * @param {HTMLElement} container
 * @param {Object} data - payload de GET /api/session/night/
 */
function renderNightFrieze(container, data) {
    container.innerHTML = '';
    if (!data || !data.night) {
        const empty = document.createElement('div');
        empty.className = 'text-xs text-obs-text-muted italic text-center py-6';
        empty.textContent = 'Aucune nuit enregistrée pour l\'instant.';
        container.appendChild(empty);
        return;
    }

    const startMs = parseIso(data.night_start);
    const endMs = parseIso(data.night_end);
    if (startMs === null || endMs === null || endMs <= startMs) return;

    const width = Math.max(container.clientWidth || 720, 480);
    const plotWidth = width - FRIEZE.marginLeft - FRIEZE.marginRight;
    const xOf = (ms) =>
        FRIEZE.marginLeft + ((Math.min(Math.max(ms, startMs), endMs) - startMs) / (endMs - startMs)) * plotWidth;
    const yOf = (rowIndex) => FRIEZE.marginTop + rowIndex * (FRIEZE.rowHeight + FRIEZE.rowGap);

    const svg = svgEl('svg', {
        width: '100%',
        height: FRIEZE.height,
        viewBox: `0 0 ${width} ${FRIEZE.height}`,
        role: 'img',
        'aria-label': `Frise de la nuit du ${data.night}`,
    });

    // Hachures pour « capteur injoignable ».
    const defs = svgEl('defs', {});
    const pattern = svgEl('pattern', {
        id: 'frieze-hatch',
        width: 6,
        height: 6,
        patternUnits: 'userSpaceOnUse',
        patternTransform: 'rotate(45)',
    });
    pattern.appendChild(
        svgEl('rect', { width: 6, height: 6, fill: 'rgba(255,165,2,0.12)' })
    );
    pattern.appendChild(
        svgEl('rect', { width: 2, height: 6, fill: FRIEZE.colors.unreachable })
    );
    defs.appendChild(pattern);
    svg.appendChild(defs);

    // Libellés et fonds de ligne.
    ROWS.forEach((row, index) => {
        const y = yOf(index);
        svg.appendChild(
            svgEl('rect', {
                x: FRIEZE.marginLeft,
                y,
                width: plotWidth,
                height: FRIEZE.rowHeight,
                fill: FRIEZE.colors.dry,
                rx: 3,
            })
        );
        const label = svgEl('text', {
            x: FRIEZE.marginLeft - 10,
            y: y + FRIEZE.rowHeight / 2 + 4,
            'text-anchor': 'end',
            fill: FRIEZE.colors.text,
            'font-size': 11,
            'font-family': 'monospace',
        });
        label.textContent = row.label;
        svg.appendChild(label);
    });

    const events = Array.isArray(data.events) ? data.events : [];

    // Ligne 1 — pluie.
    toSegments(
        events,
        (e) => e.event === 'rain',
        (e) => e.state,
        startMs,
        endMs
    ).forEach((seg) => {
        if (seg.value === 'dry') return;
        svg.appendChild(
            svgEl('rect', {
                x: xOf(seg.from),
                y: yOf(0),
                width: Math.max(xOf(seg.to) - xOf(seg.from), 1),
                height: FRIEZE.rowHeight,
                fill: seg.value === 'wet' ? FRIEZE.colors.wet : 'url(#frieze-hatch)',
                rx: 3,
            })
        );
    });

    // Ligne 2 — cimier ouvert, d'un cycle `open` réussi au `close` suivant.
    toSegments(
        events,
        (e) => e.event === 'cimier' && (e.action === 'open' || e.action === 'close'),
        (e) => e.action,
        startMs,
        endMs
    ).forEach((seg) => {
        if (seg.value !== 'open') return;
        svg.appendChild(
            svgEl('rect', {
                x: xOf(seg.from),
                y: yOf(1),
                width: Math.max(xOf(seg.to) - xOf(seg.from), 1),
                height: FRIEZE.rowHeight,
                fill: FRIEZE.colors.cimierOpen,
                opacity: 0.55,
                rx: 3,
            })
        );
    });

    // Marqueurs de décision sur la ligne cimier.
    events
        .filter((e) => e.event === 'decision')
        .forEach((e) => {
            const ts = parseIso(e.ts);
            if (ts === null) return;
            const isReal = e.action === 'close';
            svg.appendChild(
                svgEl('line', {
                    x1: xOf(ts),
                    x2: xOf(ts),
                    y1: yOf(1) - 5,
                    y2: yOf(1) + FRIEZE.rowHeight + 5,
                    stroke: isReal ? FRIEZE.colors.closeMarker : FRIEZE.colors.wouldCloseMarker,
                    'stroke-width': 2,
                    'stroke-dasharray': isReal ? '' : '3 3',
                })
            );
        });

    // Ligne 3 — sessions de suivi.
    (data.tracking || []).forEach((session) => {
        const from = parseIso(session.start_time);
        if (from === null) return;
        const to = parseIso(session.end_time) || endMs;
        const x = xOf(from);
        const w = Math.max(xOf(to) - x, 2);
        svg.appendChild(
            svgEl('rect', {
                x,
                y: yOf(2),
                width: w,
                height: FRIEZE.rowHeight,
                fill: FRIEZE.colors.tracking,
                opacity: 0.5,
                rx: 3,
            })
        );
        if (w > 48 && session.object_name) {
            const name = svgEl('text', {
                x: x + 6,
                y: yOf(2) + FRIEZE.rowHeight / 2 + 4,
                fill: '#1b1b1b',
                'font-size': 10,
                'font-family': 'monospace',
            });
            name.textContent = session.object_name;
            svg.appendChild(name);
        }
    });

    // Axe horaire : une graduation toutes les 2 h.
    const axisY = FRIEZE.marginTop + ROWS.length * (FRIEZE.rowHeight + FRIEZE.rowGap);
    svg.appendChild(
        svgEl('line', {
            x1: FRIEZE.marginLeft,
            x2: FRIEZE.marginLeft + plotWidth,
            y1: axisY,
            y2: axisY,
            stroke: FRIEZE.colors.axis,
        })
    );
    for (let hour = 0; hour <= 24; hour += 2) {
        const ts = startMs + hour * 3600 * 1000;
        if (ts > endMs) break;
        const x = xOf(ts);
        svg.appendChild(
            svgEl('line', { x1: x, x2: x, y1: axisY, y2: axisY + 4, stroke: FRIEZE.colors.axis })
        );
        const tick = svgEl('text', {
            x,
            y: axisY + 16,
            'text-anchor': 'middle',
            fill: FRIEZE.colors.text,
            'font-size': 10,
            'font-family': 'monospace',
        });
        tick.textContent = String((12 + hour) % 24).padStart(2, '0') + 'h';
        svg.appendChild(tick);
    }

    container.appendChild(svg);
}

window.renderNightFrieze = renderNightFrieze;
```

- [ ] **Step 2 : ajouter la carte au template**

Dans `web/templates/session.html`, insérer une nouvelle section juste après la section « Evolution Altitude / Azimut » :

```html
<!-- ═══ Section Nuit (frise pluie / cimier / suivi) ═══ -->
<section class="panel panel-astro mb-4" x-data>
    <div class="flex items-center justify-between mb-3 gap-3 flex-wrap">
        <h2 class="section-title section-title-fire">Nuit</h2>
        <select id="night-selector"
                class="bg-obs-input border border-obs-border rounded-button px-2 py-1
                       text-obs-text font-mono text-xs
                       focus-visible:outline focus-visible:outline-2
                       focus-visible:outline-accent-amber focus-visible:outline-offset-2"
                aria-label="Choisir la nuit à afficher"></select>
    </div>
    <div id="night-frieze" class="w-full overflow-x-auto"></div>
    <div class="chart-legend mt-2 text-xs text-obs-text-secondary">
        <div class="flex items-center gap-1">
            <span class="legend-swatch" style="background:#4aa3ff"></span><span>Pluie</span>
        </div>
        <div class="flex items-center gap-1">
            <span class="legend-swatch" style="background:#ffa502"></span><span>Capteur injoignable</span>
        </div>
        <div class="flex items-center gap-1">
            <span class="legend-swatch" style="background:#00d26a"></span><span>Cimier ouvert</span>
        </div>
        <div class="flex items-center gap-1">
            <span class="legend-swatch" style="background:#d4a055"></span><span>Suivi</span>
        </div>
        <div class="flex items-center gap-1">
            <span class="legend-swatch" style="background:#ff4757"></span><span>Fermeture pluie</span>
        </div>
        <div class="flex items-center gap-1">
            <span class="legend-swatch" style="background:#ffa502;opacity:.6"></span><span>Aurait fermé</span>
        </div>
    </div>
</section>
```

Ajouter dans le bloc `<style>` de la page, à la suite des styles de légende existants :

```css
.legend-swatch {
    display: inline-block;
    width: 12px;
    height: 12px;
    border-radius: 3px;
}
```

Enfin, charger le script — repérer dans `session.html` (ou `base.html`) la balise chargeant `session.js` et ajouter **avant** elle :

```html
<script src="{% static 'js/night_frieze.js' %}"></script>
```

- [ ] **Step 3 : brancher le chargement des données**

Ajouter à la fin de `web/static/js/session.js` :

```javascript
// =============================================================================
// FRISE DE NUIT
// =============================================================================

async function loadNight(dateKey) {
    const container = document.getElementById('night-frieze');
    const selector = document.getElementById('night-selector');
    if (!container || !selector) return;

    const url = dateKey ? `/api/session/night/?date=${dateKey}` : '/api/session/night/';
    let data;
    try {
        const response = await fetch(url);
        if (!response.ok) return;
        data = await response.json();
    } catch (_e) {
        return;
    }

    // Peuple le sélecteur une seule fois, puis reflète la nuit affichée.
    if (selector.options.length !== (data.available_nights || []).length) {
        selector.innerHTML = '';
        (data.available_nights || []).forEach((night) => {
            const option = document.createElement('option');
            option.value = night;
            option.textContent = night;
            selector.appendChild(option);
        });
    }
    if (data.night) selector.value = data.night;

    window.renderNightFrieze(container, data);
}

document.addEventListener('DOMContentLoaded', () => {
    const selector = document.getElementById('night-selector');
    if (!selector) return;
    selector.addEventListener('change', (event) => loadNight(event.target.value));
    loadNight();
    // Redessine à la volée : le SVG est calculé pour la largeur du conteneur.
    window.addEventListener('resize', () => loadNight(selector.value));
});
```

- [ ] **Step 4 : vérifier la non-régression**

Run: `uv run --extra dev pytest tests/test_session_views.py -v`
Expected: PASS.

- [ ] **Step 5 : commit**

```bash
git add web/static/js/night_frieze.js web/static/js/session.js web/templates/session.html
git commit -m "feat(pluie): frise de nuit SVG sur la page Session (pluie / cimier / suivi)"
```

---

## Task 15 : vérification bout en bout du lot 2

- [ ] **Step 1 : produire une nuit factice**

Avec la stack arrêtée :

```bash
uv run python - <<'PY'
from datetime import datetime, timedelta
from services import night_journal

base = datetime.now().replace(hour=21, minute=0, second=0, microsecond=0)
night_journal.append_event("cimier", at=base, action="open", result="ok")
night_journal.append_event("rain", at=base + timedelta(hours=2), state="wet", armed=False)
night_journal.append_event("decision", at=base + timedelta(hours=2, seconds=20),
                           action="would_close", reason="rain")
night_journal.append_event("rain", at=base + timedelta(hours=2, minutes=4), state="dry", armed=False)
night_journal.append_event("rain", at=base + timedelta(hours=4), state="unreachable", armed=False)
night_journal.append_event("rain", at=base + timedelta(hours=4, minutes=6), state="dry", armed=False)
night_journal.append_event("rain", at=base + timedelta(hours=5), state="wet", armed=True)
night_journal.append_event("decision", at=base + timedelta(hours=5, seconds=20),
                           action="close", reason="rain")
night_journal.append_event("cimier", at=base + timedelta(hours=5, minutes=1),
                           action="close", result="ok")
print("nuit écrite :", night_journal.list_nights()[0])
PY
```

- [ ] **Step 2 : démarrer et inspecter**

```bash
./start_dev.sh start
```

Ouvrir `http://127.0.0.1:8000/session/` et contrôler à l'œil :
- la carte « Nuit » affiche trois lignes libellées et un axe horaire de 12 h à 12 h ;
- la bande bleue de pluie tombe bien vers 23 h, la zone hachurée vers 1 h ;
- le marqueur pointillé ambre (« aurait fermé ») et le marqueur plein rouge (« a fermé ») sont aux bons endroits ;
- la bande verte « cimier ouvert » s'arrête au marqueur rouge ;
- le sélecteur liste les nuits disponibles et bascule l'affichage ;
- la légende suffit à lire la frise **sans aucun survol** ;
- à 1280×720, la carte tient sans faire déborder la page.

- [ ] **Step 3 : vérifier avec une session de suivi**

S'il existe des fichiers dans `data/sessions/`, choisir une nuit qui en contient et vérifier que la 3ᵉ ligne affiche la bande et le nom d'objet. Sinon, en fabriquer une avec `session_storage.save_session` sur le modèle du test de la Task 13, Step 1.

- [ ] **Step 4 : suite complète et lint**

```bash
./start_dev.sh stop
uv run --extra dev pytest -q
uv run --extra dev ruff format --check core/ services/ web/ tests/
uv run --extra dev ruff check core/ services/ web/ tests/
```
Expected: PASS partout.

- [ ] **Step 5 : nettoyer, bumper, documenter**

Supprimer la nuit factice : `rm data/nights/<clé>.jsonl`.

Passer `version` à `6.13.0` dans `pyproject.toml`, et ajouter la ligne correspondante au changelog de `CLAUDE.md` (frise de nuit sur la page Session, endpoint `night`, trois lignes pluie/cimier/suivi).

- [ ] **Step 6 : commit**

```bash
git add pyproject.toml CLAUDE.md
git commit -m "chore(pluie): v6.13.0 — frise de restitution de la nuit"
```

---

## Après le plan : déploiement terrain

À ne pas oublier au moment de livrer sur le Pi — ces valeurs vivent dans `data/config.json` (non suivi par git), le merge structurel du chantier A ne les créera pas avec les bonnes valeurs terrain :

```json
"weather_provider": {
  "type": "shelly_rain",
  "host": "192.168.1.87",
  "input_id": 0,
  "invert": false,
  "protection_enabled": false
}
```

`protection_enabled` reste à `false` : c'est l'UI qui l'armera, une fois la campagne d'observation concluante.

Vérifier ensuite `data/nights/` accessible en écriture par l'utilisateur qui fait tourner `cimier_service` (`chown slenk:slenk`, comme le reste de `data/`).
