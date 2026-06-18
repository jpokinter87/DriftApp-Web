# Nettoyage cimier V3 + intégration des conventions validées — Plan d'implémentation

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Intégrer dans le code applicatif la convention moteur validée terrain (le moteur tourne sur `turn=off` ⇒ `motor_on_relay_state=False` par défaut) et purger les scories documentaires (fantômes Pico W, « 220V », « Gen 3 », « à valider au banc »).

**Architecture:** Le standalone `scripts/diagnostics/cimier_manual.py`, validé du premier coup en terrain (17-18/06), est désormais la source de vérité. On flippe le défaut `motor_on_relay_state` (code + `data/config.json`), on met les tests au diapason, puis on nettoie la documentation et on allège le traçage de débogage hérité des sessions ratées. Aucun changement de flow `_run_cycle`.

**Tech Stack:** Python 3, `uv`, `pytest` (+ `pytest-xdist`), `ruff`. Outils dev via `uv run --extra dev …`.

**Spec de référence :** `docs/superpowers/specs/2026-06-18-cimier-v3-nettoyage-conventions-validees-design.md`

**Règles projet importantes :**
- Commandes Python via `uv run --extra dev …`.
- **Pas de bump `pyproject.toml`** (chantier cimier en cours).
- Pas de valeurs terrain (IP/host) en dur dans le template repo (rester `noop`/vide).
- Commits conventionnels, scope `cimier`, trailer `Co-Authored-By: Claude Opus 4.8 (1M context) <noreply@anthropic.com>`.

---

## Rappel du mapping (à ne pas inverser)

`MotorShelly` API `legacy` : `turn_on()` → `…/relay/0?turn=("on" if motor_on_relay_state else "off")`.
- Validé : le moteur **tourne** sur `turn=off` ⇒ `turn_on()` doit émettre `turn=off` ⇒ **`motor_on_relay_state=False`**.
- `turn_off()` émet alors `turn=on` (moteur stoppé).
- API `rpc` : idem avec `on=true`/`on=false` (`False` ⇒ `turn_on()` émet `on=false`).

`open_dir_state=True` et `switch_reader.invert=True` sont **déjà** conformes : on n'y touche pas.

---

## Task 1 : Intégrer la convention moteur validée (`motor_on_relay_state=False` par défaut)

**Files:**
- Modify: `core/hardware/motor_shelly.py` (défaut ctor ligne ~110 + docstrings des conventions `motor_on_relay_state` / `open_dir_state` + note boot)
- Modify: `core/config/config_loader.py` (défaut `MotorShellyConfig.motor_on_relay_state` ligne ~193)
- Modify: `data/config.json` (`cimier.motor_shelly.motor_on_relay_state` + son commentaire)
- Test: `tests/test_motor_shelly.py`, `tests/test_config_loader.py`

- [ ] **Step 1 : Mettre les tests `test_config_loader.py` au défaut validé (RED)**

Dans `tests/test_config_loader.py`, le test des défauts (autour de la ligne 556) assume `motor_on_relay_state is True`. Le passer à `False` :

```python
        assert ms.open_dir_state is True
        assert ms.motor_on_relay_state is False
```

(Ne PAS toucher aux tests lignes ~572-585 / ~620-626 : ils passent `False` explicitement, restent valides.)

Ajouter en fin de fichier un test qui verrouille la valeur du template repo :

```python
def test_template_config_motor_on_relay_state_is_validated_false():
    """Convention validée terrain (moteur tourne sur turn=off) : le template
    data/config.json doit porter motor_on_relay_state=False par défaut."""
    from core.config.config_loader import ConfigLoader

    config = ConfigLoader().load()
    assert config.cimier.motor_shelly.motor_on_relay_state is False
```

- [ ] **Step 2 : Lancer ces tests, vérifier l'échec**

Run : `uv run --extra dev pytest tests/test_config_loader.py -k "motor_on_relay_state or template_config" -v`
Expected : FAIL (le défaut dataclass et le template valent encore `True`).

- [ ] **Step 3 : Mettre `test_motor_shelly.py` au défaut validé (RED)**

Les tests qui construisent `MotorShelly` **sans** `motor_on_relay_state` assument l'ancien défaut `True`. Inverser leurs assertions de valeur `on=`/`turn=` :

Dans `TestMotorShellyOnOffRpc` :
```python
    def test_turn_on_url_format_uses_motor_host(self):
        mock = make_mock_urlopen()
        sh = MotorShelly(HOST_MOTOR, HOST_DIR, urlopen=mock)
        sh.turn_on()
        url = _called_url(mock)
        assert url == "http://" + HOST_MOTOR + "/rpc/Switch.Set?id=0&on=false"

    def test_turn_off_url_format_uses_motor_host(self):
        mock = make_mock_urlopen()
        sh = MotorShelly(HOST_MOTOR, HOST_DIR, urlopen=mock)
        sh.turn_off()
        url = _called_url(mock)
        assert url == "http://" + HOST_MOTOR + "/rpc/Switch.Set?id=0&on=true"
```
```python
    def test_turn_on_with_safety_timer(self):
        """Filet de sécurité WiFi-drop : Shelly auto-off après N secondes."""
        mock = make_mock_urlopen()
        sh = MotorShelly(HOST_MOTOR, HOST_DIR, urlopen=mock)
        sh.turn_on(timer_s=90.0)
        url = _called_url(mock)
        assert HOST_MOTOR in url
        assert "toggle_after=90" in url
        assert "on=false" in url
```

Dans `TestMotorShellyOnOffLegacy` :
```python
    def test_turn_on_url_format(self):
        mock = make_mock_urlopen()
        sh = MotorShelly(HOST_MOTOR, HOST_DIR, api="legacy", urlopen=mock)
        sh.turn_on()
        assert _called_url(mock) == "http://" + HOST_MOTOR + "/relay/0?turn=off"

    def test_turn_off_url_format(self):
        mock = make_mock_urlopen()
        sh = MotorShelly(HOST_MOTOR, HOST_DIR, api="legacy", urlopen=mock)
        sh.turn_off()
        assert _called_url(mock) == "http://" + HOST_MOTOR + "/relay/0?turn=on"

    def test_turn_on_with_safety_timer_legacy(self):
        mock = make_mock_urlopen()
        sh = MotorShelly(HOST_MOTOR, HOST_DIR, api="legacy", urlopen=mock)
        sh.turn_on(timer_s=90.0)
        url = _called_url(mock)
        assert "timer=90" in url
        assert "turn=off" in url
```

Dans `TestMotorShellyInvertedMotorLogic`, renommer le test du défaut :
```python
    def test_motor_on_relay_state_default_is_false(self):
        sh = MotorShelly(HOST_MOTOR, HOST_DIR, urlopen=make_mock_urlopen())
        assert sh.motor_on_relay_state is False
```

Dans `TestMotorShellySequences`, les cycles par défaut émettent désormais `on=false` pour MOTOR :
```python
    def test_open_cycle_set_direction_then_turn_on(self):
        """Ouverture : set_direction(True) → turn_on(timer_s=90).
        URL 1 sur DIR Shelly, URL 2 sur MOTOR Shelly avec timer."""
        mock = make_mock_urlopen()
        sh = MotorShelly(HOST_MOTOR, HOST_DIR, urlopen=mock)
        sh.set_direction(open_direction=True)
        sh.turn_on(timer_s=90.0)
        urls = _called_urls(mock)
        assert len(urls) == 2
        assert HOST_DIR in urls[0]
        assert "on=true" in urls[0]
        assert HOST_MOTOR in urls[1]
        assert "on=false" in urls[1]
        assert "toggle_after=90" in urls[1]

    def test_close_cycle_set_direction_then_turn_on(self):
        mock = make_mock_urlopen()
        sh = MotorShelly(HOST_MOTOR, HOST_DIR, urlopen=mock)
        sh.set_direction(open_direction=False)
        sh.turn_on(timer_s=90.0)
        urls = _called_urls(mock)
        assert HOST_DIR in urls[0]
        assert "on=false" in urls[0]
        assert HOST_MOTOR in urls[1]
        assert "on=false" in urls[1]
```

Préserver la couverture de la branche `True` (relais ON = moteur ON) en ajoutant une classe explicite (le défaut ne la teste plus) :
```python
class TestMotorShellyRelayOnConvention:
    """Branche non-défaut : motor_on_relay_state=True (relais ON = moteur ON).
    Couverture conservée bien que la convention validée terrain soit False."""

    def test_turn_on_relay_on_rpc(self):
        mock = make_mock_urlopen()
        sh = MotorShelly(HOST_MOTOR, HOST_DIR, motor_on_relay_state=True, urlopen=mock)
        sh.turn_on()
        assert "on=true" in _called_url(mock)

    def test_turn_on_relay_on_legacy(self):
        mock = make_mock_urlopen()
        sh = MotorShelly(
            HOST_MOTOR, HOST_DIR, api="legacy", motor_on_relay_state=True, urlopen=mock
        )
        sh.turn_on()
        assert _called_url(mock) == "http://" + HOST_MOTOR + "/relay/0?turn=on"
```

Reformuler le bloc de commentaire au-dessus de `TestMotorShellyInvertedMotorLogic` (≈ lignes 216-221) pour qu'il décrive le **défaut validé** et non un « cas Serge inversé » :
```python
# ----------------------------------------------------------------------
# Convention moteur validée terrain (défaut) : motor_on_relay_state=False
# ----------------------------------------------------------------------
# Le moteur tourne quand le circuit MOTOR est OUVERT (oscillateur câblé NC).
# turn_on() met donc le relais à OFF (turn=off) pour démarrer, et turn_off()
# le met à ON (turn=on) pour arrêter. Validé du premier coup terrain 17-18/06.
```

- [ ] **Step 4 : Lancer `test_motor_shelly.py`, vérifier l'échec**

Run : `uv run --extra dev pytest tests/test_motor_shelly.py -v`
Expected : FAIL sur les tests réécrits (le code émet encore `on=true`/`turn=on` par défaut) ; la nouvelle classe `TestMotorShellyRelayOnConvention` passe déjà.

- [ ] **Step 5 : Flipper le défaut dans `core/hardware/motor_shelly.py`**

Constructeur (≈ ligne 110) :
```python
        open_dir_state: bool = True,
        motor_on_relay_state: bool = False,
```

Remplacer la docstring de la convention `motor_on_relay_state` (le bloc actuel décrivant True=défaut/NO et False=cas Serge) par :
```
      ``motor_on_relay_state`` :
        - False (défaut, **convention validée terrain 17-18/06**) : le moteur
          tourne quand le relais MOTOR est **ouvert** (oscillateur câblé NC).
          ``turn_on()`` met donc le relais à OFF (``turn=off`` / ``on=false``)
          pour démarrer, et ``turn_off()`` à ON pour arrêter.
        - True : convention « intuitive » NO (contact fermé = circuit
          alimenté). ``turn_on()`` met le relais à ON. Non utilisé en V3.
```

Remplacer la docstring de la convention `open_dir_state` par :
```
      ``open_dir_state`` :
        - True (défaut, convention validée terrain) :
          ``set_direction(open_direction=True)`` met le relais DIR à ON
          (``turn=on`` = sens montée / ouverture).
        - False : convention inversée (DPDT externe câblé dans l'autre sens).
```

Remplacer la « Note opérationnelle Shelly Gen 3 — état au boot » par :
```
    Note opérationnelle Shelly Gen 1 — état au boot :
        Avec la convention validée (``motor_on_relay_state=False``), le
        ``default_state`` du Shelly MOTOR doit être réglé côté Shelly UI à
        **« ON »** (relais fermé) pour que le moteur reste à l'arrêt au boot
        du Shelly. À régler une fois lors de l'install terrain ; indépendant
        du code Python.
```

- [ ] **Step 6 : Flipper le défaut dans `core/config/config_loader.py`**

`MotorShellyConfig` (≈ ligne 193) :
```python
    open_dir_state: bool = True
    motor_on_relay_state: bool = False
```

- [ ] **Step 7 : Mettre `data/config.json` au défaut validé**

Section `cimier.motor_shelly` : passer `"motor_on_relay_state": true` → `false`, et remplacer le commentaire `_comment` de la section pour refléter la vérité validée :
```json
    "motor_shelly": {
      "_comment": "SHELLY-1-MOT (.85) + SHELLY-1-UPDN (.86), API legacy. Conventions validées terrain 17-18/06 : moteur tourne quand relais MOT turn=off (motor_on_relay_state=false), UP=turn=on (open_dir_state=true). host_motor/host_dir vides → NoopMotorShelly tant que non déployé.",
      "host_motor": "",
      "host_dir": "",
      "relay_motor": 0,
      "relay_dir": 0,
      "open_dir_state": true,
      "motor_on_relay_state": false,
      "api": "legacy",
      "timer_safety_sec": 90.0
    }
```

- [ ] **Step 8 : Lancer la suite ciblée, vérifier le vert**

Run :
```bash
uv run --extra dev pytest tests/test_motor_shelly.py tests/test_config_loader.py -v
```
Expected : PASS (tous). En cas d'échec résiduel ailleurs, lancer aussi `tests/test_cimier_service.py` (attendu vert : il passe `motor_on_relay_state` explicitement ou utilise `SimMotorShelly`).

- [ ] **Step 9 : Format + lint**

Run : `uv run --extra dev ruff format core/hardware/motor_shelly.py core/config/config_loader.py tests/test_motor_shelly.py tests/test_config_loader.py && uv run --extra dev ruff check core/hardware/motor_shelly.py core/config/config_loader.py tests/test_motor_shelly.py tests/test_config_loader.py`
Expected : aucune erreur.

- [ ] **Step 10 : Commit**

```bash
git add core/hardware/motor_shelly.py core/config/config_loader.py data/config.json tests/test_motor_shelly.py tests/test_config_loader.py
git commit -m "$(cat <<'EOF'
fix(cimier): convention moteur validée terrain — motor_on_relay_state=False par défaut

Le moteur tourne sur turn=off (oscillateur câblé NC, validé terrain 17-18/06).
Flip du défaut dans MotorShelly + MotorShellyConfig + data/config.json. Cause
racine probable du sens/mouvement erratique des sessions 14/06.

Co-Authored-By: Claude Opus 4.8 (1M context) <noreply@anthropic.com>
EOF
)"
```

---

## Task 2 : Purger les scories documentaires (Pico W / 220V / Gen 3 / à valider)

**Files (commentaires/docstrings uniquement — 0 logique) :**
- Modify: `core/hardware/motor_shelly.py` (docstring de module, en-tête)
- Modify: `services/cimier_service.py` (220V→24V ; ghost `pico_state` ; commentaire dev-mode)
- Modify: `core/hardware/power_switch.py` (docstring de module)
- Modify: `core/hardware/shelly_switch_reader.py` (docstring de module)
- Modify: `core/hardware/weather_provider.py` (commentaires)
- Modify: `core/config/config_loader.py` (docstrings résiduelles Pico/220V)
- Modify: `web/cimier/views.py` (commentaire 220V)
- Modify: `data/config.json` (« à VALIDER AU BANC »)
- Modify: `tests/test_motor_shelly.py` (docstring d'en-tête)

- [ ] **Step 1 : Remplacer la docstring de module de `core/hardware/motor_shelly.py`**

Remplacer tout le bloc docstring de tête (du `"""` ligne 1 au `"""` ligne 40) par :
```python
"""
Pilote moteur cimier via 2 relais Shelly (archi V3 tout-Shelly).

Contexte
--------
Le pilotage STEP/DIR du moteur cimier n'a jamais réussi à le faire tourner ;
le circuit de commande manuel (oscillateur + 2 interrupteurs : ON/OFF moteur
+ DPDT direction) le fait tourner de façon reproductible. Le pivot V3
automatise ce circuit avec des Shelly Gen 1 (contact sec) :
  - Shelly MOTOR (.85) : ON/OFF moteur (remplace l'interrupteur manuel).
  - Shelly DIR   (.86) : pilote un relais DPDT externe qui permute la ligne
                         DIR (sens du moteur).
Les fins de course haut/bas sont lues via un Shelly Uni+ (.84), cf.
``core/hardware/shelly_switch_reader.py``.

`cimier_service` (côté Pi) orchestre :
  1. set_direction(open_direction=True) → relais DIR positionné
  2. turn_on(timer_s=90) → moteur démarre, kill auto Shelly à 90 s en cas de
     WiFi-drop (filet de sécurité hardware, indépendant du Pi)
  3. polling des butées (Shelly Uni+) jusqu'à fin de course
  4. turn_off() → moteur stoppé

Le moteur tourne à vitesse fixe (potard de l'oscillateur) ; la précision
positionnelle vient des fins de course mécaniques, pas des pas. Suffisant
pour un cimier (mécanisme binaire open/closed).

API Shelly supportée
--------------------
- ``api="legacy"`` (terrain V3) : Shelly Gen 1
    URL : ``http://<host>/relay/<relay>?turn=<on|off>[&timer=<N>]``
- ``api="rpc"`` (défaut) : Shelly Gen 2 / Plus / Pro
    URL : ``http://<host>/rpc/Switch.Set?id=<relay>&on=<true|false>[&toggle_after=<N>]``

L'argument `urlopen` permet d'injecter un mock pour les tests.
"""
```

- [ ] **Step 2 : Nettoyer `services/cimier_service.py` (220V→24V + ghost pico_state)**

Appliquer ces remplacements (chaîne exacte → nouvelle) :
- `power_switch.turn_on()`` (Shelly 220V cascade).` → `power_switch.turn_on()`` (Shelly 24V).`
- `220V, invariant).` → `24V, invariant).`
- `appelés dans ``finally`` (sécurité 220V + état moteur connu).` → `appelés dans ``finally`` (sécurité 24V + état moteur connu).`
- `# Phase A : power_on (Shelly 220V cascade).` → `# Phase A : power_on (Shelly 24V).`
- `# Cleanup garanti : motor_off + power_off (invariant 220V).` → `# Cleanup garanti : motor_off + power_off (invariant 24V).`

Pour le ghost `pico_state` (≈ ligne 945, docstring de `_derive_current_cimier_state`), remplacer la phrase :
```
        Archi Shelly (Bloc 2) : le Pico est capteur-only — pas de ``pico_state``
        legacy. On dérive l'état du cimier des derniers ``open_switch`` /
        ``closed_switch`` observés.
```
par :
```
        Archi V3 tout-Shelly : on dérive l'état du cimier des derniers
        ``open_switch`` / ``closed_switch`` observés (Shelly Uni+).
```

Dans le commentaire dev-mode (`_apply_dev_mode_overrides`, ≈ ligne 1010), le bloc reste correct (il décrit le simulateur) ; aucune mention Pico à retirer ici. Ne pas modifier.

- [ ] **Step 3 : Réécrire la docstring de module de `core/hardware/power_switch.py`**

La docstring décrit l'ancienne cascade « 220V→12V » + Pico W (abandonnée). La remplacer par la réalité V3 (un Shelly Gen 1 coupant l'alim 24V du module cimier entre les cycles). Remplacer le bloc docstring de tête par :
```python
"""
Coupe / rétablit l'alimentation 24V du module cimier via un Shelly (archi V3).

Le Shelly SHELLY-1-24V (.83) alimente le module cimier (contrôleur autonome
STEP + DM556T). ``cimier_service`` le coupe hors cycle (économie / sécurité)
et le rétablit en début de cycle, avec une attente d'appairage WiFi des
Shelly aval (MOTOR/DIR) avant d'énergiser le moteur.

API supportée :
  - ``api="legacy"`` (Gen 1) : ``http://<host>/relay/<id>?turn=<on|off>``
  - ``api="rpc"`` (Gen 2/Plus) : ``http://<host>/rpc/Switch.Set?id=<id>&on=<bool>``

Aucune valeur terrain (IP / index) en dur — tout via le constructeur, rempli
par ``PowerSwitchConfig`` depuis ``data/config.json``.

L'argument ``urlopen`` permet d'injecter un mock pour les tests.
"""
```
⚠️ Avant d'écrire : ouvrir le fichier et vérifier que ce bloc ne référence aucune fonction/constante définie dans la docstring elle-même (pure prose). Conserver toute ligne de code sous la docstring intacte.

- [ ] **Step 4 : Nettoyer `core/hardware/shelly_switch_reader.py` (ghost Pico)**

Remplacer la ligne 3 :
```
Remplace le Pico W capteur : les 2 microswitches (Haut/Bas) sont câblés sur
```
par :
```
Archi V3 : les 2 microswitches (Haut/Bas) sont câblés sur
```

- [ ] **Step 5 : Nettoyer `core/hardware/weather_provider.py` (ghost Pico)**

Remplacer les mentions « capteur sur Pico W cimier » / « PicoWWeatherProvider » dans les **commentaires/docstring** par une formulation neutre (« capteur cimier »). ⚠️ Si une classe `PicoWWeatherProvider` existe réellement (pas juste un commentaire), **ne pas la renommer/supprimer** dans cette tâche — se limiter aux commentaires, et le signaler en fin de tâche.

Exemple de remplacement (commentaire ligne ≈14) :
```
capteurs ultérieur (v6.4+, capteur cimier d'après l'interview de
```
et (ligne ≈23) :
```
  - (futur) provider capteur cimier : humidité / pluie (backlog météo,
```

- [ ] **Step 6 : Nettoyer les docstrings résiduelles de `core/config/config_loader.py`**

Remplacements (chaîne exacte → nouvelle), **commentaires/docstrings uniquement** :
- `"""Configuration du switch d'alimentation cimier (Shelly 220V).` → `"""Configuration du switch d'alimentation cimier (Shelly 24V).`
- `Remplace la génération STEP/DIR via Pico W par 2 Shellys 1 Gen 3` → `Archi V3 : pilotage moteur via 2 Shelly Gen 1 (contact sec)`
- `Remplace le Pico W capteur. Les 2 microswitches Haut/Bas sont lus via les` → `Archi V3 : les 2 microswitches Haut/Bas sont lus via les`
- `220V/12V → polling Pico W ready → re-push invert si non-défaut → /open` → `alim 24V → settle WiFi Shelly → set_direction → motor_on → poll butées`

Ne PAS toucher au champ `boot_poll_timeout_s` (ligne ≈308) ni à son commentaire « legacy (boot Pico) — dette, non utilisé en V3 » : suppression de code mort hors périmètre (à signaler comme backlog).

- [ ] **Step 7 : Nettoyer `web/cimier/views.py` (220V)**

Remplacer dans le commentaire ligne ≈67 :
```
    cycle_poll), passant en `power_off` puis `cooldown` (sécurité 220V).
```
par :
```
    cycle_poll), passant en `power_off` puis `cooldown` (sécurité 24V).
```

- [ ] **Step 8 : Retirer « à VALIDER AU BANC » de `data/config.json`**

Section `cimier._comment` (ligne ≈90) : retirer la mention de validation au banc devenue obsolète. Remplacer :
```json
    "_comment": "Archi V3 tout-Shelly (suppression Pico W). Opt-in (enabled=false). IPs terrain : 24V=.83, Uni+=.84, MOT=.85, UPDN=.86. Conventions inversées (motor_on_relay_state, open_dir_state, switch_reader.invert) à VALIDER AU BANC.",
```
par :
```json
    "_comment": "Archi V3 tout-Shelly. Opt-in (enabled=false). IPs terrain : 24V=.83, Uni+=.84, MOT=.85, UPDN=.86. Conventions validées terrain 17-18/06 (motor_on_relay_state=false, open_dir_state=true, switch_reader.invert=true).",
```

- [ ] **Step 9 : Nettoyer la docstring d'en-tête de `tests/test_motor_shelly.py`**

Remplacer le bloc docstring de tête (lignes 1-16) mentionnant « Pico W » / « Shellys 1 Gen 3 » par :
```python
"""Tests du module core.hardware.motor_shelly.

Archi V3 tout-Shelly : pilotage moteur cimier via 2 Shelly Gen 1 distincts
(1 relais chacun, contact sec) — Shelly MOTOR (ON/OFF) + Shelly DIR (DPDT).

Conventions de test :
  - host MOTOR  : "192.168.1.85"
  - host DIR    : "192.168.1.86"
  - Discrimination motor vs dir = HOST (les 2 Shellys ont chacun un relais
    d'index 0 par défaut → l'index ne discrimine plus).

Pattern miroir de tests/test_power_switch.py : mocks urlopen, format URL,
gestion d'erreurs, support legacy (Gen 1, terrain) et RPC (Gen 2/Plus).
"""
```

- [ ] **Step 10 : Vérifier la propreté (grep) + suite + lint**

Run :
```bash
grep -rn "Pico W\|220V\|Gen 3\|à VALIDER\|à valider\|VALIDER AU BANC" \
  core/hardware/motor_shelly.py services/cimier_service.py core/hardware/power_switch.py \
  core/hardware/shelly_switch_reader.py core/hardware/weather_provider.py \
  core/config/config_loader.py web/cimier/views.py data/config.json tests/test_motor_shelly.py
```
Expected : **aucune sortie** (sauf, tolérée, la ligne `boot_poll_timeout_s` « boot Pico » volontairement conservée — vérifier que c'est la seule occurrence restante).

Run :
```bash
uv run --extra dev pytest tests/test_motor_shelly.py tests/test_power_switch.py \
  tests/test_shelly_switch_reader.py tests/test_config_loader.py tests/test_cimier_service.py -q
uv run --extra dev ruff format core/ services/ web/cimier/ tests/test_motor_shelly.py
uv run --extra dev ruff check core/ services/ web/cimier/ tests/test_motor_shelly.py
```
Expected : tests PASS, ruff propre.

- [ ] **Step 11 : Commit**

```bash
git add core/hardware/motor_shelly.py services/cimier_service.py core/hardware/power_switch.py \
  core/hardware/shelly_switch_reader.py core/hardware/weather_provider.py \
  core/config/config_loader.py web/cimier/views.py data/config.json tests/test_motor_shelly.py
git commit -m "$(cat <<'EOF'
docs(cimier): purge des scories — fantômes Pico W, 220V→24V, Gen 3→Gen 1, "à valider"

Nettoyage documentaire pur (0 logique). L'archi V3 tout-Shelly est en place
depuis 6.7.0 ; les docstrings/commentaires traînaient encore l'ère Pico W et
la cascade 220V/12V abandonnée.

Co-Authored-By: Claude Opus 4.8 (1M context) <noreply@anthropic.com>
EOF
)"
```

---

## Task 3 : Re-documenter `dir_settle`/`timer_safety` + alléger le traçage stop

**Files:**
- Modify: `services/cimier_service.py` (commentaire `dir_settle` ; trim log `stop_command_received`)

- [ ] **Step 1 : Garde — vérifier qu'aucun test ne verrouille le log à retirer**

Run :
```bash
grep -rn "stop_command_received" tests/
```
Expected : **aucune sortie**. Si un test l'asserte, l'adapter (le retirer de l'assertion) au Step 3 plutôt que de supprimer le log.

- [ ] **Step 2 : Reformuler le commentaire `dir_settle` (≈ lignes 672-676)**

Remplacer le bloc de commentaire au-dessus de `dir_settle = float(self._config.dir_settle_s)` par une explication factuelle (sans la narration « mystère 8 ms ») :
```python
            # Settle DPDT : laisser le relais DIR (Shelly UPDN) + le DPDT externe
            # finir de commuter AVANT d'énergiser le moteur. C'est l'équivalent
            # explicite du délai que le standalone (cimier_manual.py) obtient
            # implicitement via sa lecture pré-check entre set_direction et
            # motor_run ; le service ne fait pas cette lecture intermédiaire, d'où
            # ce sleep court pour garantir une bascule mécanique propre du DPDT.
```

- [ ] **Step 3 : Alléger `_check_for_stop_command` (≈ lignes 849-858)**

Le log `poll_stopped source=stop_command` (dans `_poll_target_switch`) trace déjà l'arrêt utilisateur ; le log `stop_command_received id/ts` était l'instrumentation de chasse au « stop fantôme ». Le retirer. Remplacer :
```python
        if action == ACTION_STOP:
            self._last_command_id_value = str(cmd.get("id", ""))
            # Traçage de l'émetteur : id + ts d'émission de la commande stop reçue
            # pendant un cycle (permet de corréler avec le client qui l'a postée).
            logger.info(
                "cimier_event=stop_command_received id=%s ts=%s",
                cmd.get("id", ""),
                cmd.get("ts", ""),
            )
            return cmd
```
par :
```python
        if action == ACTION_STOP:
            self._last_command_id_value = str(cmd.get("id", ""))
            return cmd
```

- [ ] **Step 4 : Suite + lint**

Run :
```bash
uv run --extra dev pytest tests/test_cimier_service.py -q
uv run --extra dev ruff format services/cimier_service.py
uv run --extra dev ruff check services/cimier_service.py
```
Expected : tests PASS (les tests `dir_settle` restent verts — on garde la logique), ruff propre.

- [ ] **Step 5 : Commit**

```bash
git add services/cimier_service.py
git commit -m "$(cat <<'EOF'
refactor(cimier): re-documente dir_settle + retire le traçage du stop fantôme

dir_settle reframé comme l'équivalent explicite du settle naturel du standalone
(sans la narration de débogage). Le log stop_command_received (instrumentation
de chasse au stop fantôme 14/06) est retiré : poll_stopped source=stop_command
trace déjà l'arrêt.

Co-Authored-By: Claude Opus 4.8 (1M context) <noreply@anthropic.com>
EOF
)"
```

---

## Vérification finale (après les 3 tasks)

- [ ] **Suite cimier complète au vert**

Run :
```bash
uv run --extra dev pytest tests/test_motor_shelly.py tests/test_config_loader.py \
  tests/test_cimier_service.py tests/test_power_switch.py tests/test_shelly_switch_reader.py \
  tests/test_cimier_simulator.py tests/test_sim_motor_shelly.py tests/test_cimier_mechanism_sim.py -q
```
Expected : tout PASS.

- [ ] **Grep de propreté global (sources cimier)**

Run :
```bash
grep -rn "Pico W\|220V\|Gen 3\|à valider\|VALIDER AU BANC" \
  core/hardware/motor_shelly.py services/cimier_service.py core/hardware/power_switch.py \
  core/hardware/shelly_switch_reader.py core/hardware/weather_provider.py web/cimier/views.py \
  data/config.json
```
Expected : aucune sortie.

- [ ] **`motor_on_relay_state=False` effectif partout**

Run :
```bash
grep -n "motor_on_relay_state" data/config.json core/config/config_loader.py core/hardware/motor_shelly.py
```
Expected : `data/config.json` → `false` ; défauts code → `False`.

- [ ] **Pas de bump de version** : vérifier que `pyproject.toml` n'a pas été modifié (`git diff --stat pyproject.toml` vide).

---

## Critères de succès (rappel spec)

1. Suite cimier ciblée verte (Tasks 1-3 + vérif finale).
2. `motor_on_relay_state=False` dans `data/config.json` ET défauts code.
3. Grep de propreté : 0 occurrence Pico W / 220V / Gen 3 / à valider dans les sources cimier.
4. `ruff format` + `ruff check` propres.
5. Pas de bump `pyproject.toml`.
6. `dir_settle` / `timer_safety` conservés (verdict 2B) et re-documentés ; traçage stop allégé.

## Hors périmètre (backlog signalé)

- Suppression du champ mort `boot_poll_timeout_s` (`config_loader.py`) — code mort « non utilisé en V3 », à retirer dans une passe dédiée.
- Re-validation terrain du **service** applicatif (un cycle open/close réel via l'UI avec `motor_on_relay_state=false`) — le standalone est validé, le service ne l'a pas encore tourné avec la convention corrigée.
- Bascule éventuelle du défaut `api` de `MotorShelly` (`rpc` → `legacy`) : non traitée (config.json fixe `legacy` explicitement).
