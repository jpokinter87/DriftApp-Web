# Sous-répertoires thématiques pour `logs/`

Date : 19/10/2026 — statut : **spec à valider** (aucun code écrit)

## Besoin

`logs/` mélange tout à plat : 175 fichiers sur la machine de dev le 19/10
(74 `motor_service_*`, 69 `django_*`, 10 `ems22d_*`, cimier, mises à jour,
redémarrages, rapports de diagnostic). On ne s'y retrouve plus, ni ici ni sur
le Pi quand Serge doit retrouver un fichier.

Une partie du volume venait des tests (corrigé en 6.21.17 : `DRIFTAPP_LOGS_DIR`)
et disparaîtra avec la purge à 7 jours. Le rangement reste utile : sur une nuit
normale le Pi produit déjà 4 familles de fichiers distinctes.

## Proposition

| Sous-dossier | Contenu | Écrit par (utilisateur systemd) |
|---|---|---|
| `logs/moteur/` | `motor_service_*.log` (démarrage + un par session de suivi) | `motor_service` (root) |
| `logs/encodeur/` | `ems22d_*.log` | `ems22d` (slenk) |
| `logs/cimier/` | `cimier_service.log*` ; en dev `cimier_simulator.log` | `cimier_service` (root) |
| `logs/web/` | `django_*.log` ; en dev `django_runserver.log` | Django (slenk) |
| `logs/diagnostics/` | `calibration_vitesse_*`, `diagnostic_moteur_*`, `inclinometre_*`, `hardware_detection.txt` | scripts lancés à la main |
| `logs/` (racine) | `update.log`, `update_status.json`, `restart.log`, `restart_status.json`, `migrate_*.log` | `update_driftapp.sh`, `restart_services.sh` |

### Décision 1 — les fichiers de mise à jour restent à la racine (recommandé)

Pendant une mise à jour par l'interface, c'est **l'ancien** script
`update_driftapp.sh` qui tourne : il écrit sa progression à l'ancien
emplacement. Le nouveau Django, redémarré en fin de mise à jour, la lirait au
nouveau : la barre de progression et le compte rendu casseraient précisément le
jour où on livre ce changement. L'OTA est le seul moyen d'atteindre le Pi sans
SSH, on ne le met pas en jeu pour du rangement.

Alternative écartée sauf avis contraire : `logs/maintenance/` avec une lecture
des deux emplacements par Django pendant une version de transition, retirée
ensuite. Deux livraisons et un code temporaire pour 4 fichiers.

### Décision 2 — chaque service range ses anciens fichiers au démarrage (recommandé)

Après la mise à jour, les fichiers déjà présents à la racine ne seraient plus
purgés (la purge à 7 jours ne regarde que le sous-dossier) et resteraient pour
toujours. Au démarrage, chaque service déplace dans son sous-dossier les
fichiers de **son** préfixe encore à la racine (opération idempotente, sans
effet ensuite).

Pourquoi pas dans `update_driftapp.sh` : c'est l'ancien script qui s'exécute à
la mise à jour (cf. 6.6.2), le déplacement n'aurait lieu qu'à la mise à jour
suivante, et la machine de dev ne passe jamais par l'OTA.

### Décision 3 — noms en français

`moteur`, `encodeur`, `cimier`, `web`, `diagnostics` : ce sont les mots de
Serge et des protocoles terrain.

## Conception

- **Une seule source pour les chemins** : `core/config/config.py` définit déjà
  `LOGS_DIR` (aujourd'hui inutilisé, comme `core/config/logging_config.py`). On
  y ajoute la prise en compte de `DRIFTAPP_LOGS_DIR` et une fonction
  `logs_subdir(nom)` qui crée et renvoie le sous-dossier. `motor_service`,
  `ems22d_calibrated.py`, `cimier_service`, les settings Django et les scripts
  de diagnostic Python l'utilisent au lieu de recalculer chacun leur chemin
  (quatre définitions dupliquées aujourd'hui).
- **Déplacement des anciens fichiers** : une fonction voisine,
  `ranger_anciens_logs(motif, nom)`, appelée par chaque service avant d'ouvrir
  son log. Un déplacement qui échoue (droits) est ignoré : il ne doit jamais
  empêcher un service de démarrer.
- **Scripts shell** (`start_dev.sh`, `start_web.sh`, `inclinometre.sh`) : chemins
  mis à jour à la main (pas d'accès à la fonction Python).
- **Droits** : chaque sous-dossier n'est écrit que par un seul service, celui
  qui le crée ; pas de dossier partagé entre root et slenk. `diagnostics/` est
  créé par le premier script qui y écrit ; le `chown -R logs/` de
  `update_driftapp.sh` (déjà présent) réaligne à chaque mise à jour.
- **`.gitignore`** : `logs/*` + `!logs/.gitkeep` (6.21.15) couvre déjà les
  sous-dossiers.

## Ce qui doit suivre

- Documentation : `CLAUDE.md` (Debugging, simulation d'averse),
  `scripts/diagnostics/README.md`, skill `diag-terrain` (les chemins y sont
  donnés à Serge).
- **PDF terrain à régénérer** : `docs/protocole_inclinometre_terrain.pdf` et
  `docs/protocole_vitesse_v6.16_terrain.pdf` citent `logs/inclinometre_*` et
  `logs/calibration_vitesse_*`. Prévenir Serge que les chemins changent.
- Hors périmètre : `core/config/logging_config.py` est du code mort (aucun
  appelant) ; le signaler, ne pas le supprimer dans ce chantier.

## Critères de succès

1. Sur la stack dev, après `./start_dev.sh start` et un suivi : plus aucun
   fichier de service à la racine de `logs/` hors fichiers de mise à jour ;
   chaque famille dans son sous-dossier.
2. Des fichiers `motor_service_*`, `ems22d_*`, `django_*`, `cimier_service.log*`
   déposés à la racine avant le démarrage se retrouvent dans leur sous-dossier
   après ; un second démarrage ne change rien.
3. La purge à 7 jours agit dans les sous-dossiers.
4. Un déplacement impossible (fichier en lecture seule, dossier sans droits)
   n'empêche pas le service de démarrer.
5. Mise à jour OTA simulée en dev : la progression s'affiche du début à la fin.
6. Suite de tests verte ; aucune écriture dans le vrai `logs/` pendant les
   tests (garde-fou 6.21.17 conservé).

## Risques

- Sur le Pi, un sous-dossier créé par root alors qu'un service slenk doit y
  écrire. Écarté par construction (un dossier par service), à vérifier au
  premier démarrage terrain : `ls -l logs/`.
- Serge cherche un fichier à l'ancien emplacement d'après un protocole imprimé.
  D'où la régénération des PDF et un message explicite à la livraison.
