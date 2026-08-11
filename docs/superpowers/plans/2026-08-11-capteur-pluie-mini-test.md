# Mini-programme de test du capteur de pluie — Plan d'implémentation

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Livrer `scripts/diagnostics/pluie_manual.py`, un standalone que Serge lance sur son portable, dehors, à côté du capteur de pluie, pour valider en une seule sortie que la chaîne MH-RD → Shelly Plus Uni (.87) → réseau → Python fonctionne — avec bandeau coloré, bips aux transitions et journal horodaté.

**Architecture:** Un fichier unique, Python 3 stdlib pure, aucun import du projet, aucune lecture de `data/config.json`, aucun IPC. Deux commandes : `read` (lecture ponctuelle des deux entrées RPC, brut affiché) et `monitor` (boucle de polling, bandeau ANSI redessiné en place, bips aux transitions, journal en append). Même patron que `scripts/diagnostics/cimier_manual.py`, qui avait tourné du premier coup sur le terrain.

**Tech Stack:** Python 3 stdlib uniquement — `urllib.request`, `json`, `argparse`, `wave`, `struct`, `math`, `subprocess`, `tempfile`, `datetime`. Aucune dépendance à installer sur le poste de Serge.

**Spec de référence:** `docs/superpowers/specs/2026-08-11-capteur-pluie-mini-test-design.md`

---

## Note sur la vérification

`scripts/diagnostics/` n'est pas collecté par pytest et ce script n'introduit **aucun test unitaire** — décision prise en spec (§6), cohérente avec `cimier_manual.py`. C'est un écart assumé au TDD habituel du dépôt.

En contrepartie, **chaque tâche se termine par une vérification exécutable dont la sortie attendue est écrite noir sur blanc**. Ne jamais cocher une étape sans avoir vu la sortie. Un script qui part à 800 km ne se débogue pas à distance.

Deux tâches s'appuient sur un **faux Shelly local**, créé en Tâche 1 et gardé hors du dépôt.

---

## Structure du fichier livré

Un seul fichier, `scripts/diagnostics/pluie_manual.py`, construit en couches successives :

| Couche | Responsabilité | Tâche |
|---|---|---|
| Constantes + `read_input` + `interpret` + `cmd_read` + CLI | Parler au Shelly, dire SEC/PLUIE, commande `read` | 1 |
| `make_beeper` + backends son + `_write_wav` | Émettre 3 tonalités distinctes, quel que soit l'OS | 2 |
| `timestamp` + `format_duration` + `Journal` | Consigner les transitions, résumer les épisodes PLUIE | 3 |
| `render` + `shelly_source` + `demo_source` + `cmd_monitor` | Boucle, affichage, bips, sortie propre | 4 |
| `scripts/diagnostics/README.md` | Mode d'emploi terrain pour Serge | 5 |

Chaque tâche laisse le script **exécutable et utile en l'état**. Après la Tâche 1, `read` fonctionne déjà : Serge pourrait s'en servir tel quel.

---

## Task 1: Squelette CLI, lecture RPC et commande `read`

**Files:**
- Create: `scripts/diagnostics/pluie_manual.py`
- Create (hors dépôt): `$SCRATCH/fake_shelly.py`

- [ ] **Step 1: Préparer le répertoire de travail temporaire**

Le faux Shelly ne doit jamais être versionné. On le place dans le scratchpad de session :

```bash
export SCRATCH=/tmp/claude-1000/-home-jp-PythonProject-DriftApp-Web/60588ffc-2aab-4c52-86fa-698bb547ae73/scratchpad
mkdir -p "$SCRATCH" && echo "$SCRATCH"
```

Attendu : le chemin s'affiche, sans erreur. (N'importe quel répertoire temporaire fait l'affaire si celui-ci n'existe plus — mais **jamais** un chemin sous `scripts/` ou `tests/`.)

- [ ] **Step 2: Écrire le faux Shelly**

Il répond comme un Shelly Plus Uni sur `/rpc/Input.GetStatus`, et expose un `/set` qui permet de simuler l'arrosoir sans mouiller quoi que ce soit.

Écrire dans `$SCRATCH/fake_shelly.py` :

```python
"""Faux Shelly Plus Uni pour vérifier pluie_manual.py sans matériel.

Lancer :  python3 fake_shelly.py
Lire   :  curl 'http://127.0.0.1:8099/rpc/Input.GetStatus?id=0'
Arroser:  curl 'http://127.0.0.1:8099/set?id=0&state=true'
Sécher :  curl 'http://127.0.0.1:8099/set?id=0&state=false'
"""

import json
from http.server import BaseHTTPRequestHandler, HTTPServer
from urllib.parse import parse_qs, urlparse

STATE = {"0": False, "1": False}


class Handler(BaseHTTPRequestHandler):
    def do_GET(self):
        parsed = urlparse(self.path)
        query = parse_qs(parsed.query)
        if parsed.path == "/set":
            STATE[query["id"][0]] = query["state"][0] == "true"
            body = b'{"ok":true}'
        elif parsed.path == "/rpc/Input.GetStatus":
            input_id = query.get("id", ["0"])[0]
            body = json.dumps({"id": int(input_id), "state": STATE[input_id]}).encode()
        else:
            self.send_response(404)
            self.end_headers()
            return
        self.send_response(200)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def log_message(self, *args):
        pass


HTTPServer(("127.0.0.1", 8099), Handler).serve_forever()
```

- [ ] **Step 3: Vérifier que le faux Shelly répond**

```bash
python3 "$SCRATCH/fake_shelly.py" &
sleep 1
curl -s 'http://127.0.0.1:8099/rpc/Input.GetStatus?id=0'
```

Attendu, exactement : `{"id": 0, "state": false}`

- [ ] **Step 4: Écrire le squelette du script**

Créer `scripts/diagnostics/pluie_manual.py` :

```python
#!/usr/bin/env python3
"""Test terrain du capteur de pluie MH-RD lu par un Shelly Plus Uni.

Standalone de diagnostic : stdlib pure, aucun import du projet, aucune config.
Se lance depuis n'importe quelle machine du réseau local — typiquement le
portable emporté dehors, à côté du capteur.

  python3 pluie_manual.py read       # lecture ponctuelle des 2 entrées, brut
  python3 pluie_manual.py monitor    # bandeau + bips aux transitions + journal
  python3 pluie_manual.py monitor --demo   # sans réseau, pour tester le son

Ce que ce programme sert à établir sur le terrain (rien n'est figé ici) :
  1. quelle entrée du Shelly porte le D0 du capteur (id=0 ou id=1) ;
  2. la polarité telle que le Shelly la rapporte (--invert si elle est inversée) ;
  3. le réglage du trimpot du module ;
  4. que la chaîne capteur -> Shelly -> réseau -> Python est vivante ;
  5. le temps de séchage du capteur (durée des épisodes PLUIE, cf. résumé de sortie).
"""

from __future__ import annotations

import argparse
import json
import sys
import urllib.error
import urllib.request

# Défauts terrain — surchargeables par flags CLI, comme dans cimier_manual.py.
DEFAULT_HOST = "192.168.1.87"
DEFAULT_INTERVAL_S = 1.0
DEFAULT_TIMEOUT_S = 3.0

# Les 2 entrées digitales du Shelly Plus Uni. On lit LES DEUX par défaut :
# « entrée n°1 » est ambigu (sérigraphie 1/2 sur le boîtier, ids 0/1 en RPC).
DIGITAL_INPUT_IDS = (0, 1)

WET = "PLUIE"
DRY = "SEC"
UNREACHABLE = "INJOIGNABLE"


class ShellyError(Exception):
    """Le Shelly n'a pas répondu, ou pas comme attendu."""


def read_input(host: str, input_id: int, timeout_s: float = DEFAULT_TIMEOUT_S):
    """Lit une entrée digitale. Renvoie (state: bool, payload: dict) ou lève ShellyError."""
    url = "http://" + host + "/rpc/Input.GetStatus?id=" + str(input_id)
    try:
        with urllib.request.urlopen(url, timeout=timeout_s) as resp:
            status = getattr(resp, "status", 200)
            raw = resp.read()
    except urllib.error.URLError as exc:
        raise ShellyError("injoignable (" + str(exc.reason) + ")") from exc
    except OSError as exc:
        raise ShellyError("erreur socket (" + str(exc) + ")") from exc
    if status != 200:
        raise ShellyError("HTTP " + str(status))
    try:
        payload = json.loads(raw.decode("utf-8"))
    except (ValueError, UnicodeDecodeError) as exc:
        raise ShellyError("JSON invalide (" + str(exc) + ")") from exc
    if not isinstance(payload, dict) or "state" not in payload:
        raise ShellyError("payload sans 'state' : " + repr(payload))
    return bool(payload["state"]), payload


def interpret(state: bool, invert: bool) -> str:
    """État brut du Shelly -> PLUIE / SEC.

    Par défaut state=True -> PLUIE. Le D0 du LM393 est actif bas côté module,
    mais ce que le Shelly rapporte dépend de son câblage d'entrée : d'où --invert
    plutôt qu'une constante. C'est le verre d'eau qui tranche, pas la datasheet.
    """
    return WET if state != invert else DRY


def input_ids(choice: str):
    """'both' -> les deux entrées ; '0'/'1' -> celle-là seulement."""
    if choice == "both":
        return DIGITAL_INPUT_IDS
    return (int(choice),)


def cmd_read(args) -> int:
    """Lecture ponctuelle : affiche l'interprétation ET le JSON brut."""
    print("Shelly " + args.host + " — lecture ponctuelle")
    for input_id in input_ids(args.input):
        try:
            state, payload = read_input(args.host, input_id, args.timeout)
        except ShellyError as exc:
            print("  id=" + str(input_id) + " : " + UNREACHABLE + " — " + str(exc))
            continue
        print(
            "  id="
            + str(input_id)
            + " : "
            + interpret(state, args.invert).ljust(6)
            + " state="
            + str(state).ljust(5)
            + " brut="
            + json.dumps(payload)
        )
    print("\nArrosez la plaque, relancez : l'entrée qui bouge est celle du capteur.")
    return 0


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description=__doc__,
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    parser.add_argument(
        "command",
        choices=("read", "monitor"),
        nargs="?",
        default="monitor",
        help="read = une lecture brute ; monitor = surveillance continue (défaut)",
    )
    parser.add_argument("--host", default=DEFAULT_HOST, help="IP du Shelly (défaut %(default)s)")
    parser.add_argument(
        "--input",
        choices=("0", "1", "both"),
        default="both",
        help="entrée(s) à lire (défaut %(default)s)",
    )
    parser.add_argument(
        "--interval", type=float, default=DEFAULT_INTERVAL_S, help="secondes entre 2 lectures"
    )
    parser.add_argument("--timeout", type=float, default=DEFAULT_TIMEOUT_S, help="timeout HTTP")
    parser.add_argument("--invert", action="store_true", help="inverse la polarité (state=True -> SEC)")
    return parser


def main(argv=None) -> int:
    args = build_parser().parse_args(argv)
    if args.command == "read":
        return cmd_read(args)
    print("monitor : implémenté en Task 4")
    return 0


if __name__ == "__main__":
    sys.exit(main())
```

- [ ] **Step 5: Vérifier `read` contre le faux Shelly, capteur sec**

```bash
python3 scripts/diagnostics/pluie_manual.py read --host 127.0.0.1:8099
```

Attendu :

```
Shelly 127.0.0.1:8099 — lecture ponctuelle
  id=0 : SEC    state=False brut={"id": 0, "state": false}
  id=1 : SEC    state=False brut={"id": 1, "state": false}

Arrosez la plaque, relancez : l'entrée qui bouge est celle du capteur.
```

- [ ] **Step 6: Vérifier `read` après « arrosage » de l'entrée 1**

```bash
curl -s 'http://127.0.0.1:8099/set?id=1&state=true' >/dev/null
python3 scripts/diagnostics/pluie_manual.py read --host 127.0.0.1:8099
```

Attendu : `id=0` reste `SEC`, `id=1` passe à `PLUIE   state=True`. C'est exactement le geste que Serge fera avec son verre d'eau.

- [ ] **Step 7: Vérifier `--invert`**

```bash
python3 scripts/diagnostics/pluie_manual.py read --host 127.0.0.1:8099 --invert
```

Attendu : les interprétations sont échangées — `id=0 : PLUIE`, `id=1 : SEC`. Le `state=` brut, lui, ne change pas.

- [ ] **Step 8: Vérifier le cas injoignable**

```bash
python3 scripts/diagnostics/pluie_manual.py read --host 127.0.0.1:9999
```

Attendu : deux lignes `INJOIGNABLE — injoignable (...)`, et **le programme se termine normalement** (pas de traceback).

- [ ] **Step 9: Formater, linter, committer**

```bash
uv run --extra dev ruff format scripts/diagnostics/pluie_manual.py
uv run --extra dev ruff check scripts/diagnostics/pluie_manual.py
git add scripts/diagnostics/pluie_manual.py
git commit -m "feat(pluie): standalone de test capteur — lecture RPC et commande read"
```

Attendu : `ruff check` affiche `All checks passed!`.

---

## Task 2: Signal sonore multiplateforme

**Files:**
- Modify: `scripts/diagnostics/pluie_manual.py`

- [ ] **Step 1: Compléter les imports**

Remplacer le bloc d'imports par :

```python
import argparse
import json
import math
import os
import shutil
import struct
import subprocess
import sys
import tempfile
import time
import urllib.error
import urllib.request
import wave
```

- [ ] **Step 2: Ajouter les tonalités et la génération de WAV**

À insérer après la définition de `UNREACHABLE`, avant `class ShellyError` :

```python
# Trois signaux distincts, reconnaissables à l'oreille sans regarder l'écran.
# (fréquence Hz, durée ms) — le sens du glissando porte l'information.
BEEPS = {
    "up": ((880, 120), (1320, 160)),  # sec -> pluie : ça monte
    "down": ((1320, 120), (660, 160)),  # pluie -> sec : ça descend
    "error": ((220, 150), (220, 150), (220, 300)),  # Shelly injoignable : 3 coups graves
}


def _write_wav(notes, rate: int = 22050) -> str:
    """Génère un WAV mono 16 bits pour une suite de (freq_hz, durée_ms). Renvoie un chemin."""
    frames = bytearray()
    for freq, milliseconds in notes:
        count = int(rate * milliseconds / 1000)
        fade = max(1.0, rate * 0.005)  # 5 ms d'attaque/extinction, sinon ça claque
        for i in range(count):
            envelope = min(1.0, min(i, count - i) / fade)
            value = int(16000 * envelope * math.sin(2 * math.pi * freq * i / rate))
            frames += struct.pack("<h", value)
    handle, path = tempfile.mkstemp(prefix="pluie_", suffix=".wav")
    os.close(handle)
    with wave.open(path, "wb") as wav:
        wav.setnchannels(1)
        wav.setsampwidth(2)
        wav.setframerate(rate)
        wav.writeframes(bytes(frames))
    return path
```

- [ ] **Step 3: Ajouter les backends et la cascade**

Juste après `_write_wav` :

```python
def _winsound_beeper():
    import winsound  # stdlib, Windows uniquement

    def beep(kind: str) -> None:
        for freq, milliseconds in BEEPS[kind]:
            winsound.Beep(freq, milliseconds)

    return beep


def _player_beeper(player: str):
    def beep(kind: str) -> None:
        path = _write_wav(BEEPS[kind])
        try:
            subprocess.run(
                [player, path],
                check=False,
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL,
            )
        finally:
            os.unlink(path)

    return beep


def _bel_beeper():
    def beep(kind: str) -> None:
        for _ in range(3 if kind == "error" else 2):
            sys.stdout.write("\a")
            sys.stdout.flush()
            time.sleep(0.15)

    return beep


def make_beeper(enabled: bool):
    """Renvoie (beep, label). beep(kind) avec kind dans {up, down, error}.

    Cascade : winsound (Windows) -> paplay -> aplay -> afplay -> BEL terminal.
    Le label est affiché au démarrage : Serge doit savoir AVANT de sortir s'il
    peut compter sur le son.
    """
    if not enabled:
        return (lambda kind: None), "coupé (--no-sound)"
    if sys.platform.startswith("win"):
        try:
            return _winsound_beeper(), "winsound"
        except ImportError:
            pass
    for player in ("paplay", "aplay", "afplay"):
        if shutil.which(player):
            return _player_beeper(player), player
    return (
        _bel_beeper(),
        "BEL terminal — beaucoup d'émulateurs le coupent, vérifiez le volume avant de sortir",
    )


def transition_sound(previous: str, new: str) -> str:
    """Quel signal pour quelle transition. L'état d'arrivée décide."""
    if new == UNREACHABLE:
        return "error"
    if new == WET:
        return "up"
    return "down"
```

- [ ] **Step 4: Ajouter le flag `--no-sound`**

Dans `build_parser()`, après l'argument `--invert` :

```python
    parser.add_argument("--no-sound", action="store_true", help="coupe les bips")
```

- [ ] **Step 5: Écouter les trois signaux**

```bash
python3 -c "
import sys; sys.path.insert(0, 'scripts/diagnostics')
import pluie_manual as p
beep, label = p.make_beeper(True)
print('backend :', label)
for kind in ('up', 'down', 'error'):
    print('  ->', kind); beep(kind)
"
```

Attendu : le backend s'affiche (`paplay` sur une station Linux avec PulseAudio), puis **trois signaux audibles et différents** — montant, descendant, trois coups graves. Si rien ne sort alors que le backend n'est pas `BEL terminal`, vérifier le volume système avant d'aller plus loin : c'est tout l'intérêt du programme qui tombe.

- [ ] **Step 6: Vérifier que `--no-sound` ne casse rien**

```bash
python3 -c "
import sys; sys.path.insert(0, 'scripts/diagnostics')
import pluie_manual as p
beep, label = p.make_beeper(False)
print('backend :', label)
beep('up'); beep('error')
print('OK, silencieux')
"
```

Attendu : `backend : coupé (--no-sound)` puis `OK, silencieux`, sans le moindre son ni erreur.

- [ ] **Step 7: Formater, linter, committer**

```bash
uv run --extra dev ruff format scripts/diagnostics/pluie_manual.py
uv run --extra dev ruff check scripts/diagnostics/pluie_manual.py
git add scripts/diagnostics/pluie_manual.py
git commit -m "feat(pluie): cascade sonore multiplateforme, 3 tonalités distinctes"
```

---

## Task 3: Journal horodaté et résumé des épisodes

**Files:**
- Modify: `scripts/diagnostics/pluie_manual.py`

- [ ] **Step 1: Ajouter l'import `datetime`**

Ajouter après le bloc `import wave` :

```python
from datetime import datetime
```

- [ ] **Step 2: Ajouter les helpers de temps**

À insérer après `transition_sound` :

```python
def timestamp() -> str:
    return datetime.now().strftime("%Y-%m-%dT%H:%M:%S")


def format_duration(seconds: float) -> str:
    total = int(seconds)
    if total < 60:
        return str(total) + " s"
    return str(total // 60) + " min " + str(total % 60).zfill(2) + " s"


def default_log_path() -> str:
    """Répertoire courant, PAS logs/ du dépôt : le portable de Serge n'a pas le dépôt."""
    return datetime.now().strftime("pluie_test_%Y%m%d_%H%M%S.log")
```

- [ ] **Step 3: Ajouter la classe `Journal`**

Juste après `default_log_path` :

```python
class Journal:
    """Consigne les transitions à l'écran et dans un fichier (append + flush).

    Le flush à chaque ligne est délibéré : une campagne d'une heure ne doit rien
    perdre sur un Ctrl-C ou une batterie à plat.

    La durée de l'état PRÉCÉDENT est portée sur la ligne de transition. C'est
    elle qui répond à la question du séchage : la durée de l'épisode PLUIE qui
    suit le dernier arrosage EST le temps de séchage du capteur.
    """

    def __init__(self, path=None):
        self.path = path
        self.lines = []
        self.episodes = []  # (état, durée_s) des états clos
        self._handle = open(path, "a", encoding="utf-8") if path else None
        self._write("# campagne démarrée " + timestamp())

    def _write(self, text: str) -> None:
        if self._handle:
            self._handle.write(text + "\n")
            self._handle.flush()

    def transition(self, previous: str, new: str, held_s: float) -> None:
        line = (
            timestamp()
            + " "
            + previous.ljust(11)
            + " -> "
            + new.ljust(11)
            + " (état précédent tenu "
            + format_duration(held_s)
            + ")"
        )
        self.lines.append(line)
        self.episodes.append((previous, held_s))
        self._write(line)

    def close(self, current: str, held_s: float) -> None:
        self.episodes.append((current, held_s))
        self._write(
            "# campagne arrêtée "
            + timestamp()
            + " — état final "
            + current
            + " tenu "
            + format_duration(held_s)
        )
        if self._handle:
            self._handle.close()
            self._handle = None

    def summary(self):
        """Lignes du résumé de sortie. C'est CE bloc que Serge nous renvoie."""
        wet = [duration for state, duration in self.episodes if state == WET]
        out = ["", "=== RÉSUMÉ ==="]
        if not wet:
            out.append("Aucun épisode PLUIE observé.")
        else:
            out.append(str(len(wet)) + " épisode(s) PLUIE :")
            for index, duration in enumerate(wet, 1):
                out.append("  #" + str(index) + " : " + format_duration(duration))
            out.append(
                "Le plus long : "
                + format_duration(max(wet))
                + "   <-- temps de séchage à retenir pour clear_delay_s"
            )
        if self.path:
            out.append("Journal complet : " + self.path)
        return out
```

- [ ] **Step 4: Ajouter les flags `--log` et `--no-log`**

Dans `build_parser()`, après `--no-sound` :

```python
    parser.add_argument(
        "--log",
        help="fichier journal (défaut : pluie_test_<horodatage>.log dans le répertoire courant)",
    )
    parser.add_argument("--no-log", action="store_true", help="n'écrit aucun fichier")
```

- [ ] **Step 5: Vérifier le journal et le résumé**

```bash
cd "$SCRATCH" && python3 -c "
import sys; sys.path.insert(0, '/home/jp/PythonProject/DriftApp-Web/scripts/diagnostics')
import pluie_manual as p
j = p.Journal('verif_journal.log')
j.transition(p.DRY, p.WET, 412)
j.transition(p.WET, p.DRY, 145)
j.transition(p.DRY, p.WET, 30)
j.close(p.WET, 605)
print('\n'.join(j.summary()))
" && cat verif_journal.log && cd /home/jp/PythonProject/DriftApp-Web
```

Attendu à l'écran :

```
=== RÉSUMÉ ===
2 épisode(s) PLUIE :
  #1 : 2 min 25 s
  #2 : 10 min 05 s
Le plus long : 10 min 05 s   <-- temps de séchage à retenir pour clear_delay_s
Journal complet : verif_journal.log
```

Deux pièges à contrôler ici, et ils sont le cœur de la tâche :

- l'épisode `#1` vaut **2 min 25 s** (145 s, la durée de l'état PLUIE *clos par* la transition
  PLUIE→SEC) — et non 412 s, qui est la durée du SEC qui précédait. Si le résumé affiche 412 s,
  l'argument `previous` est associé à la mauvaise durée ;
- le résumé liste **2** épisodes, pas 3. Les 30 s de la troisième transition closent un état **SEC**
  (son `previous` vaut `DRY`), et `summary()` ne retient que les états PLUIE. Un résumé à 3 entrées
  signifierait que le filtre `state == WET` ne fonctionne pas.

Le `cat` doit montrer les 3 lignes horodatées encadrées par `# campagne démarrée` / `# campagne arrêtée`.

- [ ] **Step 6: Vérifier le mode sans fichier**

```bash
python3 -c "
import sys; sys.path.insert(0, 'scripts/diagnostics')
import pluie_manual as p
j = p.Journal(None)
j.transition(p.DRY, p.WET, 10)
j.close(p.WET, 20)
print('\n'.join(j.summary()))
"
```

Attendu : le résumé s'affiche avec 1 épisode de 20 s, **sans** ligne `Journal complet :`, et aucun fichier n'est créé.

- [ ] **Step 7: Formater, linter, committer**

```bash
uv run --extra dev ruff format scripts/diagnostics/pluie_manual.py
uv run --extra dev ruff check scripts/diagnostics/pluie_manual.py
git add scripts/diagnostics/pluie_manual.py
git commit -m "feat(pluie): journal horodaté des transitions et résumé des épisodes"
```

---

## Task 4: Boucle `monitor`, bandeau ANSI et mode démo

**Files:**
- Modify: `scripts/diagnostics/pluie_manual.py`

- [ ] **Step 1: Ajouter les codes ANSI**

À insérer après la définition de `BEEPS` :

```python
# Couleurs de fond pleines : lisibles d'un coup d'œil sur un écran en extérieur.
ANSI = {
    WET: "\033[1;97;41m",  # blanc sur rouge
    DRY: "\033[1;30;42m",  # noir sur vert
    UNREACHABLE: "\033[1;30;43m",  # noir sur jaune
}
ANSI_RESET = "\033[0m"
ANSI_CLEAR = "\033[2J\033[H"
```

- [ ] **Step 2: Ajouter le rendu**

À insérer après la classe `Journal` :

```python
def render(state: str, since_s: float, history, title: str, detail: str) -> None:
    """Redessine le bloc en place : l'écran ne doit pas défiler pendant une heure."""
    lines = [
        title,
        "",
        ANSI[state] + "   " + state.center(30) + "   " + ANSI_RESET
        + "   depuis "
        + format_duration(since_s),
        "   " + detail,
        "",
        "Dernières transitions :",
    ]
    if history:
        lines += ["  " + line for line in history[-5:]]
    else:
        lines.append("  (aucune pour l'instant)")
    lines += ["", "Ctrl-C pour arrêter et afficher le résumé."]
    sys.stdout.write(ANSI_CLEAR + "\n".join(lines) + "\n")
    sys.stdout.flush()
```

- [ ] **Step 3: Ajouter les deux sources d'état**

Juste après `render` :

```python
def shelly_source(args):
    """Générateur (état, détail) lu sur le Shelly.

    En mode 'both' — le défaut, tant qu'on ignore quelle entrée porte le D0 —
    l'état global est PLUIE si l'UNE des entrées est en pluie, et INJOIGNABLE
    l'emporte sur tout : une lecture perdue ne doit jamais passer pour du beau
    temps. Le détail par entrée reste affiché sous le bandeau.
    """
    ids = input_ids(args.input)
    while True:
        states = []
        detail = []
        for input_id in ids:
            try:
                raw, _ = read_input(args.host, input_id, args.timeout)
            except ShellyError as exc:
                states.append(UNREACHABLE)
                detail.append("id=" + str(input_id) + " " + UNREACHABLE + " (" + str(exc) + ")")
            else:
                value = interpret(raw, args.invert)
                states.append(value)
                detail.append("id=" + str(input_id) + " " + value)
        if UNREACHABLE in states:
            yield UNREACHABLE, " · ".join(detail)
        elif WET in states:
            yield WET, " · ".join(detail)
        else:
            yield DRY, " · ".join(detail)


def demo_source():
    """Alterne SEC / PLUIE / INJOIGNABLE sans réseau : vérifier le son avant de sortir."""
    scenario = ((DRY, 6), (WET, 6), (DRY, 6), (UNREACHABLE, 6))
    while True:
        for state, seconds in scenario:
            deadline = time.monotonic() + seconds
            while time.monotonic() < deadline:
                yield state, "démo — aucun réseau, aucun Shelly"
```

- [ ] **Step 4: Écrire la boucle `monitor`**

À insérer après `demo_source` :

```python
def cmd_monitor(args) -> int:
    beep, sound_label = make_beeper(not args.no_sound)
    journal = Journal(None if args.no_log else (args.log or default_log_path()))
    source = demo_source() if args.demo else shelly_source(args)
    title = (
        "CAPTEUR DE PLUIE — "
        + ("DÉMO" if args.demo else "Shelly " + args.host)
        + "   son : "
        + sound_label
    )

    print("son : " + sound_label)
    if journal.path:
        print("journal : " + journal.path)
    time.sleep(1.5)

    state = None
    since = time.monotonic()
    try:
        while True:
            new, detail = next(source)
            now = time.monotonic()
            if state is None:
                state, since = new, now
            elif new != state:
                journal.transition(state, new, now - since)
                beep(transition_sound(state, new))
                state, since = new, now
            render(state, now - since, journal.lines, title, detail)
            time.sleep(args.interval)
    except KeyboardInterrupt:
        if state is not None:
            journal.close(state, time.monotonic() - since)
        print("\n".join(journal.summary()))
    return 0
```

- [ ] **Step 5: Ajouter le flag `--demo` et brancher la commande**

Dans `build_parser()`, après `--no-log` :

```python
    parser.add_argument("--demo", action="store_true", help="états simulés, sans réseau")
```

Puis, dans `main()`, remplacer les deux lignes du stub :

```python
    print("monitor : implémenté en Task 4")
    return 0
```

par :

```python
    return cmd_monitor(args)
```

- [ ] **Step 6: Vérifier le mode démo**

```bash
timeout 26 python3 scripts/diagnostics/pluie_manual.py monitor --demo --no-log --interval 0.5
```

Attendu, en ~26 s : le bandeau change de couleur trois fois (vert → rouge → vert → jaune), **trois bips distincts** accompagnent les transitions (montant, descendant, trois coups graves), la liste « Dernières transitions » se remplit et les durées affichées tournent autour de 6 s. `timeout` tue le processus sans résumé — c'est normal, le résumé demande un vrai Ctrl-C, vérifié à l'étape suivante.

- [ ] **Step 7: Vérifier la boucle réelle, les transitions et le passage en INJOIGNABLE**

Un seul script enchaîne tout le scénario : arrosage, séchage, panne réseau, retour, `Ctrl-C`. Le
`kill -INT` reproduit exactement le `Ctrl-C` de Serge et doit donc déclencher le résumé.

```bash
pkill -f fake_shelly.py ; sleep 1
python3 "$SCRATCH/fake_shelly.py" & sleep 1
python3 scripts/diagnostics/pluie_manual.py monitor --host 127.0.0.1:8099 \
    --interval 0.5 --no-sound --log "$SCRATCH/verif_monitor.log" > "$SCRATCH/verif_ecran.txt" &
MON=$!
sleep 4 ; curl -s 'http://127.0.0.1:8099/set?id=1&state=true'  >/dev/null   # arrosage
sleep 8 ; curl -s 'http://127.0.0.1:8099/set?id=1&state=false' >/dev/null   # séchage
sleep 4 ; pkill -f fake_shelly.py                                           # panne réseau
sleep 4 ; python3 "$SCRATCH/fake_shelly.py" & sleep 4                       # retour réseau
kill -INT $MON ; sleep 1
echo "=== JOURNAL ===" ; cat "$SCRATCH/verif_monitor.log"
```

Attendu dans le journal — quatre transitions horodatées, encadrées par `# campagne démarrée` et
`# campagne arrêtée` :

```
SEC         -> PLUIE       (état précédent tenu 4 s)
PLUIE       -> SEC         (état précédent tenu 8 s)
SEC         -> INJOIGNABLE (état précédent tenu 4 s)
INJOIGNABLE -> SEC         (état précédent tenu 4 s)
```

Les durées peuvent dévier d'une seconde (période de polling), pas davantage. Points à contrôler :

- l'épisode PLUIE dure bien **~8 s**, la valeur qui alimentera `clear_delay_s` en conditions réelles ;
- le passage en INJOIGNABLE apparaît **et le programme a continué de poller** — les deux dernières
  lignes le prouvent. Une coupure Wi-Fi ne doit pas tuer une campagne en cours.

Puis vérifier le résumé, imprimé sur la sortie standard capturée :

```bash
tail -8 "$SCRATCH/verif_ecran.txt"
```

Attendu : le bloc `=== RÉSUMÉ ===` annonçant **1 épisode PLUIE d'environ 8 s** et le chemin du journal.

- [ ] **Step 8: Vérifier le rendu visuel et sonore à l'œil**

Les codes ANSI ne se jugent pas dans un fichier redirigé. Relancer 20 secondes en interactif, cette
fois **avec le son**, pendant que le faux Shelly tourne encore :

```bash
timeout 20 python3 scripts/diagnostics/pluie_manual.py monitor --host 127.0.0.1:8099 --no-log
```

Attendu : bandeau **vert `SEC`** occupant toute la largeur, détail `id=0 SEC · id=1 SEC` en dessous,
compteur « depuis » qui s'incrémente, écran **redessiné en place sans défiler**. Arroser depuis un
autre appel pour entendre le bip :

```bash
curl -s 'http://127.0.0.1:8099/set?id=1&state=true' >/dev/null
```

Attendu : bascule **rouge `PLUIE`** + bip montant, la transition apparaissant dans « Dernières
transitions ».

- [ ] **Step 9: Formater, linter, committer**

```bash
uv run --extra dev ruff format scripts/diagnostics/pluie_manual.py
uv run --extra dev ruff check scripts/diagnostics/pluie_manual.py
git add scripts/diagnostics/pluie_manual.py
git commit -m "feat(pluie): boucle monitor, bandeau ANSI, bips aux transitions et mode démo"
```

---

## Task 5: Mode d'emploi terrain

Ajout par rapport à la spec, assumé : sans marche à suivre, les cinq réponses attendues du §2 de la spec n'arriveront pas d'une seule sortie. Le texte est écrit **pour Serge**, pas pour un développeur.

**Files:**
- Modify: `scripts/diagnostics/README.md`

- [ ] **Step 1: Repérer où insérer**

```bash
grep -n "^### " scripts/diagnostics/README.md
```

Attendu : la liste des scripts numérotés. La nouvelle section prend le numéro suivant, à la fin de la série.

- [ ] **Step 2: Écrire la section**

Ajouter à la suite du dernier bloc `### N. ...` (remplacer `N` par le numéro suivant relevé à l'étape 1) :

````markdown
### N. `pluie_manual.py`

**Objectif** : valider sur le terrain le capteur de pluie MH-RD lu par le Shelly Plus Uni (192.168.1.87), avec signal lumineux et sonore — l'écran d'exploitation est à l'intérieur, le capteur dehors.

**Prérequis** : aucun. Python 3 stdlib pure, aucune dépendance, aucune config. Se lance depuis n'importe quelle machine du réseau local — de préférence le portable emporté à côté du capteur.

**Marche à suivre**

1. **Avant de sortir**, vérifier que le son fonctionne sur cette machine :
   ```bash
   python3 scripts/diagnostics/pluie_manual.py monitor --demo
   ```
   Trois signaux doivent être audibles : montant (sec → pluie), descendant (pluie → sec), trois coups graves (Shelly injoignable). Si le programme annonce `son : BEL terminal`, le bip dépend de l'émulateur : monter le volume, ou changer de machine. `Ctrl-C` pour sortir.

2. **Identifier l'entrée et la polarité** — la commande du verre d'eau :
   ```bash
   python3 scripts/diagnostics/pluie_manual.py read
   ```
   Arroser la plaque, relancer. L'entrée dont l'état change est celle du capteur. Si l'interprétation est à l'envers (`PLUIE` quand c'est sec), ajouter `--invert` à toutes les commandes suivantes.

3. **Régler le trimpot** : tourner dans le sens des aiguilles d'une montre augmente la sensibilité. Chercher le point où quelques gouttes suffisent à faire basculer, sans que la rosée du matin déclenche.

4. **Campagne de mesure** — c'est elle qui donne le temps de séchage :
   ```bash
   python3 scripts/diagnostics/pluie_manual.py monitor
   ```
   Arroser franchement, **noter l'heure du dernier arrosage**, puis laisser tourner sans y toucher jusqu'au retour au vert. `Ctrl-C` affiche le résumé : la durée de l'épisode PLUIE le plus long est le temps de séchage recherché.

**Ce qu'il faut nous renvoyer** : le bloc `=== RÉSUMÉ ===` affiché au `Ctrl-C`, le fichier `pluie_test_<horodatage>.log` créé dans le répertoire courant, et la réponse à ces deux questions : quelle entrée (`id=0` ou `id=1`) porte le capteur, et `--invert` a-t-il été nécessaire.

**Options** : `--host` (IP du Shelly), `--input {0,1,both}`, `--interval` (secondes entre deux lectures), `--invert`, `--no-sound`, `--log CHEMIN`, `--no-log`, `--demo`.

**Note** : ce script ne pilote rien et ne décide rien — il lit et il affiche. Le capteur n'est pas encore branché à l'automatisation du cimier.
````

- [ ] **Step 3: Relire le rendu**

```bash
tail -45 scripts/diagnostics/README.md
```

Attendu : la section s'affiche avec les blocs de code correctement fermés, et les commandes copiables telles quelles.

- [ ] **Step 4: Committer**

```bash
git add scripts/diagnostics/README.md
git commit -m "docs(pluie): mode d'emploi terrain du test capteur de pluie"
```

---

## Après le plan

- [ ] **Nettoyer les traces de vérification**

```bash
rm -f "$SCRATCH"/verif_*.log ; pkill -f fake_shelly.py ; git status --short
```

Attendu : aucun fichier `pluie_test_*.log`, `verif_*.log` ni `fake_shelly.py` dans `git status`. Ces artefacts ne doivent jamais entrer dans le dépôt.

- [ ] **Push**

Passer par la skill `pre-push`, qui tranchera le bump de `pyproject.toml`. Position de départ pour cette décision : **pas de bump**. Ce cycle n'ajoute qu'un script de diagnostic, hors de tout chemin d'exécution de l'application — rien à proposer en mise à jour OTA. Si `pre-push` conclut autrement, suivre `pre-push`.

- [ ] **Transmettre à Serge**

Lui envoyer la section « Marche à suivre » du README. Les cinq réponses attendues sont listées dans « Ce qu'il faut nous renvoyer ».

**Le cycle suivant ne démarre qu'au retour de Serge** : `ShellyRainWeatherProvider`, fermeture d'urgence sur pluie, point météo UI. Les conventions (entrée, polarité, `clear_delay_s`) seront figées dans `data/config.json` à partir de ses mesures — jamais devinées ici.
