# Diagnostic hardware — protocoles multimètre/pinout pour Serge

Procédures **durables** (techniques de mesure, faits matériels stables). Les IPs/ports
viennent toujours de `read_terrain_values.py`, jamais d'ici.

Architecture en vigueur :
- **Coupole** : Pi → USB série → **Pi Pico RP2040** (firmware PIO) → **DM860T en 36 V**
  → moteur NEMA. Encodeur EMS22A lu par `ems22d`.
- **Cimier V3 tout-Shelly** (pivot v6.7, plus de Pico W) : contrôleur autonome STEP +
  **DM556T**, piloté par 4 Shelly — 24V (alim du module), Uni+ (butées HAUT/BAS, RPC),
  MOT (marche/arrêt moteur), UPDN (sens via DPDT externe).
- **Pluie** : capteur MH-RD (sortie D0) sur un Shelly Plus Uni dédié, résistance
  chauffante sur un relais Shelly Gen 1 dédié.

## Sommaire
- [Règles d'or (à rappeler systématiquement)](#règles-dor-à-rappeler-systématiquement)
- [Pico RP2040 de la coupole](#pico-rp2040-de-la-coupole)
- [Moteur muet ou qui « frémit » sans tourner](#moteur-muet-ou-qui-frémit-sans-tourner)
- [Driver : alimentation, DIP, ENA, bobines](#driver--alimentation-dip-ena-bobines)
- [Shelly du cimier (V3)](#shelly-du-cimier-v3)
- [Capteur de pluie](#capteur-de-pluie)

## Règles d'or (à rappeler systématiquement)

- **Deux drivers sont montés en parallèle sur le moteur de la coupole** : le DM860T
  piloté par notre Pico, et le DM556T du boîtier constructeur UPAN. Ne brancher
  PUL+/DIR+ que sur le **DM860T**.
- **Arrêter `motor_service` avant toute commande `mpremote`** sur le Pico (le service
  garde `/dev/ttyACM0` ouvert). Ne jamais lancer `sudo mpremote`.
- **Vérifier chaque point au multimètre AVANT de souder ou de rebrancher**, puis
  reconnecter **fil par fil avec re-test** entre chaque étape.
- **Vérifier le point de masse côté module**, pas seulement côté carte : un fil de
  masse soudé sur un 3,3 V a déjà grillé un régulateur.

## Pico RP2040 de la coupole

Procédure de flash et de dépannage complète : `firmware/README.md` (consultable sur le
Pi). Points de contrôle :
1. `ls /dev/ttyACM*` → le Pico doit apparaître (sinon câble USB / Pico non alimenté).
2. Un mouvement coupé net en pleine course, avec `ERROR` dans le log moteur, oriente
   vers le firmware (version flashée ?) avant le matériel.
3. Signal STEP en 3,3 V direct : suffisant pour le DM860T, pas de réhausseur.

## Moteur muet ou qui « frémit » sans tourner

Arbre de décision (si le Pico émet des fronts STEP propres, ne PAS re-suspecter le
firmware) :

- **Aucun bruit du tout** → alim puissance du driver et ENA (driver pas énergisé).
- **Micro-claquement à chaque pas sans rotation** → courant de phase trop bas (DIP) ou
  **bobine ouverte** (câblage moteur).
- **Bruit de calage au démarrage** → départ sans rampe ou vitesse trop haute
  (`motor_driver.fast_delay_us`, `ramp_time_s`) : voir la config avant le matériel.

## Driver : alimentation, DIP, ENA, bobines

Vaut pour le DM860T (coupole, 36 V) comme pour le DM556T (cimier). Suspects par ordre
de probabilité quand le signal arrive mais le moteur ne tourne pas :
1. **Alim puissance** V+/VDC : séparée des rails logiques. Mesurer sa présence. NE PAS
   la confondre avec PUL+/DIR+ (logique).
2. **DIP switches** : courant de phase (trop bas = pas de couple) et microstepping
   (coupole : 4 microsteps). Comparer aux réglages connus.
3. **ENA** : vérifier qu'il n'est pas maintenu en état « désactivé ».
4. **4 fils moteur A+/A−/B+/B−** : continuité de chaque paire (A+↔A−, B+↔B−) →
   quelques ohms. Bobine **ouverte** = moteur qui frémit sans tourner.

## Shelly du cimier (V3)

Hosts lus en config : `power_switch.host` (24V), `switch_reader.host` (Uni+),
`motor_shelly.host_motor` (MOT), `motor_shelly.host_dir` (UPDN).

```bash
curl -s http://<power_switch.host>/relay/0                         # {"ison": …}
curl -s "http://<power_switch.host>/relay/0?turn=on"               # forcer le 24 V
curl -s "http://<switch_reader.host>/rpc/Input.GetStatus?id=1"     # butée HAUT
curl -s "http://<switch_reader.host>/rpc/Input.GetStatus?id=0"     # butée BAS
```
Attendu : JSON quasi instantané. Timeout = Shelly injoignable (WiFi/IP/alim).

Conventions validées terrain (17-18/06), à ne pas « corriger » :
- **Moteur MOT** : le moteur tourne quand le relais est sur `turn=off`
  (`motor_on_relay_state=false`). Relais ON = moteur arrêté ; d'où `default_state=ON`
  obligatoire sur le Shelly MOT (sinon moteur incontrôlé à son réveil).
- **Sens UPDN** : ouverture = `turn=on` (`open_dir_state=true`).
- **Butées NC** : `state=true` = contact fermé = repos ; `state=false` = butée atteinte
  (`switch_reader.invert=true`). Les deux à `false` = anomalie (shunts débranchés).
- MOT et UPDN sont alimentés **en aval du 24 V** : injoignables quand il est coupé, et
  ~2 s après chaque mise sous tension (reboot). Pour découpler un problème, forcer le
  24 V à ON via `curl`, puis tester le reste.
- Batterie vide : les Shelly ne se réveillent qu'au contact des patins de recharge, la
  coupole au parking (45°).

## Capteur de pluie

Shelly Plus Uni dédié (`weather_provider.host`), sortie D0 du MH-RD sur l'entrée `id=0` :
```bash
curl -s "http://<weather_provider.host>/rpc/Input.GetStatus?id=0"   # state=true = pluie
```
- Pluie réelle mais `state=false` → réglage du trimpot du comparateur (seuil trop dur).
- Alternance rapide true/false sous l'averse → le capteur « bavarde » ; voir les lignes
  `rain_read` dans `logs/cimier_service.log`.
- Résistance chauffante (`rain_heater_switch.host`, `/relay/0`) : ON tant que la
  protection pluie est armée ; l'auto_off du relais est réglé à 300 s côté app Shelly.
