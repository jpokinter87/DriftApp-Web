# Cimier tout-Shelly (suppression Pico W) — Plan d'implémentation

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Migrer le pilotage cimier de l'architecture Pico W vers l'architecture V3 « tout-Shelly » : lecture des fins de course via Shelly Uni+ (RPC), alimentation 24V + moteur MOT/UPDN via Shelly, suppression totale du Pico W et de son firmware.

**Architecture :** On conserve la machine d'états `_run_cycle` (9 phases) de `cimier_service` — elle correspond déjà à la cinématique V3. On remplace seulement le **transport de lecture capteur** (Pico `GET /status` → Shelly Uni+ `GET /rpc/Input.GetStatus`) via une nouvelle classe `ShellySwitchReader` injectée, on repointe les configs Shelly (24V/MOT/UPDN), et on supprime le mort Pico W. `MotorShelly`, `ShellyPowerSwitch`, scheduler astropy, IPC et endpoints Django sont réutilisés tels quels.

**Tech Stack :** Python 3.12, `uv` (toujours `--extra dev`), `pytest`, `urllib` (clients HTTP existants), `http.server` (simulateur dev). Spec source : `docs/superpowers/specs/2026-06-08-cimier-tout-shelly-v3-design.md`.

**Conventions projet :**
- Commandes Python via `uv run --extra dev ...`.
- Avant chaque commit : `uv run --extra dev ruff format` puis `uv run --extra dev ruff check`.
- Aucune valeur terrain (IP/host/ids) en dur dans le code — tout via `data/config.json`.
- **Pas de bump de version** (chantier cimier en cours).
- Le repo utilise un dépôt git ; les commits sont locaux (le push reste à la main de l'utilisateur via `/pre-push`).

---

## Plan d'adressage de référence (rappel, → `data/config.json` uniquement)

| Shelly | IP terrain | API | Rôle |
|--------|-----------|-----|------|
| SHELLY-1-24V | 192.168.1.83 | legacy | alim module — cycle ON/OFF |
| SHELLY-UNI+ | 192.168.1.84 | rpc | butées : `id=0`→BAS, `id=1`→HAUT |
| SHELLY-1-MOT | 192.168.1.85 | legacy | marche/arrêt moteur |
| SHELLY-1-UPDN | 192.168.1.86 | legacy | sens (UP/DN) |

Sémantique Uni+ (configurable, validée banc) : `state=True` = « Ouvert » = pas en butée ; `state=False` = « fermé » = butée atteinte. Donc avec `invert=True` : `open_switch = NOT input(HAUT)`, `closed_switch = NOT input(BAS)`.

---

## Fichiers touchés (vue d'ensemble)

| Fichier | Action | Tâche |
|---------|--------|-------|
| `core/hardware/shelly_switch_reader.py` | créer | T1 |
| `tests/test_shelly_switch_reader.py` | créer | T1 |
| `core/config/config_loader.py` | modifier (`SwitchReaderConfig`, `CimierConfig`, `_parse_cimier`) | T2 |
| `tests/test_config_loader.py` | modifier | T2 |
| `services/cimier_service.py` | modifier (reader injecté, preflight/poll, factory, dev-mode, retrait `HttpClient`) | T3 |
| `tests/test_cimier_service.py` | modifier (FakeSwitchReader) | T3 |
| `core/hardware/cimier_simulator.py` | réécrire (émulateur Shelly unifié) | T4 |
| `tests/test_cimier_simulator.py` | modifier | T4 |
| `firmware/cimier/` (dossier) | supprimer | T5 |
| `tests/test_cimier_controller.py` | supprimer | T5 |
| `data/config.json` | modifier (section `cimier`) | T6 |
| `CLAUDE.md` | modifier (archi cimier) | T6 |
| `docs/synoptique electronique cimier V2.pdf` + `V3.pdf` + spec | versionner | T6 |

Réutilisés **sans modification** : `core/hardware/motor_shelly.py`, `core/hardware/power_switch.py`, `core/hardware/cimier_mechanism_sim.py`, `core/hardware/sim_motor_shelly.py`, `services/cimier_scheduler.py`, `services/cimier_ipc_manager.py`, `services/motor_ipc_writer.py`, `core/observatoire/sun_altitude.py`, `web/cimier/`.

---

## Task 1 : `ShellySwitchReader` (lecture butées Uni+)

**Files:**
- Create: `core/hardware/shelly_switch_reader.py`
- Test: `tests/test_shelly_switch_reader.py`

- [ ] **Step 1 : Écrire les tests qui échouent**

Créer `tests/test_shelly_switch_reader.py` :

```python
"""Tests ShellySwitchReader — lecture des butées cimier via Shelly Uni+ (RPC)."""

from __future__ import annotations

import io
import json
import urllib.error

import pytest

from core.hardware.shelly_switch_reader import (
    NoopSwitchReader,
    ShellySwitchReader,
    SwitchReaderError,
    SwitchState,
)


class _FakeResp:
    """Réponse urlopen factice (context manager)."""

    def __init__(self, payload, status=200):
        self.status = status
        self._body = json.dumps(payload).encode("utf-8") if isinstance(payload, dict) else payload

    def __enter__(self):
        return self

    def __exit__(self, *a):
        return False

    def read(self):
        return self._body


def _urlopen_map(mapping):
    """Renvoie un urlopen factice routant l'URL → _FakeResp selon `id=` présent."""

    def _fake(url, timeout=None):
        for key, resp in mapping.items():
            if "id=" + str(key) in url:
                if isinstance(resp, Exception):
                    raise resp
                return resp
        raise AssertionError("URL inattendue: " + url)

    return _fake


def test_invert_default_butee_atteinte_quand_input_false():
    # HAUT (id=1) state=False → butée haute atteinte → open_switch=True
    # BAS  (id=0) state=True  → pas en butée basse  → closed_switch=False
    reader = ShellySwitchReader(
        host="1.2.3.4",
        urlopen=_urlopen_map(
            {1: _FakeResp({"id": 1, "state": False}), 0: _FakeResp({"id": 0, "state": True})}
        ),
    )
    state = reader.read()
    assert isinstance(state, SwitchState)
    assert state.open_switch is True
    assert state.closed_switch is False
    assert state.both_switches is False


def test_both_switches_quand_les_deux_en_butee():
    reader = ShellySwitchReader(
        host="1.2.3.4",
        urlopen=_urlopen_map(
            {1: _FakeResp({"id": 1, "state": False}), 0: _FakeResp({"id": 0, "state": False})}
        ),
    )
    state = reader.read()
    assert state.open_switch is True
    assert state.closed_switch is True
    assert state.both_switches is True


def test_invert_false_passe_input_brut():
    reader = ShellySwitchReader(
        host="1.2.3.4",
        invert=False,
        urlopen=_urlopen_map(
            {1: _FakeResp({"id": 1, "state": True}), 0: _FakeResp({"id": 0, "state": False})}
        ),
    )
    state = reader.read()
    assert state.open_switch is True
    assert state.closed_switch is False


def test_mapping_ids_configurable():
    # open_input_id=3, closed_input_id=7
    reader = ShellySwitchReader(
        host="1.2.3.4",
        open_input_id=3,
        closed_input_id=7,
        urlopen=_urlopen_map(
            {3: _FakeResp({"id": 3, "state": False}), 7: _FakeResp({"id": 7, "state": True})}
        ),
    )
    state = reader.read()
    assert state.open_switch is True
    assert state.closed_switch is False


def test_url_rpc_construite():
    seen = []

    def _capture(url, timeout=None):
        seen.append(url)
        return _FakeResp({"id": 0, "state": True})

    ShellySwitchReader(host="9.9.9.9", urlopen=_capture).read()
    assert any(u.startswith("http://9.9.9.9/rpc/Input.GetStatus?id=") for u in seen)


def test_urlerror_leve_switchreadererror():
    reader = ShellySwitchReader(
        host="1.2.3.4",
        urlopen=_urlopen_map({1: urllib.error.URLError("down"), 0: _FakeResp({"state": True})}),
    )
    with pytest.raises(SwitchReaderError):
        reader.read()


def test_http_non_200_leve_switchreadererror():
    reader = ShellySwitchReader(
        host="1.2.3.4",
        urlopen=_urlopen_map({1: _FakeResp({"state": False}, status=500), 0: _FakeResp({"state": True})}),
    )
    with pytest.raises(SwitchReaderError):
        reader.read()


def test_payload_sans_state_leve_switchreadererror():
    reader = ShellySwitchReader(
        host="1.2.3.4",
        urlopen=_urlopen_map({1: _FakeResp({"id": 1}), 0: _FakeResp({"state": True})}),
    )
    with pytest.raises(SwitchReaderError):
        reader.read()


def test_json_invalide_leve_switchreadererror():
    reader = ShellySwitchReader(
        host="1.2.3.4",
        urlopen=_urlopen_map({1: _FakeResp(b"pas du json"), 0: _FakeResp({"state": True})}),
    )
    with pytest.raises(SwitchReaderError):
        reader.read()


def test_api_non_rpc_rejetee():
    with pytest.raises(ValueError):
        ShellySwitchReader(host="1.2.3.4", api="legacy")


def test_noop_reader_renvoie_etat_configurable():
    r = NoopSwitchReader(open_switch=True, closed_switch=False)
    state = r.read()
    assert state.open_switch is True
    assert state.closed_switch is False
    assert state.both_switches is False
    r.closed_switch = True
    assert r.read().both_switches is True
```

- [ ] **Step 2 : Lancer les tests, vérifier l'échec**

Run: `uv run --extra dev pytest tests/test_shelly_switch_reader.py -v`
Expected: FAIL — `ModuleNotFoundError: No module named 'core.hardware.shelly_switch_reader'`.

- [ ] **Step 3 : Écrire l'implémentation**

Créer `core/hardware/shelly_switch_reader.py` :

```python
"""Lecture des fins de course cimier via un Shelly Uni+ (archi V3).

Remplace le Pico W capteur : les 2 microswitches (Haut/Bas) sont câblés sur
les 2 entrées du Shelly Uni+, lues via l'API RPC Gen 2
``GET /rpc/Input.GetStatus?id=<n>`` → ``{"id": n, "state": <bool>}``.

Sémantique terrain (synoptique V3 — **à valider au banc**, donc configurable) :
  - ``state=True``  = « Ouvert »  = contact ouvert = PAS en butée.
  - ``state=False`` = « fermé »   = butée atteinte.
Avec ``invert=True`` (défaut) : butée atteinte = input False.

Mapping d'entrées (configurable) :
  - ``open_input_id``   : entrée du microswitch HAUT (défaut id=1).
  - ``closed_input_id`` : entrée du microswitch BAS  (défaut id=0).

Aucune valeur terrain en dur — host / ids / inversion via le constructeur,
remplis par ``SwitchReaderConfig`` depuis ``data/config.json``.

L'argument ``urlopen`` permet d'injecter un mock pour les tests.
"""

from __future__ import annotations

import json
import urllib.error
import urllib.request
from dataclasses import dataclass


class SwitchReaderError(Exception):
    """Erreur de communication avec le Shelly Uni+."""


@dataclass(frozen=True)
class SwitchState:
    """État des fins de course dérivé des 2 entrées du Shelly Uni+."""

    open_switch: bool
    closed_switch: bool
    both_switches: bool
    raw: dict


class ShellySwitchReader:
    """Lit les 2 microswitches cimier via un Shelly Uni+ (RPC Gen 2)."""

    def __init__(
        self,
        host: str,
        api: str = "rpc",
        open_input_id: int = 1,
        closed_input_id: int = 0,
        invert: bool = True,
        timeout_s: float = 3.0,
        urlopen=None,
    ) -> None:
        if api != "rpc":
            raise ValueError(
                "ShellySwitchReader ne supporte que api='rpc' (Shelly Uni+ Gen 2), reçu " + repr(api)
            )
        self._host = host
        self._api = api
        self._open_input_id = int(open_input_id)
        self._closed_input_id = int(closed_input_id)
        self._invert = bool(invert)
        self._timeout_s = float(timeout_s)
        self._urlopen = urlopen or urllib.request.urlopen

    def _read_input(self, input_id: int):
        url = "http://" + self._host + "/rpc/Input.GetStatus?id=" + str(input_id)
        try:
            with self._urlopen(url, timeout=self._timeout_s) as resp:
                status = getattr(resp, "status", 200)
                raw = resp.read()
        except urllib.error.URLError as exc:
            raise SwitchReaderError("Shelly Uni+ unreachable: " + str(exc.reason)) from exc
        except OSError as exc:
            raise SwitchReaderError("Shelly Uni+ socket error: " + str(exc)) from exc
        if status != 200:
            raise SwitchReaderError("Shelly Uni+ HTTP " + str(status))
        try:
            payload = json.loads(raw.decode("utf-8"))
        except (ValueError, UnicodeDecodeError) as exc:
            raise SwitchReaderError("Shelly Uni+ JSON invalide: " + str(exc)) from exc
        if not isinstance(payload, dict) or "state" not in payload:
            raise SwitchReaderError("Shelly Uni+ payload sans 'state': " + repr(payload))
        return bool(payload["state"]), payload

    def read(self) -> SwitchState:
        haut_state, haut_raw = self._read_input(self._open_input_id)
        bas_state, bas_raw = self._read_input(self._closed_input_id)
        if self._invert:
            open_switch = not haut_state
            closed_switch = not bas_state
        else:
            open_switch = haut_state
            closed_switch = bas_state
        return SwitchState(
            open_switch=open_switch,
            closed_switch=closed_switch,
            both_switches=open_switch and closed_switch,
            raw={"haut": haut_raw, "bas": bas_raw},
        )

    @property
    def host(self) -> str:
        return self._host


class NoopSwitchReader:
    """Reader inerte (dev/tests) : renvoie un ``SwitchState`` fixe configurable.

    Les attributs ``open_switch`` / ``closed_switch`` sont mutables pour qu'un
    test ou le dev puisse simuler une transition de butée.
    """

    def __init__(self, open_switch: bool = False, closed_switch: bool = False) -> None:
        self.open_switch = bool(open_switch)
        self.closed_switch = bool(closed_switch)

    def read(self) -> SwitchState:
        return SwitchState(
            open_switch=self.open_switch,
            closed_switch=self.closed_switch,
            both_switches=self.open_switch and self.closed_switch,
            raw={},
        )
```

- [ ] **Step 4 : Lancer les tests, vérifier le succès**

Run: `uv run --extra dev pytest tests/test_shelly_switch_reader.py -v`
Expected: PASS (12 tests).

- [ ] **Step 5 : Format + lint + commit**

```bash
uv run --extra dev ruff format core/hardware/shelly_switch_reader.py tests/test_shelly_switch_reader.py
uv run --extra dev ruff check core/hardware/shelly_switch_reader.py tests/test_shelly_switch_reader.py
git add core/hardware/shelly_switch_reader.py tests/test_shelly_switch_reader.py
git commit -m "feat(cimier): ShellySwitchReader — lecture butées via Shelly Uni+ (RPC)"
```

---

## Task 2 : Config `SwitchReaderConfig` + `CimierConfig`

**Files:**
- Modify: `core/config/config_loader.py` (ajout dataclass `SwitchReaderConfig`, champ `CimierConfig.switch_reader`, retrait `host`/`port`/`invert_direction`, `_parse_cimier`)
- Test: `tests/test_config_loader.py`

> Note : `boot_poll_timeout_s` (sémantique boot Pico) devient mort mais n'est pas
> introduit par ce changement — le **laisser en place** (signaler comme dette, ne
> pas l'enlever sans demande). On retire uniquement `host`, `port`,
> `invert_direction`, rendus inutilisés par la migration.

- [ ] **Step 1 : Écrire les tests qui échouent**

Ajouter à `tests/test_config_loader.py` (nouvelle classe de test) :

```python
class TestSwitchReaderConfig:
    def test_defaults(self):
        from core.config.config_loader import SwitchReaderConfig

        c = SwitchReaderConfig()
        assert c.type == "noop"
        assert c.host == ""
        assert c.api == "rpc"
        assert c.open_input_id == 1
        assert c.closed_input_id == 0
        assert c.invert is True
        assert c.timeout_s == 3.0

    def test_parse_switch_reader_from_json(self, tmp_path):
        import json

        from core.config.config_loader import load_config

        cfg_path = tmp_path / "config.json"
        cfg_path.write_text(
            json.dumps(
                {
                    "cimier": {
                        "enabled": True,
                        "switch_reader": {
                            "type": "shelly_uni",
                            "host": "192.168.1.84",
                            "api": "rpc",
                            "open_input_id": 1,
                            "closed_input_id": 0,
                            "invert": True,
                        },
                    }
                }
            ),
            encoding="utf-8",
        )
        cfg = load_config(cfg_path)
        sr = cfg.cimier.switch_reader
        assert sr.type == "shelly_uni"
        assert sr.host == "192.168.1.84"
        assert sr.open_input_id == 1
        assert sr.closed_input_id == 0
        assert sr.invert is True

    def test_switch_reader_defaults_when_absent(self, tmp_path):
        import json

        from core.config.config_loader import load_config

        cfg_path = tmp_path / "config.json"
        cfg_path.write_text(json.dumps({"cimier": {"enabled": False}}), encoding="utf-8")
        cfg = load_config(cfg_path)
        assert cfg.cimier.switch_reader.type == "noop"

    def test_legacy_pico_keys_ignored(self, tmp_path):
        # Anciennes clés Pico host/port présentes : ne doivent PAS faire planter
        # le parse (rétro-compat lecture), mais ne sont plus exposées.
        import json

        from core.config.config_loader import load_config

        cfg_path = tmp_path / "config.json"
        cfg_path.write_text(
            json.dumps({"cimier": {"enabled": False, "host": "192.168.1.84", "port": 80}}),
            encoding="utf-8",
        )
        cfg = load_config(cfg_path)
        assert not hasattr(cfg.cimier, "host")
        assert not hasattr(cfg.cimier, "port")
```

Et **retirer** de `tests/test_config_loader.py` toute assertion existante portant sur `cimier.host`, `cimier.port`, `cimier.invert_direction` (rechercher `\.host`, `\.port`, `invert_direction` dans la classe de test cimier).

- [ ] **Step 2 : Lancer les tests, vérifier l'échec**

Run: `uv run --extra dev pytest tests/test_config_loader.py -k "SwitchReader or cimier or Cimier" -v`
Expected: FAIL — `ImportError: cannot import name 'SwitchReaderConfig'`.

- [ ] **Step 3 : Ajouter la dataclass `SwitchReaderConfig`**

Dans `core/config/config_loader.py`, après la classe `MotorShellyConfig` (vers la ligne 196) :

```python
@dataclass
class SwitchReaderConfig:
    """Configuration de la lecture des fins de course cimier (Shelly Uni+, V3).

    Remplace le Pico W capteur. Les 2 microswitches Haut/Bas sont lus via les
    2 entrées du Shelly Uni+ (RPC Gen 2 ``Input.GetStatus``).

    type:
      - "shelly_uni" → lit via ``core.hardware.shelly_switch_reader.ShellySwitchReader``
      - "noop"       → reader inerte (dev/tests sans hardware)

    ``open_input_id`` / ``closed_input_id`` : index d'entrée Shelly Uni+ pour
    les microswitches HAUT et BAS. ``invert`` : True → butée atteinte = input
    False (« fermé », convention synoptique V3, à valider au banc).

    IP réelle uniquement dans ``data/config.json`` (terrain) — code Python neutre.
    """

    type: str = "noop"
    host: str = ""
    api: str = "rpc"
    open_input_id: int = 1
    closed_input_id: int = 0
    invert: bool = True
    timeout_s: float = 3.0
```

- [ ] **Step 4 : Modifier `CimierConfig`**

Dans la dataclass `CimierConfig` (vers ligne 278), **retirer** les champs `host`, `port`, `invert_direction` et **ajouter** `switch_reader`. Le bloc devient :

```python
    enabled: bool = False
    cycle_timeout_s: float = 90.0
    boot_poll_timeout_s: float = 30.0  # legacy (boot Pico) — dette, non utilisé en V3
    post_off_quiet_s: float = 10.0
    shelly_settle_s: float = 2.0  # attente appairage WiFi Shelly MOT/UPDN (synoptique "à mesurer")
    verbose_logging: bool = False  # true → logs DEBUG par itération (debug à distance)
    switch_reader: SwitchReaderConfig = field(default_factory=SwitchReaderConfig)
    power_switch: PowerSwitchConfig = field(default_factory=PowerSwitchConfig)
    weather_provider: WeatherProviderConfig = field(default_factory=WeatherProviderConfig)
    automation: CimierAutomationConfig = field(default_factory=CimierAutomationConfig)
    motor_shelly: MotorShellyConfig = field(default_factory=MotorShellyConfig)
```

(Le `__post_init__` validant `cycle_timeout_s > 0` reste inchangé.)

- [ ] **Step 5 : Modifier `_parse_cimier`**

Dans `_parse_cimier` (vers ligne 550) : ajouter le parsing `switch_reader`, retirer `host`/`port`/`invert_direction` du `return CimierConfig(...)`.

Ajouter après la ligne `ms = c.get("motor_shelly", {}) ...` :

```python
        sr = c.get("switch_reader", {}) if isinstance(c, dict) else {}
        if not isinstance(sr, dict):
            sr = {}
        sr_defaults = SwitchReaderConfig()
```

Dans le `return CimierConfig(...)` : **supprimer** les lignes `host=...`, `port=...`, `invert_direction=...`, et **ajouter** (à côté de `power_switch=...`) :

```python
            switch_reader=SwitchReaderConfig(
                type=str(sr.get("type", sr_defaults.type)),
                host=str(sr.get("host", sr_defaults.host)),
                api=str(sr.get("api", sr_defaults.api)),
                open_input_id=int(sr.get("open_input_id", sr_defaults.open_input_id)),
                closed_input_id=int(sr.get("closed_input_id", sr_defaults.closed_input_id)),
                invert=bool(sr.get("invert", sr_defaults.invert)),
                timeout_s=float(sr.get("timeout_s", sr_defaults.timeout_s)),
            ),
```

- [ ] **Step 6 : Lancer les tests, vérifier le succès**

Run: `uv run --extra dev pytest tests/test_config_loader.py -v`
Expected: PASS (la classe `TestSwitchReaderConfig` + les tests cimier existants adaptés passent).

- [ ] **Step 7 : Format + lint + commit**

```bash
uv run --extra dev ruff format core/config/config_loader.py tests/test_config_loader.py
uv run --extra dev ruff check core/config/config_loader.py tests/test_config_loader.py
git add core/config/config_loader.py tests/test_config_loader.py
git commit -m "feat(cimier): SwitchReaderConfig + retrait clés Pico (host/port/invert_direction)"
```

---

## Task 3 : Intégration dans `cimier_service`

**Files:**
- Modify: `services/cimier_service.py`
- Test: `tests/test_cimier_service.py`

Objectif : injecter `ShellySwitchReader` à la place du `HttpClient` Pico ; `_preflight_switches` et `_poll_target_switch` lisent via le reader ; suppression de `HttpClient`, `_base_url`, des références `cimier.host`/`port`.

- [ ] **Step 1 : Adapter les tests (introduire `FakeSwitchReader`)**

En tête de `tests/test_cimier_service.py`, ajouter le helper :

```python
from core.hardware.shelly_switch_reader import SwitchState


class FakeSwitchReader:
    """Reader programmable pour tester cimier_service sans HTTP.

    ``script`` : liste de tuples (open_switch, closed_switch) consommée à
    chaque ``read()``. Le dernier tuple est répété une fois la liste épuisée.
    ``raise_error`` : si fourni, ``read()`` lève cette exception.
    """

    def __init__(self, script=None, raise_error=None):
        self._script = list(script or [(False, False)])
        self._raise_error = raise_error
        self.read_count = 0

    def read(self):
        self.read_count += 1
        if self._raise_error is not None:
            raise self._raise_error
        idx = min(self.read_count - 1, len(self._script) - 1)
        op, cl = self._script[idx]
        return SwitchState(open_switch=op, closed_switch=cl, both_switches=op and cl, raw={})
```

Puis remplacer mécaniquement, dans chaque test, l'injection `http_client=<AutoFakeHttpClient...>` par `switch_reader=FakeSwitchReader(script=[...])`, où le script encode la séquence `(open_switch, closed_switch)` que le test attendait du Pico. Exemples de correspondance :
- Préflight « déjà ouvert » → `FakeSwitchReader(script=[(True, False)])`.
- Préflight « both switches » → `FakeSwitchReader(script=[(True, True)])`.
- Cycle nominal open (butée atteinte au Nᵉ poll) → `script=[(False, False)] * (N-1) + [(True, False)]`.
- Capteur injoignable → `FakeSwitchReader(raise_error=SwitchReaderError("down"))` (importer `SwitchReaderError`).

Supprimer la classe `AutoFakeHttpClient` (et tout helper Pico `/status`) du fichier de test une fois toutes les références migrées.

- [ ] **Step 2 : Lancer les tests, vérifier l'échec**

Run: `uv run --extra dev pytest tests/test_cimier_service.py -x -q`
Expected: FAIL — `TypeError: __init__() got an unexpected keyword argument 'switch_reader'` (le constructeur n'accepte pas encore `switch_reader`).

- [ ] **Step 3 : Imports + factory `make_switch_reader`**

Dans `services/cimier_service.py`, ajouter aux imports (après l'import `power_switch`) :

```python
from core.hardware.shelly_switch_reader import (
    NoopSwitchReader,
    ShellySwitchReader,
    SwitchReaderError,
)
```

Ajouter à l'import config `SwitchReaderConfig` :

```python
from core.config.config_loader import (
    CimierConfig,
    ConfigLoader,
    MotorShellyConfig,
    PowerSwitchConfig,
    SiteConfig,
    SwitchReaderConfig,
    load_config,
)
```

Après `make_motor_shelly(...)` (vers ligne 191), ajouter la factory :

```python
SwitchReaderProtocol = Any  # duck-typed : read() -> SwitchState


def make_switch_reader(cfg: SwitchReaderConfig) -> SwitchReaderProtocol:
    """Factory : instancie le reader de butées d'après la config.

    type ∈ {noop, shelly_uni}.
    """
    t = (cfg.type or "noop").lower()
    if t == "noop":
        return NoopSwitchReader()
    if t == "shelly_uni":
        if not cfg.host:
            raise ValueError("SwitchReaderConfig.host vide pour shelly_uni")
        return ShellySwitchReader(
            host=cfg.host,
            api=cfg.api,
            open_input_id=cfg.open_input_id,
            closed_input_id=cfg.closed_input_id,
            invert=cfg.invert,
            timeout_s=cfg.timeout_s,
        )
    raise ValueError("SwitchReaderConfig.type inconnu: " + repr(cfg.type))
```

- [ ] **Step 4 : Supprimer `HttpClient`, modifier le constructeur**

Supprimer la classe `HttpClient` (lignes ~109-147) et la constante `DEFAULT_HTTP_TIMEOUT_S` si elle n'est plus utilisée ailleurs.

Dans `CimierService.__init__`, remplacer le paramètre `http_client` par `switch_reader` :

```python
        switch_reader: Optional[SwitchReaderProtocol] = None,
```

et remplacer `self._http = http_client or HttpClient()` par :

```python
        self._switch_reader = (
            switch_reader
            if switch_reader is not None
            else make_switch_reader(cimier_config.switch_reader)
        )
```

- [ ] **Step 5 : Réécrire `_preflight_switches`**

Remplacer le corps de `_preflight_switches` (lignes ~435-515) par :

```python
    def _preflight_switches(self, action: str, cmd_id: str) -> Tuple[str, str, Dict[str, Any]]:
        """Lit les butées (Shelly Uni+) avant toute action électrique.

        Retourne (decision, reason, payload) :
          - decision: "noop"|"proceed"|"error"|"unreachable"
          - reason: chaîne lisible (vide si proceed)
          - payload: dict {open_switch, closed_switch} si lu, {} sinon
        """
        t0 = self._clock()
        try:
            state = self._switch_reader.read()
        except SwitchReaderError as exc:
            latency_ms = int((self._clock() - t0) * 1000)
            logger.info(
                "cimier_event=preflight action=%s id=%s decision=unreachable latency_ms=%d exc=%s",
                action,
                cmd_id,
                latency_ms,
                exc,
            )
            return ("unreachable", "precheck_unreachable", {})

        latency_ms = int((self._clock() - t0) * 1000)
        open_sw = state.open_switch
        closed_sw = state.closed_switch
        payload = {"open_switch": open_sw, "closed_switch": closed_sw}
        self._last_open_switch = open_sw
        self._last_closed_switch = closed_sw

        if state.both_switches:
            logger.info(
                "cimier_event=preflight action=%s id=%s decision=error "
                "reason=both_switches_triggered open_switch=%s closed_switch=%s latency_ms=%d",
                action,
                cmd_id,
                str(open_sw).lower(),
                str(closed_sw).lower(),
                latency_ms,
            )
            return ("error", "both_switches_triggered", payload)

        if action == ACTION_OPEN and open_sw:
            logger.info(
                "cimier_event=preflight action=%s id=%s decision=noop reason=already_open latency_ms=%d",
                action,
                cmd_id,
                latency_ms,
            )
            return ("noop", "already_open", payload)

        if action == ACTION_CLOSE and closed_sw:
            logger.info(
                "cimier_event=preflight action=%s id=%s decision=noop reason=already_closed latency_ms=%d",
                action,
                cmd_id,
                latency_ms,
            )
            return ("noop", "already_closed", payload)

        logger.info(
            "cimier_event=preflight action=%s id=%s decision=proceed "
            "open_switch=%s closed_switch=%s latency_ms=%d",
            action,
            cmd_id,
            str(open_sw).lower(),
            str(closed_sw).lower(),
            latency_ms,
        )
        return ("proceed", "", payload)
```

- [ ] **Step 6 : Réécrire `_poll_target_switch`**

Remplacer le corps de `_poll_target_switch` (lignes ~787-840) par :

```python
    def _poll_target_switch(self, action: str, cmd_id: str) -> str:
        """Boucle de lecture Shelly Uni+ jusqu'à fin de course cible atteinte.

        Returns:
            "ok"       : butée cible atteinte.
            "timeout"  : cycle_timeout_s dépassé.
            "stopped"  : commande stop reçue.
            "error"    : both_switches au cours du polling.
        """
        deadline = self._clock() + self._config.cycle_timeout_s

        while self._clock() < deadline:
            if self._stop_requested:
                return "stopped"
            if self._check_for_stop_command() is not None:
                return "stopped"
            try:
                t0 = self._clock()
                state = self._switch_reader.read()
                latency_ms = int((self._clock() - t0) * 1000)
            except SwitchReaderError as exc:
                logger.debug("cimier_event=poll_exception id=%s exc=%s", cmd_id, exc)
                self._sleep(self._cycle_poll_interval_s)
                continue

            self._last_open_switch = state.open_switch
            self._last_closed_switch = state.closed_switch
            target_now = state.open_switch if action == ACTION_OPEN else state.closed_switch

            if state.both_switches:
                logger.error("cimier_event=poll_both_switches id=%s", cmd_id)
                return "error"
            if target_now:
                target_key = "open_switch" if action == ACTION_OPEN else "closed_switch"
                logger.info(
                    "cimier_event=switch_transition switch=%s from=false to=true elapsed_ms=%d id=%s",
                    target_key,
                    latency_ms,
                    cmd_id,
                )
                return "ok"
            if self._config.verbose_logging or os.environ.get("CIMIER_DEV_MODE"):
                logger.debug(
                    "cimier_event=poll_status id=%s open_switch=%s closed_switch=%s",
                    cmd_id,
                    str(state.open_switch).lower(),
                    str(state.closed_switch).lower(),
                )
            self._sleep(self._cycle_poll_interval_s)
        return "timeout"
```

- [ ] **Step 7 : Supprimer `_base_url`, adapter `run_forever` + logging + dev-mode + entry-point**

Supprimer la méthode `_base_url` (lignes ~970-971).

Dans `run_forever`, remplacer le garde-fou `if not self._config.host: ...` (lignes ~281-292) par :

```python
        sr_cfg = self._config.switch_reader
        if sr_cfg.type == "shelly_uni" and not sr_cfg.host:
            logger.error(
                "cimier_event=config_error switch_reader.host vide — "
                "set cimier.switch_reader.host dans data/config.json"
            )
            self._publish_status(
                state=STATE_ERROR,
                phase=PHASE_IDLE,
                last_action="",
                command_id="",
                error_message="switch_reader_not_configured",
            )
            return
```

Remplacer le log `cimier_event=started ...` (lignes ~295-301) par :

```python
        logger.info(
            "cimier_event=started switch_reader=%s power=%s motor_host=%s dir_host=%s",
            self._config.switch_reader.host or "(noop)",
            self._config.power_switch.host or "(noop)",
            self._config.motor_shelly.host_motor or "(noop)",
            self._config.motor_shelly.host_dir or "(noop)",
        )
```

Remplacer `_apply_dev_mode_overrides` (lignes ~1009-1020) par la version V3 (simulateur unifié `127.0.0.1:8001`, conventions naturelles côté sim, `timer_safety_sec=0` — le sim n'implémente pas `toggle_after`) :

```python
def _apply_dev_mode_overrides(cimier_cfg) -> None:
    """Patche en place la config cimier pour pointer le simulateur dev unifié.

    Le simulateur (`core.hardware.cimier_simulator`) émule sur 127.0.0.1:8001 :
      - les butées Shelly Uni+ (RPC Input.GetStatus id=0 BAS / id=1 HAUT),
      - 3 relais legacy : id=0 → 24V, id=1 → MOT, id=2 → UPDN.
    Conventions naturelles côté sim (relais ON = actif) ; les conventions
    terrain potentiellement inversées sont validées au banc, pas en dev.
    Ne touche jamais data/config.json sur disque (patch mémoire seulement).
    """
    cimier_cfg.enabled = True
    cimier_cfg.switch_reader.type = "shelly_uni"
    cimier_cfg.switch_reader.host = "127.0.0.1:8001"
    cimier_cfg.switch_reader.api = "rpc"
    cimier_cfg.switch_reader.open_input_id = 1
    cimier_cfg.switch_reader.closed_input_id = 0
    cimier_cfg.switch_reader.invert = True
    cimier_cfg.power_switch.type = "shelly_gen1"
    cimier_cfg.power_switch.host = "127.0.0.1:8001"
    cimier_cfg.power_switch.switch_id = 0
    cimier_cfg.motor_shelly.host_motor = "127.0.0.1:8001"
    cimier_cfg.motor_shelly.host_dir = "127.0.0.1:8001"
    cimier_cfg.motor_shelly.relay_motor = 1
    cimier_cfg.motor_shelly.relay_dir = 2
    cimier_cfg.motor_shelly.api = "legacy"
    cimier_cfg.motor_shelly.motor_on_relay_state = True
    cimier_cfg.motor_shelly.open_dir_state = True
    cimier_cfg.motor_shelly.timer_safety_sec = 0.0
```

Dans `_build_service_from_config`, après `power_switch = make_power_switch(...)`, ajouter la construction du reader et la passer au service :

```python
    power_switch = make_power_switch(cfg.cimier.power_switch)
    switch_reader = make_switch_reader(cfg.cimier.switch_reader)
    weather_provider = make_weather_provider(cfg.cimier.weather_provider)
    return CimierService(
        cimier_config=cfg.cimier,
        power_switch=power_switch,
        switch_reader=switch_reader,
        weather_provider=weather_provider,
        site_config=cfg.site,
    )
```

Et adapter le log dev-mode dans `_build_service_from_config` (lignes ~1028-1033) :

```python
        logger.info(
            "cimier_dev_mode=on switch_reader=%s power=%s",
            cfg.cimier.switch_reader.host,
            cfg.cimier.power_switch.host,
        )
```

Enfin, mettre à jour le **docstring de module** (lignes 1-31) : remplacer les mentions « Pico capteur », « GET /status », « AutoFakeHttpClient » par « Shelly Uni+ », « ShellySwitchReader.read() », « FakeSwitchReader ». (Documentation seule, pas de logique.)

- [ ] **Step 8 : Lancer les tests, itérer jusqu'au vert**

Run: `uv run --extra dev pytest tests/test_cimier_service.py -v`
Expected: PASS. Corriger au besoin les scripts `FakeSwitchReader` des tests dont la séquence de butées ne correspondait pas (un test qui « timeout » attend un script qui ne déclenche jamais la cible ; un test « ok » attend une transition).

- [ ] **Step 9 : Régression cimier large**

Run: `uv run --extra dev pytest tests/test_cimier_service.py tests/test_cimier_scheduler.py tests/test_web_cimier_views.py -q`
Expected: PASS.

- [ ] **Step 10 : Format + lint + commit**

```bash
uv run --extra dev ruff format services/cimier_service.py tests/test_cimier_service.py
uv run --extra dev ruff check services/cimier_service.py tests/test_cimier_service.py
git add services/cimier_service.py tests/test_cimier_service.py
git commit -m "feat(cimier): cimier_service lit les butées via ShellySwitchReader (retrait HttpClient Pico)"
```

---

## Task 4 : Simulateur Shelly unifié (dev)

**Files:**
- Modify (réécriture) : `core/hardware/cimier_simulator.py`
- Test: `tests/test_cimier_simulator.py`

Objectif : le simulateur n'émule plus le Pico W (`/status`,`/info`) mais le **Shelly Uni+** (RPC inputs) **et 3 relais legacy** (24V/MOT/UPDN), adossés au `CimierMechanismSim` animé en temps réel. Ainsi un cycle `open`/`close` complet est jouable en dev (`CIMIER_DEV_MODE=1`) avec les vraies classes `ShellyPowerSwitch` / `MotorShelly` / `ShellySwitchReader`.

- [ ] **Step 1 : Écrire/adapter les tests qui échouent**

Remplacer le contenu de `tests/test_cimier_simulator.py` par :

```python
"""Tests du simulateur Shelly unifié cimier (dev) — relais + Uni+ + mécanisme."""

from __future__ import annotations

import json
import urllib.request

import pytest

from core.hardware.cimier_simulator import CimierSimulator


@pytest.fixture
def sim():
    s = CimierSimulator(port=0, boot_delay_s=0.0, initial_state="closed", full_travel_s=0.5)
    s.start()
    assert s.wait_ready(timeout=2.0)
    yield s
    s.stop()


def _get_json(url):
    with urllib.request.urlopen(url, timeout=2.0) as resp:
        return json.loads(resp.read().decode("utf-8"))


def test_uni_inputs_reflect_initial_closed(sim):
    # closed → BAS en butée (contact fermé → state False), HAUT pas en butée (state True)
    bas = _get_json(sim.url + "/rpc/Input.GetStatus?id=0")
    haut = _get_json(sim.url + "/rpc/Input.GetStatus?id=1")
    assert bas["state"] is False
    assert haut["state"] is True


def test_relay_endpoints_return_200(sim):
    for relay in (0, 1, 2):
        payload = _get_json(sim.url + "/relay/{}?turn=on".format(relay))
        assert "ison" in payload


def test_open_cycle_animates_to_top(sim):
    # 24V on, UPDN up (ouverture), MOT on → la position doit atteindre le haut
    _get_json(sim.url + "/relay/0?turn=on")  # 24V
    _get_json(sim.url + "/relay/2?turn=on")  # UPDN = ouverture
    _get_json(sim.url + "/relay/1?turn=on")  # MOT on
    import time

    deadline = time.monotonic() + 3.0
    haut_state = True
    while time.monotonic() < deadline:
        haut_state = _get_json(sim.url + "/rpc/Input.GetStatus?id=1")["state"]
        if haut_state is False:  # butée haute atteinte (contact fermé)
            break
        time.sleep(0.05)
    assert haut_state is False


def test_power_off_freezes_motion(sim):
    _get_json(sim.url + "/relay/0?turn=off")  # 24V OFF
    _get_json(sim.url + "/relay/2?turn=on")
    _get_json(sim.url + "/relay/1?turn=on")  # MOT on mais pas de 24V
    import time

    time.sleep(0.6)
    haut = _get_json(sim.url + "/rpc/Input.GetStatus?id=1")["state"]
    assert haut is True  # pas bougé : toujours pas en butée haute
```

- [ ] **Step 2 : Lancer les tests, vérifier l'échec**

Run: `uv run --extra dev pytest tests/test_cimier_simulator.py -v`
Expected: FAIL (anciens endpoints `/status`,`/info` ; pas de `/rpc/Input.GetStatus` ni `/relay/...` animé).

- [ ] **Step 3 : Réécrire le simulateur**

Remplacer **tout** le contenu de `core/hardware/cimier_simulator.py` par :

```python
"""Simulateur Shelly unifié cimier (archi V3, dev/tests).

Émule, sur un seul port HTTP, les Shellys du boîtier cimier adossés à un
``CimierMechanismSim`` animé en temps réel :

  - Shelly Uni+ (RPC Gen 2) : ``GET /rpc/Input.GetStatus?id=<n>`` →
    ``{"id": n, "state": <bool>}``. id=0 → microswitch BAS, id=1 → HAUT.
    Convention V3 : ``state=True`` = contact ouvert = PAS en butée ;
    ``state=False`` = contact fermé = butée atteinte.
  - 3 relais legacy (Gen 1) : ``GET /relay/<n>?turn=on|off`` →
    ``{"ison": <bool>}``. n=0 → 24V (alim), n=1 → MOT (moteur), n=2 → UPDN
    (sens : ON = ouverture).

Un thread animateur fait progresser la position tant que 24V ET MOT sont ON
(course complète en ``full_travel_s``). Conventions naturelles (relais ON =
actif) — les conventions terrain potentiellement inversées sont validées au
banc, pas en dev.

CLI : uv run python -m core.hardware.cimier_simulator [--port 8001]
      [--initial closed|open|mid] [--full-travel 60]
"""

from __future__ import annotations

import argparse
import json
import sys
import threading
import time
from http.server import BaseHTTPRequestHandler, HTTPServer
from urllib.parse import parse_qs, urlparse

from core.hardware.cimier_mechanism_sim import CimierMechanismSim

DEFAULT_PORT = 8001

RELAY_24V = 0
RELAY_MOT = 1
RELAY_UPDN = 2

INPUT_BAS = 0
INPUT_HAUT = 1


class _SilentHandler(BaseHTTPRequestHandler):
    server_version = "CimierSimulator/1.0"

    def log_message(self, fmt, *args):
        return

    def _send_json(self, status, payload):
        body = json.dumps(payload).encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(body)))
        self.send_header("Connection", "close")
        self.end_headers()
        self.wfile.write(body)

    def do_GET(self):  # noqa: N802
        sim = self.server.simulator
        parsed = urlparse(self.path)
        qs = parse_qs(parsed.query)

        if parsed.path == "/rpc/Input.GetStatus":
            try:
                input_id = int(qs.get("id", ["-1"])[0])
            except (TypeError, ValueError):
                input_id = -1
            state = sim.input_state(input_id)
            if state is None:
                self._send_json(404, {"error": "unknown_input", "id": input_id})
                return
            self._send_json(200, {"id": input_id, "state": state})
            return

        if parsed.path.startswith("/relay/"):
            try:
                relay_id = int(parsed.path.rsplit("/", 1)[1])
            except (TypeError, ValueError):
                self._send_json(404, {"error": "bad_relay"})
                return
            turn = qs.get("turn", [""])[0]
            ison = sim.set_relay(relay_id, turn)
            if ison is None:
                self._send_json(404, {"error": "unknown_relay", "id": relay_id})
                return
            self._send_json(200, {"ison": ison})
            return

        self._send_json(404, {"error": "not_found", "path": self.path})

    def do_POST(self):  # noqa: N802
        self._send_json(404, {"error": "not_found", "method": "POST", "path": self.path})


class _SimulatorHTTPServer(HTTPServer):
    allow_reuse_address = True

    def __init__(self, server_address, handler, simulator):
        super().__init__(server_address, handler)
        self.simulator = simulator


class CimierSimulator:
    """Émulateur Shelly unifié : relais (24V/MOT/UPDN) + Uni+, mécanisme animé."""

    def __init__(
        self,
        port=DEFAULT_PORT,
        boot_delay_s=0.0,
        initial_state="closed",
        full_travel_s=60.0,
        host="127.0.0.1",
    ):
        self._host = host
        self._port = port
        self._boot_delay_s = float(boot_delay_s)
        self._initial_state = initial_state
        self._full_travel_s = float(full_travel_s)

        self._mechanism = None
        self._server = None
        self._server_thread = None
        self._boot_thread = None
        self._animator_thread = None
        self._ready_event = threading.Event()
        self._stop_event = threading.Event()
        self._lock = threading.Lock()

        self._power_on = False  # relais 24V
        self._last_advance_ts = None

    # --- lifecycle -----------------------------------------------------
    def start(self):
        with self._lock:
            if self._server is not None or (
                self._boot_thread is not None and self._boot_thread.is_alive()
            ):
                raise RuntimeError("simulator already started")
            self._stop_event.clear()
            self._ready_event.clear()
            self._mechanism = CimierMechanismSim(
                initial_state=self._initial_state, full_travel_s=self._full_travel_s
            )
            self._power_on = False
            self._boot_thread = threading.Thread(
                target=self._boot_then_serve, name="cimier-sim-boot", daemon=True
            )
            self._boot_thread.start()

    def stop(self):
        self._stop_event.set()
        for attr in ("_server",):
            server = getattr(self, attr)
            if server is not None:
                try:
                    server.shutdown()
                except Exception:
                    pass
                try:
                    server.server_close()
                except Exception:
                    pass
        for attr in ("_boot_thread", "_server_thread", "_animator_thread"):
            th = getattr(self, attr)
            if th is not None:
                th.join(timeout=2.0)
        self._server = None
        self._server_thread = None
        self._boot_thread = None
        self._animator_thread = None
        self._ready_event.clear()

    def is_ready(self):
        return self._ready_event.is_set()

    def wait_ready(self, timeout=None):
        return self._ready_event.wait(timeout=timeout)

    @property
    def url(self):
        return "http://{}:{}".format(self._host, self._actual_port())

    @property
    def port(self):
        return self._actual_port()

    @property
    def mechanism(self):
        return self._mechanism

    def _actual_port(self):
        if self._server is not None:
            return self._server.server_address[1]
        return self._port

    # --- API métier (appelée par le handler, thread-safe) --------------
    def input_state(self, input_id):
        """État brut d'une entrée Uni+ (None si id inconnu).

        Convention V3 : butée atteinte → contact fermé → state=False.
        """
        with self._lock:
            self._advance_locked()
            if input_id == INPUT_HAUT:
                return not self._mechanism.open_switch
            if input_id == INPUT_BAS:
                return not self._mechanism.closed_switch
            return None

    def set_relay(self, relay_id, turn):
        """Pilote un relais simulé. Retourne l'état (ison) ou None si inconnu."""
        on = turn == "on"
        with self._lock:
            self._advance_locked()
            if relay_id == RELAY_24V:
                self._power_on = on
                return on
            if relay_id == RELAY_MOT:
                self._mechanism.set_motor(on)
                return on
            if relay_id == RELAY_UPDN:
                self._mechanism.set_direction(open_direction=on)
                return on
            return None

    # --- animation -----------------------------------------------------
    def _advance_locked(self):
        """Avance le mécanisme du temps écoulé (à appeler sous self._lock)."""
        now = time.monotonic()
        if self._last_advance_ts is None:
            self._last_advance_ts = now
            return
        elapsed = now - self._last_advance_ts
        self._last_advance_ts = now
        if self._power_on and self._mechanism.motor_on:
            self._mechanism.advance(elapsed)

    def _animate_loop(self):
        while not self._stop_event.is_set():
            with self._lock:
                self._advance_locked()
            self._stop_event.wait(timeout=0.05)

    def _boot_then_serve(self):
        if self._boot_delay_s > 0:
            self._stop_event.wait(timeout=self._boot_delay_s)
        if self._stop_event.is_set():
            return
        try:
            server = _SimulatorHTTPServer((self._host, self._port), _SilentHandler, self)
        except OSError as exc:
            print(
                "[cimier_simulator] bind {}:{} echoue: {}".format(self._host, self._port, exc),
                file=sys.stderr,
            )
            return
        self._server = server
        self._last_advance_ts = time.monotonic()
        self._server_thread = threading.Thread(
            target=server.serve_forever, name="cimier-sim-http", daemon=True
        )
        self._server_thread.start()
        self._animator_thread = threading.Thread(
            target=self._animate_loop, name="cimier-sim-anim", daemon=True
        )
        self._animator_thread.start()
        self._ready_event.set()


def _parse_args(argv):
    parser = argparse.ArgumentParser(
        description="Simulateur Shelly unifié cimier (dev/tests) : relais + Uni+.",
    )
    parser.add_argument("--port", type=int, default=DEFAULT_PORT)
    parser.add_argument("--host", default="127.0.0.1")
    parser.add_argument("--initial", choices=("closed", "open", "mid"), default="closed")
    parser.add_argument("--full-travel", type=float, default=60.0)
    return parser.parse_args(argv)


def main(argv=None):
    args = _parse_args(argv)
    sim = CimierSimulator(
        port=args.port,
        host=args.host,
        initial_state=args.initial,
        full_travel_s=args.full_travel,
    )
    print(
        "[cimier_simulator] booting on http://{}:{} (initial={}, full_travel={}s)".format(
            args.host, args.port, args.initial, args.full_travel
        ),
        file=sys.stderr,
    )
    sim.start()
    if not sim.wait_ready(timeout=5.0):
        print("[cimier_simulator] echec demarrage", file=sys.stderr)
        sim.stop()
        return 1
    print(
        "[cimier_simulator] pret. curl http://{}:{}/rpc/Input.GetStatus?id=1".format(
            args.host, args.port
        ),
        file=sys.stderr,
    )
    try:
        while True:
            time.sleep(1.0)
    except KeyboardInterrupt:
        print("[cimier_simulator] arret demande (Ctrl-C)", file=sys.stderr)
    finally:
        sim.stop()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
```

> Note : le constructeur garde la même signature publique (`port`, `boot_delay_s`,
> `initial_state`, `full_travel_s`, `host`) et les mêmes propriétés
> (`url`, `port`, `mechanism`, `wait_ready`) → `start_dev.sh` reste compatible.
> L'argument CLI `--boot-delay` est retiré (inutile sans latence boot Pico) ;
> vérifier en Step 5 que `start_dev.sh` ne le passe pas.

- [ ] **Step 4 : Lancer les tests, vérifier le succès**

Run: `uv run --extra dev pytest tests/test_cimier_simulator.py -v`
Expected: PASS (5 tests).

- [ ] **Step 5 : Vérifier la compatibilité `start_dev.sh`**

Run: `grep -n "cimier_simulator" start_dev.sh`
Inspecter la ligne de lancement. Si elle passe `--boot-delay`, retirer l'argument (le simulateur V3 ne l'accepte plus). Sinon, aucun changement.

- [ ] **Step 6 : Format + lint + commit**

```bash
uv run --extra dev ruff format core/hardware/cimier_simulator.py tests/test_cimier_simulator.py
uv run --extra dev ruff check core/hardware/cimier_simulator.py tests/test_cimier_simulator.py
git add core/hardware/cimier_simulator.py tests/test_cimier_simulator.py start_dev.sh
git commit -m "feat(cimier): simulateur Shelly unifié dev (relais 24V/MOT/UPDN + Uni+ animé)"
```

---

## Task 5 : Suppression du Pico W (firmware + tests morts)

**Files:**
- Delete: `firmware/cimier/` (dossier : `main.py`, `cimier_controller.py`, `README.md`)
- Delete: `tests/test_cimier_controller.py`

- [ ] **Step 1 : Vérifier l'absence de référence résiduelle**

Run:
```bash
grep -rn "firmware/cimier\|cimier_controller\|from cimier_controller\|import cimier_controller" --include="*.py" . | grep -v ".venv"
```
Expected: aucune ligne (le simulateur a été nettoyé en T4). Si une ligne subsiste, la corriger avant de supprimer.

- [ ] **Step 2 : Supprimer les fichiers**

```bash
git rm -r firmware/cimier
git rm tests/test_cimier_controller.py
```

- [ ] **Step 3 : Lancer la régression cimier complète**

Run:
```bash
uv run --extra dev pytest tests/test_cimier_service.py tests/test_cimier_scheduler.py \
  tests/test_cimier_simulator.py tests/test_cimier_mechanism_sim.py \
  tests/test_web_cimier_views.py tests/test_config_loader.py \
  tests/test_shelly_switch_reader.py -q
```
Expected: PASS, aucune collecte d'erreur d'import.

- [ ] **Step 4 : Commit**

```bash
git add -A
git commit -m "chore(cimier): suppression Pico W (firmware/cimier + tests contrôleur obsolètes)"
```

---

## Task 6 : Config terrain template + documentation

**Files:**
- Modify: `data/config.json` (section `cimier`)
- Modify: `CLAUDE.md` (architecture cimier)
- Add: `docs/synoptique electronique cimier V2.pdf`, `V3.pdf`, spec design

- [ ] **Step 1 : Mettre à jour `data/config.json` (template repo, `enabled=false`)**

Remplacer la section `cimier` par la forme V3 (defaults sûrs : `switch_reader.type="noop"`, `power_switch.type="noop"`, hosts moteur vides → aucun hardware sollicité par défaut). Retirer `host`, `port`, `invert_direction`. Ajouter `switch_reader`. Pré-positionner les commentaires terrain (IPs réelles documentées, mais `type` neutre tant que non déployé) :

```json
  "cimier": {
    "_comment": "Archi V3 tout-Shelly (suppression Pico W). Opt-in (enabled=false). IPs terrain : 24V=.83, Uni+=.84, MOT=.85, UPDN=.86. Conventions inversées (motor_on_relay_state, open_dir_state, switch_reader.invert) à VALIDER AU BANC.",
    "enabled": false,
    "cycle_timeout_s": 90.0,
    "post_off_quiet_s": 10.0,
    "shelly_settle_s": 2.0,
    "verbose_logging": false,
    "switch_reader": {
      "_comment": "type ∈ {shelly_uni, noop}. shelly_uni = Shelly Uni+ RPC. id=1 HAUT, id=0 BAS. invert=true : butée atteinte = input false (fermé).",
      "type": "noop",
      "host": "192.168.1.84",
      "api": "rpc",
      "open_input_id": 1,
      "closed_input_id": 0,
      "invert": true,
      "timeout_s": 3.0
    },
    "power_switch": {
      "_comment": "SHELLY-1-24V (.83) — alim module cimier, coupé hors cycle. type ∈ {shelly_gen1, shelly_gen2, noop}. Gen 1 → legacy /relay/0.",
      "type": "noop",
      "host": "192.168.1.83",
      "switch_id": 0
    },
    "weather_provider": {
      "_comment": "Capteur pluie : backlog séparé. type=noop (toujours OK).",
      "type": "noop"
    },
    "automation": {
      "_comment": "Scheduler astropy inchangé. mode ∈ {manual, semi, full}.",
      "mode": "full",
      "opening_sun_altitude_deg": -12.0,
      "closing_target_sun_altitude_deg": -6.0,
      "closing_advance_minutes": 10,
      "clock_safety_margin_minutes": 5,
      "parking_target_azimuth_deg": 45.0,
      "parking_timeout_minutes": 5,
      "deparking_nudge_deg": 1.0,
      "scheduler_interval_seconds": 60,
      "retrigger_cooldown_hours": 12
    },
    "motor_shelly": {
      "_comment": "SHELLY-1-MOT (.85) + SHELLY-1-UPDN (.86), API legacy. Conventions V3 à valider banc : moteur tourne quand relais turn=on (motor_on_relay_state=true), UP=turn=on (open_dir_state=true). host_motor/host_dir vides → NoopMotorShelly tant que non déployé.",
      "host_motor": "",
      "host_dir": "",
      "relay_motor": 0,
      "relay_dir": 0,
      "open_dir_state": true,
      "motor_on_relay_state": true,
      "api": "legacy",
      "timer_safety_sec": 90.0
    }
  }
```

- [ ] **Step 2 : Vérifier que la config se charge**

Run:
```bash
uv run --extra dev python -c "from core.config.config_loader import ConfigLoader; c=ConfigLoader().load(); print(c.cimier.switch_reader.type, c.cimier.power_switch.host, c.cimier.motor_shelly.api)"
```
Expected: `noop 192.168.1.83 legacy`.

- [ ] **Step 3 : Mettre à jour `CLAUDE.md`**

Dans `CLAUDE.md`, section cimier (architecture / debugging) : remplacer les mentions Pico W par l'archi V3. Points à corriger :
- Apercu / architecture : indiquer que le cimier est piloté tout-Shelly (24V/MOT/UPDN/Uni+), Contrôleur autonome + DM556T, **plus de Pico W ni de firmware/cimier**.
- Ajouter un mini tableau du plan d'adressage IP (24V .83, Uni+ .84, MOT .85, UPDN .86) et la cinématique (cf. spec).
- Section « Indicateurs cimier vides en dev » : la référence au simulateur Pico W devient « simulateur Shelly unifié `core.hardware.cimier_simulator` (relais + Uni+) ».
- Retirer/adapter les renvois à `firmware/cimier/README.md` et à la cascade Pico W.
- Ajouter une entrée changelog (sans bump de version dans `pyproject.toml`) décrivant le pivot V3.

- [ ] **Step 4 : Versionner les documents source + spec**

```bash
git add "docs/synoptique electronique cimier V2.pdf" "docs/synoptique electronique cimier V3.pdf" \
  docs/superpowers/specs/2026-06-08-cimier-tout-shelly-v3-design.md \
  docs/superpowers/plans/2026-06-08-cimier-tout-shelly-v3.md
```

- [ ] **Step 5 : Commit final (config + docs)**

```bash
git add data/config.json CLAUDE.md
git commit -m "docs(cimier): config template V3 tout-Shelly + doc architecture (suppression Pico W)"
```

- [ ] **Step 6 : Suite de tests complète (non-régression globale)**

Run: `uv run --extra dev pytest -q`
Expected: PASS (aucune régression hors périmètre). Investiguer tout échec lié à un import `firmware.cimier` ou `HttpClient` résiduel.

---

## Validation finale (critères de succès de la spec)

- [ ] `grep -rn "cimier_controller\|firmware/cimier\|HttpClient" --include="*.py" . | grep -v .venv` → vide.
- [ ] `ShellySwitchReader` couvert par `tests/test_shelly_switch_reader.py` (inversion + ids configurables).
- [ ] Cycle open/close jouable en dev :
  ```bash
  CIMIER_DEV_MODE=1 ./start_dev.sh restart && ./start_dev.sh status
  # puis dashboard : Ouvrir cimier → la timeline doit montrer power_on→...→switch_transition→power_off
  cat /dev/shm/cimier_status.json
  ```
- [ ] Suite cimier verte (T5 Step 3).
- [ ] Conventions terrain (`invert`, `motor_on_relay_state`, `open_dir_state`) restées configurables et documentées (banc Serge).
- [ ] Aucun bump de `pyproject.toml`.

---

## Notes de déploiement terrain (post-merge, hors plan de code)

À transmettre à Serge (via skill `/diag-terrain` si besoin) :
1. Renseigner dans `data/config.json` du Pi : `switch_reader.type="shelly_uni"`, `power_switch.type="shelly_gen1"`, `motor_shelly.host_motor/host_dir` (.85/.86), `enabled=true`.
2. **Valider au banc** les 3 conventions inversées : déclencher chaque microswitch et lire `cat /dev/shm/cimier_status.json` (`open_switch`/`closed_switch`) ; ajuster `switch_reader.invert` si inversé. Vérifier sens (UP/DN) et marche/arrêt moteur ; ajuster `open_dir_state` / `motor_on_relay_state`.
3. Vérifier la coupure directe hardware des microswitches sur le Contrôleur (backstop indépendant du software).
```

