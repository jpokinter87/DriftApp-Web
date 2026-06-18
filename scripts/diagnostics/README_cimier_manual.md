# `cimier_manual.py` — pilotage manuel du cimier V3

Petit script **autonome** pour piloter le cimier à la main, commande par commande, en
séquençant directement les requêtes HTTP des 4 Shelly. Il encode **la vérité du synoptique**
(`docs/synoptique electronique cimier V3.pdf`), sans aucune couche du code applicatif (pas de
cooldown, pas d'IPC, pas de config). C'est l'outil de validation au banc avant de reporter la
séquence dans le code.

## Lancer le script

Aucune dépendance à installer (Python standard uniquement) :

```bash
cd ~/DriftApp
python3 scripts/diagnostics/cimier_manual.py <commande> [argument] [options]
```

Chaque appel **affiche l'URL exactement envoyée** puis la réponse du Shelly — exactement comme
si on tapait le `curl` à la main.

## Le matériel piloté

| Shelly | IP | Rôle |
|--------|-----|------|
| SHELLY-1-24V | 192.168.1.83 | Alimentation du module cimier |
| SHELLY Uni+ | 192.168.1.84 | Lecture des deux butées (HAUT / BAS) |
| SHELLY-1-MOT | 192.168.1.85 | Marche/arrêt moteur |
| SHELLY-1-UPDN | 192.168.1.86 | Sens (montée / descente) via relais DPDT |

## Les commandes

### Primitives (une commande = un ordre, comme à la main)

```bash
python3 scripts/diagnostics/cimier_manual.py read        # état des deux butées (HAUT et BAS)
python3 scripts/diagnostics/cimier_manual.py power on     # alimente le module
python3 scripts/diagnostics/cimier_manual.py power off    # coupe l'alimentation
python3 scripts/diagnostics/cimier_manual.py dir up       # sens montée
python3 scripts/diagnostics/cimier_manual.py dir down     # sens descente
python3 scripts/diagnostics/cimier_manual.py motor run    # démarre le moteur
python3 scripts/diagnostics/cimier_manual.py motor stop   # arrête le moteur
```

### Composites (la séquence complète, une fois les primitives validées)

```bash
python3 scripts/diagnostics/cimier_manual.py open    # cycle d'ouverture complet
python3 scripts/diagnostics/cimier_manual.py close   # cycle de fermeture complet
python3 scripts/diagnostics/cimier_manual.py stop    # arrêt immédiat du moteur
```

`open` / `close` déroulent la cinématique du synoptique :

1. Alimente le module (24V ON)
2. Attend que les Shelly s'appairent au Wifi (2 s, réglable)
3. Met le moteur au repos puis sélectionne le sens
4. Vérifie la butée visée : si déjà atteinte → ne fait rien, coupe l'alim
5. Démarre le moteur
6. Surveille la butée toutes les 100 ms
7. Arrête le moteur dès que la butée est atteinte
8. Coupe l'alimentation (24V OFF)

## Conventions et options (validation au banc)

Le script part des conventions du synoptique. Si le hardware se comporte autrement, on bascule
une convention **sans éditer le fichier**, via une option :

| Option | Défaut | Signification |
|--------|--------|---------------|
| `--mot-run off\|on` | `off` | Valeur `turn=` qui **fait tourner** le moteur (logique inversée : `off`) |
| `--dir-up on\|off` | `on` | Valeur `turn=` du sens **montée** |
| `--switch-closed false\|true` | `false` | Valeur `state=` d'une butée **atteinte** |
| `--settle <s>` | `2.0` | Attente d'appairage Wifi des Shelly |
| `--poll <s>` | `0.1` | Intervalle de lecture de la butée pendant le mouvement |
| `--timeout <s>` | `3.0` | Délai max d'une requête HTTP |

Exemples :

```bash
# Le moteur tourne dans le mauvais sens ? inverser le sens montée :
python3 scripts/diagnostics/cimier_manual.py open --dir-up off

# Appairage Wifi plus lent : allonger l'attente :
python3 scripts/diagnostics/cimier_manual.py open --settle 3
```

L'aide complète : `python3 scripts/diagnostics/cimier_manual.py --help`.

## Points importants (pièges du synoptique encodés dans le script)

- **Moteur en logique inversée** : le moteur **tourne** quand le relais MOT est sur `turn=off`,
  et **s'arrête** sur `turn=on`. C'est pour ça que `motor run` envoie `turn=off`.
- **Butées** : sur le Shelly Uni+, `id=1` = HAUT, `id=0` = BAS. Une butée renvoie
  `state=true` quand elle est **ouverte** (non atteinte) et `state=false` quand elle est
  **fermée** (butée **atteinte**).

## Protocole de test conseillé

```bash
cd ~/DriftApp
python3 scripts/diagnostics/cimier_manual.py read        # 1) lire l'état réel des butées
python3 scripts/diagnostics/cimier_manual.py power on     # 2)
python3 scripts/diagnostics/cimier_manual.py dir up       # 3)
python3 scripts/diagnostics/cimier_manual.py motor run    # 4) le moteur doit TOURNER, bon sens
python3 scripts/diagnostics/cimier_manual.py motor stop   # 5)
python3 scripts/diagnostics/cimier_manual.py power off
python3 scripts/diagnostics/cimier_manual.py open         # 6) cycle complet une fois (4)+(5) OK
```

Noter les valeurs d'options qui fonctionnent : elles seront reportées dans la configuration du
code applicatif (`data/config.json`).
