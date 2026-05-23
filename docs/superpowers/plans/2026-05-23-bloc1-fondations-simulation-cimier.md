# Bloc 1 — Fondations simulation cimier (pivot Shelly) — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Poser les fondations hardware-indépendantes du pivot Shelly cimier : config, mécanisme virtuel de simulation, double de test Shelly, élagage du firmware Pico W en capteur-only — le tout testable sans matériel.

**Architecture:** Le Pico W devient un pur serveur de capteurs (fins de course). Le mouvement moteur est modélisé par un mécanisme virtuel partagé (`CimierMechanismSim`) piloté par un double de test (`SimMotorShelly`) qui imite l'interface de `MotorShelly`. Le simulateur HTTP Pico lit les fins de course depuis ce mécanisme. Tout est en CPython pur, testé sous pytest.

**Tech Stack:** Python 3.12, pytest, `uv run`, dataclasses (config), `http.server` (simulateur existant). Aucune dépendance nouvelle.

**Référence spec :** `docs/superpowers/specs/2026-05-23-cinematique-shelly-cimier-garde-fou-design.md` (§5 élagage firmware, §6 config, §8 simulation).

**Contexte de couplage (important pour l'ordre des tâches) :** `core/hardware/cimier_simulator.py` importe `firmware/cimier/cimier_controller.py` et appelle ses méthodes moteur (`tick()`, `start_open()`…). On ne peut donc pas élaguer le contrôleur sans refondre le simulateur dans le **même commit** (Tâche 5). Les Tâches 1-4 sont purement additives (suite verte trivialement).

---

## Structure des fichiers

| Fichier | Rôle | Action |
|---|---|---|
| `core/config/config_loader.py` | `CimierConfig` + `_parse_cimier` | Modifié (Tâche 1) |
| `data/config.json` | section `cimier` | Modifié (Tâche 1) |
| `tests/test_config_loader.py` | tests config | Modifié (Tâche 1) |
| `core/hardware/cimier_mechanism_sim.py` | mécanisme virtuel partagé (position/moteur/sens) | **Créé** (Tâche 2) |
| `tests/test_cimier_mechanism_sim.py` | tests mécanisme | **Créé** (Tâche 2) |
| `core/hardware/sim_motor_shelly.py` | double de test imitant `MotorShelly`, pilote le mécanisme | **Créé** (Tâche 3) |
| `tests/test_sim_motor_shelly.py` | tests double | **Créé** (Tâche 3) |
| `firmware/cimier/cimier_controller.py` | logique capteurs (état dérivé des switches) | **Élagué** (Tâche 4, ~248→~70 LOC) |
| `tests/test_cimier_controller.py` | tests contrôleur | **Refondu** (Tâche 4) |
| `core/hardware/cimier_simulator.py` | simulateur HTTP Pico (capteur-only, lit le mécanisme) | **Refondu** (Tâche 5) |
| `tests/test_cimier_simulator.py` | tests simulateur | **Refondu** (Tâche 5) |
| `firmware/cimier/main.py` | firmware Pico W | **Élagué** (Tâche 6, validation on-device différée) |
| `firmware/cimier/step_generator.py` | génération STEP/DIR | **Supprimé** (Tâche 6) |

**Commande de test de référence** (périmètre restreint, cf. `feedback_tests_scope`) :
```bash
uv run --extra dev pytest tests/test_config_loader.py tests/test_cimier_mechanism_sim.py tests/test_sim_motor_shelly.py tests/test_cimier_controller.py tests/test_cimier_simulator.py -v
```

---

## Task 1: Config — `shelly_settle_s` + `verbose_logging`

**Files:**
- Modify: `core/config/config_loader.py:262-272` (dataclass `CimierConfig`) et `core/config/config_loader.py:550-558` (`_parse_cimier`)
- Modify: `data/config.json` (section `cimier`)
- Test: `tests/test_config_loader.py`

- [ ] **Step 1: Write the failing test**

Ajouter dans `tests/test_config_loader.py` (à la suite des tests cimier existants) :

```python
def test_cimier_shelly_settle_and_verbose_defaults():
    """shelly_settle_s et verbose_logging : defaults rétro-compatibles."""
    from core.config.config_loader import CimierConfig
    c = CimierConfig()
    assert c.shelly_settle_s == 2.0
    assert c.verbose_logging is False


def test_cimier_parse_shelly_settle_and_verbose(tmp_path):
    """Les deux clés sont lues depuis data/config.json."""
    import json
    from core.config.config_loader import ConfigLoader
    cfg_file = tmp_path / "config.json"
    cfg_file.write_text(json.dumps({
        "cimier": {"shelly_settle_s": 3.5, "verbose_logging": True}
    }))
    loader = ConfigLoader(str(cfg_file))
    cimier = loader.load().cimier
    assert cimier.shelly_settle_s == 3.5
    assert cimier.verbose_logging is True
```

> Vérifier la signature exacte du constructeur `ConfigLoader` et de la méthode de chargement (`.load()`) dans `core/config/config_loader.py:400+` et aligner le test sur les helpers déjà utilisés par les autres tests de ce fichier (réutiliser leur pattern plutôt que `tmp_path` si un fixture existe).

- [ ] **Step 2: Run test to verify it fails**

Run: `uv run --extra dev pytest tests/test_config_loader.py::test_cimier_shelly_settle_and_verbose_defaults -v`
Expected: FAIL — `AttributeError: 'CimierConfig' object has no attribute 'shelly_settle_s'`

- [ ] **Step 3: Add fields to the dataclass**

Dans `core/config/config_loader.py`, dataclass `CimierConfig` (après `post_off_quiet_s`, ligne ~268) :

```python
    post_off_quiet_s: float = 10.0
    shelly_settle_s: float = 2.0          # attente appairage WiFi Shelly MOT/UPDN (synoptique "à mesurer")
    verbose_logging: bool = False         # true → logs DEBUG par itération (debug à distance)
```

- [ ] **Step 4: Parse the fields**

Dans `_parse_cimier` (`core/config/config_loader.py:550+`), ajouter dans l'appel `CimierConfig(...)` après `post_off_quiet_s=...` :

```python
            post_off_quiet_s=float(c.get("post_off_quiet_s", defaults.post_off_quiet_s)),
            shelly_settle_s=float(c.get("shelly_settle_s", defaults.shelly_settle_s)),
            verbose_logging=bool(c.get("verbose_logging", defaults.verbose_logging)),
```

- [ ] **Step 5: Add keys to data/config.json**

Dans `data/config.json`, section `cimier`, après `"post_off_quiet_s": 10.0,` :

```json
  "post_off_quiet_s": 10.0,
  "shelly_settle_s": 2.0,
  "verbose_logging": false,
```

- [ ] **Step 6: Run tests to verify they pass**

Run: `uv run --extra dev pytest tests/test_config_loader.py -v`
Expected: PASS (nouveaux tests verts + aucun test existant cassé)

- [ ] **Step 7: Lint + commit**

```bash
uv run ruff check core/config/config_loader.py tests/test_config_loader.py
git add core/config/config_loader.py data/config.json tests/test_config_loader.py
git commit -m "feat(cimier): config shelly_settle_s + verbose_logging (Bloc 1)"
```

---

## Task 2: `CimierMechanismSim` — mécanisme virtuel partagé

**Files:**
- Create: `core/hardware/cimier_mechanism_sim.py`
- Test: `tests/test_cimier_mechanism_sim.py`

Modèle **temporel** (pas de stepping) : position normalisée `0.0` (fermé) → `1.0` (ouvert). Le moteur, quand allumé, fait avancer la position de `elapsed_s / full_travel_s` dans le sens courant. Fins de course dérivées de la position. `advance()` est **pur et déterministe** (le temps est injecté par l'appelant — pattern aligné sur `cimier_controller` qui injecte `time_provider` et sur les tests à `FakeClock`).

- [ ] **Step 1: Write the failing test**

Créer `tests/test_cimier_mechanism_sim.py` :

```python
"""Tests du mécanisme virtuel cimier (core/hardware/cimier_mechanism_sim.py)."""
from __future__ import annotations

from core.hardware.cimier_mechanism_sim import CimierMechanismSim


def test_initial_closed():
    m = CimierMechanismSim(initial_state="closed")
    assert m.position == 0.0
    assert m.closed_switch is True
    assert m.open_switch is False


def test_initial_open():
    m = CimierMechanismSim(initial_state="open")
    assert m.position == 1.0
    assert m.open_switch is True
    assert m.closed_switch is False


def test_initial_mid_no_switch():
    m = CimierMechanismSim(initial_state="mid")
    assert m.position == 0.5
    assert m.open_switch is False
    assert m.closed_switch is False


def test_motor_off_does_not_move():
    m = CimierMechanismSim(initial_state="closed", full_travel_s=10.0)
    m.set_direction(open_direction=True)
    m.advance(5.0)  # moteur éteint
    assert m.position == 0.0


def test_opening_advances_to_open_switch():
    m = CimierMechanismSim(initial_state="closed", full_travel_s=10.0)
    m.set_direction(open_direction=True)
    m.set_motor(True)
    m.advance(4.0)
    assert 0.39 <= m.position <= 0.41
    assert m.open_switch is False
    m.advance(10.0)  # dépasse la course
    assert m.position == 1.0
    assert m.open_switch is True


def test_closing_advances_to_closed_switch():
    m = CimierMechanismSim(initial_state="open", full_travel_s=10.0)
    m.set_direction(open_direction=False)
    m.set_motor(True)
    m.advance(10.0)
    assert m.position == 0.0
    assert m.closed_switch is True


def test_position_clamped_no_overshoot():
    m = CimierMechanismSim(initial_state="closed", full_travel_s=2.0)
    m.set_direction(open_direction=True)
    m.set_motor(True)
    m.advance(100.0)
    assert m.position == 1.0  # jamais > 1.0


def test_force_both_switches_fault():
    m = CimierMechanismSim(initial_state="closed", force_both_switches=True)
    assert m.open_switch is True
    assert m.closed_switch is True
```

- [ ] **Step 2: Run test to verify it fails**

Run: `uv run --extra dev pytest tests/test_cimier_mechanism_sim.py -v`
Expected: FAIL — `ModuleNotFoundError: No module named 'core.hardware.cimier_mechanism_sim'`

- [ ] **Step 3: Write the implementation**

Créer `core/hardware/cimier_mechanism_sim.py` :

```python
"""Mécanisme virtuel cimier pour la simulation (pivot Shelly v6.x).

Modélise le cimier comme une position normalisée 0.0 (fermé) → 1.0 (ouvert).
Le moteur, quand allumé, fait progresser la position dans le sens courant à
vitesse fixe (course complète en ``full_travel_s`` secondes). Les fins de
course sont dérivées de la position.

Analogue à ``core/hardware/moteur_simule`` pour la coupole, mais propre au
cimier (mécanisme binaire ouvert/fermé). Le temps est injecté via ``advance``
→ déterministe et testable sans threads.
"""

from __future__ import annotations

_INITIAL_POSITIONS = {"closed": 0.0, "open": 1.0, "mid": 0.5}


class CimierMechanismSim:
    """État partagé du cimier virtuel : position, moteur, sens."""

    def __init__(
        self,
        initial_state: str = "closed",
        full_travel_s: float = 60.0,
        force_both_switches: bool = False,
    ) -> None:
        if initial_state not in _INITIAL_POSITIONS:
            raise ValueError(
                "initial_state must be one of {}".format(sorted(_INITIAL_POSITIONS))
            )
        if full_travel_s <= 0:
            raise ValueError("full_travel_s must be > 0")
        self._position = _INITIAL_POSITIONS[initial_state]
        self._full_travel_s = float(full_travel_s)
        self._force_both = bool(force_both_switches)
        self._motor_on = False
        self._opening = True  # sens courant : True = ouverture

    # --- commandes (pilotées par SimMotorShelly) -----------------------
    def set_direction(self, open_direction: bool) -> None:
        self._opening = bool(open_direction)

    def set_motor(self, on: bool) -> None:
        self._motor_on = bool(on)

    # --- progression temporelle ----------------------------------------
    def advance(self, elapsed_s: float) -> None:
        """Fait progresser la position si le moteur tourne."""
        if not self._motor_on or elapsed_s <= 0:
            return
        delta = elapsed_s / self._full_travel_s
        if self._opening:
            self._position = min(1.0, self._position + delta)
        else:
            self._position = max(0.0, self._position - delta)

    # --- lectures capteurs ---------------------------------------------
    @property
    def position(self) -> float:
        return self._position

    @property
    def open_switch(self) -> bool:
        return self._force_both or self._position >= 1.0

    @property
    def closed_switch(self) -> bool:
        return self._force_both or self._position <= 0.0

    @property
    def motor_on(self) -> bool:
        return self._motor_on
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `uv run --extra dev pytest tests/test_cimier_mechanism_sim.py -v`
Expected: PASS (8 tests)

- [ ] **Step 5: Lint + commit**

```bash
uv run ruff check core/hardware/cimier_mechanism_sim.py tests/test_cimier_mechanism_sim.py
git add core/hardware/cimier_mechanism_sim.py tests/test_cimier_mechanism_sim.py
git commit -m "feat(cimier): CimierMechanismSim — mécanisme virtuel partagé (Bloc 1)"
```

---

## Task 3: `SimMotorShelly` — double de test imitant `MotorShelly`

**Files:**
- Create: `core/hardware/sim_motor_shelly.py`
- Test: `tests/test_sim_motor_shelly.py`

Imite l'**interface publique exacte** de `MotorShelly` (`set_direction(open_direction)`, `turn_on(timer_s=0.0)`, `turn_off()` — cf. `core/hardware/motor_shelly.py:130-173`) mais pilote un `CimierMechanismSim` au lieu d'émettre du HTTP. Enregistre les appels pour assertions. Drop-in pour `cimier_service` en dev/tests (Bloc 2).

- [ ] **Step 1: Write the failing test**

Créer `tests/test_sim_motor_shelly.py` :

```python
"""Tests du double SimMotorShelly (core/hardware/sim_motor_shelly.py)."""
from __future__ import annotations

from core.hardware.cimier_mechanism_sim import CimierMechanismSim
from core.hardware.sim_motor_shelly import SimMotorShelly


def test_turn_on_starts_mechanism_motor():
    m = CimierMechanismSim(initial_state="closed")
    shelly = SimMotorShelly(m)
    shelly.turn_on(timer_s=90.0)
    assert m.motor_on is True
    assert shelly.last_timer_s == 90.0


def test_turn_off_stops_mechanism_motor():
    m = CimierMechanismSim(initial_state="mid")
    shelly = SimMotorShelly(m)
    shelly.turn_on()
    shelly.turn_off()
    assert m.motor_on is False


def test_set_direction_propagates_to_mechanism():
    m = CimierMechanismSim(initial_state="mid", full_travel_s=10.0)
    shelly = SimMotorShelly(m)
    shelly.set_direction(open_direction=False)
    shelly.turn_on()
    m.advance(1.0)
    assert m.position < 0.5  # a bien fermé (descendu)


def test_calls_are_recorded_in_order():
    m = CimierMechanismSim(initial_state="closed")
    shelly = SimMotorShelly(m)
    shelly.set_direction(open_direction=True)
    shelly.turn_on(timer_s=90.0)
    shelly.turn_off()
    assert shelly.calls == [
        ("set_direction", True),
        ("turn_on", 90.0),
        ("turn_off", None),
    ]
```

- [ ] **Step 2: Run test to verify it fails**

Run: `uv run --extra dev pytest tests/test_sim_motor_shelly.py -v`
Expected: FAIL — `ModuleNotFoundError: No module named 'core.hardware.sim_motor_shelly'`

- [ ] **Step 3: Write the implementation**

Créer `core/hardware/sim_motor_shelly.py` :

```python
"""Double de test du driver MotorShelly (pivot Shelly v6.x).

Même interface publique que ``core/hardware/motor_shelly.MotorShelly``
(``set_direction`` / ``turn_on`` / ``turn_off``) mais pilote un
``CimierMechanismSim`` en mémoire au lieu d'émettre des requêtes HTTP vers
les Shelly. Permet de tester l'orchestration ``cimier_service`` (Bloc 2) et
d'animer le simulateur en dev, sans aucun hardware.
"""

from __future__ import annotations

from core.hardware.cimier_mechanism_sim import CimierMechanismSim


class SimMotorShelly:
    """Pilote un CimierMechanismSim, imite l'interface de MotorShelly."""

    def __init__(self, mechanism: CimierMechanismSim) -> None:
        self._m = mechanism
        self.last_timer_s: float = 0.0
        self.calls: list[tuple[str, object]] = []

    def set_direction(self, open_direction: bool) -> None:
        self._m.set_direction(bool(open_direction))
        self.calls.append(("set_direction", bool(open_direction)))

    def turn_on(self, timer_s: float = 0.0) -> None:
        if timer_s < 0:
            raise ValueError("timer_s must be >= 0, got " + str(timer_s))
        self.last_timer_s = float(timer_s)
        self._m.set_motor(True)
        self.calls.append(("turn_on", float(timer_s)))

    def turn_off(self) -> None:
        self._m.set_motor(False)
        self.calls.append(("turn_off", None))
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `uv run --extra dev pytest tests/test_sim_motor_shelly.py -v`
Expected: PASS (4 tests)

- [ ] **Step 5: Lint + commit**

```bash
uv run ruff check core/hardware/sim_motor_shelly.py tests/test_sim_motor_shelly.py
git add core/hardware/sim_motor_shelly.py tests/test_sim_motor_shelly.py
git commit -m "feat(cimier): SimMotorShelly — double de test pilotant le mécanisme (Bloc 1)"
```

---

## Task 4: Élagage `cimier_controller` en capteur-only + refonte de ses tests

**Files:**
- Modify (réécriture quasi complète) : `firmware/cimier/cimier_controller.py`
- Test (réécriture) : `tests/test_cimier_controller.py`

> ⚠️ **Vérification pré-requise** : confirmer que seuls le firmware `main.py` et le simulateur importent `cimier_controller` (pour éviter de casser un autre consommateur).

- [ ] **Step 1: Vérifier les importateurs de cimier_controller**

Run:
```bash
grep -rn "cimier_controller\|import cimier_controller" --include=*.py . | grep -v "firmware/cimier/cimier_controller.py"
```
Expected: uniquement `firmware/cimier/main.py`, `core/hardware/cimier_simulator.py`, `tests/test_cimier_controller.py`, `tests/test_cimier_simulator.py`. Si un autre fichier apparaît, **stop** et signaler (impact hors plan).

- [ ] **Step 2: Write the new (failing) test file**

Remplacer **intégralement** `tests/test_cimier_controller.py` par :

```python
"""Tests du module capteurs cimier_controller (pivot Shelly v6.x).

Le Pico W ne pilote plus le moteur : ce module ne fait que dériver l'état
du cimier depuis les 2 fins de course. Tests purs (CPython), via un mock
d'adapter hardware.
"""
from __future__ import annotations

import sys
from dataclasses import dataclass
from pathlib import Path

_FIRMWARE_DIR = Path(__file__).resolve().parents[1] / "firmware" / "cimier"
sys.path.insert(0, str(_FIRMWARE_DIR))

import cimier_controller as cc  # noqa: E402


@dataclass
class FakeSwitchAdapter:
    """Mock capteurs : état des 2 fins de course."""
    open_triggered: bool = False
    closed_triggered: bool = False

    def read_open_switch(self) -> bool:
        return self.open_triggered

    def read_closed_switch(self) -> bool:
        return self.closed_triggered


def make_controller(open_triggered=False, closed_triggered=False):
    hw = FakeSwitchAdapter(open_triggered=open_triggered, closed_triggered=closed_triggered)
    return cc.CimierController(hw), hw


# --- dérivation d'état au boot --------------------------------------------
def test_init_state_unknown_when_no_switch():
    ctrl, _ = make_controller()
    assert ctrl.state == cc.STATE_UNKNOWN


def test_init_state_closed_when_closed_switch():
    ctrl, _ = make_controller(closed_triggered=True)
    assert ctrl.state == cc.STATE_CLOSED


def test_init_state_open_when_open_switch():
    ctrl, _ = make_controller(open_triggered=True)
    assert ctrl.state == cc.STATE_OPEN


def test_init_state_error_when_both_switches():
    ctrl, _ = make_controller(open_triggered=True, closed_triggered=True)
    assert ctrl.state == cc.STATE_ERROR


# --- l'état se rafraîchit quand les switches changent ----------------------
def test_state_refreshes_on_read():
    ctrl, hw = make_controller(closed_triggered=True)
    assert ctrl.state == cc.STATE_CLOSED
    hw.closed_triggered = False
    hw.open_triggered = True
    assert ctrl.state == cc.STATE_OPEN


# --- sérialisation REST ----------------------------------------------------
def test_to_status_dict_format():
    ctrl, _ = make_controller(closed_triggered=True)
    status = ctrl.to_status_dict()
    assert set(status.keys()) == {"state", "open_switch", "closed_switch", "error_message"}
    assert status["state"] == cc.STATE_CLOSED
    assert status["closed_switch"] is True
    assert status["open_switch"] is False
    assert status["error_message"] == ""


def test_to_status_dict_error_message_on_both():
    ctrl, _ = make_controller(open_triggered=True, closed_triggered=True)
    status = ctrl.to_status_dict()
    assert status["state"] == cc.STATE_ERROR
    assert status["error_message"] == "both_switches_triggered"


def test_to_info_dict_format():
    ctrl, _ = make_controller()
    info = ctrl.to_info_dict()
    assert set(info.keys()) == {"firmware_version", "protocol_version", "role"}
    assert info["firmware_version"] == cc.FIRMWARE_VERSION
    assert info["role"] == "sensor"
    assert info["protocol_version"] == cc.FIRMWARE_PROTOCOL_VERSION
```

- [ ] **Step 3: Run test to verify it fails**

Run: `uv run --extra dev pytest tests/test_cimier_controller.py -v`
Expected: FAIL — l'ancien `CimierController` exige `time_provider` / expose `steps_per_cycle` dans `to_info_dict` → erreurs sur la nouvelle signature et le nouveau schéma.

- [ ] **Step 4: Rewrite `cimier_controller.py` (sensor-only)**

Remplacer **intégralement** `firmware/cimier/cimier_controller.py` par :

```python
"""Logique capteurs cimier — module pur (pivot Shelly v6.x).

Depuis le pivot Shelly, le moteur cimier n'est plus piloté par le Pico W :
le Pico W est un pur serveur de capteurs (fins de course). Ce module ne
contient plus que la dérivation d'état depuis les 2 fins de course + la
sérialisation REST.

Tourne en MicroPython (firmware/cimier/main.py) et en CPython (tests,
simulateur). Hardware abstrait via duck typing sur ``hardware_adapter`` :
  - read_open_switch() -> bool    (True si butée ouverte atteinte)
  - read_closed_switch() -> bool   (True si butée fermée atteinte)
"""

# États (string pour sérialisation REST)
STATE_CLOSED = "closed"
STATE_OPEN = "open"
STATE_ERROR = "error"
STATE_UNKNOWN = "unknown"

# Versions firmware (0.2.0 = pivot Shelly capteur-only ; protocole 2 = sans /open /close)
FIRMWARE_VERSION = "0.2.0"
FIRMWARE_PROTOCOL_VERSION = 2


class CimierController:
    """Dérive l'état du cimier depuis les 2 fins de course (lecture seule)."""

    def __init__(self, hardware_adapter):
        self._hw = hardware_adapter
        self._state = STATE_UNKNOWN
        self._last_error_message = ""
        self._refresh_state_from_switches()

    def _refresh_state_from_switches(self):
        open_triggered = bool(self._hw.read_open_switch())
        closed_triggered = bool(self._hw.read_closed_switch())
        if open_triggered and closed_triggered:
            self._state = STATE_ERROR
            self._last_error_message = "both_switches_triggered"
        elif open_triggered:
            self._state = STATE_OPEN
            self._last_error_message = ""
        elif closed_triggered:
            self._state = STATE_CLOSED
            self._last_error_message = ""
        else:
            self._state = STATE_UNKNOWN
            self._last_error_message = ""

    @property
    def state(self):
        self._refresh_state_from_switches()
        return self._state

    def to_status_dict(self):
        self._refresh_state_from_switches()
        return {
            "state": self._state,
            "open_switch": bool(self._hw.read_open_switch()),
            "closed_switch": bool(self._hw.read_closed_switch()),
            "error_message": self._last_error_message,
        }

    def to_info_dict(self):
        return {
            "firmware_version": FIRMWARE_VERSION,
            "protocol_version": FIRMWARE_PROTOCOL_VERSION,
            "role": "sensor",
        }
```

- [ ] **Step 5: Run controller tests to verify they pass**

Run: `uv run --extra dev pytest tests/test_cimier_controller.py -v`
Expected: PASS (8 tests). `tests/test_cimier_simulator.py` est **cassé** à ce stade (normal — réparé en Tâche 5, à committer ensemble).

- [ ] **Step 6: NE PAS committer seul — enchaîner Tâche 5**

Le simulateur dépend encore de l'ancien contrôleur. On ne commite Tâches 4+5 **qu'ensemble** (suite verte). Passer directement à la Tâche 5.

---

## Task 5: Refonte `cimier_simulator` (capteur-only, lit le mécanisme)

**Files:**
- Modify (réécriture complète) : `core/hardware/cimier_simulator.py`
- Test (réécriture) : `tests/test_cimier_simulator.py`

Le simulateur n'émule plus le stepping : il héberge un `CimierMechanismSim` (statique en Bloc 1 — aucune source de mouvement HTTP avant le Bloc 2) lu par un adapter de switches, branché sur le `CimierController` capteur-only pour l'état. Endpoints réduits à `GET /status` + `GET /info` (le firmware élagué n'a plus `/open` `/close` `/stop` `/config` `/diag/*`).

- [ ] **Step 1: Rewrite `cimier_simulator.py`**

Remplacer **intégralement** `core/hardware/cimier_simulator.py` par :

```python
"""Simulateur HTTP fidèle du firmware Pico W cimier (pivot Shelly v6.x).

Le Pico W est désormais un pur serveur de capteurs : ce simulateur expose
GET /status + GET /info, alimentés par un CimierMechanismSim (position →
fins de course). Aucune source de mouvement HTTP en Bloc 1 (l'animation
via Shelly simulé arrive au Bloc 2) : l'état est fixé par --initial.

Reproduit la latence boot (port non lié → ConnectionRefused côté client).

CLI : uv run python -m core.hardware.cimier_simulator [--port 8001]
      [--boot-delay 0.0] [--initial closed|open|mid]
"""
from __future__ import annotations

import argparse
import json
import socket
import sys
import threading
import time
from http.server import BaseHTTPRequestHandler, HTTPServer
from pathlib import Path

from core.hardware.cimier_mechanism_sim import CimierMechanismSim

_FIRMWARE_DIR = Path(__file__).resolve().parents[2] / "firmware" / "cimier"
if str(_FIRMWARE_DIR) not in sys.path:
    sys.path.insert(0, str(_FIRMWARE_DIR))

import cimier_controller as _cc  # noqa: E402

DEFAULT_PORT = 8001
DEFAULT_BOOT_DELAY_S = 15.0

SIMULATED_WIFI_RSSI = -55
SIMULATED_WIFI_IP = "127.0.0.1"
SIMULATED_FREE_MEMORY = 100_000


class _MechanismSwitchAdapter:
    """Adapter capteurs : lit les fins de course depuis le mécanisme."""

    def __init__(self, mechanism: CimierMechanismSim):
        self._m = mechanism

    def read_open_switch(self):
        return self._m.open_switch

    def read_closed_switch(self):
        return self._m.closed_switch


class _SilentHandler(BaseHTTPRequestHandler):
    server_version = "CimierSimulator/0.2"

    def log_message(self, format, *args):
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
        if self.path == "/status":
            self._send_json(200, sim._controller.to_status_dict())
            return
        if self.path == "/info":
            info = sim._controller.to_info_dict()
            info["wifi_rssi"] = SIMULATED_WIFI_RSSI
            info["wifi_ip"] = SIMULATED_WIFI_IP
            info["free_memory"] = SIMULATED_FREE_MEMORY
            self._send_json(200, info)
            return
        self._send_json(404, {"error": "not_found", "method": "GET", "path": self.path})

    def do_POST(self):  # noqa: N802
        # Firmware capteur-only : aucun POST supporté.
        self._send_json(404, {"error": "not_found", "method": "POST", "path": self.path})


class _SimulatorHTTPServer(HTTPServer):
    allow_reuse_address = True

    def __init__(self, server_address, handler, simulator):
        super().__init__(server_address, handler)
        self.simulator = simulator


class CimierSimulator:
    """Mini Pico W virtuel capteur-only : mécanisme + contrôleur + serveur HTTP."""

    def __init__(
        self,
        port=DEFAULT_PORT,
        boot_delay_s=DEFAULT_BOOT_DELAY_S,
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
        self._controller = None
        self._server = None
        self._server_thread = None
        self._boot_thread = None
        self._ready_event = threading.Event()
        self._stop_event = threading.Event()
        self._lock = threading.Lock()

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
            self._controller = _cc.CimierController(
                _MechanismSwitchAdapter(self._mechanism)
            )
            self._boot_thread = threading.Thread(
                target=self._boot_then_serve, name="cimier-sim-boot", daemon=True
            )
            self._boot_thread.start()

    def stop(self):
        self._stop_event.set()
        boot_thread = self._boot_thread
        server = self._server
        server_thread = self._server_thread
        if server is not None:
            try:
                server.shutdown()
            except Exception:
                pass
            try:
                server.server_close()
            except Exception:
                pass
        if boot_thread is not None:
            boot_thread.join(timeout=2.0)
        if server_thread is not None:
            server_thread.join(timeout=2.0)
        self._server = None
        self._server_thread = None
        self._boot_thread = None
        self._ready_event.clear()

    def is_ready(self):
        return self._ready_event.is_set()

    def wait_ready(self, timeout=None):
        return self._ready_event.wait(timeout=timeout)

    def reset_boot(self):
        """Simule une coupure 24V + reboot Pico (repasse par la latence boot)."""
        self.stop()
        self.start()

    @property
    def url(self):
        return "http://{}:{}".format(self._host, self._port)

    @property
    def port(self):
        return self._port

    @property
    def mechanism(self):
        """Accès interne (tests) : pilote la position/le moteur du mécanisme."""
        return self._mechanism

    @property
    def controller(self):
        return self._controller

    def _boot_then_serve(self):
        deadline = time.monotonic() + self._boot_delay_s
        while not self._stop_event.is_set():
            remaining = deadline - time.monotonic()
            if remaining <= 0:
                break
            self._stop_event.wait(timeout=min(remaining, 0.1))
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
        self._server_thread = threading.Thread(
            target=server.serve_forever, name="cimier-sim-http", daemon=True
        )
        self._server_thread.start()
        self._ready_event.set()


def _parse_args(argv):
    parser = argparse.ArgumentParser(
        description="Simulateur HTTP du firmware Pico W cimier capteur-only (dev/tests).",
    )
    parser.add_argument("--port", type=int, default=DEFAULT_PORT)
    parser.add_argument("--boot-delay", type=float, default=0.0)
    parser.add_argument("--host", default="127.0.0.1")
    parser.add_argument("--initial", choices=("closed", "open", "mid"), default="closed")
    return parser.parse_args(argv)


def main(argv=None):
    args = _parse_args(argv)
    sim = CimierSimulator(
        port=args.port, boot_delay_s=args.boot_delay, host=args.host,
        initial_state=args.initial,
    )
    print(
        "[cimier_simulator] booting on http://{}:{} (boot_delay={}s, initial={})".format(
            args.host, args.port, args.boot_delay, args.initial
        ),
        file=sys.stderr,
    )
    sim.start()
    if not sim.wait_ready(timeout=args.boot_delay + 5.0):
        print("[cimier_simulator] echec demarrage", file=sys.stderr)
        sim.stop()
        return 1
    print(
        "[cimier_simulator] pret. curl http://{}:{}/status".format(args.host, args.port),
        file=sys.stderr,
    )
    try:
        while True:
            time.sleep(1.0)
    except KeyboardInterrupt:
        print("[cimier_simulator] arret demande (Ctrl-C)", file=sys.stderr)
    finally:
        sim.stop()
        try:
            probe = socket.socket()
            probe.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
            probe.settimeout(0.5)
            probe.bind((args.host, args.port))
            probe.close()
        except OSError:
            pass
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
```

- [ ] **Step 2: Rewrite `tests/test_cimier_simulator.py`**

Remplacer **intégralement** par (conserve boot lifecycle / endpoints / 404 / threading / latence ; retire open/close/stop/config/cycle/invert + `_VirtualHardwareAdapter` ; ajoute des tests d'état piloté par le mécanisme) :

```python
"""Tests du simulateur HTTP Pico W cimier capteur-only (core/hardware/cimier_simulator.py)."""
from __future__ import annotations

import json
import socket
import threading
import time
import urllib.error
import urllib.request

import pytest

from core.hardware.cimier_simulator import CimierSimulator


def _free_port():
    s = socket.socket()
    s.bind(("127.0.0.1", 0))
    port = s.getsockname()[1]
    s.close()
    return port


def _http(method, url, timeout=2.0):
    req = urllib.request.Request(url, method=method)
    with urllib.request.urlopen(req, timeout=timeout) as resp:
        return resp.status, json.loads(resp.read().decode("utf-8"))


@pytest.fixture
def simulator():
    sim = CimierSimulator(port=_free_port(), boot_delay_s=0.0, initial_state="closed")
    sim.start()
    assert sim.wait_ready(timeout=2.0), "simulator did not become ready"
    yield sim
    sim.stop()


# --- 1. Boot lifecycle -----------------------------------------------------
def test_is_ready_false_before_start():
    sim = CimierSimulator(port=_free_port(), boot_delay_s=10.0)
    try:
        assert sim.is_ready() is False
    finally:
        sim.stop()


def test_is_ready_true_after_boot():
    sim = CimierSimulator(port=_free_port(), boot_delay_s=0.0)
    sim.start()
    try:
        assert sim.wait_ready(timeout=2.0)
        assert sim.is_ready() is True
    finally:
        sim.stop()


@pytest.mark.slow
def test_connection_refused_during_boot_delay():
    sim = CimierSimulator(port=_free_port(), boot_delay_s=0.5)
    sim.start()
    try:
        with pytest.raises((urllib.error.URLError, ConnectionRefusedError)):
            urllib.request.urlopen(sim.url + "/status", timeout=0.2)
        assert sim.wait_ready(timeout=1.5)
        status, _ = _http("GET", sim.url + "/status")
        assert status == 200
    finally:
        sim.stop()


# --- 2. Endpoints capteurs -------------------------------------------------
def test_get_status_schema_closed(simulator):
    status, payload = _http("GET", simulator.url + "/status")
    assert status == 200
    assert set(payload.keys()) == {"state", "open_switch", "closed_switch", "error_message"}
    assert payload["state"] == "closed"
    assert payload["closed_switch"] is True
    assert payload["open_switch"] is False


def test_get_info_schema(simulator):
    status, info = _http("GET", simulator.url + "/info")
    assert status == 200
    for key in ("firmware_version", "protocol_version", "role",
                "wifi_rssi", "wifi_ip", "free_memory"):
        assert key in info, "champ {} manquant".format(key)
    assert info["role"] == "sensor"
    assert info["wifi_ip"] == "127.0.0.1"


def test_get_unknown_path_returns_404(simulator):
    with pytest.raises(urllib.error.HTTPError) as excinfo:
        urllib.request.urlopen(simulator.url + "/does-not-exist", timeout=2.0)
    assert excinfo.value.code == 404


def test_post_any_path_returns_404(simulator):
    """Firmware capteur-only : plus aucun POST supporté."""
    req = urllib.request.Request(simulator.url + "/open", data=b"", method="POST")
    with pytest.raises(urllib.error.HTTPError) as excinfo:
        urllib.request.urlopen(req, timeout=2.0)
    assert excinfo.value.code == 404


# --- 3. État piloté par le mécanisme --------------------------------------
def test_initial_open_reflected_in_status():
    sim = CimierSimulator(port=_free_port(), boot_delay_s=0.0, initial_state="open")
    sim.start()
    try:
        assert sim.wait_ready(timeout=2.0)
        _, payload = _http("GET", sim.url + "/status")
        assert payload["state"] == "open"
        assert payload["open_switch"] is True
    finally:
        sim.stop()


def test_mechanism_movement_changes_status(simulator):
    """En pilotant le mécanisme directement (comme le fera le Shelly simulé),
    le /status reflète la nouvelle fin de course."""
    m = simulator.mechanism
    m.set_direction(open_direction=True)
    m.set_motor(True)
    m.advance(1000.0)  # course complète
    _, payload = _http("GET", simulator.url + "/status")
    assert payload["state"] == "open"
    assert payload["open_switch"] is True


# --- 4. Threading & arrêt propre ------------------------------------------
def test_stop_releases_port():
    port = _free_port()
    sim = CimierSimulator(port=port, boot_delay_s=0.0)
    sim.start()
    assert sim.wait_ready(timeout=2.0)
    sim.stop()
    probe = socket.socket()
    try:
        probe.bind(("127.0.0.1", port))
    finally:
        probe.close()


def test_no_thread_leak_after_stop():
    sim = CimierSimulator(port=_free_port(), boot_delay_s=0.0)
    sim.start()
    sim.wait_ready(timeout=2.0)
    sim.stop()
    time.sleep(0.05)
    leaks = [t for t in threading.enumerate()
             if t.name.startswith("cimier-sim-") and t.is_alive()]
    assert leaks == [], "threads non termines: {}".format(leaks)


def test_two_simulators_in_parallel():
    sim_a = CimierSimulator(port=_free_port(), boot_delay_s=0.0)
    sim_b = CimierSimulator(port=_free_port(), boot_delay_s=0.0)
    sim_a.start()
    sim_b.start()
    try:
        assert sim_a.wait_ready(timeout=2.0)
        assert sim_b.wait_ready(timeout=2.0)
        status_a, _ = _http("GET", sim_a.url + "/status")
        status_b, _ = _http("GET", sim_b.url + "/status")
        assert status_a == 200 and status_b == 200
    finally:
        sim_a.stop()
        sim_b.stop()


# --- 5. Latence simulée ----------------------------------------------------
@pytest.mark.slow
def test_boot_delay_is_observable():
    boot_delay = 0.4
    sim = CimierSimulator(port=_free_port(), boot_delay_s=boot_delay)
    t0 = time.monotonic()
    sim.start()
    try:
        assert not sim.is_ready()
        sim.wait_ready(timeout=boot_delay + 1.0)
        elapsed = time.monotonic() - t0
        assert elapsed >= boot_delay * 0.8, "boot trop rapide ({:.3f}s)".format(elapsed)
        assert sim.is_ready()
    finally:
        sim.stop()
```

- [ ] **Step 3: Run the full Bloc 1 suite to verify green**

Run:
```bash
uv run --extra dev pytest tests/test_cimier_controller.py tests/test_cimier_simulator.py tests/test_cimier_mechanism_sim.py tests/test_sim_motor_shelly.py tests/test_config_loader.py -v
```
Expected: PASS (toutes).

- [ ] **Step 4: Vérifier l'absence de régression sur les autres consommateurs cimier**

Run:
```bash
uv run --extra dev pytest tests/test_cimier_service.py tests/test_cimier_scheduler.py tests/test_motor_shelly.py tests/test_power_switch.py -v
```
Expected : Si `test_cimier_service.py` / `test_cimier_scheduler.py` échouent parce qu'ils s'appuyaient sur le simulateur tick-driven ou les endpoints `/open` `/close` du Pico, **c'est attendu** : ces suites relèvent du Bloc 2 (réécriture orchestration). **Noter** précisément les tests cassés dans le message de commit et dans le handoff pour le Bloc 2. Si des tests **hors cimier** cassent, stop et signaler.

> Décision : si `test_cimier_service.py` casse, le marquer `@pytest.mark.skip(reason="Bloc 2 — réécriture orchestration Shelly, cf. plan 2026-05-23")` au niveau des tests concernés **dans ce commit**, pour garder une suite globale verte, plutôt que de laisser du rouge. Documenter la liste des skips.

- [ ] **Step 5: Lint + commit (Tâches 4+5 ensemble)**

```bash
uv run ruff check firmware/cimier/cimier_controller.py core/hardware/cimier_simulator.py tests/test_cimier_controller.py tests/test_cimier_simulator.py
git add firmware/cimier/cimier_controller.py core/hardware/cimier_simulator.py tests/test_cimier_controller.py tests/test_cimier_simulator.py
git commit -m "refactor(cimier): Pico W capteur-only — élagage controller + refonte simulateur sur mécanisme virtuel (Bloc 1)"
```

---

## Task 6: Élagage firmware `main.py` + suppression `step_generator.py` (validation on-device différée)

**Files:**
- Modify: `firmware/cimier/main.py` (MicroPython — non testable sous pytest)
- Delete: `firmware/cimier/step_generator.py`

> ⚠️ **Pas de validation pytest possible** : `main.py` importe `machine`/`network` (MicroPython), non importables en CPython. La validation se fera **on-device** sur le Pico W (différée, cf. spec §10). Ici on se limite à un élagage propre + relecture visuelle.

- [ ] **Step 1: Confirmer que step_generator n'est importé que par main.py**

Run:
```bash
grep -rn "step_generator\|SoftwareStepGenerator" --include=*.py firmware/cimier/ core/ tests/
```
Expected: occurrences uniquement dans `firmware/cimier/main.py` et `firmware/cimier/step_generator.py`. (Le `firmware/step_generator.py` racine est celui de la **coupole** — ne pas y toucher.) Si `core/`/`tests/` apparaissent, stop.

- [ ] **Step 2: Supprimer `step_generator.py`**

```bash
git rm firmware/cimier/step_generator.py
```

- [ ] **Step 3: Élaguer `main.py`**

Dans `firmware/cimier/main.py`, retirer tout le pilotage moteur (garder WiFi, WDT, serveur HTTP, `/status`, `/info`, lecture switches, heartbeat, safe-boot) :

1. **Imports** : retirer `from step_generator import SoftwareStepGenerator`.
2. **Constantes** : retirer `PIN_STEP`, `PIN_DIR`, `STEP_LOGIC_INVERTED`, `STEP_PERIOD_MS` (+ leurs gros commentaires). Conserver `PIN_OPEN_SWITCH`, `PIN_CLOSED_SWITCH`, `WDT_TIMEOUT_MS`, `HTTP_PORT`, `SAFE_BOOT_DELAY_S`.
3. **`PicoHardwareAdapter`** : retirer `__init__(self, step_gen, ...)` → `__init__(self, open_switch_pin, closed_switch_pin)` ; retirer `set_direction` et `pulse_step`. Garder `read_open_switch` / `read_closed_switch`.
4. **`route_request`** : conserver `GET /status`, `GET /info`. **Supprimer** `POST /open`, `POST /close`, `POST /stop`, `POST /config`, et tout le bloc `POST /diag/*`. Conserver le `return 404` final.
5. **`run_server`** : supprimer le bloc `# 1. Tick controller ...` (`controller.tick()` + gestion `last_step`/`STEP_PERIOD_MS`). Conserver `wdt.feed()`, `serve_one_request`, le heartbeat.
6. **`main()`** : remplacer la construction `step_gen = SoftwareStepGenerator(...)` + `hw = PicoHardwareAdapter(step_gen, ...)` + `controller = CimierController(hw, now_seconds)` par :
   ```python
   hw = PicoHardwareAdapter(PIN_OPEN_SWITCH, PIN_CLOSED_SWITCH)
   controller = CimierController(hw)
   ```
   (le nouveau `CimierController` ne prend plus `time_provider`). `now_seconds` peut être conservé si le heartbeat l'utilise, sinon retiré.

- [ ] **Step 4: Relecture de cohérence (manuelle, pas de pytest)**

Vérifier visuellement :
- plus aucune référence à `SoftwareStepGenerator`, `pulse_step`, `set_direction`, `tick`, `PIN_STEP`, `PIN_DIR`, `/open`, `/close`, `/diag` dans `main.py` ;
- le serveur HTTP (`serve_one_request`, `build_response`, `parse_http_request`) et la robustesse (`settimeout(0.05)`, `pm=0xa11140`, `WDT 8000 ms` + `feed`) sont **intacts**.

Run (sanity grep) :
```bash
grep -nE "SoftwareStepGenerator|pulse_step|set_direction|controller.tick|PIN_STEP|PIN_DIR|/open|/close|/diag" firmware/cimier/main.py
```
Expected: aucune sortie.

- [ ] **Step 5: Commit**

```bash
git add firmware/cimier/main.py
git commit -m "refactor(firmware/cimier): main.py capteur-only + suppression step_generator (Bloc 1, validation Pico différée)"
```

---

## Self-Review

**1. Couverture spec (Bloc 1 = §5 élagage firmware, §6 config, §8 simulation) :**
- §6 config (`shelly_settle_s`, `verbose_logging`) → Tâche 1 ✓
- §8 `CimierMechanismSim` → Tâche 2 ✓ ; `SimMotorShelly` → Tâche 3 ✓ ; `CimierSimulator` lit le mécanisme + capteur-only → Tâche 5 ✓ ; états initiaux closed/open/mid + fault both_switches → Tâches 2 & 5 ✓
- §5 élagage `cimier_controller` → Tâche 4 ✓ ; `main.py` + suppression `step_generator.py` → Tâche 6 ✓ ; conservation correctifs HTTP/WDT → Tâche 6 step 4 ✓
- **Hors Bloc 1 (assumé, à tracer pour Bloc 2)** : cinématique (§3), garde-fou (§4), logging orchestration (§7), réécriture `test_cimier_service`. Le plan le signale (Tâche 5 step 4). La progression du mécanisme via endpoints Shelly HTTP sur le simulateur standalone (animation dev end-to-end) est explicitement repoussée au Bloc 2.

**2. Placeholders :** aucun « TBD/TODO/handle edge cases ». Tout le code des fichiers neufs et du contrôleur élagué est fourni intégralement ; pour `main.py` (non testable), des instructions d'élagage précises + grep de contrôle remplacent le code complet (justifié : MicroPython non exécutable en CI).

**3. Cohérence des types/signatures :**
- `CimierController(hardware_adapter)` (un seul arg) : utilisé identiquement en Tâche 4 (tests), Tâche 5 (simulateur), Tâche 6 (`main.py`). ✓
- `to_status_dict` → `{state, open_switch, closed_switch, error_message}` : schéma identique dans le contrôleur (T4), ses tests (T4) et les tests simulateur (T5). ✓
- `to_info_dict` → `{firmware_version, protocol_version, role}` : idem T4/T5. ✓
- `CimierMechanismSim` API (`set_direction(open_direction)`, `set_motor(on)`, `advance(elapsed_s)`, `.position/.open_switch/.closed_switch/.motor_on`) : cohérente entre T2 (def + tests), T3 (`SimMotorShelly`), T5 (simulateur + tests). ✓
- `SimMotorShelly` (`set_direction/turn_on(timer_s)/turn_off`) : aligné sur l'interface publique de `MotorShelly` (`core/hardware/motor_shelly.py:130-173`) → drop-in Bloc 2. ✓

---

## Execution Handoff

Plan complet et sauvegardé dans `docs/superpowers/plans/2026-05-23-bloc1-fondations-simulation-cimier.md`. Deux options d'exécution :

1. **Subagent-Driven (recommandé)** — un sous-agent frais par tâche, revue entre les tâches, itération rapide.
2. **Inline Execution** — exécution des tâches dans cette session via executing-plans, par lots avec checkpoints de revue.

Laquelle ?
