# Code Review Report — 01-04: Scripts, Daemon & Synthèse Globale

**Date:** 2026-03-13
**Scope:** main.py, main_gui.py, ems22d_calibrated.py, start_web.sh, start_dev.sh + synthèse
**Fichiers analysés:** 5/5

---

## Résumé (ce rapport)

| Sévérité | Nombre |
|----------|--------|
| CRITIQUE | 0 |
| HAUT | 3 |
| MOYEN | 5 |
| BAS | 4 |
| **Total** | **12** |

---

## HAUT

### H-20: `main.py` et `main_gui.py` — duplication quasi-totale
- **Fichiers:** `main.py`, `main_gui.py`
- **Type:** duplication
- **Description:** Les deux fichiers sont identiques à 90% (logging, config, détection hardware, error handling). Seule la ligne de lancement diffère (`DriftApp(config)` vs `DriftAppGUI(config)`). C'est 90 lignes × 2 au lieu de ~100 lignes partagées.
- **Recommandation:** Extraire une fonction `bootstrap(app_class)` commune.

### H-21: `ems22d_calibrated.py` — constantes en dur au lieu de config.json
- **Fichier:** `ems22d_calibrated.py:38-55`
- **Type:** incohérence
- **Description:** Le daemon encodeur hardcode toutes ses constantes : `SWITCH_GPIO=27`, `SWITCH_CALIB_ANGLE=45`, `CALIBRATION_FACTOR=0.010851`, `SPI_BUS=0`, etc. Ces mêmes valeurs existent dans `data/config.json` (sections `encodeur` et `parking`). Si on modifie config.json, le daemon garde les anciennes valeurs.
- **Recommandation:** Charger la config depuis `config.json` au démarrage du daemon, avec fallback sur les constantes actuelles.

### H-22: `start_dev.sh` — utilise `python3` système au lieu du venv
- **Fichier:** `start_dev.sh:59,76`
- **Type:** bug-risk
- **Description:** `start_dev.sh` utilise `python3` (système) alors que `start_web.sh` utilise `$PROJECT_DIR/.venv/bin/python`. En développement, le python système pourrait ne pas avoir les dépendances (Django, astropy, etc.) installées.
- **Recommandation:** Utiliser le même pattern que `start_web.sh` : vérifier et utiliser le venv.

---

## MOYEN

### M-31: `ems22d_calibrated.py` — pas de gestion de signal SIGTERM
- **Fichier:** `ems22d_calibrated.py:402-418`
- **Type:** robustesse
- **Description:** Le daemon gère `KeyboardInterrupt` (SIGINT) mais pas SIGTERM. Quand systemd arrête le service (`systemctl stop ems22d`), il envoie SIGTERM. Sans handler, le daemon est tué brutalement sans `close_spi()` ni `gpiochip_close()`.
- **Recommandation:** Ajouter `signal.signal(signal.SIGTERM, lambda *_: d.stop())`.

### M-32: `ems22d_calibrated.py` — TCP server utilise `accept()` bloquant
- **Fichier:** `ems22d_calibrated.py:286-299`
- **Type:** design
- **Description:** `tcp_worker()` utilise `s.accept()` bloquant. Quand `self.running = False`, le thread reste bloqué sur `accept()` et ne se termine que si un dernier client se connecte. Le socket n'a pas de timeout.
- **Recommandation:** Ajouter `s.settimeout(1.0)` et gérer `socket.timeout` dans la boucle.

### M-33: `ems22d_calibrated.py` — filtre anti-saut ne gère pas la circularité
- **Fichier:** `ems22d_calibrated.py:344-353`
- **Type:** bug
- **Description:** Le filtre anti-saut calcule `diff = abs(angle - self.last_valid_angle)` puis `diff = min(diff, 360 - diff)`. Mais la correction `angle = self.last_valid_angle` quand diff > 30° est un filtre grossier. Si la coupole bouge vraiment de 31° (GOTO rapide), le filtre le rejette et bloque la mise à jour de l'angle pendant toute la durée du mouvement.
- **Recommandation:** Augmenter le seuil à 45° ou désactiver le filtre temporairement pendant les GOTO (via un flag IPC).

### M-34: `start_web.sh` — `pkill -f` peut tuer des processus non désirés
- **Fichier:** `start_web.sh:115-120`
- **Type:** bug-risk
- **Description:** `pkill -f "motor_service.py"` tue tout processus dont la ligne de commande contient "motor_service.py", y compris un éditeur ou un `tail -f` sur ce fichier.
- **Recommandation:** Utiliser des PID files ou `pkill -P` pour cibler uniquement les processus enfants.

### M-35: `start_dev.sh` — `cd web` puis `cd ..` dans `start_django()`
- **Fichier:** `start_dev.sh:75-76`
- **Type:** bug-risk
- **Description:** Changer de répertoire dans une fonction de script bash affecte le répertoire courant du script. Si `start_django()` échoue entre `cd web` et `cd ..`, les commandes suivantes s'exécutent dans le mauvais répertoire.
- **Recommandation:** Utiliser `(cd web && python3 manage.py runserver ...)` dans un sous-shell, ou passer le chemin complet.

---

## BAS

### L-22: `main.py` — `time.sleep(0.5)` avant lancement app
- **Fichier:** `main.py:70`
- **Type:** inutile
- **Description:** 500ms d'attente sans raison apparente entre le log système et le lancement de l'app.
- **Recommandation:** Supprimer.

### L-23: `ems22d_calibrated.py` — import `datetime` aliasé en `dt_logging`
- **Fichier:** `ems22d_calibrated.py:64`
- **Type:** style
- **Description:** `from datetime import datetime as dt_logging` — alias non standard, utilisé une seule fois pour le timestamp de session.
- **Recommandation:** Utiliser `from datetime import datetime` directement.

### L-24: `start_web.sh` — restart duplique le code de start
- **Fichier:** `start_web.sh:203-224`
- **Type:** duplication
- **Description:** La branche `restart` copie-colle le code de `start` au lieu d'appeler `$0 start`.
- **Recommandation:** Simplifier en `stop_all; sleep 2; $0 start` (comme `start_dev.sh` le fait déjà).

### L-25: `start_dev.sh` — `check_dependencies` utilise `pip` au lieu de `uv`
- **Fichier:** `start_dev.sh:48`
- **Type:** incohérence
- **Description:** Le projet utilise `uv` (venv, sync) d'après start_web.sh, mais start_dev.sh propose `pip install django djangorestframework`.
- **Recommandation:** Utiliser `uv sync` ou `uv pip install`.

---

# SYNTHÈSE GLOBALE — Phase 1 Complète

## Statistiques consolidées

| Rapport | Fichiers | Critiques | Hauts | Moyens | Bas | Total |
|---------|----------|-----------|-------|--------|-----|-------|
| 01-01 Core | 10 | 2 | 8 | 12 | 9 | 31 |
| 01-02 Tracking | 8 | 2 | 6 | 10 | 7 | 25 |
| 01-03 Services & Web | 8 | 2 | 5 | 8 | 5 | 20 |
| 01-04 Scripts & Synthèse | 5 | 0 | 3 | 5 | 4 | 12 |
| **TOTAL** | **31** | **6** | **22** | **35** | **25** | **88** |

## Top 10 — Priorités pour le refactoring (Phase 2)

| # | ID | Sévérité | Description | Effort |
|---|----|---------|----|--------|
| 1 | C-01 | CRITIQUE | Double système de config (config.py vs config_loader.py) | M |
| 2 | C-02 | CRITIQUE | Mode fast_track mort encore parsé | S |
| 3 | C-03 | CRITIQUE | Références mortes FAST_TRACK dans tracker.py | S |
| 4 | C-04 | CRITIQUE | Chemin relatif config.json dans catalogue.py | S |
| 5 | C-05 | CRITIQUE | SECRET_KEY + DEBUG + ALLOWED_HOSTS en dur | S |
| 6 | C-06 | CRITIQUE | MotorServiceClient dupliqué | S |
| 7 | H-01 | HAUT | read_stable() moyenne incorrecte 0°/360° | S |
| 8 | H-02 | HAUT | Double lecture position feedback controller | M |
| 9 | H-04 | HAUT | read_angle() boucle infinie possible | S |
| 10 | H-09 | HAUT | MoteurCoupole statique en simulation | M |

**Légende effort :** S = Small (< 30min), M = Medium (1-2h), L = Large (> 2h)

## Patterns transversaux identifiés

### 1. Duplication de code (systémique)
- Jour Julien : 3 copies (calculations.py, ephemerides.py, motor_service.py)
- Normalisation angles : 2 copies (angle_utils.py, calculations.py)
- MotorServiceClient : 2 copies (hardware/views.py, tracking/views.py)
- Main bootstrap : 2 copies (main.py, main_gui.py)
- Shortest path : 2 implémentations (angle_utils.py, adaptive_tracking.py)

### 2. Double système de configuration
`config.py` (ancien) et `config_loader.py` (nouveau) coexistent avec des incompatibilités. Le catalogue dépend encore de l'ancien. Le daemon encodeur ignore les deux.

### 3. Simulation incomplète
- `MoteurCoupole` appelé statiquement dans tracker (H-09)
- Position simulée non synchronisée entre processus (H-05)
- Daemon encodeur non simulé — constantes en dur (H-21)

### 4. Robustesse daemon
- `read_angle()` boucle infinie possible (H-04)
- Pas d'atomicité lecture commandes IPC (M-24)
- Pas de SIGTERM handler (M-31)

### 5. Code mort
- FAST_TRACK dans config_loader, tracker (C-02, C-03)
- `load_site_config()`, `to_dict()`, `_add_time_component()`, ramp methods
- `encoder_reader.py` duplique DaemonEncoderReader

## Recommandation pour Phase 2 (Refactoring)

**Ordre de traitement suggéré :**
1. **Config unification** (C-01, C-02, C-04, H-15, H-21) — le plus impactant, débloque tout
2. **Code mort** (C-03, M-01, M-02, M-12, M-16, M-07) — nettoyage rapide, réduit la surface
3. **Bugs latents** (H-01, H-04, H-14, M-17, M-27, M-33) — corrections ciblées
4. **Duplication** (C-06, H-11, H-20, M-14, M-15, M-23) — DRY
5. **Performance** (H-02, H-10, H-12, M-11) — optimisations
6. **Sécurité web** (C-05, H-19, L-21) — hardening Django
7. **Architecture** (H-18, H-08, H-05, M-31, M-32) — refactoring structural

---

*Rapport généré : 2026-03-13*
*Reviewer : Claude (revue automatisée)*
