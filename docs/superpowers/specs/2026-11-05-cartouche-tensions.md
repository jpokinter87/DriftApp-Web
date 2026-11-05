# Cartouches « Tensions » et « Capteurs », butées perdues en cycle

**Date** : 05/11/2026 — demande terrain (Serge), validée par JP.

## Besoin

Surveiller depuis le dashboard, et retrouver dans les logs, la tension :

- des **batteries** du boîtier cimier : `http://192.168.1.84/rpc/Voltmeter.GetStatus?id=100`
  (Shelly Uni+ des butées). Pleine charge = 12,6 V. Le Shelly n'est alimenté que
  coupole sous tension : injoignable le reste du temps, ce n'est pas une panne ;
- du **chargeur** : `http://192.168.1.87/rpc/Voltmeter.GetStatus?id=100` (Shelly
  Plus Uni du capteur de pluie, toujours sous tension : il doit toujours répondre).

Réponse Shelly : `{"id":100,"voltage":12.43,...}`, on lit `voltage`.

## Décisions (JP, 05/11)

- Affichage : valeurs brutes en volts, **fond coloré** selon le niveau.
- Journal de nuit : **un relevé toutes les 5 min**, plus une ligne immédiate quand
  une mesure apparaît ou disparaît (boîtier cimier mis sous tension ou coupé).

## Conception

- **Lecture** : `cimier_service`, qui interroge déjà .84 et .87. Nouveau module
  `core/hardware/voltage_monitor.py` (`VoltageMonitor`) appelé dans `tick()` ;
  le HTTP passe par `core/hardware/shelly_rpc.py` (nouvelle `read_voltage`, même
  gestion d'erreur que `read_input_state`).
- **Config** `cimier.voltages` (hôtes dans `data/config.json` et le template,
  jamais dans le code) : `battery_host`, `battery_id`, `charger_host`,
  `charger_id`, `timeout_s` (2 s), `read_interval_s` (60 s),
  `journal_interval_s` (300 s), `battery_good_v` (12,4), `battery_low_v` (12,0).
  Hôte vide = mesure non lue ; les deux vides = fonction absente.
- **Publication** : clé `voltages` de `/dev/shm/cimier_status.json`
  (`battery`/`charger` : `voltage` ou `null`, `read_at`, `error` ; seuils).
- **Journal** : événement `voltages` (`battery`, `charger` en volts ou `null`,
  `reason` = `periodic` | `change`), plus une ligne `cimier_event=voltages` dans
  `cimier_service.log` (chronologie de nuit).
- **Dashboard** : cartouche `TENSIONS` pleine largeur sous `CORRECTIONS`
  (colonne boussole). Pastille par mesure : vert ≥ `battery_good_v`, ambre entre
  les deux seuils, rouge < `battery_low_v`, grise « hors tension » (batteries)
  ou ambre « injoignable » (chargeur). Mêmes seuils pour le chargeur : une sortie
  chargeur sous 12,4 V est anormale. Thèmes nuit et jour couverts.
- **Dev** : le simulateur Shelly répond à `Voltmeter.GetStatus` (id 100 batteries
  12,55 V, id 101 chargeur 13,60 V) et `GET /dev/voltage?id=100&v=11.8` change une
  valeur ; `_apply_dev_mode_overrides` pointe les deux mesures sur le simulateur.

## Ajout du 05/11 : pastille « prêt » (Serge, validé par JP)

Éviter de remonter le cimier alors que le Shelly Uni+ des butées ne répond pas.
Cartouche `CAPTEURS` sous `CORRECTIONS` : vert « ✓ PRÊT — tout répond », rouge
« ✗ Injoignable : … » avec la liste, ambre tant que rien n'est vérifié.

- `cimier_service._health_check()` toutes les `cimier.health_check_interval_s`
  (60 s), **seulement au repos** (aucune commande en attente, hors cooldown) :
  butées = vraie lecture `Input.GetStatus` ; 24 V = `PowerSwitch.probe()`
  (`/relay/<n>` ou `Switch.GetStatus`, sans commuter) ; pluie = dernière lecture
  de la veille aboutie (pas l'état confirmé, que l'anti-rebond retarde).
  Publié sous `health` ; chaque changement → `cimier_event=health` et
  événement `health` au journal de nuit.
- MOT (.85) et UPDN (.86) ne sont alimentés qu'avec le 24 V : non vérifiables.
- Côté page : moteur = status présent et sans erreur (pas de critère de
  fraîcheur : au repos `motor_service` ne réécrit son status que sur
  événement) ; encodeur ni absent, ni figé, ni en erreur ; service cimier frais.

## Ajout du 05/11 : butées perdues pendant un cycle

Trouvé en lisant `_poll_target_switch` : une lecture des butées en échec y
était ignorée, et le moteur tournait jusqu'à `cycle_timeout_s` (90 s). Désormais,
sans lecture réussie depuis `cimier.switch_lost_timeout_s` (3 s), le cycle
s'arrête : moteur et 24 V coupés (cleanup existant), erreur
`switches_unreachable`. Avec un délai de lecture de 3 s, une seule lecture en
timeout suffit à couper ; un refus de connexion rapide laisse quelques essais.

## Hors périmètre

Graphique de tension sur la page Session, alertes, tension pendant un cycle
cimier (la boucle ne tourne pas pendant le cycle).

## Critères de succès

- Tests : `read_voltage` (OK, injoignable, payload invalide), `VoltageMonitor`
  (cadence, journal périodique et sur changement, describe), parser config,
  simulateur.
- En dev : cartouche affiché, `/dev/voltage` fait changer la couleur.
