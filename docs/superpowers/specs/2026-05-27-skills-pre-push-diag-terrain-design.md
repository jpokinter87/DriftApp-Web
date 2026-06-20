# Spec — Skills d'amélioration du workflow : `pre-push` et `diag-terrain`

**Date** : 2026-05-27
**Auteur** : JP + Claude (brainstorming)
**Statut** : validé (design), en attente relecture spec avant implémentation
**Origine** : analyse de la trace distillée de nos interactions (26 mémoires projet) + des 13 slash-commands DriftApp existants.

## Contexte et motivation

Les 13 skills DriftApp existants (`.claude/commands/`) couvrent bien le domaine métier
mais sont quasi tous écrits pour **s'exécuter sur le Pi** (`sudo systemctl`, `/dev/shm`,
`journalctl`). Or la machine de dev est à **800 km** du Pi
(`[[project_machine_dev_distante]]`) → décalage structurel entre l'outillage et la réalité.

Deux patterns de friction reviennent à chaque cycle de développement et ne sont couverts
par aucun skill :

- **A. Rituel d'avant-push** : bump version, tests ciblés, lint/format, grep IP en dur —
  règles éparpillées dans 4-5 mémoires de feedback, donc parfois oubliées.
- **B. Debug matériel par procuration via Serge** : le plus gros gouffre de temps du projet
  (≈2 semaines sur le bring-up Pico W). Pattern invariant : générer un protocole
  copier-coller → Serge l'exécute sur site → recolle → on interprète.

Le pattern C (discipline début/fin de session) est déjà couvert par PAUL
(`/paul:pause` + `/paul:resume`) — hors périmètre.

## Décisions de cadrage (validées)

| Sujet | Décision |
|---|---|
| Skills à créer | ① `pre-push` + ② `diag-terrain` |
| Mécanisme pre-push | Skill guidé (pas de hook git) |
| Bump pre-push | Détection auto du périmètre cimier + confirmation utilisateur |
| Portée pre-push | Jusqu'au push (commit + push après OK explicite) |
| Périmètre diag-terrain | Logiciel Pi **et** hardware (multimètre) |
| Valeurs terrain diag-terrain | Lecture dynamique (`data/config.json` + mémoires), pas de valeurs figées |
| Format de livraison | Vrais skills `SKILL.md` (via `skill-creator`), project-scoped |

Faits dépôt confirmés : version `6.4.0`, outils `ruff` + `black` (pas de mypy),
commits conventionnels (`feat/fix/refactor(scope):`), aucun hook git.

---

## Skill ① — `pre-push`

**Objectif** : dérouler en une passe la checklist d'hygiène avant un push, en encodant
des règles aujourd'hui dispersées dans les mémoires de feedback.

**Déclenchement (description)** : « je vais pousser », « commit + push », « prépare le push »,
ou invocation explicite. Avant tout commit/push vers `origin/main`.

**Contrainte transverse** : toutes les commandes Python via `uv run --extra dev …`
(`[[feedback_uv_sync_dev]]`).

**Déroulé** — chaque étape s'arrête sur feu rouge et rend la main :

1. **Périmètre** — `git status` + `git diff --stat` → modules touchés + fichiers de test liés.
2. **Tests ciblés** — `uv run --extra dev pytest tests/test_<module>.py … -q` sur le
   périmètre (`[[feedback_tests_scope]]`). Bascule **suite complète** si code partagé
   touché (`core/config`, IPC `services/ipc_manager.py`, `core/tracking/tracker.py`).
3. **Format + lint** — `uv run --extra dev ruff format` puis `uv run --extra dev ruff check`.
4. **Grep valeurs en dur** — sur le **diff** (`core/`, `services/`, `web/`, hors fixtures) :
   `192\.168\.`, `/dev/tty`, `/dev/shm`, `localhost`, `127\.0\.0\.1`. **Bloque** si trouvé
   hors test (`[[feedback_no_hardcoded_ips]]`).
5. **Décision de bump** — détecte si le diff touche le **périmètre cimier**
   (chemins `firmware/cimier`, motifs `*cimier*`, sim mécanisme `CimierMechanismSim` /
   `SimMotorShelly`) :
   - oui → propose **PAS de bump** (rappel `[[project_cimier_shelly_pivot_definitive_spec]]`) ;
   - non → propose un **bump patch** dans `pyproject.toml` (`[[feedback_version_bump]]`) ;
   - dans les deux cas → **confirmation utilisateur** avant d'écrire.
6. **Message de commit** — rédige un message conventionnel calqué sur l'historique.
7. **Commit + push** — **uniquement après OK explicite**. Récap final (version, tests,
   fichiers, message).

**Ne fait pas** : ne pousse jamais sans OK explicite ; ne crée pas de branche
(le workflow projet pousse sur `main`) ; ne lance pas mypy (absent du projet).

---

## Skill ② — `diag-terrain`

**Objectif** : transformer un symptôme terrain en protocole de diagnostic prêt pour Serge,
puis interpréter ses retours — sans jamais exécuter quoi que ce soit sur le Pi.

**Déclenchement (description)** : incident terrain rapporté (« Serge a un souci avec… »,
« le Pico/Shelly/moteur déconne sur site », « la coupole ne répond plus »).

**Contrainte structurante** : machine de dev à 800 km, **aucun accès runtime au Pi**
(`[[project_machine_dev_distante]]`). Le skill **génère** les commandes pour Serge et
**interprète** ses retours — il ne les lance jamais lui-même.

### Mode A — Générer un protocole (entrée = symptôme)

- **Lecture dynamique des valeurs** à l'exécution : `data/config.json`
  (`cimier.host`, `cimier.power_switch.host`, ports, GPIO) + mémoires projet
  (pinout Pico W, Shelly `[[reference_shelly_cimier_power]]`, pivots câblage
  `[[project_cimier_wiring_pivot_20260512]]`). Placeholder « à confirmer » si absent.
- **Section logiciel Pi** (SSH copier-coller) selon le symptôme : `systemctl status`,
  `cat /dev/shm/*.json`, `journalctl -u <service>`, `ls -la /dev/shm/`.
- **Section hardware** (si pertinent) : étapes multimètre / continuité / pinout numérotées,
  chacune avec son **« résultat attendu »** pour que Serge sache quoi rapporter.
- **Règles d'or** rappelées (ex. jamais QC 3.0 + USB Pi simultanés ; n'importe quel GND
  du Pico marche, la pin 38 n'est pas spéciale).
- Sortie **en français**, prête à coller dans WhatsApp/SMS, étapes numérotées séquentielles.

### Mode B — Interpréter (entrée = retour de Serge)

- Parse mesures/sorties → **diagnostic** + **hypothèses classées par probabilité** +
  **prochaine étape unique** à faire exécuter.

**Ne fait pas** : ne lance aucune commande Pi/hardware en local ; ne fige aucune IP/pinout
dans son texte (tout lu dynamiquement).

---

## Livraison

- Deux skills `SKILL.md` créés via `skill-creator`, project-scoped dans le dépôt.
- Atout vs slash-commands existantes : `description` de déclenchement contextuel.
- Option différée : wrapper slash-command mince (`/pre-push`, `/diag-terrain`) si besoin
  de parité avec la convention `.claude/commands/`.

## Critères de succès

- `pre-push` : déroule les 7 étapes, bloque sur IP en dur, gère l'exception bump cimier,
  ne pousse qu'après OK.
- `diag-terrain` : produit un protocole FR copier-coller avec valeurs issues de
  `data/config.json`, et un mode interprétation exploitable.
- Aucun des deux ne tente d'accéder au runtime du Pi depuis la machine de dev.
