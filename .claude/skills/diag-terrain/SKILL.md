---
name: diag-terrain
description: >-
  Génère un protocole de diagnostic prêt à transmettre à Serge (l'opérateur sur
  site) pour un incident terrain du système DriftApp Web (coupole astronomique
  Observatoire Ubik), puis interprète ses retours. La machine de dev est à 800 km
  du Raspberry Pi : ce skill NE lance jamais les commandes lui-même, il produit des
  étapes copier-coller (SSH/systemd/IPC côté Pi + protocoles multimètre/continuité/
  pinout côté hardware) avec un « résultat attendu » par étape, puis diagnostique à
  partir de ce que Serge recolle. À utiliser quand un incident terrain est rapporté :
  « Serge a un souci avec le Pico / Shelly / moteur », « la coupole ne répond plus
  sur site », « le cimier ne s'ouvre pas », « l'encodeur est figé en prod »,
  « le moteur frémit mais ne tourne pas ».
---

# diag-terrain — diagnostic par procuration (site distant)

## Contrainte structurante (ne jamais l'oublier)

La machine de dev est à **800 km du Pi de production**. Aucun accès au runtime du Pi
(`/dev/shm`, `systemctl`, `journalctl`, processus), ni au matériel. **Ce skill ne lance
aucune commande Pi/hardware en local.** Il :

1. **génère** un protocole copier-coller pour Serge (en français, prêt pour WhatsApp/SMS) ;
2. **interprète** ce que Serge recolle, et propose **une** prochaine étape.

Les seules choses lisibles ici : le code du dépôt, les logs déjà copiés dans `logs/`,
les sessions dans `data/sessions/`, et `data/config.json`.

## Étape préalable — valeurs terrain (script)

Ne jamais coder en dur les IPs/ports/GPIO dans le protocole. Les lire à l'exécution :

```bash
python3 .claude/skills/diag-terrain/scripts/read_terrain_values.py
```

Injecter ces valeurs (Pico W host, Shelly host, ports, GPIO, type de driver…) dans le
protocole. Toute valeur « non configuré » → faire **demander la valeur à Serge** dans
le protocole plutôt que d'inventer.

⚠️ Le script lit le `data/config.json` **du dépôt**, qui sur la machine de dev est le
**template** : les *hosts/ports* sont les réservations DHCP terrain (fiables), mais des
champs divergent dev↔prod (`cimier.enabled=false`, `power_switch.type=noop` côté template).
Ne jamais en déduire un diagnostic ; inclure dans le protocole une étape qui fait
**confirmer la valeur sur le Pi** (ex. `grep -A3 '"cimier"' data/config.json` en SSH).

## Mode A — Générer un protocole (entrée = symptôme)

1. Lancer le script de valeurs terrain ci-dessus.
2. Identifier la **couche** concernée par le symptôme (souvent les deux) :
   - **Logiciel Pi** (service mort, IPC figé, suivi qui ne démarre pas, Django KO,
     cimier silencieux) → lire `references/pi_software.md`.
   - **Hardware** (Pico W injoignable, court-circuit/surcourant, moteur muet ou qui
     frémit, Shelly, câblage) → lire `references/hardware.md`.
3. Assembler un protocole **numéroté et séquentiel**. Chaque étape comporte :
   - la **commande exacte** (SSH) ou le **point de mesure** (multimètre), avec les
     valeurs terrain réelles injectées ;
   - le **résultat attendu** (« doit afficher `active (running)` », « continuité OUVERTE »,
     « ≈ 3,3 V ») pour que Serge sache quoi rapporter.
4. Rappeler les **règles d'or** pertinentes (cf. `references/hardware.md`, ex. jamais
   QC 3.0 + USB Pi simultanés).
5. Sortie en **français**, condensée, copier-collable telle quelle.

## Mode B — Interpréter (entrée = retour de Serge)

1. Parser les sorties/mesures recollées.
2. Croiser avec le symptôme initial et les références.
3. Produire : **diagnostic** (ce qui est confirmé / écarté) + **hypothèses restantes
   classées par probabilité** + **une seule prochaine étape** à faire exécuter (éviter
   de noyer Serge sous dix manips à la fois).
4. Si le diagnostic est tranché (ex. composant HS), le dire clairement et proposer
   l'action (remplacement, reconfiguration `data/config.json`, redéploiement).

## Références

- `references/pi_software.md` — banque de commandes SSH/systemd/IPC/journalctl par
  symptôme logiciel.
- `references/hardware.md` — protocoles multimètre/continuité/pinout (Pico W, Shelly,
  DM556T, ULN2803A) + règles d'or. Faits hardware durables uniquement ; les IPs/ports
  viennent toujours du script de valeurs terrain.
