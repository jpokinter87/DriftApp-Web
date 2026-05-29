# Bloc 3 — Doc/firmware capteur-only + dette T4 backend

**Date :** 2026-05-29
**Auteur :** JP (brainstorming Claude/Opus 4.7)
**Statut :** Validé — prêt pour plan d'implémentation
**Périmètre :** Chantier cimier pivot Shelly, items actionnables sans terrain.

---

## 1. Contexte

Bloc 1 (fondations simulation, mergé local commits `50f52d8` → `b239ee0`) et
Bloc 2 (orchestration/cinématique Shelly/garde-fou/logging, mergé local
commits `7007880` → `a4d94bf`) sont **terminés en local**, **non poussés sur
`origin/main`**. Suite globale verte (1132/0). Le firmware Pico W est désormais
**capteur-only** (v0.2.0, protocole 2) ; l'orchestration moteur vit côté
`cimier_service` via 2 Shelly (MOT + UPDN).

Le backlog post-Bloc 2 contient 6 items (cf. mémoire
`project_cimier_shelly_pivot_definitive_spec`). Bloc 3 cible **les 2 items
100 % actionnables sans validation terrain Serge** :

1. **Doc/firmware on-device** périmée sur ~30 % du contenu (références à
   STEP/DIR, microsteps, endpoints `POST /open|/close|/stop`, `invert`,
   `step_generator.py`, `ramp.py`).
2. **Dette T4** : guard manquant `cycle_timeout_s <= 0` + ambiguïté
   `result="ok"` entre cycle nominal réussi et cycle interrompu par stop
   utilisateur.

Reportés en Bloc 4 final (post-validation terrain) : latence stop HTTP,
IPs définitives DHCP, bump `pyproject.toml` 6.4.0 → 6.5.0, push
`origin/main`.

## 2. Objectifs

- **G1 — Doc firmware fidèle au code** : un Serge qui arrive sur le projet
  doit pouvoir flasher un Pico W, le câbler et débugger les fins de course en
  suivant uniquement `firmware/cimier/README.md`, sans tomber sur une
  référence à un endpoint ou un fichier supprimé.
- **G2 — Distinction logs cycles** : un cycle terminé par STOP utilisateur
  doit être distinguable d'un cycle nominal réussi dans les journaux
  d'orchestration, sans rouvrir l'IPC ni croiser plusieurs sources.
- **G3 — Refus net config invalide** : un `cycle_timeout_s <= 0` doit faire
  échouer le démarrage du service avec un message explicite, pas dégénérer
  silencieusement en sortie immédiate de la boucle de polling.

## 3. Architecture cible

### 3.1 Section 1 — Doc/firmware capteur-only

**Fichiers touchés :**

| Fichier | Action | Volume |
|---|---|---|
| `firmware/cimier/README.md` | Réécriture from-scratch | 601 → ~180 LOC |
| `firmware/cimier/main.py` | Patch 2 commentaires WDT obsolètes | ~6 LOC |
| `firmware/cimier/tests/*.sh` (5 fichiers) | `git rm -f` | -5 fichiers |
| `~/.claude/projects/.../memory/project_cimier_shelly_pivot_definitive_spec.md` | Retrait mention `ramp.py orphelin` (fichier déjà absent) | ~1 LOC |

**Nouveau README — sommaire (~180 LOC, structure cible) :**

1. **Rôle** — Pico W = capteur fins de course seul (v0.2.0, protocole 2,
   pivot Shelly). Renvoi vers
   `docs/superpowers/specs/2026-05-23-cinematique-shelly-cimier-garde-fou-design.md`
   pour l'orchestration moteur Shelly.
2. **Pré-requis hardware** — Pico W + MicroPython 1.20+, 2 fins de course NC
   sur GP14 / GP15 + GND switches, alim Pico W 12 V permanente (cascade
   Shelly 220 V coupée fin de session, le Pico reste vivant).
3. **Procédure flash** — Bootsel + drag-n-drop `.uf2` MicroPython 1.20+,
   puis `mpremote cp main.py cimier_controller.py secrets.py :`.
4. **`secrets.py`** — Template `WIFI_SSID` + `WIFI_PASSWORD` (uniquement,
   pas d'IP statique : l'IP est fixée côté DHCP routeur).
5. **Endpoints réels (2 GET seuls)** :
   - `GET /status` → `{state, open_switch, closed_switch, error_message}`
   - `GET /info` → `{firmware_version, protocol_version, role, wifi_rssi, ...}`

   Note explicite : depuis v0.2.0, `POST /open`, `POST /close`, `POST /stop`,
   `POST /config` et tous les endpoints `/diag/*` ont été **supprimés**
   (orchestration moteur déplacée côté `cimier_service` via Shelly).
6. **Debug terrain** — 2 snippets `curl` (status, info) + recette pour
   simuler une fin de course en jumpant GP14 ou GP15 vers GND switches.
   Aucun script shell maintenu.
7. **Câblage Shelly externe (récapitulatif)** — Diagramme ASCII court
   rappelant la cascade `SHELLY-1-24 → SHELLY-1-MOT → SHELLY-1-UPDN →
   DM556T → moteur` avec renvoi vers la spec pour les détails (pas de
   doc Shelly dans `firmware/cimier/`).
8. **Watchdog** — 1 paragraphe : WDT hardware 8000 ms, fenêtre de
   safe-boot 3 s au démarrage pour reprise REPL.

**`main.py` — patch commentaires WDT obsolètes :**

```
ligne 197 : "50 ms < 200 ms WDT donc safe"
         → "50 ms ≪ 8000 ms WDT donc safe"
ligne 267 : "un WDT 200 ms reset le Pico avant la fin"
         → "un WDT court reset le Pico avant la fin (WDT armé après
            WiFi, voir étape 4 plus bas)"
```

(La constante `WDT_TIMEOUT_MS = 8000` ligne 53 est déjà correcte. Les
docstrings ligne 17 et le commentaire ligne 49 le sont aussi.)

**Scripts `tests/*.sh`** : `git rm -f firmware/cimier/tests/{boucle_10_rst,boucle_60_status,cycle_trace,test,test_discrim}.sh`.
Pas de remplacement — la vérification se fait via curl documenté dans le
nouveau README, et la suite pytest backend couvre déjà le cycle
bout-en-bout via simulator (8 tests `TestFullCycleViaSimulator`, T7 commit
`31db797`).

**Mémoire `project_cimier_shelly_pivot_definitive_spec.md`** : retirer la
mention `firmware/cimier/ramp.py orphelin` du backlog ligne 44 (fichier
déjà absent, vérifié `ls`).

### 3.2 Section 2 — Dette T4 backend

**Fichiers touchés :**

| Fichier | Action |
|---|---|
| `core/config/config_loader.py` | Ajout `__post_init__` à `CimierConfig` (guard `cycle_timeout_s > 0`) |
| `services/cimier_service.py` | Propagation `_poll_outcome` jusqu'au log `cycle_end`, distinction `result=stopped` |
| `tests/test_config_loader.py` | +1 test paramétré (guard) |
| `tests/test_cimier_service.py` | +1 test (`result=stopped`) |

**Fix A — `result="ok"` ambigu** (`services/cimier_service.py:747-754`) :

État actuel :

```python
if error_message == "cycle_timeout":
    result = "timeout"
elif error_message == "":
    # Soit cycle nominal OK, soit interruption stop → traités comme ok.
    result = "ok"
else:
    result = "error"
```

`_poll_target_switch` retourne pourtant déjà `"stopped"` explicitement
(lignes 786, 796) mais l'info est perdue à l'agrégation. État cible :
conserver l'outcome du poll jusqu'au log final.

```python
# Pseudocode cible (l'implémentation exacte est laissée au plan)
if error_message == "cycle_timeout":
    result = "timeout"
elif poll_outcome == "stopped":
    result = "stopped"
elif error_message == "":
    result = "ok"
else:
    result = "error"
```

**Pas de propagation au sous-dict IPC `current_status`** : aucun nouveau
champ `result_kind` exposé au frontend (YAGNI — le log structuré
`cimier_event=cycle_end ... result=stopped` suffit au diagnostic à
distance, et le frontend n'a pas besoin de distinguer stop / nominal
pour son rendu actuel).

**Fix B — `cycle_timeout_s <= 0` non gardé** :

`CimierConfig` (`core/config/config_loader.py:246-274`) est un `@dataclass`
mutable sans `__post_init__`. Cible :

```python
def __post_init__(self) -> None:
    if self.cycle_timeout_s <= 0:
        raise ValueError(
            f"cimier.cycle_timeout_s doit être > 0, "
            f"reçu {self.cycle_timeout_s}"
        )
```

Refus net au démarrage du service (avant tout cycle), message explicite
qui pointe vers la clé fautive dans `data/config.json`. Pas de
backward-compat : un fichier avec `cycle_timeout_s: 0` doit se faire
recadrer.

**Tests cibles** (périmètre restreint conformément à
`feedback_tests_scope`) :

- `tests/test_config_loader.py` — `test_cimier_config_rejects_cycle_timeout_zero_or_negative`,
  paramétré `[-1.0, 0.0, 0]`.
- `tests/test_cimier_service.py` — `test_cycle_end_logs_result_stopped_when_stop_during_polling`,
  via la fixture `simulator` existante (T7) : on déclenche un STOP
  pendant que le mécanisme est entre les 2 butées, on assert que le
  log final est `cycle_end ... result=stopped`.

`TestOrchestrationLogging` (T5, `f79a314`) verrouille déjà
`cycle_end ... result=ok` pour le cycle nominal — il reste vert sans
modification car le mapping `_poll_outcome == "ok"` + `error_message == ""`
→ `result="ok"` est préservé.

## 4. Critères de succès

- `firmware/cimier/README.md` ne contient plus aucune référence à
  `POST /open`, `POST /close`, `POST /stop`, `POST /config`, `/diag`,
  `invert`, `STEP/DIR`, `DM560T`, `step_generator.py`, `ramp.py`,
  `microsteps`, ni à des scripts `tests/*.sh` (vérifié par `grep`).
- `firmware/cimier/tests/` n'existe plus dans l'index Git.
- `firmware/cimier/main.py` : aucune mention résiduelle d'un `WDT 200 ms`
  dans les commentaires (lignes 197 et 267 patchées). Les autres
  occurrences de `200` non liées au WDT (ex. `time.sleep_ms(200)` ligne
  99 lié au power management WiFi `pm=0xA11140`) restent inchangées.
- Mémoire `project_cimier_shelly_pivot_definitive_spec.md` : ligne
  backlog `firmware/cimier/ramp.py orphelin` retirée.
- `CimierConfig(cycle_timeout_s=0)` lève `ValueError` avec message
  contenant `"cycle_timeout_s"` et `"> 0"`.
- `cimier_service` log `cycle_end ... result=stopped` quand un STOP
  utilisateur interrompt le polling, et `result=ok` quand le cycle
  atteint nominalement la butée cible.
- Suite tests cimier_service + config_loader : 100 % verte. Suite globale :
  1132 → 1134 passés, 0 fail. Lint `ruff check` + format clean.

## 5. Hors scope

- Latence HTTP stop (mesure terrain, attend Serge sous tension).
- IPs définitives DHCP (`motor_shelly.host_motor` / `host_dir`),
  attendent attribution DHCP terrain.
- Bump `pyproject.toml` 6.4.0 → 6.5.0 (en fin de chantier, après
  validation terrain).
- Push `origin/main` (en fin de chantier, après validation terrain).
- Tout nouveau `result_kind` exposé au frontend Django (YAGNI, log
  structuré suffit).
- Refonte des docstrings `cimier_service.py` (Bloc 2 a déjà rafraîchi
  la docstring module).

## 6. Risques et mitigations

| Risque | Probabilité | Mitigation |
|---|---|---|
| Réécriture README perd une info utile (ex : variante de câblage) | Moyenne | Diff côte-à-côte ancien/nouveau avant suppression définitive ; les variantes obsolètes restent en histoire Git. |
| `_poll_outcome` propagé via une nouvelle variable casse `TestOrchestrationLogging` | Faible | Le test verrouille les chaînes de log existantes, pas les variables internes ; tant que `result=ok` reste émis sur cycle nominal il reste vert. À vérifier en RED-GREEN-REFACTOR. |
| Guard `__post_init__` casse un test existant qui instancie `CimierConfig(cycle_timeout_s=0)` | Faible | Grep ciblé sur `cycle_timeout_s=0` dans `tests/` avant implémentation ; correction des fixtures fautives si présentes. |
| Suppression scripts `tests/*.sh` retire un outil que Serge utilisait sur site | Faible | Scripts non commités (cf. mémoire), donc inexistants pour Serge. Les snippets curl du nouveau README couvrent l'usage. |

## 7. Plan d'exécution attendu

Le plan détaillé sera produit par `superpowers:writing-plans`. Structure
attendue : ~6-8 tâches TDD (RED → GREEN → REFACTOR → COMMIT par tâche,
**1 commit par tâche, pas de push**) :

1. Section 1 / README from-scratch (gros commit doc — pas de tests).
2. Section 1 / patch `main.py` 2 commentaires WDT.
3. Section 1 / `git rm` scripts `tests/*.sh`.
4. Section 1 / patch mémoire (retrait mention `ramp.py`).
5. Section 2 / Fix B — guard `cycle_timeout_s > 0` (test RED → impl → GREEN).
6. Section 2 / Fix A — propagation `result=stopped` (test RED → impl → GREEN).
7. Lint final `ruff format` + `ruff check` + suite restreinte verte.

Aucun bump version, aucun push. La validation terrain Serge clôt le
chantier global et déclenche le Bloc 4 final (latence + IPs + bump +
push).
