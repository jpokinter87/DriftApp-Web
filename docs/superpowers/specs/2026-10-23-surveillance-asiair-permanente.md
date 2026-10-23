# Surveillance permanente de l'ASIAIR

Date : 23/10/2026 — statut : **spec validée** (décisions JP du 23/10)

## Besoin

La sonde ASIAIR (6.23.3, `scripts/asiair_sonde.sh demarrer`) est devenue
indispensable : ses journaux des 21 et 22/10 ont expliqué le retournement de la
monture, les GOTO de recentrage, l'écart de pointage d'EQMod (6.24.1, 6.24.2).
Elle ne tourne aujourd'hui que si Serge pense à la lancer, et s'arrête au
redémarrage du Pi. On veut qu'elle tourne en permanence et garde ses journaux,
pour analyser les incidents après coup et préparer de futures évolutions.

## Décisions

| # | Question | Décision |
|---|---|---|
| 1 | Hébergement | **Service systemd dédié** `asiair_monitor.service` : indépendant du moteur et du cimier, relancé par systemd, installé et redémarré par l'OTA, inclus dans « Redémarrer les services » |
| 2 | Rétention | **14 nuits**, un fichier par nuit (midi → midi, comme le journal de nuit) |
| 3 | Activation | Nouvelle clé `asiair.monitor_enabled`, **true** dans le template : active dès que `asiair.host` est renseigné, désactivable sur la page Configuration |

## Comportement

- Le service lit la section `asiair` au démarrage. `monitor_enabled=false` ou
  `host` vide : il le dit une fois dans son log et reste inactif (sans quitter :
  systemd et l'OTA le voient actif). Un changement de configuration s'applique
  par « Redémarrer les services ».
- Même dialogue que la sonde : port 4400, lectures seules toutes les 5 s
  (`scope_get_info`, `scope_get_pierside`, `scope_get_track_state`), tout ce qui
  est reçu (réponses et événements non sollicités) est journalisé.
- **Journal brut** : `logs/asiair/AAAA-MM-JJ.jsonl` (même format de ligne que la
  sonde : `t`, `heure`, `msg` ou `sonde`). Le fichier change à midi
  (`night_journal.night_key`), purge au-delà de 14 jours
  (`night_journal.purge_old`) au démarrage et à chaque changement de nuit.
  Volume constaté : ~8 Mo par nuit, ~120 Mo au pire.
- **Journal lisible** : `logs/asiair/asiair_monitor.log` (1 Mo × 3, rotation),
  les lignes qu'affichait la console de la sonde, plus les messages du pilote
  INDI (`INDIServer`, champ `Msg` : « Stopping Tracking », « Target pier side
  set to EAST »…), jusqu'ici gardés dans le seul JSONL.
- **ASIAIR éteint** (de jour) : une seule ligne au début de la coupure, une
  au retour (« reconnecté après n min »), dans les deux journaux. La sonde en
  écrivait une toutes les 10 s.
- Service sous `User=slenk` : il ne touche à aucun matériel du Pi.

## Ce qui disparaît

`scripts/diagnostics/asiair_sonde.py` : sa logique est déplacée dans
`services/asiair_monitor.py` (ses tests suivent). `scripts/asiair_sonde.sh` ne
garde que `etat` (service actif ou non + dernières lignes du journal lisible) :
`demarrer`/`arreter` n'ont plus lieu d'être, `essai` ouvrirait une seconde
connexion qui écrirait dans le même journal.

## Hors champ

- Le watcher du suivi (6.24, `AsiairPierWatcher`) garde sa propre connexion.
  Le faire lire l'état publié par ce service est une évolution possible, pas
  nécessaire : l'ASIAIR accepte plusieurs clients (sonde et watcher ont tourné
  ensemble le 22/10).
- Pas d'affichage sur le dashboard.
- `start_dev.sh` ne lance pas ce service : en dev l'ASIAIR est injoignable.

## Critères de succès

- Tests : nuit miniature contre un faux ASIAIR (journal de la bonne nuit, lignes
  INDI au journal lisible), coupure longue journalisée une seule fois, bascule
  de fichier à midi, service inactif sans host ou désactivé.
- Garde-fous OTA existants (`tests/test_ota_restart.py`, qui énumèrent les
  `*.service` du dépôt) verts avec la nouvelle unité.
- Vérifié en local : service lancé contre un faux ASIAIR, puis ASIAIR coupé et
  rétabli.
