---
name: pre-push
description: >-
  Checklist d'hygiène avant un commit/push sur le dépôt DriftApp Web (contrôle de
  coupole astronomique). Déroule en une passe : tests pytest ciblés sur le périmètre
  touché, ruff format + check, détection de valeurs terrain codées en dur (IP/host/
  device/IPC) dans le diff, bump de pyproject.toml (systématique), rédaction d'un message de commit
  conventionnel, puis commit + push. À utiliser quand
  l'utilisateur s'apprête à pousser : « je vais pousser », « commit + push »,
  « prépare le push », « pousse les changements », ou avant toute écriture vers
  origin/main.
---

# pre-push — hygiène d'avant-push DriftApp

Workflow à dérouler avant de pousser. **S'arrêter à chaque feu rouge** et rendre la
main à l'utilisateur. Toutes les commandes Python passent par `uv run --extra dev …`.

## Étape 0 — Analyse du delta (script)

Lancer l'analyse en lecture seule (ne modifie rien) :

```bash
python3 .claude/skills/pre-push/scripts/check_push_readiness.py --repo .
```

Le rapport fournit : fichiers concernés,
valeurs en dur ajoutées, tests à lancer, version courante. Utiliser ses conclusions
pour les étapes suivantes au lieu de les recalculer à la main.

## Étape 1 — Tests ciblés

Lancer les tests du **périmètre touché** uniquement (pas la suite complète) :

```bash
uv run --extra dev pytest tests/test_<module>.py [tests/test_<voisin>.py] -q
```

Exception : si le diff touche du **code partagé** (`core/config/config.py`,
`core/config/config_loader.py`, `services/ipc_manager.py`, `core/tracking/tracker.py`),
lancer la **suite complète** `uv run --extra dev pytest -q`. Le script signale ce cas.

Tests rouges → **stop**, corriger avant d'aller plus loin.

## Étape 2 — Format + lint (UNIQUEMENT les fichiers modifiés)

**Ne jamais lancer ruff repo-wide** : le code existant n'est pas intégralement
ruff-formaté (≈119 fichiers seraient reformatés, ≈153 erreurs pré-existantes/
intentionnelles comme le `django.setup()` E402 des tests). Cela polluerait le diff et
noierait les vraies erreurs. Cibler **les fichiers Python du périmètre touché**, listés
par le script à l'étape 0 :

```bash
uv run --extra dev ruff format <fichiers .py modifiés>
uv run --extra dev ruff check <fichiers .py modifiés>
```

Corriger les erreurs de lint sur ces fichiers (ou justifier proprement une exception
ciblée). `ruff` est le seul formateur du projet (black retiré en 6.21.14) ; le dépôt est
entièrement propre et la CI vérifie `ruff format --check .` + `ruff check .`. Il n'y a
**pas de mypy** dans ce projet → ne pas l'ajouter.

## Étape 3 — Valeurs terrain en dur

Le script a déjà scanné les **lignes ajoutées** (hors tests) pour `192.168.x.x`,
`/dev/tty`, `/dev/shm`, `localhost`, `127.0.0.1`.

S'il signale une occurrence : c'est une valeur terrain qui doit vivre dans
`data/config.json`, pas dans le code (`core/`, `services/`, `web/`). **Bloquer le
push** et la déplacer en config avec un défaut neutre (`""`, `0`, `False`). Seule
exception légitime : `127.0.0.1` dans des tests/fixtures (déjà exclus du scan).

## Étape 4 — Décision de bump pyproject.toml

**Bump systématique** à chaque push : patch par défaut (ex. `6.4.0` → `6.4.1`),
mineur pour un milestone complet. Sans bump, la MAJ OTA n'est jamais proposée sur
le terrain. Ajouter la ligne correspondante au changelog de `CLAUDE.md`.

## Étape 5 — Message de commit

Rédiger un message **conventionnel** calqué sur l'historique du dépôt :
`type(scope): description` (`feat`, `fix`, `refactor`, `docs`, `test`…), scope =
module concerné (`cimier`, `motor_service`, `web`…). Suivre la convention de signature
de commit en vigueur dans la session.

## Étape 6 — Commit + push

Une fois les tests verts, **commit + push d'office** (attendu par l'utilisateur),
sauf consigne explicite d'attendre. Récapituler ensuite : version, résultat des
tests, fichiers inclus, message de commit.

```bash
git add <fichiers>
git commit -m "<message>"
git push
```

Le workflow projet pousse sur `main` (pas de branche feature systématique). Ne jamais
pousser sans validation.
