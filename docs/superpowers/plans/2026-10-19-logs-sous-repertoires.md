# Sous-répertoires thématiques pour `logs/` — plan d'implémentation

**Spec :** `docs/superpowers/specs/2026-10-19-logs-sous-repertoires.md`
(décisions 1 à 3 validées par JP le 19/10/2026).

**Objectif :** chaque famille de logs dans son sous-dossier (`moteur/`,
`encodeur/`, `cimier/`, `web/`, `diagnostics/`), fichiers de mise à jour
laissés à la racine, anciens fichiers rangés au démarrage de chaque service.

**Version cible :** 6.22.0 (un seul bump, en fin de plan).

## Écart à la spec, à connaître

La spec plaçait les helpers dans `core/config/config.py`. Ce module lit
`data/config.json` dès l'import, et ni `ems22d_calibrated.py` ni les settings
Django n'importent `core` aujourd'hui : y brancher le démon encodeur lui
ajouterait une lecture de config au démarrage. Les helpers vont donc dans un
module neuf, sans effet de bord, **`core/utils/log_paths.py`**
(bibliothèque standard seule). `core/config/config.py::LOGS_DIR` reste en
l'état (testé par `tests/test_config.py`, sans appelant) : le signaler, pas y
toucher.

Rappel de l'existant (inchangé) : la purge n'est pas la même partout —
motor_service et Django gardent 7 jours, ems22d garde les 10 derniers
fichiers, cimier_service tourne sur 1 Mo × 3. Chaque purge doit simplement
viser le sous-dossier.

---

## Tâche 1 — `core/utils/log_paths.py`

**Fichiers :** `core/utils/log_paths.py` (neuf), `tests/test_log_paths.py` (neuf).

API :

```python
def logs_root() -> Path:
    """DRIFTAPP_LOGS_DIR si défini (tests), sinon <projet>/logs. Lu à chaque appel."""

def logs_subdir(nom: str) -> Path:
    """logs_root() / nom, créé si besoin (parents=True, exist_ok=True)."""

def ranger_anciens_logs(motifs: Iterable[str], nom: str) -> int:
    """Déplace dans logs_subdir(nom) les fichiers de la racine qui
    correspondent à l'un des motifs glob. Renvoie le nombre déplacé.
    Un fichier déjà présent à destination n'est pas écrasé (on laisse
    l'ancien à la racine). Toute OSError est avalée, fichier par fichier :
    ne jamais empêcher un service de démarrer."""
```

- [x] Tests d'abord (doivent échouer) : sous-dossier créé sous
  `DRIFTAPP_LOGS_DIR` ; fichiers d'un motif déplacés, ceux d'un autre motif
  laissés ; second appel → 0 ; destination existante non écrasée ; dossier
  racine sans droit d'écriture (`chmod 0o500`) → pas d'exception, renvoie 0 ;
  fichiers de mise à jour (`update.log`, `update_status.json`,
  `restart*.json`) jamais concernés par les motifs des services.
- [x] Implémenter, `ruff`, tests verts.

## Tâche 2 — motor_service → `logs/moteur/`

**Fichier :** `services/motor_service.py` (bloc de configuration des logs en
tête de module, `rotate_log_for_tracking`, `main()`).

- [x] Test : avec `DRIFTAPP_LOGS_DIR` pointé vers un dossier contenant
  `motor_service_20261001_120000.log`, un rechargement du module range ce
  fichier dans `moteur/` et y crée le log de démarrage ; `LOGS_DIR` vaut
  `…/moteur`. (Rechargement via `importlib` dans un sous-processus
  `python -c` pour ne pas recharger le module partagé du processus de test —
  cf. note mémoire CI/xdist : pas de `importlib.reload` en fixture.)
- [x] `LOGS_DIR = logs_subdir("moteur")`, appel
  `ranger_anciens_logs(["motor_service_*.log"], "moteur")` **avant**
  `cleanup_old_logs()`. Retirer le `LOGS_DIR.mkdir` devenu redondant dans
  `main()`.
- [x] Adapter `tests/test_logs_isolation.py` (attend désormais `…/moteur`).

## Tâche 3 — ems22d → `logs/encodeur/`

**Fichier :** `ems22d_calibrated.py` (lignes `LOG_DIR`, `cleanup_old_logs`).

- [x] Test sur le modèle de `tests/test_ems22d_force_calibration.py` (stub
  `lgpio`) : un `ems22d_*.log` à la racine est rangé dans `encodeur/` à
  l'import, `LOG_DIR` vaut `…/encodeur`.
- [x] `LOG_DIR = logs_subdir("encodeur")` + rangement de `ems22d_*.log` avant
  `cleanup_old_logs(10)`. Le script est lancé depuis la racine du projet par
  `ems22d.service` : vérifier que `core.utils.log_paths` s'importe (sinon
  ajouter le `sys.path.insert` utilisé ailleurs).

## Tâche 4 — cimier_service → `logs/cimier/`

**Fichiers :** `services/cimier_service.py` (`LOG_DIR`, `_build_log_handlers`).

- [x] Test : `_build_log_handlers()` hors dev-mode ouvre
  `…/cimier/cimier_service.log` et range `cimier_service.log*` (fichier courant
  et rotations `.1`…`.3`) présents à la racine.
- [x] Le rangement se fait dans `_build_log_handlers()`, avant l'ouverture du
  `RotatingFileHandler` (pas à l'import : le module est importé par les tests
  et par Django). En dev-mode, ranger aussi (le fichier est alors ouvert par la
  redirection de `start_dev.sh`, cf. tâche 7).

## Tâche 5 — Django → `logs/web/`

**Fichier :** `web/driftapp_web/settings.py` (`LOGS_DIR`, purge, `DJANGO_LOG_FILE`).

- [x] Test : `settings.LOGS_DIR` vaut `…/web` (adapter
  `tests/test_logs_isolation.py`).
- [x] `LOGS_DIR = logs_subdir("web")`, rangement de `django_*.log` avant
  `_cleanup_old_django_logs()`.
- [x] **Ne pas toucher** `web/health/views.py` (`UPDATE_STATUS_FILE`,
  `UPDATE_LOG_FILE`, `RESTART_STATUS_FILE`) ni `scripts/update_driftapp.sh`,
  `scripts/restart_services.sh` (décision 1). Vérification en fin de plan :
  `git diff --stat` ne les liste pas.

## Tâche 6 — Scripts de diagnostic → `logs/diagnostics/`

**Fichiers :** `scripts/diagnostics/calibration_vitesse_encodeur.py`,
`calibration_vitesse_max.py`, `diagnostic_moteur_complet.py`,
`inclinometre_monture.py`, `scripts/inclinometre.sh`,
`core/hardware/hardware_detector.py` (`save_detection_report`).

- [x] Python : remplacer `PROJECT_ROOT / "logs"` par
  `logs_subdir("diagnostics")` (règle aussi le `mkdir` manquant de
  `calibration_vitesse_encodeur.py` relevé par la revue).
- [x] `inclinometre.sh` : `CONSOLE=logs/diagnostics/inclinometre_console.txt`
  et `mkdir -p logs/diagnostics`. Vérifier en dev : `scripts/inclinometre.sh
  etat` sans capteur ne plante pas sur le chemin.
- [x] `save_detection_report` : défaut `logs/diagnostics/hardware_detection.txt`.
- [x] Pas de rangement automatique ici (pas de service qui démarre) : les
  anciens rapports restent à la racine, ce sont des fichiers ponctuels.
- [x] `compare_ngc3690_real_vs_simu.py` pointe un log historique précis :
  laisser tel quel.
- [x] *Ajouté en cours de route :* `logs_subdir` rend à l'utilisateur de `sudo`
  un dossier créé sous sudo (le README fait lancer `diagnostic_moteur_complet.py`
  avec sudo : `diagnostics/` aurait appartenu à root et `inclinometre.sh`, lancé
  en slenk, n'aurait plus pu y écrire avant la mise à jour suivante).
- [x] *Ajouté en cours de route :* `calibration_vitesse_max.py` écrivait dans
  `scripts/diagnostics/logs/` (racine calculée depuis l'ancien emplacement du
  script). Script obsolète (modes CRITICAL/CONTINUOUS de la v5.10), à signaler,
  pas supprimé.

## Tâche 7 — `start_dev.sh` et `start_web.sh`

- [x] `start_dev.sh` : redirections vers `logs/cimier/cimier_simulator.log`,
  `logs/cimier/cimier_service.log`, `logs/moteur/motor_service.log`,
  `logs/web/django_runserver.log` ; `mkdir -p` des sous-dossiers en tête ;
  messages `tail -f …` et aide de `status` mis à jour.
- [x] `start_web.sh` (chemin hors systemd) : `logs/cimier/cimier_service.log`,
  `logs/web/django.log`, `mkdir -p` correspondants.
- [x] *Ajouté en cours de route :* le secours manuel de `start_web.sh` redirigeait
  la sortie de cimier_service vers le fichier où le service écrit déjà lui-même
  (chaque ligne en double depuis la 6.15) : sortie console à part,
  `logs/cimier/cimier_service_console.log`.

## Tâche 8 — Documentation et PDF terrain

- [x] `CLAUDE.md` : chemins dans « Debugging Courant » (indicateurs cimier,
  simuler une averse), aide `start_dev.sh`.
- [x] `scripts/diagnostics/README.md` (section « Les scripts génèrent des
  rapports dans `logs/` »).
- [x] Skill `diag-terrain` (`SKILL.md`, `references/hardware.md`,
  `references/pi_software.md`) : `logs/cimier/cimier_service.log`, et préciser
  que les fichiers d'avant la mise à jour ont été rangés automatiquement.
- [x] Régénérer `docs/protocole_inclinometre_terrain.pdf` et
  `docs/protocole_vitesse_v6.16_terrain.pdf` (générateurs dans
  `scripts/diagnostics/gen_protocole_*_pdf.py`, `uv run --with fpdf2 …`) ;
  relire le rendu (pages concernées).
- [x] *Écart :* `docs/protocole_vitesse_v6.16_terrain.pdf` **non modifié**. C'est
  le protocole d'une campagne close (27/09) qui fait installer la 6.16.0 :
  y écrire `logs/diagnostics/` le rendrait incohérent. Pour une nouvelle
  campagne, le script affiche le chemin de son rapport (« Rapport détaillé : … »).
- [x] Protocole inclinomètre : édition passée à 6.22.0 (en-tête, sous-titre,
  prérequis, dépannage), pour que Serge distingue la nouvelle version ; pages
  1, 4 et 6 relues en rendu.

## Tâche 9 — Vérification de bout en bout (critères de succès de la spec)

- [x] Déposer à la racine de `logs/` de la machine de dev quelques copies
  datées de `motor_service_*`, `ems22d_*`, `django_*`, `cimier_service.log.1`.
- [x] `./start_dev.sh start 8080`, démarrer un suivi (`M31`, `skip_goto`),
  arrêter. Attendu : plus aucun fichier de service à la racine ; chaque famille
  dans son sous-dossier ; log de session `moteur/motor_service_…_M31.log`.
- [x] Redémarrer la stack : rien ne bouge (idempotence).
- [x] `./start_dev.sh status` et les `tail -f` indiqués pointent des fichiers
  qui existent.
- [x] Fichiers de mise à jour : inchangés à la racine, et `git diff --stat`
  ne touche ni `web/health/views.py`, ni `scripts/update_driftapp.sh`, ni
  `scripts/restart_services.sh`. (Le critère 5 de la spec, « OTA simulée en
  dev », se ramène à ça : le chemin OTA n'est pas modifié. La vraie
  vérification est la mise à jour sur le Pi.)
- [x] Suite complète, `ruff format --check .`, `ruff check .` ; aucune
  écriture dans le vrai `logs/` pendant les tests (même contrôle `find -newer`
  qu'en 6.21.17).
- [x] *Résultats (19/10, 23:06) :* témoins moteur/web/cimier rangés ; témoin
  `ems22d` resté à la racine (le démon ne tourne pas en dev, rangement vérifié
  en tâche 3 avec le Python système) ; log de session `moteur/…_M31.log` ;
  redémarrage : aucun fichier déplacé, seuls deux logs de démarrage ajoutés ;
  `/api/health/update/status/` 200 sur `logs/update_status.json` ; diff OTA
  contre origin vide ; 1592 tests verts, ruff propre, rien écrit dans `logs/`.
- [x] *Hors chantier, constaté :* échec intermittent de
  `TestCalibrateView::test_calibrate_post_returns_503_when_motor_client_fails`
  (2 sur ~20 passages ; doublon `hardware.views` / `web.hardware.views` sous
  xdist, déjà relevé en 6.11.0) ; un test interroge le vrai SIMBAD
  (`NoResultsWarning` intermittent).

## Tâche 10 — Livraison

- [x] Bump 6.22.0 (`pyproject.toml` + `uv lock`), entrée CLAUDE.md, commit,
  push.
- [ ] Message pour Serge (à rédiger avec JP) : où trouver les logs
  désormais, nouveaux PDF, et contrôle au premier démarrage `ls -l logs/`
  (sous-dossiers créés, propriétaires : `moteur/` et `cimier/` root,
  `encodeur/` et `web/` slenk).

## Risques et points d'arrêt

- Si un service ne démarre plus en dev après la tâche 2, 3 ou 4 : s'arrêter,
  ne pas enchaîner — c'est exactement le cas que `ranger_anciens_logs` doit
  rendre impossible.
- Sur le Pi, `logs/` appartient à slenk et motor_service tourne en root :
  `moteur/` créé par root, n'écrit que root, OK. Un `encodeur/` ou `web/` créé
  par root rendrait le démon encodeur ou Django muets : par construction seul
  leur service les crée ; le `chown -R logs/` de l'OTA réaligne de toute façon.
