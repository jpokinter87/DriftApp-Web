# 📋 Déploiement DriftApp v6.7.0 — protocole terrain (Serge)

> **Nouveauté v6.7.0** : le cimier passe en architecture **« tout-Shelly »** — le
> **Pico W est supprimé**. Les fins de course sont lues par le **Shelly Uni+ (.84)**,
> le moteur piloté par **Shelly MOT (.85)** + **UPDN (.86)**, l'alim par
> **Shelly 24V (.83)**.
>
> Le déploiement se fait en **3 phases**. **La Phase A (mise à jour logicielle) est
> sans risque** : le cimier reste désactivé, le moteur/suivi/encodeur ne changent pas.
> Les Phases B et C ne se font **que si le matériel Shelly V3 est installé et alimenté**.

Valeurs terrain (réservations DHCP) :

| Shelly | IP | Rôle |
|--------|-----|------|
| SHELLY-1-24V | 192.168.1.83 | Alimentation module cimier (`power_switch`) |
| SHELLY-UNI+  | 192.168.1.84 | Lecture microswitches HAUT/BAS (`switch_reader`) |
| SHELLY-1-MOT | 192.168.1.85 | Marche/arrêt moteur (`motor_shelly.host_motor`) |
| SHELLY-1-UPDN| 192.168.1.86 | Sens UP/DN via DPDT (`motor_shelly.host_dir`) |

---

## ⚠️ Avant de commencer 

Avant la Phase A :
1. **Le matériel cimier V3 est-il en place sur site ?** (les 4 Shelly ci-dessus + le
   contrôleur d'impulsions branché au DM556T). Oui / Non / Partiel.
2. Les **4 IP Shelly** sont-elles bien celles du tableau ? (corrige si DHCP a changé)

---

## PHASE 0 — État des lieux (à recoller tel quel)

```bash
cd ~/DriftApp
echo "--- version courante ---"; grep '^version' pyproject.toml
echo "--- branche + propreté ---"; git status -sb | head -20
echo "--- services ---"; sudo systemctl is-active ems22d motor_service cimier_service driftapp_web
echo "--- unit cimier présente ? ---"; systemctl list-unit-files | grep cimier_service || echo "PAS de cimier_service"
```

**Attendu / à renvoyer :** la version affichée, l'état git (propre ou fichiers modifiés
listés), les 4 `active`/`inactive`, et si `cimier_service` existe.

> 🛑 **STOP** Selon la version et l'état git, 
> variantes de Phase A suivre (la MAJ OTA a un déblocage one-shot connu si le
> Pi n'a jamais reçu la 6.6.2).

---

## PHASE A — Mise à jour logicielle vers 6.7.0 (sans risque, cimier OFF)

**A1. Sauvegarde de la config actuelle** (indispensable — réutilisée en Phase B) :
```bash
cd ~/DriftApp
cp data/config.json ~/config_AVANT_6.7.0_$(date +%F).json
echo "Backup OK :"; ls -la ~/config_AVANT_6.7.0_*.json
```
**Attendu :** le fichier backup listé.

**A2. Récupération du code 6.7.0.** Deux voies — *JP confirme laquelle après la Phase 0* :

- **Voie 1 (recommandée si l'OTA marche)** : bouton **« Mettre à jour »** dans
  l'interface web. Il gère le diff de `config.json` et demande quoi garder.
  → suivre l'assistant, **garder le local** pour site/moteur/encodeur.

- **Voie 2 (manuelle, si l'OTA refuse / Pi pas encore en 6.6.2)** :
```bash
cd ~/DriftApp
git checkout -- scripts/update_driftapp.sh   # déblocage one-shot OTA (bug 6.6.2)
git fetch origin
git stash push -m "config-terrain-avant-6.7.0"   # écarte les modifs locales le temps du pull
git pull --ff-only origin main
uv sync --frozen
```
**Attendu :** `Updating … 6.7.0`, `uv sync` sans erreur. Si `git pull` refuse encore
(« local changes »), **s'arrêter et m'envoyer le message**.

**A3. Vérifier la version + redémarrer les services :**
```bash
grep '^version' pyproject.toml          # doit afficher 6.7.0
sudo systemctl restart ems22d motor_service driftapp_web
sudo systemctl is-active ems22d motor_service driftapp_web
```
**Attendu :** `version = "6.7.0"`, trois `active`.

**A4. Vérifier que le cœur fonctionne toujours** (cimier encore OFF, rien ne doit
changer côté coupole) :
```bash
cat /dev/shm/motor_status.json | python3 -m json.tool | head -15
curl -s http://localhost:8000/api/health/ | head
```
**Attendu :** `motor_status.json` frais (status `idle`/tracking), health `healthy`.
Dans le navigateur, le pied de page doit afficher **6.7.0**.

> ✅ **Fin de Phase A.** La 6.7.0 tourne, le cimier est inactif, **rien d'autre n'a
> changé**. Une **session d'astrophoto normale** est possible sans risque. Renvoie-moi
> A3+A4. Les Phases B/C se font quand le matériel V3 est prêt.

---

## PHASE B — Activation du cimier V3 (seulement si le matériel Shelly est installé)

**B1. Vérifier d'abord que les 4 Shelly répondent** (avant de toucher la config) :
```bash
for ip in 83 84 85 86; do echo -n "192.168.1.$ip : "; curl -s -m 3 http://192.168.1.$ip/status >/dev/null && echo OK || echo INJOIGNABLE; done
echo "--- Uni+ entrées brutes ---"
curl -s http://192.168.1.84/rpc/Input.GetStatus?id=1   # HAUT
curl -s http://192.168.1.84/rpc/Input.GetStatus?id=0   # BAS
```
**Attendu :** les 4 `OK`, et l'Uni+ renvoie du JSON `{"id":…, "state":true/false}`.
Un `INJOIGNABLE` → **stop**, régler le réseau/Shelly avant d'aller plus loin.

**B2. Éditer la section `cimier` de `data/config.json`** :
```bash
nano data/config.json
```
Remplacer **uniquement** le bloc `"cimier": { … }` par celui-ci (laisser intactes les
sections `site`, `moteur`, `encodeur`, `motor_driver`) :
```json
  "cimier": {
    "enabled": true,
    "cycle_timeout_s": 90.0,
    "post_off_quiet_s": 10.0,
    "shelly_settle_s": 2.0,
    "verbose_logging": true,
    "switch_reader": {
      "type": "shelly_uni",
      "host": "192.168.1.84",
      "api": "rpc",
      "open_input_id": 1,
      "closed_input_id": 0,
      "invert": true,
      "timeout_s": 3.0
    },
    "power_switch": { "type": "shelly_gen1", "host": "192.168.1.83", "switch_id": 0 },
    "weather_provider": { "type": "noop" },
    "automation": { "mode": "manual" },
    "motor_shelly": {
      "host_motor": "192.168.1.85",
      "host_dir": "192.168.1.86",
      "relay_motor": 0,
      "relay_dir": 0,
      "open_dir_state": true,
      "motor_on_relay_state": true,
      "api": "legacy",
      "timer_safety_sec": 90.0
    }
  }
```
> ⚠️ Note : `automation.mode = "manual"` et `verbose_logging = true` **exprès pour la
> validation** — pas d'ouverture/fermeture automatique tant que les conventions ne sont
> pas validées, et logs détaillés. On repassera en `full` après (étape C5).

**B3. Vérifier que le JSON est valide AVANT de redémarrer** (une virgule en trop casse
tout) :
```bash
python3 -m json.tool data/config.json >/dev/null && echo "JSON OK" || echo "JSON CASSE — ne pas redemarrer"
```
**Attendu :** `JSON OK`. Si `CASSE` → rouvrir `nano`, corriger (ou restaurer le backup
A1 et recommencer).

**B4. Redémarrer le cimier et vérifier qu'il démarre proprement :**
```bash
sudo systemctl restart cimier_service
sudo systemctl is-active cimier_service
sudo journalctl -u cimier_service -n 20 --no-pager
cat /dev/shm/cimier_status.json | python3 -m json.tool
```
**Attendu :** `active`, une ligne `cimier_event=started switch_reader=192.168.1.84 …`,
et `cimier_status.json` présent avec un `state` non nul. Pas de `Traceback`.

> 🛑 **STOP — renvoie-moi B1, B4** 
> On ne passe à la Phase C qu'une fois le service
> `active` et joignable.

---

## PHASE C — Validation au banc des 3 conventions (⚠️ le cimier bouge)

> **Sécurité** : pendant cette phase le mécanisme peut bouger. Garder le **bouton STOP**
> (UI ou coupure 24V) à portée. À faire de jour, à vue du cimier.

**C1. Convention des butées (`switch_reader.invert`) — SANS moteur.**
Actionner **à la main** le microswitch **HAUT**, le maintenir, et lire :
```bash
curl -s http://192.168.1.84/rpc/Input.GetStatus?id=1; echo
cat /dev/shm/cimier_status.json | python3 -m json.tool | grep -E "open_switch|closed_switch"
```
Puis relâcher, et faire pareil avec le microswitch **BAS** (`id=0`, regarder
`closed_switch`).
**Attendu (convention V3) :** appui sur **HAUT** → `open_switch` passe à **true** ;
sur **BAS** → `closed_switch` à **true**.
- ✅ Si ça correspond → `invert` est bon.
- ❌ Si c'est inversé → repasser `"invert": false` (B2), `json.tool` +
  `restart cimier_service`, refaire C1.

**C2. Convention du sens (`open_dir_state`).** Lancer une **OUVERTURE** depuis le
dashboard (« Ouvrir cimier »), prêt à STOPPER.
**Attendu :** le cimier part **dans le sens de l'ouverture**.
- ❌ S'il part en **fermeture** → STOP, inverser `"open_dir_state": false` (B2),
  `restart`, refaire C2.

**C3. Convention marche/arrêt moteur (`motor_on_relay_state`).** Pendant C2, observer :
**Attendu :** le moteur **tourne pendant le cycle** puis **s'arrête** à la butée (ou au
STOP).
- ❌ Si le moteur **ne tourne pas** alors que le relais MOT est activé, ou **tourne en
  continu** → inverser `"motor_on_relay_state": false` (B2), `restart`, refaire.

**C4. Cycle complet supervisé.** Une fois C1–C3 OK : lancer une **ouverture** puis une
**fermeture** complètes, à vue.
```bash
sudo journalctl -u cimier_service -f
```
**Attendu :** dans les logs, la séquence
`power_on → set_direction → motor_on → switch_transition (open_switch true) → motor_off → power_off`,
et idem en fermeture (`closed_switch true`). Pas de `both_switches`, pas de `timeout`.

> 🛑 **STOP — renvoie-moi C1 à C4** (retours `cimier_status.json` + observation
> physique) pour confirmation des conventions finales.

**C5. Bascule en automatique (après validation).** Quand tout est validé, repasser
`automation.mode` en `"full"` (et éventuellement `verbose_logging` en `false`) dans
`data/config.json`, `json.tool` + `restart cimier_service`.

---

## En cas de pépin
- `cimier_service` redémarre en boucle / `Traceback` → recoller
  `journalctl -u cimier_service -n 40`.
- Un Shelly injoignable en cours de cycle → log `set_direction_failed` /
  `precheck_unreachable` (rappel : Shelly Gen 1 capricieux en WiFi déjà vus le
  30-31/05 — hard reset / réappairage si besoin).
- Tout doute → STOP, couper le **24V (.83)**, recoller les logs.

---

*Protocole généré le 2026-06-10 pour la v6.7.0 (commit `e1e7edf`). Les voies A2
(OTA vs manuel) seront tranchées après le retour de la Phase 0 (version réelle du Pi +
état du matériel V3).*
