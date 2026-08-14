# Capteur de pluie — intégration cimier

**Date** : 2026-08-14
**Statut** : design validé, prêt pour plan d'implémentation
**Périmètre** : provider pluie réel, armement par case à cocher, fermeture d'urgence,
journal de nuit persistant et frise de restitution dans l'UI.

---

## 1. Ce que le terrain a établi

La campagne du 14/08 (`logs/pluie_test_20260814_115519.log`, standalone
`scripts/diagnostics/pluie_manual.py`) répond aux cinq questions du cycle précédent :

| Question | Réponse | Source |
|---|---|---|
| Quelle entrée du Shelly `.87` porte le D0 | `id=0` | relevé Serge |
| Polarité rapportée par le Shelly | `state=true` = PLUIE (`invert=false`) | options du log |
| Réglage du trimpot | validé, quelques centilitres suffisent | 2 épisodes déclenchés à la demande |
| Chaîne capteur → Shelly → réseau → Python | vivante | transitions horodatées |
| Temps de séchage du MH-RD | 1 min 28 s puis **1 min 51 s** | résumé du log |

Le risque identifié au §8 du design précédent — un D0 en 3,3 V que l'entrée du Shelly Plus Uni
ne verrait pas — **ne s'est pas matérialisé**. Aucun étage d'adaptation n'est nécessaire.

### Conséquence : pas de `clear_delay_s`

Le design du 31/05 prévoyait un délai logiciel avant de reconsidérer l'état sec (600 s proposés,
jamais mesurés). La mesure le rend inutile : **le capteur porte lui-même ~2 minutes d'hystérésis
physique**, la grille restant humide après la dernière goutte. Un délai logiciel ferait doublon.
Et la décision produit (§3.3) est de ne pas rouvrir du tout après une fermeture pluie — ce qui
retire à ce paramètre son dernier consommateur. **`clear_delay_s` est abandonné.**

---

## 2. Objectif

1. **Refuser l'ouverture automatique** au crépuscule quand il pleut.
2. **Fermer le cimier en urgence** si la pluie survient alors qu'il est ouvert.
3. **Ne rien faire de tout cela tant que l'opérateur ne l'a pas armé** — une case
   « Protection pluie » décochée par défaut, pour mener des campagnes d'observation
   sous orage réel sans que le système agisse.
4. **Restituer la nuit graphiquement dans l'UI**, sans avoir à lire un log en SSH.

Le point 3 est la demande centrale : des orages sont annoncés sur la zone, et la protection ne
sera armée qu'une fois son comportement observé assez longtemps pour être cru.

---

## 3. Décisions de conception

### 3.1 Lecture : `ShellyRainWeatherProvider`

Implémente le contrat `WeatherProvider` existant (`is_safe_to_open` / `is_safe_to_keep_open` /
`describe`) — **aucun changement chez les consommateurs**, le scheduler continue d'appeler
`is_safe_to_open()` comme il le fait depuis la v6.2.

Le transport RPC `GET /rpc/Input.GetStatus?id=<n>` est déjà écrit dans
`ShellySwitchReader._read_input` (parsing, typage des erreurs, timeout). Il est **extrait en
fonction de module** et réutilisé par les deux lecteurs : une seule implémentation du dialogue
Shelly, pas deux qui divergeront.

**Pas d'I/O caché dans le contrat.** Une méthode `read_now()` fait la requête et met à jour l'état
interne ; les trois méthodes du contrat renvoient le dernier état connu, sans réseau. La veille
(§3.4) appelle `read_now()` à sa cadence ; le scheduler consulte le même état sans déclencher de
requête supplémentaire. Cela évite deux pollings concurrents sur le même capteur et rend les
méthodes du contrat instantanées et déterministes en test.

**Anti-rebond : deux lectures concordantes** (`confirm_reads`, défaut 2) avant tout changement
d'état, dans les deux sens. Coût : ~20 s de latence supplémentaire, négligeable devant les ~47 s
que dure une fermeture. Bénéfice : une lecture aberrante isolée ne peut pas mettre fin à une nuit
d'observation.

**Capteur injoignable** (URLError, HTTP ≠ 200, JSON invalide, payload sans `state`) :

- `is_safe_to_keep_open()` → **`True`** : on ne ferme **jamais** sur une absence de donnée.
  La fiabilité des Shelly est un sujet documenté du projet (deux Gen 1 défaillants en 12 h le
  30/05) ; une coupure Wi-Fi passagère ne doit pas tuer une session en cours.
- `is_safe_to_open()` → **`False`** : on n'ouvre pas à l'aveugle. L'asymétrie est volontaire —
  refuser d'ouvrir est réversible et sans coût, fermer ne l'est pas.
- L'état est tracé dans `describe()`, remonté à l'UI et journalisé.

Le provider ne lève jamais vers ses consommateurs.

### 3.2 Armement : `RainProtection`

Objet qui **enveloppe** le provider et implémente le même contrat. Il porte la politique ; le
provider ne porte que la mesure.

- **Désarmé** (défaut) : `is_safe_to_open()` et `is_safe_to_keep_open()` renvoient `True` sans
  condition. Le capteur est lu, publié, affiché, journalisé — et **strictement inerte**.
- **Armé** : relaie le provider. Refus d'ouverture automatique **et** fermeture d'urgence — la
  case gouverne tout le comportement pluie, un seul modèle mental.
- `describe()` renvoie l'état du provider enrichi de `armed` et `latched`.

**Hot-reload** : l'état armé est relu depuis `data/config.json` à chaque tour de veille, donc la
case prend effet en ≤ 10 s sans redémarrage — même mécanique que le hot-reload du mode
d'automatisation (v6.0 Phase 4).

### 3.3 Verrou anti-réouverture

Une fermeture pluie pose un **latch** sur `RainProtection` : toute ouverture automatique
ultérieure est refusée, même si le capteur redevient sec. Décision produit explicite — une monture
plongée dans le noir puis re-exposée en pleine nuit n'est pas un scénario qu'on souhaite provoquer
pour rattraper une éclaircie.

Aujourd'hui, la non-réouverture ne tiendrait qu'à un effet de bord : `retrigger_cooldown_hours=12`
bloque un second OPEN dans la même nuit — mais cette mémoire est en RAM et un redémarrage de
`cimier_service` la perd. Le latch rend l'intention explicite et testable.

Il ne se lève que sur une **commande `open` humaine** (clic sur « Ouvrir ») ou un redémarrage du
service. Aucune levée automatique.

### 3.4 Veille : un bloc cadencé dans `cimier_service.tick()`

Sur le modèle exact du bloc scheduler existant, cadencé par `watch_interval_s` (défaut 10 s) :

1. hot-reload du flag d'armement depuis `config.json` ;
2. `read_now()` sur le provider ;
3. publication de l'état dans `cimier_status.json` + journal de nuit si transition (§3.6) ;
4. déclenchement de la fermeture **si et seulement si** : armé **et** pluie confirmée **et** le
   cimier est effectivement observé ouvert.

Pas de latch anti-répétition nécessaire : après une fermeture réussie l'état devient `closed`, ce
qui coupe la condition. Si la fermeture échoue (timeout), l'état reste `open` et la veille
réessaie au tour suivant — comportement souhaitable.

Pendant un cooldown, l'état dérivé est `cooldown` et non `open` : la veille s'abstient et réessaie
10 s plus tard. C'est nécessaire, `cimier_service` étant en **mode Drop** — une commande écrite
pendant le cooldown serait consommée puis jetée (v6.7.3).

**Limite assumée** : `tick()` ne tourne pas pendant l'exécution d'un cycle, qui est synchrone.
Fenêtre aveugle ≤ 47 s si la pluie démarre pendant une ouverture. Hors périmètre.

**Latence pire cas** de bout en bout : 2 lectures d'anti-rebond (≤ 20 s) + fermeture (~47 s)
≈ **1 min 10 s** après les premières gouttes.

### 3.5 Séquence de fermeture : une seule implémentation

La séquence `tracking_stop` → attente de consommation → `goto 45°` → `close` existe aujourd'hui
en **deux copies** : `CimierScheduler._trigger_close` et `ParkingSessionView`. C'est précisément
la divergence entre ces deux copies qui a produit le bug de parking corrigé en 6.11.3 — le
correctif de mai n'avait été appliqué qu'à l'une des deux, laissant l'autre cassée trois mois.

Ajouter une **troisième** copie pour la fermeture pluie serait reproduire la cause du bug. La
séquence est donc extraite dans `services/session_close_sequence.py` et consommée par les trois
appelants. C'est le seul refactor de ce cycle, et il sert directement le sujet.

### 3.6 Journal de nuit persistant

La timeline du dashboard est un buffer mémoire de 50 entrées, perdu au rechargement de page :
inutilisable pour analyser une nuit le lendemain matin. `cimier_service` écrit donc un journal
sur disque, `services/night_journal.py`.

**Transitions, pas échantillons.** Le log terrain produit 3 lignes en 4 minutes sous arrosage ;
une nuit d'orage en produira quelques dizaines. Échantillonner toutes les 10 s donnerait
8 640 points par nuit pour la même information. Une ligne n'est écrite que quand quelque chose
change.

**Un fichier par nuit**, `data/nights/<AAAA-MM-JJ>.jsonl`, la nuit étant découpée **midi → midi**
en heure locale pour ne pas scinder une session à minuit. Append immédiat avec `flush` — une
coupure ne doit rien perdre, même discipline que le standalone. Écriture défensive : une erreur
d'E/S est journalisée et jamais propagée, un disque plein ne doit pas empêcher une fermeture.

Événements enregistrés :

| `event` | Champs | Émis quand |
|---|---|---|
| `rain` | `state` ∈ {`wet`,`dry`,`unreachable`}, `armed` | transition confirmée du capteur |
| `decision` | `action` ∈ {`close`,`would_close`}, `reason` | la protection agit, ou aurait agi (§3.7) |
| `cimier` | `action` ∈ {`open`,`close`}, `result` | fin de cycle cimier |

Tous horodatés en ISO 8601 local. Le journal accueille les événements cimier parce qu'une frise
de la pluie seule ne montrerait que la moitié de l'histoire : ce qu'on veut lire, c'est « il a plu
à 2 h 13, le cimier était ouvert, la protection était désarmée ».

**Rétention 30 jours**, purge au même endroit que l'écriture. Les fichiers pèsent quelques
kilo-octets ; 30 jours couvrent une saison d'essais et permettent de comparer plusieurs épisodes.

### 3.7 Décision à blanc

Désarmée, quand la logique **aurait** déclenché une fermeture, elle journalise
`decision action=would_close` sans rien faire.

C'est ce qui sépare « le capteur a vu la pluie » de « la protection aurait fermé au bon moment,
ni trop tôt sur une bruine, ni trop tard sous l'averse ». C'est cette seconde question que la
campagne doit trancher avant qu'on coche la case.

### 3.8 Piège : la case ne garde pas le cimier fermé

Décochée, la protection n'agit sur rien — mais **c'est le mode d'automatisation qui décide des
ouvertures**. En `full`, le scheduler ouvre au crépuscule sur les seules éphémérides, et la pluie
ne l'en empêche pas puisque la protection est désarmée. Un soir d'orage en `full` + protection
décochée, **le cimier s'ouvre**.

Une campagne d'observation se mène donc en `manual` ou `semi` (qui ne déclenchent jamais
d'ouverture). L'UI affiche un avertissement explicite quand la combinaison `full` + protection
décochée est active, plutôt que de laisser ce piège à la vigilance de l'opérateur.

---

## 4. Configuration

Section `cimier.weather_provider` étendue. Defaults rétro-compatibles : une config sans ces clés
reste en `noop`, comportement strictement inchangé.

```json
"weather_provider": {
  "_comment": "Capteur pluie MH-RD sur Shelly Plus Uni (.87), D0 sur l'entrée id=0. type ∈ {noop, shelly_rain}. protection_enabled=false : le capteur est lu et affiché mais n'agit sur rien (mode observation).",
  "type": "noop",
  "host": "192.168.1.87",
  "input_id": 0,
  "invert": false,
  "timeout_s": 3.0,
  "protection_enabled": false,
  "watch_interval_s": 10.0,
  "confirm_reads": 2
}
```

- `type` : `noop` dans le template repo, `shelly_rain` dans le `config.json` terrain — même
  convention que `switch_reader`, dont l'IP figure au template avec un type `noop`.
- `invert: false` et `input_id: 0` sont les valeurs **mesurées** le 14/08, pas des hypothèses.
- `protection_enabled` est la case à cocher. Persistée ici, elle apparaît aussi automatiquement
  dans la page `/configuration/`, qui se génère depuis le template.
- Aucune valeur terrain dans le code Python.

L'écriture depuis le dashboard suit le pattern de `AutomationView` (lecture, modification d'une
clé, écriture atomique tmp+rename), et non `write_user_config` du chantier B : ce dernier réécrit
la configuration entière à travers le merge structurel, ce qui est justifié pour un formulaire
complet mais disproportionné pour basculer un booléen. Les deux cohabitent déjà.

`data/nights/` est ajouté au `.gitignore` — comme `data/sessions/`, ce sont des données terrain.

---

## 5. UI

### 5.1 Dashboard — cartouche cimier

- **Case « Protection pluie »**, décochée par défaut, à côté du sélecteur Mode auto.
  `POST /api/cimier/rain-protection/`, calqué sur `AutomationView` (lecture/écriture atomique de
  `config.json`, réponse `apply_pending`).
- **Pastille d'état** `SEC` / `PLUIE` / `CAPTEUR ?` à côté de la case. Sans elle, une campagne
  d'observation serait aveugle : décochée, la case ne produit aucun effet visible. Alimentée par
  `cimier_status.json`, déjà transmis brut par `/api/cimier/status/`.
- **Avertissement** `full` + protection décochée (§3.8).
- Entrées de timeline sur fermeture pluie, décision à blanc et capteur injoignable.

Contrainte écran tactile 720 p : aucune information ne dépend du survol, l'ajout reste dans
l'esprit du dégraissage v6.11.0 (une ligne, pas un panneau).

### 5.2 Page Session — carte « Nuit »

Nouvelle carte avec **sélecteur de date**, indexée par nuit et non par session de tracking : une
nuit d'orage passée cimier fermé ne produit aucune session, et doit malgré tout être consultable.

**Frise temporelle, pas courbe.** Le signal est binaire ; une courbe serait la mauvaise forme.
Trois lignes sur un axe des heures commun (midi → midi) :

1. **Pluie** — bande pleine = pluie, fond clair = sec, hachures = capteur injoignable ;
2. **Cimier** — bande = ouvert, avec marqueurs verticaux aux décisions (`a fermé` plein,
   `aurait fermé` en pointillés) ;
3. **Suivi** — bandes des sessions de tracking, étiquetées du nom d'objet.

La troisième ligne est lue **à l'affichage** depuis les fichiers déjà persistés dans
`data/sessions/` : aucun couplage nouveau entre `cimier_service` et `motor_service`.

**SVG inline généré en JS**, pas Chart.js : un diagramme de bandes s'y exprime mal (barres
flottantes détournées), là où le SVG donne un contrôle exact, reste net à toute largeur et se
lit sans tooltip — l'écran de l'observatoire est tactile, rien ne doit dépendre du survol.
Légende et graduations horaires portent l'information directement.

`GET /api/session/night/?date=AAAA-MM-JJ` renvoie les trois séries plus la liste des nuits
disponibles pour peupler le sélecteur.

---

## 6. Simulation

`core/hardware/cimier_simulator.py` émule déjà les quatre Shelly. Il gagne l'entrée pluie du
`.87` et un endpoint `/dev/rain?on=1|0` permettant de **déclencher une averse en cours de session
dev**, sans redémarrer quoi que ce soit. Les overrides `CIMIER_DEV_MODE` pointent
`weather_provider` vers le simulateur.

Tout le pipeline devient exerçable sur la machine de dev : refus d'ouverture, fermeture
d'urgence, latch, décision à blanc, journal, frise. C'est la ligne de conduite du projet — une
machine de dev à 800 km du Pi ne peut pas se permettre de découvrir les comportements sur site.

---

## 7. Tests

TDD, périmètre cimier + session.

**`tests/test_weather_provider.py`**
- `ShellyRainWeatherProvider` avec `urlopen` injecté : sec, pluie, `invert`, anti-rebond
  (une lecture isolée ne bascule pas, deux concordantes oui), injoignable →
  `is_safe_to_open()` False et `is_safe_to_keep_open()` True, contenu de `describe()`.
- `RainProtection` : désarmée → toujours `True` alors que le provider dit qu'il pleut, tout en
  exposant l'état réel dans `describe()` ; armée → relaie ; latch posé par une fermeture pluie et
  levé par une commande `open`.
- Factory : `type="shelly_rain"` instancie le bon provider, type inconnu → `ValueError`.

**`tests/test_config_loader.py`** — parsing des nouvelles clés, defaults rétro-compatibles
(config sans section → `noop`, comportement v6.11 inchangé).

**`tests/test_cimier_service.py`** — veille : pluie confirmée + armé + cimier ouvert → séquence
émise ; désarmé → rien, mais `would_close` journalisé ; cimier fermé → rien ; cooldown → rien puis
retry ; injoignable → pas de fermeture ; hot-reload du flag pris en compte au tour suivant.

**`tests/test_session_close_sequence.py`** — la séquence extraite, et les trois appelants qui la
consomment (garde-fou anti-régression du bug 6.11.3).

**`tests/test_night_journal.py`** — append/flush, découpage midi→midi, purge 30 jours, robustesse
sur erreur d'E/S (journalisée, jamais propagée).

**Web** — `GET`/`POST /api/cimier/rain-protection/`, `GET /api/session/night/`.

**Régression** — suite complète verte (1180 au dernier décompte).

---

## 8. Ordre de livraison

Deux lots, le premier déployable seul.

**Lot 1 — protection et journal.** Provider, `RainProtection`, veille, séquence factorisée, case
à cocher, pastille, avertissement `full`, journal de nuit, simulation, tests.

**Lot 2 — restitution.** Endpoint `night`, frise SVG, sélecteur de date sur la page Session.

Le journal (§3.6) appartient au **lot 1**, pas au lot 2 dont il est pourtant la source : sans lui,
les nuits qui s'écoulent entre les deux livraisons ne laissent aucune trace exploitable.

---

## 9. Hors périmètre

- **Réouverture après retour au sec** — décision produit, §3.3.
- **Interruption d'un cycle en cours par la pluie** — §3.4, fenêtre ≤ 47 s.
- **Entrée analogique A0** (intensité de pluie) : le Shelly Uni lit du TOR, l'intensité
  demanderait un autre montage.
- **Vent, nuages, humidité** : le contrat `WeatherProvider` les accueillera sans casser
  l'existant, mais ils n'ont ni capteur ni cadrage.
- **Alerte poussée hors UI** (SMS, notification) : la question « comment prévenir Serge à 3 h du
  matin » est distincte et non posée.

---

## 10. Critères de succès

- En simulation : averse déclenchée → refus d'ouverture si armé, fermeture d'urgence en < 1 min 15,
  latch qui tient malgré le retour au sec, `would_close` journalisé si désarmé, frise fidèle.
- Case décochée : le capteur bascule, s'affiche, se journalise, et **rien ne bouge**.
- Suite pytest verte, aucune valeur terrain dans le code.
- `type="noop"` reste le défaut : une config non migrée se comporte exactement comme en v6.11.
- Validation terrain : une nuit d'orage observée protection décochée en mode `manual`, dont la
  frise se relit le lendemain dans l'UI et confirme que la fermeture serait tombée au bon moment.

---

## Références

- Résultat de la campagne : `logs/pluie_test_20260814_115519.log`
- Standalone : `scripts/diagnostics/pluie_manual.py`, spec `2026-08-11-capteur-pluie-mini-test-design.md`
- Design initial (approche GPIO, remplacée par le Shelly) : `2026-05-31-cimier-capteur-pluie-design.md`
- Backlog : mémoire `project_cimier_weather_rain_backlog`
- Contrat météo : `core/hardware/weather_provider.py`
- Infra RPC réutilisée : `core/hardware/shelly_switch_reader.py`
- Fiche capteur : `docs/AZdelivery raindrops module.pdf`
