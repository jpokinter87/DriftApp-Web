# Dépassement des grands déplacements — spec

Date : 23/10/2026. Version visée : 6.25.1.

## Constat

Les grands déplacements rapides (≥ 3°, rotation directe sans feedback) vont
toujours trop loin, dans le sens du mouvement. Relevé dans les logs terrain
(« GOTO optimisé: rotation directe » puis « Correction finale: erreur ») :

| Date | Commandé | Dépassement | % |
|------|---------:|------------:|--:|
| 22/10 09:07 | +50,7° | 1,09° | 2,1 |
| 22/10 09:24 | +72,6° | 1,74° | 2,4 |
| 16/10 12:32 | +134,4° | 3,08° | 2,3 |
| 17/10 22:38 | −133,5° | 3,39° | 2,5 |
| 16/10 12:34 | −128,6° | 4,04° | 3,1 |
| 22/10 04:03 | +117,9° | 4,78° | 4,1 |
| 17/10 02:58 | +123,6° | 5,06° | 4,1 |

## Ce que les logs établissent

1. **Ce n'est pas la rampe 6.19.** La campagne vitesse du 27/09, faite avant
   le flash 6.19, mesurait déjà 10,06 à 10,48° parcourus pour 10° commandés,
   à 260 µs comme à 104 µs. Les mouvements dans le sens + (non perturbés par le
   microswitch) donnent 1,5 à 2,2 %. Les mouvements dans le sens − finissaient
   sur le microswitch 45° : le recalage en fin de mouvement gonfle la mesure
   (4,2 à 4,8 %), ces valeurs-là ne comptent pas.
2. **Tous les GOTO relevés finissent au parking et franchissent le microswitch
   pendant la rotation directe** (ex. 22/10 04:05:01, 4 s avant l'arrêt). Le
   dépassement mesuré est donc un dépassement **physique** au-delà de 45°.
3. Les deux cas les plus propres (22/10 09:06 et 09:22) : aller par feedback
   encodeur depuis un recalage frais, retour en pas. Ils donnent le même
   rapport : **1 degré-pas = 1,021 à 1,024 degré-encodeur**. Les cas à 4 %
   viennent après une nuit entière de suivi : l'encodeur a dérivé en plus.

## Ce que les logs ne peuvent pas trancher

Chaque mesure disponible compare les pas à l'encodeur ; elle donne le
**rapport** des deux échelles, jamais laquelle est fausse :

- `steps_correction_factor` (1,08849, config) trop fort d'environ 2 % ;
- ou `CALIBRATION_FACTOR` de l'encodeur (0,010851, codé dans
  `ems22d_calibrated.py`) trop faible d'environ 2 % ;
- ou un peu des deux, plus un glissement de la roue de l'encodeur (la dérive
  sur une nuit le suggère).

Les deux facteurs datent d'avant la v4.3, sans trace de leur mesure. Corriger
le mauvais décalerait toutes les positions de la coupole par rapport à
l'abaque (mesurée avec l'encodeur) ; on ne corrige rien sans mesure.

La seule référence physique est le microswitch 45°. Un tour complet entre
deux passages sur le microswitch mesure chaque échelle séparément :

- **échelle encodeur** : ce que l'encodeur a compté entre deux passages
  (360° physiques exactement, même front, même sens) ;
- **échelle des pas** : pas commandés pour le parcours total, dont 360°
  entre les deux passages et deux bouts courts mesurés à l'encodeur.

## Livrable (étape 1, mesure)

1. `ems22d_calibrated.py` : à chaque recalage (microswitch ou forcé), journaliser
   l'angle lu juste avant et l'écart corrigé
   (`recalage | source=switch avant=…° ecart=…°`). Chaque fin de nuit, le
   parking franchit le microswitch : la dérive de l'encodeur sur la nuit sera
   lisible dans le log sans rien faire de plus.
2. `scripts/diagnostics/mesure_tour_complet.py` : pour chaque sens et chaque
   vitesse (260 µs et `fast_delay_us`), GOTO à 6° avant le microswitch, JOG
   de 385°, capture des deux recalages, calcul des deux échelles et des
   facteurs corrigés proposés. Ne modifie ni la config ni le démon. Rapport
   JSON dans `logs/diagnostics/`. Durée totale ~30 min.
3. Tests des fonctions de calcul (pures) et du log de recalage.

## Étape 2 (après le retour terrain, hors de ce lot)

Corriger le facteur que la mesure désigne. Si c'est l'encodeur, l'abaque
mesurée avec l'ancien facteur devra être examinée (azimuts décalés en
proportion de leur distance à 45°). Si l'écart dépend du sens ou de la
vitesse, c'est un glissement, pas un facteur : autre chantier.

## Non-objectifs

Pas de correction de facteur dans ce lot. Pas de changement du GOTO
(la correction finale par feedback rattrape déjà l'écart).
