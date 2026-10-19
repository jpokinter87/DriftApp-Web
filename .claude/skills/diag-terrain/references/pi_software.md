# Diagnostic logiciel Pi — banque de commandes pour Serge

Commandes à **faire taper par Serge directement sur le Pi** : il ne pratique pas
le SSH. Terminal par-dessus le dashboard en kiosque avec **Ctrl+Alt+T** (retour
Alt+Tab), puis `cd ~/DriftApp`. Préférer des commandes courtes ; la flèche Haut
rappelle la précédente. Injecter les valeurs réelles (host, port) lues via
`read_terrain_values.py`. Chaque commande est donnée avec son **résultat attendu**.

## Sommaire
- [Rappel architecture 3 processus](#rappel-architecture-3-processus)
- [Symptôme : un service est mort / ne démarre pas](#symptôme--un-service-est-mort--ne-démarre-pas)
- [Symptôme : IPC figé ou périmé](#symptôme--ipc-figé-ou-périmé)
- [Symptôme : encodeur indisponible / FROZEN](#symptôme--encodeur-indisponible--frozen)
- [Symptôme : le suivi ne démarre pas](#symptôme--le-suivi-ne-démarre-pas)
- [Symptôme : cimier vide / inactif](#symptôme--cimier-vide--inactif)
- [Symptôme : calibration bloquée](#symptôme--calibration-bloquée)
- [Symptôme : Django inaccessible](#symptôme--django-inaccessible)

## Rappel architecture 3 processus

```
Django (8000) → /dev/shm/motor_command.json → motor_service
       ↑                                            │
       └── /dev/shm/motor_status.json  ←────────────┘
       └── /dev/shm/ems22_position.json ← ems22d (50 Hz)
cimier_service ↔ /dev/shm/cimier_*.json (v6.0+)
```
Services systemd : `ems22d`, `motor_service`, `cimier_service`, `driftapp_web`.

## Symptôme : un service est mort / ne démarre pas

```bash
sudo systemctl status ems22d motor_service cimier_service driftapp_web --no-pager
```
Attendu : `active (running)` pour chacun. Sinon noter lequel + la dernière ligne d'erreur.

Logs du service fautif (50 dernières lignes) :
```bash
sudo journalctl -u <service> -n 50 --no-pager
```
Attendu : pas de traceback Python ni de boucle de redémarrage. Repérer `Traceback`,
`Permission denied`, `Address already in use`, `watchdog`.

Relance ciblée :
```bash
sudo systemctl restart <service>
```

## Symptôme : IPC figé ou périmé

```bash
ls -la /dev/shm/
cat /dev/shm/motor_status.json
cat /dev/shm/ems22_position.json
```
Attendu : fichiers présents. `ems22_position.json` rafraîchi ~50 Hz (20 ms),
`motor_status.json` ~20 Hz (50 ms). Comparer l'horodatage interne (champ `timestamp`/
`updated_at`) à l'heure du Pi (`date`). Écart > 1 s = **figé** → le producteur
(ems22d ou motor_service) est mort ou bloqué → voir section service mort.

Astuce fraîcheur fichier :
```bash
stat -c '%y' /dev/shm/motor_status.json && date
```

## Symptôme : encodeur indisponible / FROZEN

```bash
cat /dev/shm/ems22_position.json
sudo systemctl status ems22d --no-pager
sudo journalctl -u ems22d -n 30 --no-pager
```
Attendu : `angle` qui évolue quand la coupole bouge ; statut non `FROZEN`. Si figé :
vérifier le bus SPI et le câblage encodeur (passer au volet hardware si l'électrique
est suspect). Historiquement : faux positifs FROZEN possibles (cf. fiabilité v5.5).

## Symptôme : le suivi ne démarre pas

Souvent : `motor_service` ne tourne pas → `motor_status.json` figé en `idle` → les
commandes écrites dans `motor_command.json` ne sont jamais consommées.
```bash
sudo systemctl status motor_service --no-pager
cat /dev/shm/motor_status.json     # champ "status"/"mode"
cat /dev/shm/motor_command.json    # commande en attente ?
```
Attendu : `motor_service` actif ; après un « Démarrer le suivi », le statut passe de
`idle` à un mode tracking. S'il reste `idle` alors qu'une commande est présente →
motor_service bloqué/mort.

## Symptôme : cimier vide / inactif

```bash
cat /dev/shm/cimier_status.json
sudo systemctl status cimier_service --no-pager
```
Attendu : fichier présent, `state` non nul. Les logs utiles sont dans le fichier
(un `journalctl` vide est normal en prod). Depuis la 6.22 ils sont rangés par thème
(`logs/moteur/`, `logs/encodeur/`, `logs/cimier/`, `logs/web/`, `logs/diagnostics/`) ;
les fichiers d'avant la mise à jour y ont été déplacés au premier démarrage.
Sur une version antérieure, chercher `logs/cimier_service.log` à la racine :
```bash
tail -n 60 logs/cimier/cimier_service.log
tail data/nights/$(date +%Y-%m-%d).jsonl    # journal de nuit (pluie, fermetures)
```
Joignabilité des Shelly V3 (hosts lus en config) :
```bash
curl -s "http://<switch_reader.host>/rpc/Input.GetStatus?id=0"   # butée BAS
curl -s "http://<switch_reader.host>/rpc/Input.GetStatus?id=1"   # butée HAUT
curl -s http://<power_switch.host>/relay/0                        # alim 24 V
```
Attendu : JSON quasi instantané. Timeout → Shelly injoignable → volet hardware
(`references/hardware.md`). Les Shelly MOT/UPDN sont alimentés en aval du 24 V :
injoignables tant que le 24 V est coupé (normal hors cycle).

## Symptôme : calibration bloquée

`calibration.status` reste `running` > 180 s :
```bash
cat /dev/shm/motor_status.json | python3 -m json.tool | grep -A6 calibration
cat /dev/shm/ems22_position.json   # last_calibration_at publié ?
sudo journalctl -u motor_service -f
```
Attendu : transition vers `ok`/`degraded`. Si bloqué : coupole bloquée mécaniquement,
microswitch HS, ou ems22d ne publie pas `last_calibration_at`.

## Symptôme : Django inaccessible

```bash
curl -s http://localhost:8000/api/health/
sudo systemctl status driftapp_web --no-pager
```
Attendu : JSON `status: healthy`. Sinon relancer `driftapp_web` et lire ses logs.
