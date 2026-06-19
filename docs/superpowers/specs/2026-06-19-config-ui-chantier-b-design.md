# Chantier B — Page Configuration UI

**Date** : 2026-06-19
**Statut** : design validé, prêt pour plan d'implémentation
**Périmètre** : backend (extension du noyau A) + nouvelle app Django `configuration` + frontend.
**Dépend de** : chantier A (`core/config/config_resilience.py`,
`docs/superpowers/specs/2026-06-19-config-resilience-design.md`). **Posé dessus, écrit à
travers lui.**

---

## 1. Problème / objectif

Le chantier A a rendu `config.json` résilient (dé-tracké, source de vérité sacrée des
valeurs, merge structurel, restauration anti-corruption). Mais l'édition reste manuelle
en SSH — périlleuse pour l'opérateur (corruption fréquente, c'est ce qui a motivé tout
le sujet). Le chantier B fournit le **chemin pavé** : une page web qui édite `config.json`
en sécurité, sans SSH, de sorte que l'édition manuelle devienne **inutile**.

Objectif : un formulaire web par clé, avec bulles d'aide et garde-fous, qui génère un
JSON valide au clic « Sauvegarder » — en passant **par le noyau A** (pas de second chemin
d'écriture).

## 2. Principe directeur

Le formulaire est **auto-généré depuis `config.template.json`**. Le template est l'unique
source de :
- la **structure** (sections, clés, imbrication),
- les **types** (inférés des valeurs par défaut),
- l'**aide** (les clés `_comment` voisines).

Conséquence : toute nouvelle clé introduite par une MAJ (et migrée dans `config.json` par
le merge structurel du chantier A) apparaît **automatiquement** dans l'UI, sans code à
modifier. Le template et l'UI ne peuvent pas diverger.

L'écriture passe par le **même** chemin atomique que `ensure_config_ready` : on réutilise
`_structural_merge` et `_atomic_write_json`. Pas de duplication de la logique d'écriture.

## 3. Décisions verrouillées (issues du brainstorming)

| Décision | Choix retenu |
|---|---|
| **Périmètre** | Tout éditable ; le risqué (GPIO, pas/tour, microsteps, facteurs…) replié sous un panneau « ⚠ Avancé ». |
| **Construction** | Générique, piloté par le template. `_comment` → bulles d'aide. Widgets enrichis pour les énumérations connues. |
| **Application** | **Notice seule** : la sauvegarde écrit `config.json` + affiche « redémarrage des services requis ». L'UI ne redémarre **pas** les services (zéro risque d'interrompre une session). |
| **Mise en page** | **Accordéon** : 1 section = 1 panneau pliable ; « Avancé » replié en bas ; barre « Sauvegarder » collante. |
| **Hébergement** | **App Django dédiée `configuration`** (1 domaine = 1 app), pas de greffe sur `health`. |

## 4. Architecture des composants

### 4.1 Backend — extension du noyau A (`core/config/config_resilience.py`)

Deux ajouts **purs et testables**, dans le module existant (stdlib-only préservé) :

**`write_user_config(values, config_path=…, template_path=…, backup_path=…) -> ConfigReport`**
- Entrée : `values` = dict complet édité par l'UI.
- Passe `values` par le **`_structural_merge` existant** vs template :
  - garantit la validité structurelle (clés inconnues retirées, clés manquantes
    re-injectées à leur défaut) ;
  - réinjecte les clés `_comment`/`_version`/`_date` que l'UI n'édite pas (elles sont
    dans le template, donc préservées par le merge — voir §6).
- `_atomic_write_json(config_path, merged)` puis refresh `lastgood` (= merged).
- Retourne un `ConfigReport` (réutilise la dataclass existante ; `status="saved"` +
  `added`/`removed` éventuels si l'édition a fait diverger la structure, ce qui ne
  devrait pas arriver puisque le formulaire vient du template).
- Invalide la mémoïsation `_REPORT_CACHE` pour ce `config_path` (le prochain
  `ensure_config_ready` doit voir le nouveau fichier).

**`build_config_schema(template) -> list[dict]`** (helper de présentation, pur)
- Parcourt le template ; produit une liste de **sections**, chacune avec ses **champs**.
- Pour chaque feuille non `_`-préfixée : `{path, label, type, value_default, help, advanced, enum?}`.
  - `type` ∈ {`bool`, `int`, `float`, `str`} inféré de la valeur par défaut.
  - `help` = clé `_comment` voisine (ex. `_port_comment` pour `port`, ou le `_comment`
    de section) si présente.
  - `advanced` = section ∈ `ADVANCED_SECTIONS` (voir §5).
  - `enum` = options si `path` ∈ registre des énumérations (voir §7).
- Les clés `_`-préfixées ne deviennent **jamais** des champs (mais alimentent `help`).

> Note : `build_config_schema` décrit la **structure et l'aide** ; les **valeurs
> courantes** viennent de `config.json` (lu séparément). La vue assemble les deux.

### 4.2 App Django `configuration`

Nouvelle app ajoutée à `INSTALLED_APPS`. Structure conforme aux apps existantes
(`hardware`, `health`, `cimier`…) :

```
web/configuration/
├── __init__.py
├── apps.py
├── urls.py
└── views.py
web/templates/configuration.html
web/static/js/configuration.js        (Alpine.js)
```

Routes :
- **`GET /configuration/`** → rend `configuration.html` (`active_tab='config'`).
- **`GET /api/configuration/`** → `{ "schema": build_config_schema(template),
  "values": <config.json courant> }`.
- **`POST /api/configuration/`** → corps = dict édité ; valide les types vs schéma ;
  appelle `write_user_config` ; renvoie `{report: ConfigReport, restart_required: true}`.
  Type invalide → **HTTP 400** avec le champ fautif.

La vue lit le template via les chemins du noyau A (`DEFAULT_TEMPLATE_PATH`,
`DEFAULT_CONFIG_PATH`). Pas de nouvelle constante de chemin.

### 4.3 Frontend (`configuration.html` + `configuration.js`)

- Étend `base.html`, ajoute l'onglet nav « Configuration » (bloc `nav_items`).
- Alpine.js : au chargement, `GET /api/configuration/` → construit l'accordéon.
- **Accordéon** : une section = un panneau pliable (thème ambre, cohérent dashboard).
  Sections terrain dépliées par défaut ; panneau « ⚠ Avancé » (regroupant les sections
  `advanced`) replié, avec bandeau d'avertissement.
- **Widgets** selon `type`/`enum` : interrupteur (bool), champ numérique (int/float),
  texte (str), menu déroulant (enum).
- **Bulles d'aide** : icône info par champ/section affichant le `help` (`_comment`).
- **État *dirty*** : la barre « Sauvegarder » collante s'active dès qu'un champ change ;
  avertissement avant quitter si modifs non sauvegardées.
- **Post-save** : notice « ✓ Configuration enregistrée — redémarrage des services requis
  pour appliquer » (réutilise le style bannière existant). Affiche le `ConfigReport.message`.

## 5. Classification « Avancé »

Constante explicite dans le backend (présentation) :

```python
ADVANCED_SECTIONS = {"moteur", "encodeur", "motor_driver", "boot_calibration", "thresholds"}
```

- Sections **terrain** dépliées : `site`, `cimier`, `suivi`, `logging`, `simulation`,
  `meridian_anticipation`.
- Une **nouvelle section inconnue** (future MAJ) → **visible** (non-avancé) par défaut :
  on préfère la rendre découvrable plutôt que la cacher.

`ADVANCED_SECTIONS` est une liste de présentation, indépendante de la logique d'écriture.

## 6. Préservation des métadonnées (`_comment`/`_version`/`_date`)

- L'UI **n'édite jamais** ces clés (elles ne deviennent pas des champs).
- Elles sont présentes dans `config.template.json` → le `_structural_merge` les
  réinjecte côté template dans le résultat. Donc même si l'UI envoie un dict sans elles,
  le merge les rétablit. **Aucune perte possible.**
- Cohérent avec le chantier A qui exclut déjà les clés `_`-préfixées du reporting
  (`added`/`removed`).

## 7. Énumérations connues

Petit registre `path → options` dans le backend :

| Path | Options |
|---|---|
| `cimier.automation.mode` | `manual`, `semi`, `full` |
| `logging.level` | `DEBUG`, `INFO`, `WARNING`, `ERROR` |
| `motor_driver.type` | `gpio`, `rp2040` |
| `cimier.switch_reader.type` | `shelly_uni`, `noop` |
| `cimier.power_switch.type` | `shelly_gen1`, `shelly_gen2`, `noop` |
| `cimier.weather_provider.type` | `noop` (extensible) |
| `cimier.motor_shelly.api` / `cimier.switch_reader.api` | `legacy`, `rpc` |

Un `path` absent du registre → widget standard selon le type. Registre **additif** : on
peut l'enrichir sans toucher au reste.

## 8. Validation (volontairement minimale)

Esprit Option 1 du chantier A : **le domaine appartient à l'opérateur**, on ne juge pas
une valeur valide.

- On garantit le **type** (le widget le contraint ; le POST le revérifie vs schéma) et
  la **structure** (merge final).
- **Chaînes vides autorisées** : un host Shelly vide = `Noop` intentionnel (cf. template
  `host_motor`/`host_dir` vides).
- **Pas** de bornes de plage métier (YAGNI ; le merge structurel est le filet final).
- Seul rejet possible : un type incohérent (texte dans un champ numérique) → 400.

## 9. Flux de données

```
GET /api/configuration/
  template.json → build_config_schema → schema (structure + types + aide + advanced/enum)
  config.json   → values
  → formulaire accordéon (Alpine)

édition locale (état dirty, aucune écriture)

POST /api/configuration/  { dict édité }
  → validation types vs schema (400 si incohérent)
  → write_user_config
      → _structural_merge(values, template)   (valide + réinjecte _comment)
      → _atomic_write_json(config.json)
      → refresh .config.lastgood.json
      → invalide _REPORT_CACHE
  → ConfigReport → notice « redémarrage des services requis »
```

Les services **ne sont pas** redémarrés (décision « notice seule »). Ils reliront
`config.json` à leur prochain boot (déclenché par l'opérateur via l'UI MAJ existante ou
SSH).

## 10. Tests (TDD)

**Backend pur** (`tests/test_config_resilience.py` étendu) :
- `write_user_config` : merge préserve les valeurs éditées **et** réinjecte `_comment` ;
  écriture atomique (passe par `.tmp` + `os.replace`) ; refresh `lastgood` ; **type
  préservé** (int reste int, float reste float) ; round-trip GET→POST sans dérive
  structurelle ; invalidation de `_REPORT_CACHE`.
- `build_config_schema` : inférence de type (bool/int/float/str) ; extraction de l'aide
  depuis `_comment` voisin ; flag `advanced` correct pour `ADVANCED_SECTIONS` ; flag
  `enum` pour les chemins du registre ; clés `_`-préfixées jamais transformées en champs.

**Vues Django** (`tests/test_web_views.py` ou nouveau `tests/test_configuration_views.py`) :
- `GET /api/configuration/` → 200 `{schema, values}` cohérents.
- `POST` valide → persiste, renvoie le `ConfigReport`, `config.json` mis à jour.
- `POST` type invalide → 400 avec champ fautif, `config.json` **inchangé**.

**Frontend** : pur Alpine, pas de test pytest (cohérent avec les chantiers UI précédents).

## 11. Critères de succès

1. La page liste **toutes** les clés de `config.json`, regroupées par section, le risqué
   sous « Avancé » replié.
2. Chaque champ affiche son aide (`_comment`) et le widget adapté à son type/énumération.
3. « Sauvegarder » écrit `config.json` **via le noyau A** (atomique, lastgood rafraîchi),
   sans corruption possible, et affiche la notice « redémarrage requis ».
4. Les valeurs terrain et les `_comment` sont préservés ; aucune clé `_`-préfixée éditable.
5. Une MAJ future qui ajoute une clé la fait apparaître dans l'UI **sans modif de code**.
6. Suite de tests verte (nouveaux tests backend + vues).

## 12. Hors périmètre

- Redémarrage de service piloté par l'UI ; rechargement à chaud.
- Validation de plages métier.
- Gestion des droits du fichier (écartée au chantier A : illusoire, compte `slenk` partagé).
- Édition des clés `_comment`/`_version`/`_date`.
