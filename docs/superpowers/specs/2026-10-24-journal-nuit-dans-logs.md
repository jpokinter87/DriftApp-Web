# Journal de nuit dans `logs/nuits/`

## Problème

Le journal de nuit (pluie, décisions de la protection, cycles cimier) s'écrit dans
`data/nights/AAAA-MM-JJ.jsonl`. Serge envoie le zip de `logs/` : le journal n'y est pas,
sauf s'il pense à ajouter `data/nights/` à la main. Le risque est l'oubli, nuit après
nuit, et `/analyse-nuit` perd alors la source la plus fiable sur le cimier et la pluie.

## Décisions

- `services/night_journal.py` : `DEFAULT_NIGHTS_DIR` = `logs/nuits/` (racine des logs de
  `core/utils/log_paths.py`, donc `DRIFTAPP_LOGS_DIR` respecté), nom français comme
  `moteur/`, `encodeur/`, `cimier/`.
- Migration au démarrage de `cimier_service` (avant la purge) : `ranger_ancien_journal()`
  déplace les `*.jsonl` de `data/nights/` vers `logs/nuits/`. Un fichier déjà présent à
  destination n'est pas écrasé. Les erreurs sont avalées : ranger ne doit jamais empêcher
  le service de démarrer (même règle que `ranger_anciens_logs`). Le dossier vide est retiré.
- `data/nights/.gitkeep` et ses lignes `.gitignore` sont retirés : `logs/` est déjà ignoré.
- `scripts/diagnostics/chronologie_nuit.py` reconnaît déjà le journal par son nom hors de
  `asiair/` : seul son message « pas de journal » change de chemin.
- Docs à jour : `CLAUDE.md`, `/analyse-nuit`, `/diag-terrain` (`pi_software.md`).

## Hors périmètre

- Les sessions de suivi (`data/sessions/`) restent où elles sont.
- La rétention (30 nuits, `purge_old`) ne change pas.

## Critères de succès

- Tests : le dossier par défaut est sous la racine des logs ; la migration déplace, ne
  remplace pas un fichier existant, tolère l'absence de l'ancien dossier.
- Tests existants du journal, du service cimier et de la page Session verts.
