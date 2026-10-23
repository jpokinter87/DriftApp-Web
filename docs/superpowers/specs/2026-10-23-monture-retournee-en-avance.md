# Monture retournée avant le méridien : la coupole la suit tout de suite

Date : 23/10/2026 — statut : **spec à valider** (décision JP du 23/10 : cible prise
au méridien, pas d'avance fixe)

## Besoin

Nuit du 23/10 (6.25.1, option `asiair.dome_flip_on_pierside` cochée,
`max_wait_minutes=15`), objet RA 21h59m46.8s Déc +62°50′, qui culmine au nord à
71° de hauteur :

| Heure | Événement |
|---|---|
| ~21:24-21:25 | La monture se retourne (Serge) |
| 21:28:17 | Dashboard : « Monture : côté Est », objet à Az 0,24°, coupole à 315° |
| 21:29:05 | `meridian_transit` : coupole 315,1° → 36,1° (57 s) |
| 21:29:22 | Méridien selon l'ASIAIR (temps sidéral de la monture 35 s en avance) |
| 21:29:57 | Méridien astronomique |

La monture a retourné ~5 min **avant** le méridien ; la coupole est restée du
mauvais côté jusqu'à ce que l'azimut DriftApp passe 0°. La cause de l'avance de la
monture reste à établir (aucun journal ASIAIR cette nuit-là : `asiair_monitor` non
installé par l'OTA) ; le 21/10 l'ASIAIR avait retourné à son méridien.

La règle de la 6.24 (`dome_flip_wait.monture_en_retard`) ne fait que **retenir** la
coupole quand la monture est en retard. Une monture en avance n'est pas gérée :
l'abaque ne connaît que l'azimut, pas le côté du pied, et donne la position
« avant » jusqu'au passage du méridien.

On veut que la coupole parte dès que la monture est retournée, même avant le
méridien, sans attendre que l'abaque change de côté.

## Décisions

| # | Question | Décision |
|---|---|---|
| 1 | Où lire l'abaque quand la monture est en avance | **À l'instant du méridien DriftApp + 30 s** (décision JP, 23/10). Pas d'avance fixe de 10 min (proposition de Serge) : elle ne couvrirait pas une avance de plus de 10 min et n'a pas de sens pour une monture en retard |
| 2 | Que fait la coupole jusqu'au méridien | Elle **tient** cette position (cible figée), puis le suivi normal reprend au passage du méridien |
| 3 | Jusqu'où avant le méridien | Seulement si le méridien DriftApp est à moins de `asiair.max_wait_minutes` ; au-delà, comportement actuel et un WARNING par épisode |
| 4 | Activation | Même option que la 6.24 (`asiair.dome_flip_on_pierside`) : pas de nouvelle clé de configuration |

## Règle

**Monture en avance** = option active ET état ASIAIR frais (< 30 s) ET côté
rapporté `pier_east` (côté d'après le méridien) ET objet **avant** le méridien selon
DriftApp (azimut dans [0°, 180°[, même critère que la 6.24, inversé) ET
`|delta_h| < 6 h` ET méridien DriftApp atteint dans moins de `max_wait_minutes`.

Les deux règles sont exclusives : la 6.24 porte sur l'objet passé au méridien
(azimut ≥ 180°), celle-ci sur l'objet pas encore passé.

### Instant du méridien

Premier instant `t` après maintenant où l'azimut de l'objet (calculé comme pour
l'abaque, `_calculate_current_coords`) entre dans [180°, 360°[. Recherche par pas
de 60 s jusqu'à `max_wait_minutes`, puis dichotomie jusqu'à 5 s. Pas trouvé dans la
fenêtre → pas de tenue.

C'est l'azimut DriftApp qui fait basculer l'abaque : en le prenant comme
référence, la cible tenue est exactement celle que donnera l'abaque juste après
la bascule, et la reprise du suivi normal se fait sans saut.

### Cible tenue

`cible = abaque(position de l'objet à t_méridien + 30 s)`, calculée **une fois**
au début de la tenue. Les 30 s placent la lecture franchement du côté « après »
de l'abaque.

Écart attendu : sur le cas du 23/10, la cible « après » ne varie que de 0,1° par
minute près du méridien (36,1° à 21:30, 34,1° à 21:48) ; une tenue de 5 min coûte
~0,5°. L'écart grandit avec la durée de la tenue, d'où la borne
`max_wait_minutes`.

### Pendant la tenue

- `check_and_correct` remplace la cible abaque par la cible tenue ; le reste est
  inchangé (seuil 0,3°, chemin le plus court, vitesse rapide ≥ 3°, feedback,
  re-sync de la 6.24.1). Le premier passage fait la bascule (~80° le 23/10).
- Fin de la tenue :
  - objet passé au méridien (azimut ≥ 180°) → `reason=transit`, suivi normal ;
  - ASIAIR frais qui rapporte `pier_west` (monture renvoyée de l'autre côté à la
    main) → `reason=pierside`, suivi normal (la coupole revient côté « avant ») ;
  - suivi arrêté.
- **ASIAIR muet pendant la tenue : la tenue continue** jusqu'au méridien. La
  monture ne revient pas seule de l'autre côté ; repartir côté « avant » sur une
  simple perte de communication ferait faire deux bascules inutiles à la coupole.
- Pas de relance de la tenue après sa fin tant que la situation ne change pas : la
  règle se réévalue à chaque correction, une nouvelle tenue n'est possible que si
  la monture est revue côté Est avant le méridien.

## Journal

Logs moteur (clé=valeur) :

- `dome_flip_early_start | pier=pier_east delta_h=… az=… meridien_dans_s=… cible=…`
- `dome_flip_early_end | reason=transit|pierside held_s=…`
- `dome_flip_early_out_of_window | az=… max_min=…` (WARNING, une fois par épisode) :
  monture côté Est mais méridien au-delà de la fenêtre.

La bascule elle-même garde le log `meridian_transit` existant (grand mouvement).

## Affichage

`tracking_info` gagne `flip_early` : `{"target": 36.1}` pendant la tenue, `null`
sinon. Cartouche « Suivi actif », ligne déjà utilisée par la 6.24 :
« Monture retournée en avance — coupole tenue à 36,1° jusqu'au méridien ».
Journal du dashboard au début (« Monture retournée avant le méridien : bascule de
la coupole ») et à la fin de la tenue. Toujours visible, aucun survol.

## Hors périmètre

- **Pourquoi la monture a retourné en avance** : à établir avec le journal
  `asiair_monitor` (installé à la prochaine MAJ) et le réglage « Flip Timing after
  Meridian » de l'ASIAIR, à demander à Serge.
- Décalage d'environ 82 s de l'angle horaire DriftApp (CIRS au lieu de TETE,
  relevé le 20/10, non corrigé) : sans effet sur cette règle, qui prend l'azimut
  DriftApp comme référence de bout en bout.
- Anticipation méridien (`meridian_anticipation`) : reste neutralisée quand
  l'option est active.

## Limites

- La tenue est une approximation : la coupole est placée pour l'objet au
  méridien, pas pour sa position réelle (quelques minutes avant). Bornée par
  `max_wait_minutes`.
- Détection à la cadence des corrections (30 s) plus celle du watcher (5 s) :
  jusqu'à ~35 s entre le changement de côté et le départ de la coupole.
- Suivi lancé sur une monture déjà côté Est avant le méridien : le GOTO initial
  va côté « avant », puis la première correction bascule la coupole (un aller
  inutile, cas rare).

## Critères de succès

- Tests unitaires de la règle : côtés, objet avant/après le méridien,
  `|delta_h| ≥ 6 h`, état périmé, méridien hors fenêtre.
- Recherche de l'instant du méridien : objet qui culmine au nord (azimut qui
  décroît en passant 0°, 2,7° → 359,8°) et au sud (azimut qui passe 180°).
- `check_and_correct` avec watcher factice, **rejeu du 23/10** : monture côté Est
  à Az 2°, coupole à 315° → bascule immédiate vers la cible « après » (~36°), pas
  de retour à 315° aux corrections suivantes, reprise normale après le méridien
  sans saut.
- ASIAIR muet pendant la tenue → la tenue continue ; `pier_west` frais → fin.
- Option inactive, ou monture côté Ouest avant le méridien → comportement
  strictement inchangé (tests 6.24 et existants verts).
- Stack dev avec faux ASIAIR : ligne du cartouche et journal.
