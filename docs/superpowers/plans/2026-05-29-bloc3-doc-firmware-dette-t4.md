# Bloc 3 — Doc/firmware capteur-only + dette T4 backend — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Clôturer le backlog Bloc 3 du chantier cimier pivot Shelly (items 100 % actionnables sans terrain) — refondre la doc firmware Pico W capteur-only, supprimer les scripts shell obsolètes, et résorber la dette T4 backend (guard `cycle_timeout_s > 0` + distinction log `result=stopped`).

**Architecture:** TDD pour les 2 modifs backend (Fix B avant Fix A, du plus simple au plus structurant) ; commits doc/firmware ciblés et indépendants ; aucun bump version, aucun push origin (chantier global non bouclé tant que Serge n'a pas validé terrain).

**Tech Stack:** Python 3.11+ (`@dataclass.__post_init__`), pytest paramétré, `ruff format` + `ruff check`, MicroPython 1.20+ (`firmware/cimier/main.py`), Markdown (README firmware).

**Spec source:** `docs/superpowers/specs/2026-05-29-bloc3-doc-firmware-dette-t4-design.md` (commit `fe368ed`).

**Décisions de cadre (rappel des mémoires) :**
- **Pas de bump `pyproject.toml`** pendant le chantier cimier — `feedback_version_bump` levé via décision JP 23/05.
- **Pas de push `origin/main`** pendant le chantier — Bloc 1+2+3 restent en local, push en Bloc 4 final.
- **Périmètre pytest restreint** aux modules touchés (`feedback_tests_scope`) : `tests/test_cimier_service.py`, `tests/test_config_loader.py`.
- **Aucune IP en dur** dans tout fichier touché (`feedback_no_hardcoded_ips`).
- **Branche de travail** : tout reste sur `main` local (cohérent avec Bloc 1 + Bloc 2 mergés FF sur `main` local). Aucun checkout `-b` à faire.

---

## File Structure

**Modifiés :**
- `core/config/config_loader.py` (~`CimierConfig` ligne 246) : ajout `__post_init__` validant `cycle_timeout_s > 0`.
- `services/cimier_service.py` (`_run_cycle` lignes 553-774) : nouvelle variable locale `poll_outcome` propagée du try jusqu'au mapping `result=` du log `cycle_end`.
- `tests/test_config_loader.py` : +1 test paramétré `test_cimier_config_rejects_cycle_timeout_zero_or_negative`.
- `tests/test_cimier_service.py` : +1 test `test_cycle_end_logs_result_stopped_when_stop_during_polling` (s'inspire de `test_stop_command_during_polling_aborts_cycle` ligne 1994).
- `firmware/cimier/main.py` (commentaires lignes 197 et 267).

**Supprimés (git rm) :**
- `firmware/cimier/tests/boucle_10_rst.sh`
- `firmware/cimier/tests/boucle_60_status.sh`
- `firmware/cimier/tests/cycle_trace.sh`
- `firmware/cimier/tests/test.sh`
- `firmware/cimier/tests/test_discrim.sh`
- (Le dossier `firmware/cimier/tests/` peut rester vide ou être supprimé entièrement si Git le permet — Git ne suit pas les dossiers vides donc la suppression est implicite.)

**Réécrits from-scratch :**
- `firmware/cimier/README.md` : 601 LOC → ~180 LOC capteur-only.

**Hors repo (Edit manuel sans commit Git) :**
- `/home/jp/.claude/projects/-home-jp-PythonProject-Dome-web-v4-6/memory/project_cimier_shelly_pivot_definitive_spec.md` ligne 44 : retrait mention `firmware/cimier/ramp.py orphelin` (fichier déjà absent).

---

## Stratégie d'exécution

Strict TDD pour T1 (Fix B) et T2 (Fix A) : RED → GREEN → REFACTOR → COMMIT par tâche.
T3, T4, T5, T6 sont des modifs documentaires/structurelles sans test : 1 commit par tâche, message conventionnel.
T7 est une vérification finale globale, pas un commit (sauf si `ruff format` propose des reformats sur d'autres fichiers — auquel cas commit séparé `chore(cimier-bloc3): lint final`).

**Ordre choisi :** backend d'abord (T1 → T2, plus risqué et nécessite la suite verte avant de passer à la doc), puis suppression scripts (T3 — geste neutre), puis main.py (T4 — petits commentaires), puis mémoire (T5 — hors repo), puis README from-scratch (T6 — gros morceau doc), puis vérification finale (T7).

---

## Task 1 : Fix B — Guard `cycle_timeout_s > 0` au `__post_init__` de `CimierConfig`

**Files:**
- Test: `tests/test_config_loader.py` (ajout)
- Modify: `core/config/config_loader.py:246-274` (ajout `__post_init__`)

- [ ] **Step 1.1 : Vérifier l'absence d'usage `cycle_timeout_s ≤ 0` dans la suite existante**

Run: `grep -rn "cycle_timeout_s=0\|cycle_timeout_s = 0\|cycle_timeout_s=-" tests/ services/ core/ web/`

Expected: 0 résultat (aucun test ne sera cassé par le guard).

> ⚠️ Si un résultat apparaît, **stopper** et reporter au superviseur avant de poursuivre — le spec assume cette absence (cf. §6 « Risques »).

- [ ] **Step 1.2 : Écrire le test paramétré RED**

Ajouter en fin de la section concernant `CimierConfig` dans `tests/test_config_loader.py` (chercher `def test_cimier_shelly_settle_and_verbose_defaults` ligne 479 comme repère, ajouter après le dernier test de la classe correspondante — sinon ajouter une nouvelle fonction au top level du fichier après les autres `test_cimier_*`) :

```python
@pytest.mark.parametrize("invalid", [-1.0, 0.0, 0])
def test_cimier_config_rejects_cycle_timeout_zero_or_negative(invalid):
    """cycle_timeout_s ≤ 0 → ValueError explicite au démarrage du service.

    Sans ce guard, le polling sortait immédiatement avec result=timeout
    trompeur (le moteur n'a pas tourné). On veut un refus net à la lecture
    de config, pas une dégénérescence silencieuse runtime (Bloc 3 dette T4).
    """
    with pytest.raises(ValueError, match="cycle_timeout_s"):
        CimierConfig(cycle_timeout_s=invalid)
```

**Si `pytest` et/ou `CimierConfig` ne sont pas déjà importés en haut du fichier**, ajouter les imports manquants (vérifier d'abord — `pytest` l'est presque certainement, `CimierConfig` aussi vu les tests existants ligne 396/428/447).

- [ ] **Step 1.3 : Lancer le test, vérifier qu'il échoue (RED)**

Run: `uv run --extra dev pytest tests/test_config_loader.py::test_cimier_config_rejects_cycle_timeout_zero_or_negative -v`

Expected: 3 FAIL (un par valeur paramétrée) avec un message du type `DID NOT RAISE ValueError` — `CimierConfig(cycle_timeout_s=0)` ne lève rien aujourd'hui.

- [ ] **Step 1.4 : Implémenter le guard dans `CimierConfig`**

Modifier `core/config/config_loader.py` — ajouter une méthode `__post_init__` à la classe `CimierConfig` (ligne 246-274 actuelles). Insérer **après** la ligne `motor_shelly: MotorShellyConfig = field(default_factory=MotorShellyConfig)` (ligne 274 actuelle) :

```python
    def __post_init__(self) -> None:
        if self.cycle_timeout_s <= 0:
            raise ValueError(
                f"cimier.cycle_timeout_s doit être > 0, "
                f"reçu {self.cycle_timeout_s}"
            )
```

L'indentation correspond aux 4 espaces de la classe (cf. les autres champs de `CimierConfig` qui sont indentés à 4 espaces).

- [ ] **Step 1.5 : Lancer le test, vérifier qu'il passe (GREEN)**

Run: `uv run --extra dev pytest tests/test_config_loader.py::test_cimier_config_rejects_cycle_timeout_zero_or_negative -v`

Expected: 3 PASS.

- [ ] **Step 1.6 : Lancer la suite `test_config_loader.py` complète pour détecter une régression**

Run: `uv run --extra dev pytest tests/test_config_loader.py -v`

Expected: tous PASS (le guard n'impacte que les valeurs ≤ 0, et Step 1.1 a confirmé qu'aucun test n'utilise de telles valeurs).

- [ ] **Step 1.7 : Lancer la suite `test_cimier_service.py` (impact en aval)**

Run: `uv run --extra dev pytest tests/test_cimier_service.py -v`

Expected: 63 PASS / 0 fail (baseline Bloc 2). Si une régression apparaît, c'est probablement une fixture qui passe `cycle_timeout_s=0` masqué — investiguer avant de committer.

- [ ] **Step 1.8 : Commit**

```bash
git add core/config/config_loader.py tests/test_config_loader.py
git commit -m "$(cat <<'EOF'
feat(cimier-bloc3): guard cycle_timeout_s > 0 au __post_init__ CimierConfig

Dette T4 (Fix B) : sans ce garde-fou, un cycle_timeout_s ≤ 0 dans
data/config.json faisait sortir immédiatement la boucle de polling avec
result=timeout trompeur (le moteur n'a pas tourné). Refus net à la lecture
de config avec message explicite pointant la clé fautive.

+1 test paramétré test_cimier_config_rejects_cycle_timeout_zero_or_negative
(-1.0, 0.0, 0). Suite test_cimier_service intact (63/0).

Co-Authored-By: Claude Opus 4.7 (1M context) <noreply@anthropic.com>
EOF
)"
```

---

## Task 2 : Fix A — Distinction `result=stopped` du `result=ok` dans `cycle_end`

**Files:**
- Test: `tests/test_cimier_service.py` (ajout après `test_stop_command_during_polling_aborts_cycle` ligne 1994)
- Modify: `services/cimier_service.py:553-774` (`_run_cycle` — propagation `poll_outcome`)

**Contexte code actuel :**
- `_run_cycle` ligne 562 : `error_message = ""` initialisé hors try.
- Ligne 707 : `outcome = self._poll_target_switch(action, cmd_id)` (variable locale au try).
- Ligne 722-724 : `if outcome == "stopped": error_message = ""` → le stop est aplati en string vide.
- Lignes 747-754 (dans le `finally`) : mapping `result=` qui ne voit que `error_message`, donc `result="ok"` pour stop **et** cycle nominal.

**Cible :** ajouter une variable `poll_outcome: str = ""` au même niveau que `error_message`, la mettre à jour dans le try (à côté de `outcome = ...`), et l'utiliser dans le mapping `finally` pour produire `result="stopped"` quand le poll s'est terminé sur stop.

- [ ] **Step 2.1 : Écrire le test RED ciblé sur le log `cycle_end`**

Ajouter **immédiatement après** `test_stop_command_during_polling_aborts_cycle` (ligne ~2024 fin), dans la classe `TestFullCycleViaSimulator` :

```python
    def test_cycle_end_logs_result_stopped_when_stop_during_polling(
        self, ipc_manager: RecordingIpcManager, caplog
    ) -> None:
        """Stop pendant polling → log cycle_end avec result=stopped (Bloc 3 dette T4).

        Distingue le cycle interrompu utilisateur (result=stopped) du cycle
        nominal réussi (result=ok), pour rendre les journaux dépiautables
        à 800 km du site.
        """
        import logging

        service, ps, sim, _ = _build_e2e_service(
            initial_state="closed",
            ipc_manager=ipc_manager,
            cycle_timeout_s=10.0,
            full_travel_s=5.0,
        )
        try:
            call_count = {"n": 0}

            def stop_after_some_polls():
                call_count["n"] += 1
                if call_count["n"] >= 3:
                    return {"id": "stop-during", "action": "stop"}
                return None

            service._check_for_stop_command = stop_after_some_polls

            with caplog.at_level(logging.INFO, logger="services.cimier_service"):
                service.execute_command({"id": "s8", "action": "open"})

            # Cycle terminé par stop → log final result=stopped.
            cycle_end_records = [
                r for r in caplog.records if "cimier_event=cycle_end" in r.getMessage()
            ]
            assert len(cycle_end_records) == 1, (
                f"attendu 1 cycle_end, vu {len(cycle_end_records)} : "
                f"{[r.getMessage() for r in cycle_end_records]}"
            )
            assert "result=stopped" in cycle_end_records[0].getMessage(), (
                f"cycle_end devrait contenir result=stopped, vu : "
                f"{cycle_end_records[0].getMessage()}"
            )
        finally:
            sim.stop()
```

> 💡 Si le logger name `services.cimier_service` ne capture rien, utiliser `with caplog.at_level(logging.INFO):` sans filtre logger (le test existant `test_cycle_logs_weather_on_start_via_simulator` ligne 2056 peut servir de référence pour le bon pattern caplog dans ce fichier).

- [ ] **Step 2.2 : Lancer le test, vérifier qu'il échoue (RED)**

Run: `uv run --extra dev pytest tests/test_cimier_service.py::TestFullCycleViaSimulator::test_cycle_end_logs_result_stopped_when_stop_during_polling -v -s`

Expected: FAIL avec message du type `cycle_end devrait contenir result=stopped, vu : cimier_event=cycle_end ... result=ok ...`.

- [ ] **Step 2.3 : Implémenter la propagation `poll_outcome`**

Modifier `services/cimier_service.py` méthode `_run_cycle` :

**A. Initialiser `poll_outcome` au même niveau que `error_message`** (ligne 562 actuelle) :

Remplacer :
```python
        cycle_start = self._clock()
        error_message = ""
```
par :
```python
        cycle_start = self._clock()
        error_message = ""
        poll_outcome = ""  # "ok"/"stopped"/"timeout"/"error" — propagé au mapping result= du finally
```

**B. Capturer l'outcome après l'appel `_poll_target_switch`** (ligne 707 actuelle) :

Remplacer :
```python
            outcome = self._poll_target_switch(action, cmd_id)
```
par :
```python
            outcome = self._poll_target_switch(action, cmd_id)
            poll_outcome = outcome
```

**C. Étendre le mapping `result=` dans le `finally`** (lignes 748-754 actuelles) :

Remplacer :
```python
            if error_message == "cycle_timeout":
                result = "timeout"
            elif error_message == "":
                # Soit cycle nominal OK, soit interruption stop → traités comme ok.
                result = "ok"
            else:
                result = "error"
```
par :
```python
            if error_message == "cycle_timeout":
                result = "timeout"
            elif poll_outcome == "stopped":
                # Interruption utilisateur pendant le polling — cleanup garanti
                # mais distinct d'un cycle nominal (Bloc 3 dette T4).
                result = "stopped"
            elif error_message == "":
                result = "ok"
            else:
                result = "error"
```

- [ ] **Step 2.4 : Lancer le test, vérifier qu'il passe (GREEN)**

Run: `uv run --extra dev pytest tests/test_cimier_service.py::TestFullCycleViaSimulator::test_cycle_end_logs_result_stopped_when_stop_during_polling -v`

Expected: PASS.

- [ ] **Step 2.5 : Vérifier la non-régression de `TestOrchestrationLogging`**

Run: `uv run --extra dev pytest tests/test_cimier_service.py::TestOrchestrationLogging -v`

Expected: tous PASS. Ce test verrouille `cycle_end ... result=ok` pour le cycle nominal — il doit rester vert car le cycle nominal a `poll_outcome="ok"` (pas `"stopped"`), donc tombe toujours dans la branche `elif error_message == ""`.

- [ ] **Step 2.6 : Vérifier la non-régression sur l'ensemble de la suite cimier_service**

Run: `uv run --extra dev pytest tests/test_cimier_service.py -v`

Expected: 64 PASS / 0 fail (63 baseline + 1 nouveau).

- [ ] **Step 2.7 : Commit**

```bash
git add services/cimier_service.py tests/test_cimier_service.py
git commit -m "$(cat <<'EOF'
feat(cimier-bloc3): distingue result=stopped de result=ok dans cycle_end

Dette T4 (Fix A) : _poll_target_switch retournait déjà "stopped"
explicitement, mais l'info était perdue au mapping final → un cycle nominal
réussi et un cycle interrompu utilisateur étaient indistinguables dans les
journaux. Propagation via une variable locale poll_outcome jusqu'au mapping
result= du finally. Cycle nominal toujours result=ok, stop devient
result=stopped, timeout/error inchangés.

+1 test test_cycle_end_logs_result_stopped_when_stop_during_polling via le
simulator HTTP réel (caplog sur services.cimier_service). Suite cimier_service
64/0 (63 baseline + 1).

Co-Authored-By: Claude Opus 4.7 (1M context) <noreply@anthropic.com>
EOF
)"
```

---

## Task 3 : Supprimer les 5 scripts `firmware/cimier/tests/*.sh`

**Files:**
- Delete: `firmware/cimier/tests/boucle_10_rst.sh`
- Delete: `firmware/cimier/tests/boucle_60_status.sh`
- Delete: `firmware/cimier/tests/cycle_trace.sh`
- Delete: `firmware/cimier/tests/test.sh`
- Delete: `firmware/cimier/tests/test_discrim.sh`

**Contexte :** ces 5 scripts ne sont **pas commités** (visibles `??` dans `git status` initial du chantier). Ils font des `POST /open`, `POST /close`, `POST /stop` côté Pico W — endpoints supprimés en Bloc 1. Ils ne sont donc plus exécutables sans erreur. Aucun remplacement (spec §3.1).

- [ ] **Step 3.1 : Vérifier le statut Git des scripts**

Run: `git status --short firmware/cimier/tests/`

Expected: les 5 fichiers apparaissent en `??` (untracked). **Si l'un d'eux apparaît tracké, basculer en `git rm` au lieu de `rm`.**

- [ ] **Step 3.2 : Supprimer les fichiers du système de fichiers**

Run: `rm -f firmware/cimier/tests/{boucle_10_rst,boucle_60_status,cycle_trace,test,test_discrim}.sh`

Expected: aucune erreur (les 5 fichiers existent, vérifiés en Step 3.1).

- [ ] **Step 3.3 : Vérifier que le dossier `firmware/cimier/tests/` est vide ou inexistant**

Run: `ls firmware/cimier/tests/ 2>&1 || echo "dossier supprimé implicitement"`

Expected: dossier vide (`ls` retourne rien) ou supprimé. Si le dossier reste vide et te dérange, exécuter `rmdir firmware/cimier/tests/` (Git ne suit pas les dossiers vides donc ça n'a pas d'impact sur l'index).

- [ ] **Step 3.4 : Vérifier qu'aucun fichier tracké ne référence ces scripts**

Run: `grep -rn "tests/test\.sh\|tests/boucle\|tests/cycle_trace\|tests/test_discrim" firmware/ docs/ README.md 2>/dev/null || echo "aucune référence"`

Expected: aucune référence (les scripts n'étaient référencés que par leur propre dossier, et le README firmware sera réécrit en T6 sans les mentionner).

- [ ] **Step 3.5 : Pas de commit (scripts non commités, suppression invisible à Git)**

Run: `git status --short firmware/cimier/`

Expected: aucun changement listé pour `firmware/cimier/tests/` (les `??` ont disparu, rien d'autre n'apparaît).

> ✅ Pas de `git add` ni de `git commit` — les fichiers n'étaient pas dans l'index, leur suppression n'affecte pas l'historique. Si Step 3.5 montre des `D` (deleted tracked) pour l'un d'eux, alors faire :
> ```bash
> git rm -f firmware/cimier/tests/<fichier>.sh
> git commit -m "chore(cimier-bloc3): supprime scripts shell obsolètes (endpoints POST Pico retirés en Bloc 1)"
> ```

---

## Task 4 : Patch des 2 commentaires WDT obsolètes dans `firmware/cimier/main.py`

**Files:**
- Modify: `firmware/cimier/main.py:197` (commentaire WDT 200ms)
- Modify: `firmware/cimier/main.py:267` (commentaire WDT 200ms)

**Contexte :** la constante `WDT_TIMEOUT_MS = 8000` (ligne 53) et le commentaire ligne 49 sont déjà à jour avec la valeur 8000 ms validée Bloc 1. Mais 2 commentaires plus loin dans le fichier mentionnent encore l'ancien WDT 200 ms.

- [ ] **Step 4.1 : Vérifier les positions exactes des commentaires à patcher**

Run: `grep -n "200 ms" firmware/cimier/main.py`

Expected: 2 occurrences à patcher (lignes ~197 et ~267 selon le spec) plus éventuellement la ligne 88 (`reveil ~200 ms`) qui concerne le power management WiFi `pm=0xA11140` — **NE PAS toucher** la ligne 88.

> ℹ️ Si une 3ème occurrence inattendue apparaît, l'évaluer au cas par cas : touche-t-elle au WDT ou à autre chose (power management, sleep `time.sleep_ms(200)`) ? Ne patcher que celles liées au WDT.

- [ ] **Step 4.2 : Patcher la première occurrence (ligne ~197)**

Remplacer (commentaire d'expression `50 ms < 200 ms WDT donc safe`) :
```python
# notifie pas POLLIN sur sockets serveur). 50 ms < 200 ms WDT donc safe.
```
par :
```python
# notifie pas POLLIN sur sockets serveur). 50 ms ≪ 8000 ms WDT donc safe.
```

> Si le caractère `≪` ne passe pas l'encodage MicroPython (le `main.py` actuel utilise déjà des caractères ASCII pur dans les commentaires), utiliser `50 ms << 8000 ms` (deux chevrons ASCII) ou `50 ms (bien en dessous des 8000 ms WDT) donc safe`. Vérifier la cohérence avec le reste du fichier via `head -20 firmware/cimier/main.py` (regarder s'il y a des accents ou non).

- [ ] **Step 4.3 : Patcher la deuxième occurrence (ligne ~267)**

Remplacer :
```python
    # 2. Hardware (le WDT est arme plus tard, apres WiFi : la connexion peut
    #    prendre plusieurs secondes et un WDT 200 ms reset le Pico avant la fin)
```
par :
```python
    # 2. Hardware (le WDT est arme plus tard, apres WiFi : la connexion peut
    #    prendre plusieurs secondes et un WDT court reset le Pico avant la fin
    #    -- WDT_TIMEOUT_MS = 8000 ms armé etape 4 ci-dessous)
```

- [ ] **Step 4.4 : Vérifier qu'il ne reste plus aucune mention `WDT 200`**

Run: `grep -n "WDT 200\|200 ms WDT" firmware/cimier/main.py`

Expected: aucun résultat. Les occurrences résiduelles de `200` doivent être étrangères au WDT (sleep WiFi power management, statut HTTP 200…).

- [ ] **Step 4.5 : Sanity check syntaxe MicroPython (`py_compile` Python 3 est tolérant)**

Run: `uv run python -m py_compile firmware/cimier/main.py`

Expected: aucune erreur. Le `py_compile` Python 3 ne vérifie pas la sémantique MicroPython spécifique (`machine.WDT`, `network`) mais détecte les erreurs de syntaxe pure.

- [ ] **Step 4.6 : Commit**

```bash
git add firmware/cimier/main.py
git commit -m "$(cat <<'EOF'
docs(cimier-bloc3): patch commentaires WDT 200ms -> 8000ms dans main.py

La constante WDT_TIMEOUT_MS = 8000 et le commentaire ligne 49 étaient déjà
à jour depuis Bloc 1 (correctifs HTTP/WDT validés). Mais 2 commentaires
descriptifs plus bas mentionnaient encore l'ancien WDT 200 ms (lignes 197
et 267). Cohérence du fichier rétablie. La mention "reveil ~200 ms" ligne
88 (power management WiFi pm=0xA11140) reste inchangée — sans rapport.

Co-Authored-By: Claude Opus 4.7 (1M context) <noreply@anthropic.com>
EOF
)"
```

---

## Task 5 : Patch mémoire — retrait mention `ramp.py orphelin` (hors repo)

**Files (HORS repo Git — Edit manuel sans commit) :**
- Modify: `/home/jp/.claude/projects/-home-jp-PythonProject-Dome-web-v4-6/memory/project_cimier_shelly_pivot_definitive_spec.md` ligne ~44

**Contexte :** le backlog mémoire mentionne `firmware/cimier/ramp.py orphelin` comme item à traiter — or le fichier est déjà absent (vérifié `ls firmware/cimier/ramp.py 2>&1` retourne RAMP ABSENT). C'est une dette mémoire à corriger.

- [ ] **Step 5.1 : Vérifier que le fichier `ramp.py` est bien absent du repo**

Run: `ls firmware/cimier/ramp.py 2>&1`

Expected: `ls: cannot access 'firmware/cimier/ramp.py': No such file or directory`.

- [ ] **Step 5.2 : Lire la ligne courante du backlog mémoire pour identifier le passage exact**

Run: `grep -n "ramp.py" /home/jp/.claude/projects/-home-jp-PythonProject-Dome-web-v4-6/memory/project_cimier_shelly_pivot_definitive_spec.md`

Expected: 1 résultat, dans la section `**Encore ouvert (backlog post-Bloc 2)**`, sur une ligne du type :
```
- Doc/firmware on-device (Bloc 3 candidate) : `firmware/cimier/README.md` périmé (cite endpoints supprimés + step_generator), `firmware/cimier/ramp.py` orphelin, commentaires `main.py` WDT 200→8000, scripts `firmware/cimier/tests/*.sh` (non committés, font POST /open disparu).
```

- [ ] **Step 5.3 : Retirer la mention `firmware/cimier/ramp.py orphelin`**

Avec Edit, remplacer dans le fichier mémoire :
```
- Doc/firmware on-device (Bloc 3 candidate) : `firmware/cimier/README.md` périmé (cite endpoints supprimés + step_generator), `firmware/cimier/ramp.py` orphelin, commentaires `main.py` WDT 200→8000, scripts `firmware/cimier/tests/*.sh` (non committés, font POST /open disparu).
```
par :
```
- Doc/firmware on-device (Bloc 3 candidate) : `firmware/cimier/README.md` périmé (cite endpoints supprimés + step_generator), commentaires `main.py` WDT 200→8000, scripts `firmware/cimier/tests/*.sh` (non committés, font POST /open disparu).
```

- [ ] **Step 5.4 : Vérifier que la mention a bien disparu**

Run: `grep -n "ramp.py" /home/jp/.claude/projects/-home-jp-PythonProject-Dome-web-v4-6/memory/project_cimier_shelly_pivot_definitive_spec.md`

Expected: aucun résultat.

- [ ] **Step 5.5 : Pas de commit Git (fichier hors repo)**

Le fichier vit dans `~/.claude/projects/.../memory/`, ce n'est pas un fichier du repo `Dome_web_v4_6`. Aucune action Git à faire.

---

## Task 6 : Réécriture from-scratch de `firmware/cimier/README.md`

**Files:**
- Modify: `firmware/cimier/README.md` (réécriture complète : 601 LOC → ~180 LOC)

**Contexte :** le README actuel décrit le firmware pré-pivot (DM560T, microsteps, POST /open|/close|/stop, helper menu, invert direction…). Tout cela a été supprimé en Bloc 1. Le README doit être réécrit pour refléter le firmware capteur-only actuel (v0.2.0, protocole 2).

**Stratégie :** écrire un fichier neuf qui écrase l'ancien d'un seul coup (Write). La structure suit la liste §3.1 du spec.

- [ ] **Step 6.1 : Confirmer le contenu actuel à écraser**

Run: `wc -l firmware/cimier/README.md && head -3 firmware/cimier/README.md`

Expected: ~601 LOC, titre `# Firmware Pico W — Cimier coupole`.

- [ ] **Step 6.2 : Récupérer l'IP du Pico W depuis la mémoire pour cohérence des exemples curl**

Note : selon `feedback_no_hardcoded_ips`, **aucune IP en dur** ne doit apparaître dans le code. Pour le README, on utilisera `<IP-DU-PICO>` comme placeholder dans les snippets curl. L'IP réelle est attribuée par DHCP routeur et notée par Serge dans `data/config.json → cimier.host` (mention à faire dans le README, sans valeur).

- [ ] **Step 6.3 : Écrire le nouveau README**

Écraser intégralement `firmware/cimier/README.md` avec le contenu suivant :

````markdown
# Firmware Pico W — Cimier coupole (capteur-only)

Firmware MicroPython pour Raspberry Pi Pico W (RP2040 + WiFi).

**Rôle depuis le pivot Shelly (v0.2.0, protocole 2)** : le Pico W est un
**pur serveur de capteurs**. Il expose l'état des 2 fins de course
(ouverte / fermée) via HTTP REST. **L'orchestration moteur est faite côté
Pi principal**, par `services/cimier_service.py`, via 2 relais Shelly
(MOT + UPDN cascadés sur SHELLY-1-24).

Voir spec d'orchestration :
[`docs/superpowers/specs/2026-05-23-cinematique-shelly-cimier-garde-fou-design.md`](../../docs/superpowers/specs/2026-05-23-cinematique-shelly-cimier-garde-fou-design.md).

---

## Aucune dépendance externe

Le mini-serveur HTTP est embarqué dans le firmware (socket pur). Pas de
`mip install`, pas de microdot. Tu n'as besoin que de MicroPython +
3 fichiers (`main.py`, `cimier_controller.py`, `secrets.py`).

---

## Pré-requis hardware

| Élément | Détail |
|---|---|
| Pico W | Modèle avec WiFi (pas la version Pico standard) |
| MicroPython | 1.20+ (UF2 téléchargé depuis micropython.org) |
| Câble USB | Micro-USB **données** (pas seulement charge) pour flasher |
| Fins de course | 2 contacts NC sur GP14 (ouvert) / GP15 (fermé), GND switches |
| Alim Pico W | 12 V permanente (pas coupée en fin de session) |

> ⚠️ Le Pico W reste vivant en permanence (alim 12 V indépendante), même
> quand la cascade Shelly 220 V est coupée en fin de session
> astrophotographique. C'est nécessaire pour que le pré-vol garde-fou du
> `cimier_service` puisse lire `/status` avant de remettre le 24 V moteur
> (cf. spec §3.0).

---

## Procédure complète (première installation)

### Étape 1 : Flasher MicroPython

1. Télécharger le firmware MicroPython pour **Pico W** :
   <https://micropython.org/download/RPI_PICO_W/> → version 1.20+ requise.
2. Mettre le Pico W en bootloader : maintenir **BOOTSEL** + brancher USB.
3. Le Pico apparaît comme `RPI-RP2`. Glisser-déposer le `.uf2` dessus.
4. Le Pico redémarre, `/dev/ttyACM0` apparaît côté hôte.

### Étape 2 : Créer `secrets.py` local

Sur la machine où est branché le Pico W, créer le fichier `secrets.py` :

```python
WIFI_SSID = "TonReseauWiFi"
WIFI_PASSWORD = "MotDePasse"
```

L'IP du Pico W est attribuée **par DHCP routeur** (réservation MAC). Pas
d'IP statique dans `secrets.py`. L'IP réelle assignée est ensuite reportée
dans `data/config.json → cimier.host` côté Pi principal.

### Étape 3 : Flasher les 3 fichiers source

Depuis le repo, à la racine `firmware/cimier/` :

```bash
mpremote cp main.py :
mpremote cp cimier_controller.py :
mpremote cp secrets.py :
mpremote reset
```

Le Pico W redémarre, se connecte au WiFi, et démarre le serveur HTTP sur
port 80. Un message banner s'affiche sur la console série pendant 3 s
(fenêtre de safe-boot, permet `Ctrl-C` pour reprendre la main en REPL si
le firmware bloque).

### Étape 4 : Vérification rapide

Depuis n'importe quelle machine du réseau local (remplacer `<IP-DU-PICO>`
par l'adresse assignée — visible sur la console série au démarrage) :

```bash
curl http://<IP-DU-PICO>/status
curl http://<IP-DU-PICO>/info
```

Réponses attendues décrites ci-dessous.

---

## Endpoints REST (2 GET seuls)

Port 80, JSON.

| Méthode | Endpoint | Réponse |
|---|---|---|
| `GET` | `/status` | `{state, open_switch, closed_switch, error_message}` |
| `GET` | `/info` | `{firmware_version, protocol_version, role, wifi_rssi, ...}` |

**Valeurs de `state`** :
- `closed` — cimier fermé (fin de course closed déclenché)
- `open` — cimier ouvert (fin de course open déclenché)
- `unknown` — entre les deux (au démarrage si aucun switch n'est encore
  fait, ou pendant un cycle en cours côté Shelly)
- `error` — both_switches_triggered (incident hardware, à investiguer)

> 🚫 **Endpoints supprimés depuis v0.2.0** : `POST /open`, `POST /close`,
> `POST /stop`, `POST /config`, `GET /diag/*`. L'orchestration moteur est
> désormais 100 % côté Pi (`cimier_service` + 2 Shelly). Tenter un POST
> sur ces endpoints retourne `405 Method Not Allowed` ou `404 Not Found`.

---

## Débogage terrain

### Lire l'état courant

```bash
curl http://<IP-DU-PICO>/status
# {"state":"closed","open_switch":false,"closed_switch":true,"error_message":""}
```

### Simuler une fin de course (banc Pico isolé)

Sur le Pico W avant montage dans la coupole :

```text
Pico GP14 ----- jumper ----- GND switches   (simule "fin de course OPEN déclenchée")
Pico GP15 ----- jumper ----- GND switches   (simule "fin de course CLOSED déclenchée")
```

`GET /status` doit refléter immédiatement le changement (les GPIO sont
configurés en pull-up interne, contact NC vers GND = `False` câblé = switch
non déclenché ; jumper ouvert = `True` câblé = switch déclenché — vérifier
la convention dans `cimier_controller.py` selon le câblage réel des
switches NC vs NO en production).

### Vérifier la version firmware

```bash
curl http://<IP-DU-PICO>/info
# {"firmware_version":"0.2.0","protocol_version":2,"role":"sensor_only",...}
```

`protocol_version: 2` confirme que c'est le firmware capteur-only Bloc 1.
Si tu vois `protocol_version: 1`, c'est l'ancien firmware (à reflasher
avec la procédure Étape 3).

---

## Câblage Shelly externe (résumé)

Le moteur cimier est piloté par 2 Shelly 1 Gen 3 cascadés sur un Shelly
220 V → 24 V :

```
SHELLY-1-24 (220V) -- ON --> alim DC 24V
                                   |
                                   v
                           SHELLY-1-MOT (24V) -- ON --> alim moteur
                                                              |
                                                              v
                                                      SHELLY-1-UPDN (24V) -- relais SPDT --> DM556T DIR
                                                                                                |
                                                                                                v
                                                                                            moteur cimier
```

Détails complets (timings, gardes-fous, IPs DHCP, conventions DIR) dans la
spec :
[`docs/superpowers/specs/2026-05-23-cinematique-shelly-cimier-garde-fou-design.md`](../../docs/superpowers/specs/2026-05-23-cinematique-shelly-cimier-garde-fou-design.md).

Le Pico W n'a **aucune ligne STEP/DIR** vers le driver — son seul rôle
est de lire les 2 fins de course et de répondre à `GET /status`.

---

## Watchdog

Watchdog hardware RP2040 armé à **8000 ms** (`WDT_TIMEOUT_MS = 8000`,
`main.py` ligne 53). Si la boucle principale ne fait pas `wdt.feed()`
pendant 8 s, le Pico reset automatiquement.

Fenêtre de **safe-boot 3 s** au démarrage (`safe_boot_window()`) :
permet de reprendre la main en REPL via `mpremote` ou minicom si le
firmware bug juste après boot. Pendant cette fenêtre, le WDT n'est PAS
encore armé.

---

## Versions

| Version | Date | Notes |
|---|---|---|
| 0.2.0 | 2026-05-23 | Pivot Shelly — firmware capteur-only, endpoints `/open`/`/close`/`/stop`/`/config`/`/diag` supprimés, WDT 8000 ms |
| 0.1.0 | Avril 2026 | Firmware initial (orchestration moteur côté Pico — déprécié) |
````

> ⚠️ Si la convention NC vs NO du Step 6.3 ne te semble pas claire au moment de l'écriture, simplifier en : *"`GET /status` doit refléter immédiatement le changement de jumper."* sans aller dans le détail booléen — la convention exacte vit dans `cimier_controller.py` et c'est suffisant.

- [ ] **Step 6.4 : Vérifier le contenu du nouveau README**

Run: `wc -l firmware/cimier/README.md && grep -c "POST /open\|POST /close\|POST /stop\|step_generator\|invert\|DM560T\|microsteps" firmware/cimier/README.md`

Expected: ~180 LOC (~150-200 ok), 0 occurrence des tokens obsolètes (le grep retourne `0`). Si le grep retourne un nombre > 0, identifier la mention résiduelle et corriger.

Note : les **seules** mentions tolérées de ces tokens sont dans la section "Endpoints supprimés depuis v0.2.0" qui les liste **explicitement pour dire qu'ils n'existent plus**. Le grep ci-dessus matche cette section — vérifier manuellement que toutes les occurrences sont dans ce contexte (sinon corriger).

> 💡 Si le grep retourne un nombre > 0 mais uniquement dans la section "Endpoints supprimés", c'est OK. Une commande plus discriminante :
> ```bash
> grep -n "POST /open\|POST /close\|POST /stop" firmware/cimier/README.md
> ```
> Doit pointer **seulement** vers la note explicative qui les liste pour annoncer leur suppression.

- [ ] **Step 6.5 : Sanity check Markdown (rendu)**

Run: `head -50 firmware/cimier/README.md`

Expected: pas de caractère bizarre, tables Markdown bien alignées (pipes `|`), liens relatifs `[](../../docs/...)` corrects.

- [ ] **Step 6.6 : Commit**

```bash
git add firmware/cimier/README.md
git commit -m "$(cat <<'EOF'
docs(cimier-bloc3): réécriture README firmware capteur-only (601 -> ~180 LOC)

Pivot Shelly v0.2.0 acté — le Pico W n'orchestre plus le moteur, il sert
seulement /status et /info. L'ancien README décrivait DM560T + microsteps
+ POST /open/close/stop + invert + step_generator + helper menu interactif,
tout supprimé en Bloc 1. Nouveau README from-scratch :
  - Rôle capteur-only (renvoi vers spec orchestration Shelly pour le reste)
  - Pré-requis hardware (2 fins de course GP14/GP15, alim Pico 12V permanente)
  - Procédure flash mpremote + secrets.py WiFi (sans IP en dur, attribuée par
    DHCP routeur et reportée dans data/config.json côté Pi)
  - Endpoints réels (GET /status, GET /info) + note explicite "endpoints
    POST supprimés depuis v0.2.0"
  - Debug terrain via curl + jumper GP14/GP15 vers GND switches (plus de
    scripts shell — supprimés en T3 du même Bloc 3)
  - Diagramme câblage Shelly externe (résumé, détails dans la spec)
  - Watchdog 8000 ms (constante WDT_TIMEOUT_MS, cohérent main.py ligne 53)

Co-Authored-By: Claude Opus 4.7 (1M context) <noreply@anthropic.com>
EOF
)"
```

---

## Task 7 : Vérification finale — lint + suite restreinte verte

**Files:** lecture seule, sauf si `ruff format` propose des changements (auquel cas commit séparé).

- [ ] **Step 7.1 : Lint `ruff check` sur les fichiers Python touchés**

Run: `uv run --extra dev ruff check core/config/config_loader.py services/cimier_service.py tests/test_config_loader.py tests/test_cimier_service.py`

Expected: `All checks passed!` ou aucune erreur (warnings tolérés s'ils sont pré-existants au chantier).

- [ ] **Step 7.2 : `ruff format --check` sur les mêmes fichiers**

Run: `uv run --extra dev ruff format --check core/config/config_loader.py services/cimier_service.py tests/test_config_loader.py tests/test_cimier_service.py`

Expected: `4 files already formatted`. Si l'un est marqué à reformater, exécuter `ruff format` (sans `--check`) sur ce(s) fichier(s) puis créer un commit `chore(cimier-bloc3): ruff format final` (voir Step 7.5).

- [ ] **Step 7.3 : Suite restreinte au périmètre du Bloc 3**

Run: `uv run --extra dev pytest tests/test_cimier_service.py tests/test_config_loader.py -v`

Expected: tout PASS. Compte cible :
- `test_cimier_service.py` : 64 (63 baseline Bloc 2 + 1 nouveau Bloc 3).
- `test_config_loader.py` : baseline + 1 nouveau (vérifier le `-v` pour le compte exact baseline).

- [ ] **Step 7.4 : Sanity check suite globale (option, sauf si très lent)**

Run: `uv run --extra dev pytest -q`

Expected: `1134 passed` (1132 baseline Bloc 2 + 2 nouveaux Bloc 3) ou approchant. **Tolérance** : des tests pré-existants peuvent être `skip` ou être hors scope ; ce qui compte est `0 failed`.

> ⏱️ Si la suite globale prend trop longtemps, restreindre comme suit :
> ```bash
> uv run --extra dev pytest tests/ -k "not astropy" -q
> ```

- [ ] **Step 7.5 : Si `ruff format` a modifié un fichier, créer un commit séparé**

```bash
# Seulement si Step 7.2 a montré un fichier à reformater :
git add <fichiers reformatés>
git commit -m "chore(cimier-bloc3): ruff format final"
```

Sinon, sauter cette étape.

- [ ] **Step 7.6 : Vérifier l'état Git final**

Run: `git log --oneline -8 && git status --short`

Expected:
- 6 nouveaux commits Bloc 3 (au-delà des 24 commits Bloc 1+2 + spec) : T1, T2, (T3 absent — pas de commit), T4, T6, et optionnellement T7. T5 n'a pas de commit (fichier hors repo).
- `git status` propre côté repo (pas de fichier modifié non commité). Les fichiers terrain (sessions, logs, scheduled_tasks.lock) restent untracked comme avant.

- [ ] **Step 7.7 : Reporter à JP**

Préparer un récap court à JP :
- Compte de commits ajoutés.
- Compte de tests verts ajoutés.
- Confirmation : aucun bump, aucun push (chantier global non bouclé, attendu pour Bloc 4 final post-validation terrain).
- Backlog reporté en Bloc 4 (du spec §5) : latence stop HTTP, IPs DHCP définitives, bump `pyproject.toml` 6.4.0 → 6.5.0, push `origin/main`.

---

## Récapitulatif des commits attendus

| Tâche | Commit ? | Message conventionnel |
|---|---|---|
| T1 — Guard `cycle_timeout_s > 0` | ✅ | `feat(cimier-bloc3): guard cycle_timeout_s > 0 au __post_init__ CimierConfig` |
| T2 — Distinction `result=stopped` | ✅ | `feat(cimier-bloc3): distingue result=stopped de result=ok dans cycle_end` |
| T3 — Suppression scripts shell | ❌ | (scripts non commités, suppression invisible à Git) |
| T4 — Patch commentaires WDT | ✅ | `docs(cimier-bloc3): patch commentaires WDT 200ms -> 8000ms dans main.py` |
| T5 — Patch mémoire | ❌ | (fichier hors repo) |
| T6 — Réécriture README | ✅ | `docs(cimier-bloc3): réécriture README firmware capteur-only (601 -> ~180 LOC)` |
| T7 — Vérification finale | ⚠️ optionnel | `chore(cimier-bloc3): ruff format final` (seulement si reformat nécessaire) |

**Total attendu : 4 à 5 commits**, tous sur `main` local, **aucun push**, **aucun bump version**.
