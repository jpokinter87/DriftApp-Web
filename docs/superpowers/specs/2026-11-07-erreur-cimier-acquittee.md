# Erreur cimier affichée jusqu'à acquittement

**Date** : 07/11/2026 — demande terrain (Serge), validée par JP.

## Besoin

Une erreur de cycle cimier (`cimier_stalled`, `cycle_timeout`, butées perdues…)
ne restait visible que `post_off_quiet_s` (10 s) dans le panneau Cimier ; la raison
survivait seulement dans la timeline, repliée par défaut. Serge veut un message qui
reste affiché jusqu'à ce qu'il l'acquitte, **y compris quand le dashboard était
éteint au moment de l'erreur** (supervision reprise plus tard dans la nuit).

## Décisions

- 6.31.7 : encart rouge sous les boutons, gardé en mémoire dans le navigateur.
- 6.31.8 (JP, 07/11) : l'erreur est gardée **côté service, sur disque** —
  `data/cimier_alert.json` (hors `/dev/shm` : survit à un redémarrage du Pi).

## Conception

- `cimier_service._record_alert(action, error_message)` aux deux sorties en erreur
  de `_run_cycle` (preflight `error`/`unreachable`, fin de cycle avec
  `error_message`). Fichier `{error_message, action, first_at, last_at, count}` ;
  les erreurs suivantes avant acquittement incrémentent `count` et gardent
  `first_at` (relances de fermeture). Écriture atomique (`.tmp` + `replace`).
- Django : `CIMIER_SERVICE_IPC["ALERT_FILE"]` ; `GET /api/cimier/status/` ajoute
  `alert` (même service arrêté) ; `POST /api/cimier/alert/ack/` efface le fichier.
  Pas de passage par `cimier_command.json` : un acquittement n'écrase jamais un
  ordre d'ouverture/fermeture en attente.
- Dashboard : encart rouge « heure — raison (N erreurs, la dernière à …) » +
  bouton « J'ai vu » (tactile, aucun survol). Date ajoutée si l'erreur n'est pas
  du jour.

## Hors périmètre

Erreurs de démarrage du service (`switch_reader_not_configured`) et commandes
inconnues : pas des incidents de nuit, non gardées.
