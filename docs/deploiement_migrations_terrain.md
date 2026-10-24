# Migrations terrain ponctuelles (historique)

Procédures one-shot déplacées depuis `CLAUDE.md` le 24/10/2026. Utiles seulement pour remonter un Pi resté sur une ancienne version.

## Déploiement v6.4 sur le Pi terrain (Calibration robuste)

**Contexte** : la prod tourne sur **5.10.0** (déployé 2026-04-24). Le saut vers **6.4.0** traverse 8 milestones intermédiaires (v5.11 → v5.12 → v6.0 → v6.1 → v6.2 → v6.3 → v6.3.x → v6.4). **Une simple MAJ via le bouton « Mettre à jour » de l'UI ne suffit pas** — interventions admin SSH requises selon les milestones franchis.

### Script automatisé : `scripts/migrate_to_v6.4.sh`

Le script `scripts/migrate_to_v6.4.sh` automatise les étapes 1 à 7 ci-dessous (idempotent, peut être relancé sans dommage). Usage :

```bash
ssh slenk@<pi-host>
cd ~/DriftApp
git fetch origin
git checkout origin/main
./scripts/migrate_to_v6.4.sh
# Modes optionnels :
#   DRY_RUN=1 ./scripts/migrate_to_v6.4.sh        # simule sans modifier
#   SKIP_HARDWARE=1 ./scripts/migrate_to_v6.4.sh  # ignore checks Pico W/Shelly
#   TARGET_REF=v6.4.0 ./scripts/migrate_to_v6.4.sh  # pin sur un tag/commit
```

Le script demande sudo une seule fois (1ère MAJ), puis les MAJ suivantes passent par OTA UI (sudoers v5.12 déployé). Backup automatique de `data/config.json` + sessions dans `data/backups/pre_v6.4_<timestamp>/`. Logs détaillés dans `logs/migrate_to_v6.4_<timestamp>.log`.

**Limites du script** :
- NON TESTÉ par CI (machine dev à 800 km du Pi). À valider terrain par Serge sur une session test avant utilisation pour une vraie MAJ.
- NE CONFIGURE PAS les 4 Shellys V3 (manuel — cf. section « Architecture cimier V3 » et synoptique `docs/synoptique electronique cimier V3.pdf`).
- En V3 il n'y a plus de firmware Pico W à flasher (`firmware/cimier/` supprimé).

### Détail des 7 étapes (manuelles si on choisit de ne pas utiliser le script)

### Étape 1 — Pré-requis sudoers (pour OTA fonctionnel ≥ v5.12)

Sans ce déploiement, `update_driftapp.sh` ne peut pas `systemctl restart` sans password → MAJ via UI échouera.

```bash
# Sur le Pi, en SSH :
ssh slenk@<pi-host>
cd ~/DriftApp
git fetch origin
git checkout <hash-v5.12>     # ou directement HEAD si on veut tout

sudo cp setup/driftapp-updater.sudoers /etc/sudoers.d/driftapp-updater
sudo chmod 0440 /etc/sudoers.d/driftapp-updater
sudo visudo -cf /etc/sudoers.d/driftapp-updater   # vérifie syntaxe
```

Une fois fait, les MAJ ultérieures via UI auto-redéploieront ce fichier (pattern v5.12).

### Étape 2 — Installation `cimier_service` (nouveau v6.0)

Le service systemd n'existe pas en 5.10. À installer **une seule fois** :

```bash
sudo cp cimier_service.service /etc/systemd/system/
sudo systemctl daemon-reload
sudo systemctl enable cimier_service
# Ne PAS encore start — il faut d'abord configurer data/config.json (étape 3 ci-dessous)
```

### Étape 3 — Hardware cimier V3 tout-Shelly (v6.7)

Le Pico W est supprimé. Le cimier est piloté par 4 Shellys Gen 1 (voir section « Architecture cimier V3 »). Vérifier :
1. Shelly 24V (.83), Uni+ (.84), MOT (.85), UPDN (.86) accessibles sur le réseau local.
2. IPs DHCP statiques configurées dans l'interface web Shelly de chaque appareil.
3. Mettre `cimier.enabled=true` + renseigner `switch_reader.host`, `motor_shelly.host_motor`, `motor_shelly.host_dir` dans `data/config.json` terrain (laisser `"noop"` dans le template repo).
4. Conventions validées terrain (17-18/06), figées dans `data/config.json` : `motor_on_relay_state=false`, `open_dir_state=true`, `switch_reader.invert=true` (cf. `docs/synoptique electronique cimier V3.pdf`). Vérifier qu'elles se comportent comme attendu lors du 1er cycle supervisé.

### Étape 4 — Configuration `data/config.json` (rétro-compat partielle)

Sections à ajouter ou compléter (les sections `calibration` et `boot_calibration` ont des defaults rétro-compatibles, les autres sont **requises** pour activer leurs fonctionnalités) :

```json
{
  "cimier": {
    "enabled": true,
    "switch_reader": { "type": "shelly_uni", "host": "192.168.1.84" },
    "power_switch": { "type": "shelly_gen1", "host": "192.168.1.83" },
    "motor_shelly": {
      "host_motor": "192.168.1.85",
      "host_dir": "192.168.1.86",
      "api": "legacy"
    },
    "automation": { "mode": "manual" }
  },
  "boot_calibration": {
    "fallback_sweep_deg": 7.0,
    "timeout_sec": 180.0,
    "poll_interval_sec": 0.1
  }
}
```

**Permissions** : s'assurer que `data/` est writable par slenk :

```bash
sudo chown -R slenk:slenk /home/slenk/DriftApp/data
sudo chmod -R u+rw /home/slenk/DriftApp/data
```

### Étape 5 — Pull + restart cascade

Une fois étapes 1–4 faites, la MAJ peut s'enclencher via l'UI **OU** manuellement :

```bash
ssh slenk@<pi-host>
cd ~/DriftApp
git pull origin main
uv sync                                # met à jour dépendances Python

sudo systemctl restart ems22d.service          # encoder daemon (Phase 1)
sudo systemctl restart motor_service.service   # routine boot + dispatch calibrate (Phase 2+3)
sudo systemctl restart cimier_service.service  # cimier autonome (v6.0+)
sudo systemctl restart driftapp_web.service    # Django (Phase 3 frontend)
```

Vérification post-restart :

```bash
sudo systemctl status ems22d motor_service cimier_service driftapp_web
cat /dev/shm/motor_status.json | python3 -m json.tool | head -30
# → doit contenir 'calibration': {'status': 'ok'|'running'|'degraded'|...}
```

### Étape 6 — Comportement attendu au premier boot post-MAJ v6.4

1. `ems22d.service` démarre → publie IPC encoder + `last_calibration_at` (Phase 1).
2. `motor_service.service` démarre → watchdog thread, puis exécute `_run_boot_calibration` (Phase 2). Durée 5–180 s pendant laquelle :
   - `current_status["status"] == "calibrating"`
   - `calibration.status == "running"`
   - **Watchdog systemd 30 s NE tuera PAS le service** car le thread daemon maintient le heartbeat indépendamment (vérifié pytest, à confirmer terrain).
3. Routine cherche le microswitch 45° via sweep court (−7° puis +14°, ~30 s total à 40°/min).
4. À la fin :
   - **Cas nominal (95 %)** : `calibration.status == "ok"`, `method == "sweep"`. UI affiche badge ✓ vert, bannière masquée, boutons mouvement actifs.
   - **Cas dégradé** : `calibration.status == "degraded"` ou `"exception"`, `error_msg` renseigné. UI affiche bannière rouge, badge ✕, **7 boutons mouvement grisés** (GOTO + 4 JOG + 2 Continu), STOPs et cimier toujours actifs (sécurité). L'utilisateur clique « Calibrer maintenant » pour relancer un cycle.

### Étape 7 — Validation terrain (post-MAJ)

À observer sur une session d'astrophotographie :
- Boot motor_service : routine se termine en `ok`, durée et méthode loggés.
- Mouvement nominal : badge ✓, bannière masquée, GOTO/JOG/tracking fonctionnels.
- Test arrêt brutal (kill -9 motor_service + redémarrage) : la routine sweep court doit trouver le switch en ≤30 s (coupole toujours parquée à ~45°).
- Test dégradé simulé (coupole déplacée hors zone switch avant restart) : bannière rouge, bouton manuel fonctionnel.

### Si quelque chose tourne mal

- **`calibration.status` reste `running` >180 s** : timeout dépassé sans transition → coupole bloquée mécaniquement, ou switch HS, ou daemon ems22d ne publie pas `last_calibration_at`. Vérifier `journalctl -u motor_service -f` et `cat /dev/shm/ems22_position.json`.
- **`motor_service` redémarre en boucle** : le watchdog tue avant la fin → le thread daemon heartbeat n'est pas effectif. Augmenter temporairement `WatchdogSec` dans `motor_service.service` (à reverter ensuite).
- **Coupole ne trouve pas le switch après sweep** : zone de parking trop éloignée de 45° → augmenter `boot_calibration.fallback_sweep_deg` dans `data/config.json`. Vérifier le microswitch mécaniquement.
- **Bannière reste affichée même après calibration ok** : cache navigateur (recharger Ctrl+F5), ou `motor_status.json` non rafraîchi (vérifier polling Django).

---

### Migration config.json dé-tracké (chantier A, juin 2026)

`data/config.json` n'est plus tracké par git ; le gabarit repo vit dans
`data/config.template.json`. Au boot, `core/config/config_resilience.py`
(`ensure_config_ready`) garantit un `config.json` valide : bootstrap depuis le
template si absent, restauration depuis `data/.config.lastgood.json` si illisible,
et **merge structurel préservant les valeurs** (les nouvelles clés d'une MAJ
prennent leur défaut, les valeurs terrain existantes sont conservées — un
changement de *défaut* sur une clé existante n'est jamais propagé). Le rapport est
publié dans `/dev/shm/config_status.json` et affiché en bannière dashboard
(`/api/health/config_status/`). Le diff-UI OTA « choisir local/upstream » est
supprimé (remplacé par ce rapport automatique).

**⚠️ Déploiement one-shot sur le Pi terrain** (la version qui dé-tracke config.json) :
le commit de migration **renomme** `data/config.json` → `data/config.template.json`
(git le voit comme un `git mv`). Un simple `git pull` **supprimerait donc
`config.json` du disque**. On protège les valeurs terrain par une sauvegarde
explicite, puis on les restaure à leur emplacement runtime (désormais ignoré par git) :

    ssh slenk@<pi-host>
    cd ~/DriftApp
    cp data/config.json data/config.json.bak               # 1. SAUVEGARDE OBLIGATOIRE des valeurs terrain
    git checkout -- data/config.json 2>/dev/null || true   # 2. arbre propre (annule les modifs locales non commitées)
    git fetch origin
    git pull --ff-only origin main                         # 3. applique le rename proprement
    cp data/config.json.bak data/config.json               # 4. restaure la config terrain (le pull l'avait déplacée)
    sudo systemctl restart ems22d motor_service cimier_service driftapp_web
    cat /dev/shm/config_status.json   # attendu : "unchanged" (config.json restauré identique)
                                      # ou "migrated" si la MAJ ajoute des clés (valeurs terrain conservées)

**Si le `git pull` est refusé** (« modifications locales seraient écrasées », ou
« Pas possible d'avancer rapidement » si le Pi a des commits locaux) : **NE PAS
utiliser `git stash`** (la détection de rename y déplace par erreur les valeurs
terrain dans `config.template.json` tracké et supprime `config.json`). À la place,
après le `cp …bak` de l'étape 1 : `git checkout -- data/config.json` (annule les
modifs locales) — ou `git reset --hard origin/main` si le Pi a des commits locaux —
puis reprendre à l'étape 3.

**Ne jamais `git add` / committer `data/config.template.json` sur le Pi** : laisser
le template à sa version dépôt (sinon la prochaine MAJ diverge). Les valeurs terrain
vivent uniquement dans `data/config.json` (ignoré par git) + `data/config.json.bak`.
