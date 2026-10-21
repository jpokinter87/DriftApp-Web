# Bascule de la coupole sur le signal de retournement de l'ASIAIR

Date : 21/10/2026 — statut : **spec validée** (décisions JP du 21/10)

## Besoin

La coupole bascule de côté au passage au méridien, parce que l'abaque
(`Loi_coupole.xlsx`) change de côté à cet instant. La monture, elle, est
retournée par l'ASIAIR plus tard : `merid_over_min` après le méridien (5 min par
défaut), et seulement avant une pose qui ne finirait pas à temps. Le 16/10 (MWP 1,
poses de 600 s), la monture a retourné ~11 min après la coupole ; Serge a dû
arrêter le suivi.

La sonde du 21/10 (`logs/diagnostics/asiair_20261021_170542.jsonl`) a montré que
l'ASIAIR fournit l'information en direct sur le port 4400, en lecture seule et sans
authentification :

- `scope_get_pierside` → `pier_west` avant le méridien, `pier_east` après le
  retournement (passé à 17:15:07, ~9 s après le début du slew de 17:14:58) ;
- `scope_get_info` → `RA` (heures, JNow) et `sidereal_time` de la monture. L'ASIAIR
  décide du retournement sur `delta_h = range12(RA − sidereal_time)`
  (firmware décompilé, `meridian_flip.cpp`).

On veut que la coupole attende le retournement réel au lieu de basculer au transit.

## Décisions

| # | Question | Décision |
|---|---|---|
| 1 | ASIAIR muet ou retournement qui ne vient pas | **Attente bornée** : ASIAIR muet → comportement actuel (bascule au transit) ; ASIAIR joignable sans retournement → coupole immobile au plus `max_wait_minutes` (défaut 30), puis bascule avec un WARNING |
| 2 | Anticipation méridien existante (`meridian_anticipation`) | **Neutralisée** quand la bascule sur signal est active ; inchangée sinon |
| 3 | Activation | **Option de config** `asiair.dome_flip_on_pierside`, désactivée dans le template, réglable sur la page Configuration |
| 4 | Affichage | **Ligne dans le cartouche « Suivi actif »** : côté du pied ASIAIR en temps normal, « Attente retournement monture — n min / 30 » pendant l'attente ; une ligne au journal à chaque transition |

## Règle

Principe (JP, 21/10) : **tant que la monture est encore du côté d'avant le
méridien, la coupole ne bascule pas** ; elle part au feu vert de l'ASIAIR
(changement de côté du pied), à vitesse rapide, pendant que la monture termine son
retournement.

« Objet passé au méridien » est jugé par **DriftApp**, avec l'azimut qui sert à
l'abaque : azimut dans [180°, 360°[ (moitié Ouest du ciel), ce qui équivaut
exactement à un angle horaire positif quelle que soit la déclinaison. On ne compare
pas au méridien de l'ASIAIR : les deux calculs ne tombent pas à la même seconde
(le 21/10 l'ASIAIR a lancé le retournement à `delta_h = +0,002 h`), et dans
l'intervalle la coupole aurait pu basculer avant le feu vert. (Révision du 21/10 ;
la première version comparait `delta_h` de l'ASIAIR au côté rapporté.)

**Attente** = option active ET état ASIAIR frais (< 30 s) ET côté rapporté
`pier_west` (côté d'avant le méridien, vérifié le 21/10 : pier_west → pier_east au
retournement) ET objet passé au méridien selon DriftApp ET `|delta_h| < 6 h` ET
délai maximal pas encore écoulé.

- `delta_h = range12(RA − sidereal_time)` de `scope_get_info` ne sert qu'au garde-fou
  `|delta_h| < 6 h` : comme l'ASIAIR, on ne raisonne qu'autour du passage supérieur.
  Au passage inférieur (sous le pôle) la monture ne retourne pas.
- Monture déjà côté Est (retournement fait en avance ou à la main) ou côté inconnu :
  pas d'attente, comportement actuel.
- Pas d'état « avant/après transit » à mémoriser : la règle se recalcule à chaque
  correction. Elle couvre aussi un suivi lancé après le méridien sur une monture pas
  encore retournée.
- Le délai maximal compte depuis la première correction suspendue. Une fois écoulé,
  l'attente est levée jusqu'à ce que la monture soit vue hors de cette situation
  (côté Est, ou objet revenu avant le méridien) ; la même cause ne la relance pas,
  un ASIAIR devenu muet non plus.

## Comportement pendant le suivi

- **Attente** : `check_and_correct` calcule la cible abaque comme aujourd'hui puis ne
  bouge pas la coupole ; prochaine vérification à l'intervalle habituel (30 s).
  Logs (moteur, clé=valeur) : `dome_flip_wait_start | pier=… delta_h=… max_min=…`
  une fois, `dome_flip_wait_end | reason=pierside|timeout|asiair_silent waited_s=…`.
  `timeout` et `asiair_silent` en WARNING.
- **Fin d'attente par retournement** : la correction suivante est faite tout de
  suite (sans attendre l'intervalle de 30 s) ; c'est la bascule ordinaire de
  l'abaque, à la vitesse rapide existante (≥ 3°).
- **ASIAIR muet** (aucune lecture réussie depuis 30 s) : pas d'attente ; une attente
  en cours est levée (`reason=asiair_silent`).
- **GOTO initial du suivi** : inchangé (hors périmètre, voir Limites).

## Lecture de l'ASIAIR

- `core/hardware/asiair_client.py` : nouvelle `lire_etat_monture(host, port,
  timeout_s) -> EtatMonture(pier, delta_h)`, sur la connexion et le décodage
  existants (`_requete`). `pier` vaut `"pier_west"`, `"pier_east"` ou `None`
  (valeur inconnue).
- `AsiairPierWatcher` (nouveau, `core/hardware/asiair_watcher.py`) : thread démon
  qui interroge l'ASIAIR toutes les 5 s et garde le dernier état réussi avec son
  heure (monotone). Méthode `etat_frais(max_age_s=30) -> EtatMonture | None`. Une
  erreur réseau n'est jamais propagée (log DEBUG, WARNING une fois par panne).
- Créé par `TrackingHandler` au démarrage d'un suivi quand l'option est active et
  `asiair.host` renseigné, arrêté avec le suivi. Passé à `TrackingSession`.
  La boucle de suivi ne fait jamais d'appel réseau.

## Configuration

Section `asiair` du template, deux clés (merge structurel → ajoutées au
`config.json` terrain avec leur défaut) :

```json
"dome_flip_on_pierside": false,
"max_wait_minutes": 30
```

`AsiairConfig` gagne les deux champs ; aide sur la page Configuration
(`HELP_REGISTRY`, test de complétude). Relues au démarrage de chaque suivi.

## Anticipation méridien

Option active (et watcher créé) → `TrackingSession` n'arme pas l'anticipation
(log `meridian_anticipation_disabled | reason=asiair_pierside`).

## Affichage

`tracking_info` gagne `asiair_pier` (`"east"`, `"west"` ou `null`) et
`flip_wait` (`{"elapsed_s", "max_s"}` ou `null`). Cartouche « Suivi actif » : une
ligne « Monture : côté Est/Ouest » ou « Attente retournement monture — 4 min / 30 »
(ambre) ; rien si l'option est inactive. Le dashboard écrit au journal le début et
la fin de l'attente. Toujours visible, aucun survol.

## Limites

- GOTO initial lancé après le méridien sur une monture pas encore retournée : la
  coupole va du côté « après » ; les corrections attendront ensuite le retournement
  (l'écart reste celui d'aujourd'hui pour ce cas rare).
- Une seule connexion de lecture toutes les 5 s ; pas d'écoute des événements
  (`ScopeTrack`, messages INDI) : le côté du pied suffit, le slew de la monture dure
  ~1 min et la coupole met du même ordre.
- Non testable sur le matériel depuis la machine de dev : faux ASIAIR TCP en test et
  sur la stack dev ; validation terrain par Serge (`Flip Timing after Meridian` à 0
  ou 5 min).

## Critères de succès

- Tests : règle (côtés, objet avant/après le méridien, `|delta_h| ≥ 6 h`, état périmé,
  délai maximal) ; watcher
  contre un faux ASIAIR TCP ; `check_and_correct` suspendu puis bascule immédiate au
  changement de côté ; rejeu de la chronologie du 21/10.
- Option désactivée → comportement strictement inchangé (tests existants verts).
- Stack dev avec faux ASIAIR : attente visible au cartouche, bascule au changement
  de côté.
