# Script de base cimier V3 — séquencement manuel — Plan d'implémentation

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Créer un script Python standalone (`scripts/diagnostics/cimier_manual.py`) qui séquence les commandes HTTP brutes des 4 Shelly du cimier V3, encodant la vérité du synoptique sans abstraction héritée, pour validation au banc par Serge.

**Architecture:** Fichier unique, stdlib `urllib` uniquement (lançable en `python3` pur hors env uv). Bloc CONFIG en tête (hosts + conventions du synoptique), fonctions pures (construction d'URL, mapping sens/moteur, parsing butée) testables, helper HTTP transparent qui imprime chaque URL, primitives CLI (`power`/`dir`/`motor`/`read`) + composites (`open`/`close`/`stop`). Conventions surchargeables par flags CLI pour itérer au banc.

**Tech Stack:** Python 3, stdlib (`urllib.request`, `json`, `argparse`, `time`), pytest + monkeypatch pour les tests de logique pure.

**Note exécution:** on est sur `main`. Créer une branche avant de commencer (`git checkout -b feat/cimier-script-manuel`). Référence : `docs/superpowers/specs/2026-06-15-cimier-script-manuel-base-design.md` et `docs/synoptique electronique cimier V3.pdf`.

---

## File Structure

- **Create** `scripts/diagnostics/cimier_manual.py` — tout le script (CONFIG, fonctions pures, HTTP, CLI).
- **Create** `tests/test_cimier_manual.py` — tests de la logique pure (URL, mapping, parsing, boucle de cycle avec HTTP mocké).

Le script est conçu pour être **importable** (fonctions pures + `_call` monkeypatchable) tout en restant exécutable en CLI via `if __name__ == "__main__"`.

---

### Task 1 : Squelette, CONFIG et fonctions pures

**Files:**
- Create: `scripts/diagnostics/cimier_manual.py`
- Test: `tests/test_cimier_manual.py`

- [ ] **Step 1 : Écrire les tests des fonctions pures (échec attendu)**

Créer `tests/test_cimier_manual.py` :

```python
"""Tests de la logique pure de scripts/diagnostics/cimier_manual.py.

Le script encode la vérité du synoptique V3 (docs/synoptique electronique cimier V3.pdf).
Conventions par défaut : moteur tourne quand relais MOT turn=off (logique inversée),
sens UP = relais UPDN turn=on, butée atteinte quand input state=False.
"""

from __future__ import annotations

import importlib.util
from pathlib import Path

import pytest

# Le script vit dans scripts/diagnostics/ (pas un package) → import par chemin.
_SPEC = importlib.util.spec_from_file_location(
    "cimier_manual",
    Path(__file__).resolve().parent.parent / "scripts" / "diagnostics" / "cimier_manual.py",
)
cimier_manual = importlib.util.module_from_spec(_SPEC)
_SPEC.loader.exec_module(cimier_manual)


def default_conv():
    return dict(cimier_manual.CONV)


def test_relay_url():
    assert cimier_manual.relay_url("192.168.1.85", "off") == "http://192.168.1.85/relay/0?turn=off"


def test_input_url():
    assert (
        cimier_manual.input_url("192.168.1.84", 1)
        == "http://192.168.1.84/rpc/Input.GetStatus?id=1"
    )


def test_motor_turn_inverted():
    conv = default_conv()
    # Synoptique : moteur TOURNE quand relais turn=off, ARRÊT quand turn=on.
    assert cimier_manual.motor_turn("run", conv) == "off"
    assert cimier_manual.motor_turn("stop", conv) == "on"


def test_dir_turn():
    conv = default_conv()
    assert cimier_manual.dir_turn("up", conv) == "on"
    assert cimier_manual.dir_turn("down", conv) == "off"


def test_butee_atteinte_default():
    conv = default_conv()
    # state=False → contact fermé → butée atteinte ; state=True → ouverte → non atteinte.
    assert cimier_manual.butee_atteinte(False, conv) is True
    assert cimier_manual.butee_atteinte(True, conv) is False
```

- [ ] **Step 2 : Lancer les tests pour vérifier l'échec**

Run: `uv run --extra dev pytest tests/test_cimier_manual.py -v`
Expected: FAIL — `FileNotFoundError` / `ModuleNotFoundError` (le script n'existe pas encore).

- [ ] **Step 3 : Écrire le squelette + CONFIG + fonctions pures**

Créer `scripts/diagnostics/cimier_manual.py` :

```python
#!/usr/bin/env python3
"""Pilotage manuel du cimier V3 — séquencement nu des commandes Shelly.

Encode LA VÉRITÉ du synoptique : docs/synoptique electronique cimier V3.pdf.
Aucune abstraction héritée (pas de cooldown / drop / IPC / parser config).
Lançable en python3 pur sur le Pi : `python3 scripts/diagnostics/cimier_manual.py read`.

Source (synoptique V3, page « Commandes ») :
  SHELLY-1-24  (.83)  ON  http://192.168.1.83/relay/0?turn=on   alim module cimier
  SHELLY-1-MOT (.85)  moteur TOURNE  turn=off  / ARRÊT turn=on   (LOGIQUE INVERSÉE)
  SHELLY-1-UPDN(.86)  UP turn=on / DN turn=off                   sens via DPDT
  SHELLY-HAUT  (.84)  http://192.168.1.84/rpc/Input.GetStatus?id=1  True=Ouvert / False=fermé
  SHELLY-BAS   (.84)  http://192.168.1.84/rpc/Input.GetStatus?id=0  True=Ouvert / False=fermé
  (butée « fermée » = contact fermé = butée ATTEINTE)
"""

from __future__ import annotations

import argparse
import json
import sys
import time
import urllib.request

HOSTS = {
    "power": "192.168.1.83",  # SHELLY-1-24V  — alim module cimier
    "uni": "192.168.1.84",    # SHELLY Uni+   — lecture butées HAUT/BAS
    "motor": "192.168.1.85",  # SHELLY-1-MOT  — moteur (logique inversée)
    "dir": "192.168.1.86",    # SHELLY-1-UPDN — sens via DPDT
}

HAUT_ID = 1  # SHELLY-HAUT : Input.GetStatus?id=1
BAS_ID = 0   # SHELLY-BAS  : Input.GetStatus?id=0

# Conventions du synoptique — surchargeables par flags CLI au banc.
CONV = {
    "mot_run": "off",         # relais MOT turn=off → moteur TOURNE
    "dir_up": "on",           # relais UPDN turn=on → sens MONTÉE
    "switch_closed": "false",  # input state=false → butée fermée (atteinte)
    "settle_s": 2.0,
    "poll_s": 0.1,
    "timeout_s": 3.0,
}


def relay_url(host: str, turn: str) -> str:
    return f"http://{host}/relay/0?turn={turn}"


def input_url(host: str, input_id: int) -> str:
    return f"http://{host}/rpc/Input.GetStatus?id={input_id}"


def motor_turn(action: str, conv: dict) -> str:
    """action ∈ {run, stop} → valeur turn= (run par défaut = off, inversé)."""
    run = conv["mot_run"]
    stop = "on" if run == "off" else "off"
    return run if action == "run" else stop


def dir_turn(action: str, conv: dict) -> str:
    """action ∈ {up, down} → valeur turn= (up par défaut = on)."""
    up = conv["dir_up"]
    down = "off" if up == "on" else "on"
    return up if action == "up" else down


def butee_atteinte(state: bool, conv: dict) -> bool:
    """True si la butée est atteinte (contact fermé). Par défaut : state=False → atteinte."""
    closed_value = conv["switch_closed"] == "true"
    return state == closed_value
```

- [ ] **Step 4 : Lancer les tests pour vérifier le succès**

Run: `uv run --extra dev pytest tests/test_cimier_manual.py -v`
Expected: PASS (5 tests verts).

- [ ] **Step 5 : Commit**

```bash
git add scripts/diagnostics/cimier_manual.py tests/test_cimier_manual.py
git commit -m "feat(cimier): script manuel base — CONFIG + fonctions pures (synoptique V3)"
```

---

### Task 2 : Helper HTTP transparent + lecture des butées

**Files:**
- Modify: `scripts/diagnostics/cimier_manual.py`
- Test: `tests/test_cimier_manual.py`

- [ ] **Step 1 : Écrire le test de `read_switch` (échec attendu)**

Ajouter à `tests/test_cimier_manual.py` :

```python
def test_read_switch_parses_state(monkeypatch):
    # _call renvoie le corps brut du Shelly Uni+ ; read_switch en extrait le booléen state.
    monkeypatch.setattr(cimier_manual, "_call", lambda url, timeout: '{"id":1,"state":true}')
    assert cimier_manual.read_switch(cimier_manual.HOSTS["uni"], 1, 3.0) is True

    monkeypatch.setattr(cimier_manual, "_call", lambda url, timeout: '{"id":0,"state":false}')
    assert cimier_manual.read_switch(cimier_manual.HOSTS["uni"], 0, 3.0) is False


def test_read_switch_returns_none_on_http_failure(monkeypatch):
    monkeypatch.setattr(cimier_manual, "_call", lambda url, timeout: None)
    assert cimier_manual.read_switch(cimier_manual.HOSTS["uni"], 1, 3.0) is None
```

- [ ] **Step 2 : Lancer le test pour vérifier l'échec**

Run: `uv run --extra dev pytest tests/test_cimier_manual.py -k read_switch -v`
Expected: FAIL — `AttributeError: module 'cimier_manual' has no attribute '_call'`.

- [ ] **Step 3 : Implémenter `_call` et `read_switch`**

Ajouter à `scripts/diagnostics/cimier_manual.py` (après `butee_atteinte`) :

```python
def _call(url: str, timeout: float):
    """GET transparent : imprime l'URL envoyée puis la réponse. None si échec réseau."""
    print(f"  -> GET {url}")
    try:
        with urllib.request.urlopen(url, timeout=timeout) as resp:
            body = resp.read().decode("utf-8", "replace").strip()
        print(f"  <- {body}")
        return body
    except Exception as exc:  # noqa: BLE001 — diagnostic : on veut voir toute erreur réseau
        print(f"  !! {exc}")
        return None


def read_switch(host: str, input_id: int, timeout: float):
    """Lit Input.GetStatus → booléen state, ou None si la lecture échoue."""
    body = _call(input_url(host, input_id), timeout)
    if body is None:
        return None
    try:
        return bool(json.loads(body)["state"])
    except (ValueError, KeyError, TypeError) as exc:
        print(f"  !! réponse illisible : {exc}")
        return None
```

- [ ] **Step 4 : Lancer les tests pour vérifier le succès**

Run: `uv run --extra dev pytest tests/test_cimier_manual.py -v`
Expected: PASS (7 tests verts).

- [ ] **Step 5 : Commit**

```bash
git add scripts/diagnostics/cimier_manual.py tests/test_cimier_manual.py
git commit -m "feat(cimier): helper HTTP transparent + lecture butées"
```

---

### Task 3 : Composite `cycle` (open/close) avec poll des butées

**Files:**
- Modify: `scripts/diagnostics/cimier_manual.py`
- Test: `tests/test_cimier_manual.py`

- [ ] **Step 1 : Écrire le test de `cycle` (échec attendu)**

Ajouter à `tests/test_cimier_manual.py` :

```python
def test_cycle_stops_on_butee(monkeypatch):
    # La butée HAUT lue est d'abord "ouverte" (True), puis "atteinte" (False) au 2e poll.
    # On capture les URLs envoyées pour vérifier l'arrêt moteur + coupure alim.
    calls = []
    switch_states = iter([True, True, False])  # pré-check ouverte, poll1 ouverte, poll2 atteinte

    def fake_call(url, timeout):
        calls.append(url)
        if "Input.GetStatus" in url:
            state = next(switch_states)
            return json.dumps({"state": state})
        return "OK"

    monkeypatch.setattr(cimier_manual, "_call", fake_call)
    monkeypatch.setattr(cimier_manual.time, "sleep", lambda s: None)

    cimier_manual.cycle("up", default_conv(), timeout=3.0, settle=0.0, poll=0.0)

    # Moteur démarré (turn=off) puis arrêté (turn=on) ; alim coupée en fin.
    assert cimier_manual.relay_url(cimier_manual.HOSTS["motor"], "off") in calls  # run
    assert cimier_manual.relay_url(cimier_manual.HOSTS["motor"], "on") in calls   # stop
    assert calls[-1] == cimier_manual.relay_url(cimier_manual.HOSTS["power"], "off")


def test_cycle_skips_when_already_at_butee(monkeypatch):
    # Pré-check : butée déjà atteinte (False) → pas de démarrage moteur, alim coupée direct.
    calls = []

    def fake_call(url, timeout):
        calls.append(url)
        if "Input.GetStatus" in url:
            return json.dumps({"state": False})  # déjà fermée = atteinte
        return "OK"

    monkeypatch.setattr(cimier_manual, "_call", fake_call)
    monkeypatch.setattr(cimier_manual.time, "sleep", lambda s: None)

    cimier_manual.cycle("up", default_conv(), timeout=3.0, settle=0.0, poll=0.0)

    # Le moteur n'a jamais démarré (run = turn=off jamais envoyé).
    assert cimier_manual.relay_url(cimier_manual.HOSTS["motor"], "off") not in calls
    assert calls[-1] == cimier_manual.relay_url(cimier_manual.HOSTS["power"], "off")
```

- [ ] **Step 2 : Lancer le test pour vérifier l'échec**

Run: `uv run --extra dev pytest tests/test_cimier_manual.py -k cycle -v`
Expected: FAIL — `AttributeError: module 'cimier_manual' has no attribute 'cycle'`.

- [ ] **Step 3 : Implémenter `cycle`**

Ajouter à `scripts/diagnostics/cimier_manual.py` :

```python
def cycle(direction: str, conv: dict, timeout: float, settle: float, poll: float) -> None:
    """Séquence d'ouverture (direction='up') ou de fermeture ('down') — cinématique synoptique V3."""
    switch_id = HAUT_ID if direction == "up" else BAS_ID
    nom = "HAUT" if direction == "up" else "BAS"

    print("1. SHELLY-1-24/ON : alimentation du module cimier")
    _call(relay_url(HOSTS["power"], "on"), timeout)

    print(f"2. Attente {settle}s (appairage Wifi des Shelly)")
    time.sleep(settle)

    print("3. Moteur au repos (relais MOT à l'arrêt)")
    _call(relay_url(HOSTS["motor"], motor_turn("stop", conv)), timeout)

    print(f"4. Sens {direction.upper()}")
    _call(relay_url(HOSTS["dir"], dir_turn(direction, conv)), timeout)

    print(f"5. Pré-check butée {nom}")
    state = read_switch(HOSTS["uni"], switch_id, timeout)
    if state is not None and butee_atteinte(state, conv):
        print(f"   butée {nom} déjà atteinte → rien à faire")
        print("9. SHELLY-1-24/OFF : coupure alimentation")
        _call(relay_url(HOSTS["power"], "off"), timeout)
        return

    print("6. SHELLY-1-MOT : démarrage du moteur")
    _call(relay_url(HOSTS["motor"], motor_turn("run", conv)), timeout)

    print(f"7. Surveillance butée {nom} toutes les {poll}s")
    while True:
        state = read_switch(HOSTS["uni"], switch_id, timeout)
        if state is not None and butee_atteinte(state, conv):
            print(f"   butée {nom} atteinte")
            break
        time.sleep(poll)

    print("8. SHELLY-1-MOT : arrêt du moteur")
    _call(relay_url(HOSTS["motor"], motor_turn("stop", conv)), timeout)

    print("9. SHELLY-1-24/OFF : coupure alimentation")
    _call(relay_url(HOSTS["power"], "off"), timeout)
```

- [ ] **Step 4 : Lancer les tests pour vérifier le succès**

Run: `uv run --extra dev pytest tests/test_cimier_manual.py -v`
Expected: PASS (9 tests verts).

- [ ] **Step 5 : Commit**

```bash
git add scripts/diagnostics/cimier_manual.py tests/test_cimier_manual.py
git commit -m "feat(cimier): composite cycle open/close avec poll butées"
```

---

### Task 4 : CLI (argparse) — primitives + composites + dispatch

**Files:**
- Modify: `scripts/diagnostics/cimier_manual.py`

> Pas de test pytest sur le parsing CLI (argparse est trivial ici, et la valeur est dans
> l'exécution hardware par Serge). Vérification manuelle par exécution en fin de tâche.

- [ ] **Step 1 : Implémenter le parser, le dispatch et `main`**

Ajouter à `scripts/diagnostics/cimier_manual.py` :

```python
def build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(
        description="Pilotage manuel cimier V3 (séquencement nu des Shelly).",
        epilog="Exemples : read | power on | dir up | motor run | open | close | stop",
    )
    p.add_argument(
        "command",
        choices=["read", "power", "dir", "motor", "open", "close", "stop"],
    )
    p.add_argument("arg", nargs="?", help="on/off (power) | up/down (dir) | run/stop (motor)")
    p.add_argument("--settle", type=float, default=CONV["settle_s"], help="attente appairage (s)")
    p.add_argument("--poll", type=float, default=CONV["poll_s"], help="intervalle poll butée (s)")
    p.add_argument("--timeout", type=float, default=CONV["timeout_s"], help="timeout HTTP (s)")
    p.add_argument("--mot-run", choices=["off", "on"], default=CONV["mot_run"],
                   help="valeur turn= qui FAIT TOURNER le moteur (synoptique : off)")
    p.add_argument("--dir-up", choices=["on", "off"], default=CONV["dir_up"],
                   help="valeur turn= du sens MONTÉE (synoptique : on)")
    p.add_argument("--switch-closed", choices=["false", "true"], default=CONV["switch_closed"],
                   help="valeur state= d'une butée ATTEINTE (synoptique : false)")
    return p


def main(argv=None) -> int:
    args = build_parser().parse_args(argv)
    conv = {
        "mot_run": args.mot_run,
        "dir_up": args.dir_up,
        "switch_closed": args.switch_closed,
        "settle_s": args.settle,
        "poll_s": args.poll,
        "timeout_s": args.timeout,
    }
    cmd, sub = args.command, args.arg

    if cmd == "read":
        haut = read_switch(HOSTS["uni"], HAUT_ID, args.timeout)
        bas = read_switch(HOSTS["uni"], BAS_ID, args.timeout)
        print(f"HAUT (id={HAUT_ID}) : state={haut} -> "
              f"{'ATTEINTE' if haut is not None and butee_atteinte(haut, conv) else 'ouverte/?'}")
        print(f"BAS  (id={BAS_ID}) : state={bas} -> "
              f"{'ATTEINTE' if bas is not None and butee_atteinte(bas, conv) else 'ouverte/?'}")
        return 0

    if cmd == "power":
        if sub not in ("on", "off"):
            print("usage : power on|off"); return 2
        _call(relay_url(HOSTS["power"], sub), args.timeout)
        return 0

    if cmd == "dir":
        if sub not in ("up", "down"):
            print("usage : dir up|down"); return 2
        _call(relay_url(HOSTS["dir"], dir_turn(sub, conv)), args.timeout)
        return 0

    if cmd == "motor":
        if sub not in ("run", "stop"):
            print("usage : motor run|stop"); return 2
        _call(relay_url(HOSTS["motor"], motor_turn(sub, conv)), args.timeout)
        return 0

    if cmd == "open":
        cycle("up", conv, args.timeout, args.settle, args.poll); return 0

    if cmd == "close":
        cycle("down", conv, args.timeout, args.settle, args.poll); return 0

    if cmd == "stop":
        _call(relay_url(HOSTS["motor"], motor_turn("stop", conv)), args.timeout)
        return 0

    return 2


if __name__ == "__main__":
    sys.exit(main())
```

- [ ] **Step 2 : Vérifier que le parsing/dispatch ne plante pas (sans hardware)**

Run: `uv run --extra dev python scripts/diagnostics/cimier_manual.py read`
Expected: deux lignes `-> GET http://192.168.1.84/rpc/Input.GetStatus?id=...` suivies de
`!! <erreur réseau>` (pas de Shelly accessible depuis la machine dev), puis
`HAUT ... state=None -> ouverte/?` / `BAS ... state=None -> ouverte/?`. **Aucune exception Python.**

Run: `uv run --extra dev python scripts/diagnostics/cimier_manual.py motor run`
Expected: `-> GET http://192.168.1.85/relay/0?turn=off` (confirme la logique inversée), puis `!! <erreur réseau>`.

- [ ] **Step 3 : Vérifier l'aide CLI**

Run: `uv run --extra dev python scripts/diagnostics/cimier_manual.py --help`
Expected: affiche les commandes et les flags `--mot-run`, `--dir-up`, `--switch-closed`, etc.

- [ ] **Step 4 : Commit**

```bash
git add scripts/diagnostics/cimier_manual.py
git commit -m "feat(cimier): CLI primitives + composites + dispatch"
```

---

### Task 5 : Lint, format et passe finale

**Files:**
- Modify: `scripts/diagnostics/cimier_manual.py`, `tests/test_cimier_manual.py` (si ruff corrige)

- [ ] **Step 1 : Formater**

Run: `uv run --extra dev ruff format scripts/diagnostics/cimier_manual.py tests/test_cimier_manual.py`
Expected: fichiers reformatés (ou « already formatted »).

- [ ] **Step 2 : Linter**

Run: `uv run --extra dev ruff check scripts/diagnostics/cimier_manual.py tests/test_cimier_manual.py`
Expected: « All checks passed! » (le `# noqa: BLE001` couvre le `except Exception` volontaire du diagnostic).

- [ ] **Step 3 : Suite de tests du périmètre**

Run: `uv run --extra dev pytest tests/test_cimier_manual.py -v`
Expected: PASS (9 tests verts).

- [ ] **Step 4 : Commit (si format/lint a modifié quelque chose)**

```bash
git add scripts/diagnostics/cimier_manual.py tests/test_cimier_manual.py
git commit -m "chore(cimier): ruff format + lint script manuel"
```

---

## Protocole de validation terrain (Serge, hors plan de code)

Une fois le script poussé, Serge le lance sur le Pi (SSH) dans l'ordre, en notant ce qui marche :

```bash
cd ~/DriftApp
python3 scripts/diagnostics/cimier_manual.py read          # 1) état réel des butées
python3 scripts/diagnostics/cimier_manual.py power on       # 2) alim module
python3 scripts/diagnostics/cimier_manual.py dir up         # 3) sens montée
python3 scripts/diagnostics/cimier_manual.py motor run      # 4) le moteur doit TOURNER (sens montée)
python3 scripts/diagnostics/cimier_manual.py motor stop     # 5) arrêt
python3 scripts/diagnostics/cimier_manual.py power off
python3 scripts/diagnostics/cimier_manual.py open           # 6) cycle complet
python3 scripts/diagnostics/cimier_manual.py close
```

Si une convention est fausse (moteur tourne dans le mauvais sens, butée mal lue), inverser via
flag sans toucher au fichier, ex : `--mot-run on`, `--dir-up off`, `--switch-closed true`,
`--settle 3`. Consigner les valeurs qui marchent.

## Phase 2 (plan séparé, après validation)

Calquer les primitives validées derrière les boutons Django, en reportant dans `data/config.json`
les conventions confirmées — notamment corriger `motor_shelly.motor_on_relay_state` de `true`
vers `false` (moteur tourne quand `turn=off`) et aligner la sémantique `switch_reader` sur
« butée atteinte = state False », deux points où le code actuel contredit le synoptique.
