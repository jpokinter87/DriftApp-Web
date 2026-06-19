# Chantier A — Noyau de résilience de `config.json`

**Date** : 2026-06-19
**Statut** : design validé, prêt pour plan d'implémentation
**Périmètre** : backend / infra. La page Configuration UI (chantier B) fera l'objet
d'un cycle brainstorming → spec → plan séparé, **posé sur ce noyau**.

---

## 1. Problème

`data/config.json` est **tracké par git**. C'est la vulnérabilité de fond :

- Tout `git pull` manuel (qui contourne l'UI OTA) réécrit le fichier tracké →
  les réglages terrain (IP Shelly, conventions cimier validées 17-18/06) sont perdus
  et remplacés par le gabarit vide du dépôt. C'est exactement l'incident vécu par
  Serge le 19/06 (le diff-UI de choix n'était pas encore actif sur sa version, il a
  fait un `git pull` qui a écrasé sa config).
- Le gabarit vide est **du JSON parfaitement valide** : un simple test d'intégrité
  syntaxique ne détecte rien.
- L'édition manuelle de `config.json` en SSH est périlleuse pour l'opérateur
  (corruption fréquente).

Tout l'édifice OTA actuel (`config_diff.py`, danse `stash`/`checkout`/`.user_backup`/
`.upstream` dans `update_driftapp.sh`, diff-UI « choisir local/upstream ») n'est qu'un
pansement autour du fait que le fichier est tracké, et il ne se déclenche **que** via
le bouton « Mettre à jour ».

## 2. Principe directeur retenu

`config.json` devient la **source de vérité des VALEURS**, sacrée. Tant que la
*structure* du JSON ne change pas (aucune clé ajoutée/retirée), on n'y touche
**jamais**. Quand la structure évolue (nouvelle version), on migre la structure en
**préservant toutes les valeurs existantes** ; seules les nouvelles clés prennent leur
valeur par défaut.

**Option 1 verrouillée (valeurs strictement sacrées)** : un changement de *défaut* sur
une clé déjà présente n'est **jamais** propagé automatiquement, même si c'est un
correctif (ex. `motor_on_relay_state` true→false en 6.8.0). Un tel correctif passe par
le changelog / une action manuelle. La logique de merge ne s'occupe **que** de
l'ajout/suppression de clés.

## 3. Architecture des fichiers

```
data/
├── config.template.json   ← TRACKÉ. Squelette + défauts (l'actuel config.json :
│                             hosts "noop"/vides, template repo). Évolue avec les versions.
├── config.json            ← .gitignore. Valeurs terrain. git n'y touche JAMAIS.
└── .config.lastgood.json  ← .gitignore. Copie cachée du dernier config.json parsable.
                              Filet anti-corruption.
```

**Migration git (one-shot, un commit)** :
- `git rm --cached data/config.json` (dé-tracke, **garde le fichier sur le disque**).
- Créer `data/config.template.json` = copie du contenu repo actuel de `config.json`.
- Ajouter au `.gitignore` : `data/config.json`, `data/.config.lastgood.json`,
  `data/config.json.tmp` (et tout `*.tmp` de la zone config).

**Sur le Pi de Serge (one-shot documenté)** : après le pull de la migration,
`config.json` reste intact sur le disque (le dé-tracking préserve le working tree),
ses valeurs survivent. Cas particulier « config.json a des modifs locales non
commitées » : étape de déploiement documentée = `cp data/config.json
data/config.json.bak` → pull → vérifier que le boot reprend le fichier tel quel. Le
filet `lastgood` se constitue dès le premier boot réussi.

## 4. Module `core/config/config_resilience.py`

Fonction publique :

```python
def ensure_config_ready(
    config_path: Path,
    template_path: Path,
    backup_path: Path,
) -> ConfigReport:
    ...
```

Appelée **une fois au démarrage de chaque process** : `services/motor_service.py`
`main()`, `services/cimier_service.py` `main()`, et au démarrage Django
(`AppConfig.ready()`). Idempotente : un second appel sans changement structurel est un
no-op (aucune écriture).

### Algorithme

```
1. config.json absent ?
   ├─ backup lastgood existe → restaurer (atomique).   → restored_from_backup
   └─ sinon → générer depuis config.template.json.       → bootstrapped_from_template
2. parser config.json
   ├─ échec (JSON invalide) :
   │    ├─ lastgood existe → restaurer.                  → recovered_corruption
   │    └─ sinon → regénérer depuis template.            → corruption_no_backup (alerte forte)
   └─ ok → continuer
3. MERGE STRUCTUREL vs template (compare les CHEMINS de clés, pas les valeurs) :
   ├─ structure identique → NE RIEN FAIRE (fichier intact au bit près). → unchanged
   └─ structure différente → deep-merge :
        • repartir du squelette template
        • clé présente des DEUX côtés → garder la VALEUR utilisateur (Option 1)
        • clé nouvelle (template seul) → défaut du template
        • clé obsolète (config seul) → retirée
        • écriture atomique (tmp + os.replace)            → migrated {added:[...], removed:[...]}
4. config.json valide en fin de routine → lastgood = config.json courant.
```

### Détails

- **Écriture atomique** : helper privé `_atomic_write_json(path, data)` = écrire dans
  `path.with_suffix(".tmp")` puis `os.replace()`. Jamais de fichier à moitié écrit.
- **lastgood** : mis à jour **uniquement** quand `config.json` parse. On n'écrase
  jamais le filet avec du garbage.
- **Comparaison structurelle** : sur l'ensemble des **chemins de clés** (récursif,
  ex. `cimier.motor_shelly.host_dir`), indépendamment des valeurs. Le merge est un
  deep-merge récursif qui suit le squelette du template.

### Frontière assumée (cohérente Option 1)

Le filet `lastgood` rattrape la **corruption** (illisible) et l'**absence**, **pas**
une valeur « valide mais erronée » saisie à la main. On ne juge jamais une valeur
valide — c'est le domaine de l'utilisateur.

### `ConfigReport`

Dataclass : `status` (enum parmi les valeurs ci-dessus) + `added: list[str]` +
`removed: list[str]` + `backup_timestamp: str | None` + `message: str`.

### Intégration / chokepoints

- Appel principal : au `main()` de chaque service + Django `ready()` (avant toute vue).
  Comme `ready()`/`main()` tournent avant la boucle/les vues, le fichier est valide
  pour tous les chargements suivants du process.
- Filet pour les chemins de chargement hors entrypoint (scripts ad-hoc `main.py`,
  `calibration_moteur.py`, tests) : le loader (`ConfigLoader.load()` / `core/config/
  config.py`) effectue un **bootstrap minimal** « si absent → copier le template »
  (cheap), mais **pas** le merge complet (qui reste réservé aux entrypoints).

## 5. Surfaçage UI (minimal pour A)

Les process sérialisent le `ConfigReport` dans `/dev/shm/config_status.json` (même
pattern IPC que `motor_status.json` / `cimier_status.json`). Réutilisation du pattern
**bannière de calibration** existant.

| `status` | UI |
|---|---|
| `unchanged` | rien (silencieux) |
| `migrated` | bannière info ambre : « Configuration migrée : N paramètres ajoutés (`liste`) à leur valeur par défaut. Tes réglages ont été conservés. » |
| `restored_from_backup` / `recovered_corruption` | bannière orange : « config.json était illisible — restauré depuis la sauvegarde du `<date>`. » |
| `bootstrapped_from_template` | bannière : « Première config générée depuis le gabarit — à renseigner. » |
| `corruption_no_backup` | bannière **rouge** : « config.json corrompu et aucune sauvegarde — valeurs par défaut chargées, reconfiguration requise. » |

Exposé via `/api/health/` (endpoint d'état existant) + une ligne sur la page Système.
L'édition détaillée des clés est hors périmètre (chantier B).

## 6. Impact OTA — nettoyage assumé

Une fois `config.json` dé-tracké, **`git pull` ne le touche plus jamais** → la logique
de conflit devient morte.

- **`scripts/update_driftapp.sh`** : retirer la danse `stash` / `checkout origin/main`
  de `config.json` / `.user_backup.<ts>` / `.upstream`. Le script garde : pull du code
  + `uv sync --frozen` + restart des services. Simplification nette.
- **`config_diff.py` + diff-UI « choisir local/upstream »** (la capture du 19/06) :
  **retirés**. Sous l'Option 1 on ne demande plus de choisir entre valeur locale et
  upstream (valeurs sacrées, structure auto-migrée). Le flux interactif est **remplacé**
  par le rapport de migration automatique (§5). Les *value-diffs* (« `8 → 7` »)
  disparaissent de l'UI (non actionnables).
- Décision validée : **on ne garde pas** de variante informative du diff-UI — un seul
  mécanisme (le rapport auto), pas deux chemins contradictoires.

⚠️ Touche du code testé (`tests/test_ota_uvlock.py`, module `config_diff`, vues
`web/health`). Le plan listera précisément retrait vs adaptation ; les tests sont
**mis à jour**, pas supprimés à l'aveugle (changements chirurgicaux).

## 7. Tests (TDD)

Code pur, testable sans matériel :

- **Merge** : structure identique → sortie identique **et fichier non réécrit** ;
  template +1 clé → défaut injecté + valeurs préservées ; template −1 clé → clé
  obsolète retirée ; clés imbriquées (`cimier.motor_shelly.host_dir`) ; **défaut changé
  sur clé commune → valeur utilisateur conservée** (verrou Option 1).
- **Bootstrap** : `config.json` absent + pas de backup → généré depuis template.
- **Récupération corruption** : JSON illisible + backup présent → restauré ; sans
  backup → regénéré depuis template + statut `corruption_no_backup`.
- **lastgood** : mis à jour seulement sur parse réussi ; jamais écrasé par du garbage.
- **Écriture atomique** : passe par un `.tmp` + `os.replace` ; `config.json` jamais
  laissé à moitié écrit sur échec en cours d'écriture.
- **OTA** : tests adaptés pour refléter le retrait de la danse `config.json`.

## 8. Critères de succès

1. Un `git pull` manuel sur le Pi ne peut plus écraser les valeurs de `config.json`.
2. Une MAJ qui ajoute des clés migre la structure en préservant 100 % des valeurs
   terrain ; les nouvelles clés sont à leur défaut ; rapport affiché.
3. Une MAJ sans changement structurel ne réécrit pas `config.json` (intact au bit près).
4. Un `config.json` corrompu (illisible) au boot est restauré depuis `lastgood` sans
   intervention, avec alerte UI.
5. Suite de tests verte (nouveaux tests merge/résilience + tests OTA adaptés).

## 9. Hors périmètre (chantier B, cycle ultérieur)

- Page Configuration UI : formulaire par clé, bulles d'info, garde-fous, génération du
  JSON valide au clic « Sauvegarder ». **Écrira à travers** `ensure_config_ready` /
  `_atomic_write_json` (pas de second chemin d'écriture).
- Verrouillage des droits du fichier : volontairement écarté (illusoire quand Django et
  l'opérateur SSH partagent le même compte UNIX `slenk`). Objectif atteint autrement :
  rendre l'édition manuelle **inutile** (UI = chemin pavé) + résilience qui **rattrape**
  une édition ratée.
