# Rampe à accélération constante et STOP doux (v6.19)

## Constat terrain (27/09/2026)

Campagne `calibration_vitesse_encodeur.py --depuis 130` (Serge) : paliers
tenus jusqu'à 104 µs, décrochage à 100 µs après 0,21° — juste après la fin
de la rampe. Démarrages et arrêts ressentis comme brutaux.

Cause : la rampe v4.5 interpole le **délai** de 3000 µs à la cible sur 500 pas
fixes. La vitesse étant l'inverse du délai, le gain se concentre à la fin :

| cible | pic d'accélération | 50 % → 100 % de la vitesse |
|---|---|---|
| 260 µs | 74 000 pas/s² | 48 ms |
| 110 µs | 738 000 pas/s² | 14 ms |

Le pic tombe à pleine vitesse, là où le couple est le plus faible. Et le STOP
coupe le train d'impulsions net, sans décélération.

## Décisions (JP, 27/09/2026)

- Rampe à **accélération constante** pour les mouvements **plus rapides que
  260 µs** ; à 260 µs et au-delà, rampe v4.5 strictement inchangée
  (corrections de suivi, calibration, petits mouvements — éprouvés).
- Durée de montée jusqu'à la vitesse rapide : **2 s**, réglable
  (`motor_driver.ramp_time_s`, page Configuration).
- **STOP doux** (décélération depuis la vitesse du moment) pour les
  mouvements rapides seulement ; arrêt immédiat conservé à 260 µs (la
  calibration au microswitch 45° n'est pas modifiée).

## Conception

### Protocole série — inchangé, compatible dans les deux sens

`MOVE <pas> <dir> <délai_us> <rampe> [accel]` : 6ᵉ jeton optionnel,
accélération en pas/s². L'ancien firmware ignore les jetons en trop ; le
nouveau applique un défaut s'il est absent. OTA et flash du Pico peuvent donc
arriver dans n'importe quel ordre.

Le Pi calcule `accel = vitesse_rapide / ramp_time_s` (pas/s²) : même
accélération pour toutes les vitesses rapides, ce qui correspond au couple
disponible plutôt qu'à une durée arbitraire.

### Firmware — paliers PIO enchaînés

Le programme PIO lit `(N-1, demi-période)`, émet N pas, puis revient lire le
FIFO : des blocs empilés s'enchaînent **sans coupure**. La rampe devient une
suite de paliers de 20 ms à vitesse constante (100 paliers pour 2 s, soit 1 %
de vitesse par palier) :

- aucun calcul ni `put()` par pas, aucun tableau par pas en mémoire ;
- croisière découpée en tronçons de 20 ms : un STOP est vu en ≤ ~60 ms ;
- STOP doux : on cesse d'empiler la croisière et on empile la descente
  (miroir de la montée déjà effectuée). Tous les paliers empilés sont émis :
  le nombre de pas renvoyé est **exact** ;
- mouvement trop court pour montée + descente complètes : profil
  triangulaire, total de pas exact.

`ramp.py::ProfilAccelConstante` (Python pur, testable) produit les paliers ;
`step_generator.py::move_segments` les pousse au PIO.

### Côté Pi

- `core/config/config.py` : `RAMP_TIME_S` (borné [0,5 ; 10] s, défaut 2,0) et
  `FAST_ACCEL_STEPS_S2`.
- `MoteurRP2040.rotation` envoie le 6ᵉ jeton et élargit le timeout série de
  la durée des rampes.

## Évolution v6.19.1 (retour terrain, 27/09 soir)

Après flash : tout fonctionne, mais la fin d'un JOG 1° à 260 µs reste
brutale (rampe v4.5 : moitié de la vitesse perdue en 48 ms). Décision JP :
**rampe à accélération constante pour tous les mouvements**, même
accélération ; **STOP immédiat conservé à 260 µs** (calibration). L'ancienne
rampe est retirée du firmware. JOG 1° : 2,77 s → 2,20 s.

## Hors périmètre

- STOP doux à 260 µs et plus lent (calibration).
- Réglage de l'accélération au-delà de la durée de rampe.

## Validation

- Tests : profil (monotonie, accélération bornée, total exact, triangulaire,
  STOP en montée / croisière / descente), émission PIO (mots poussés, STOP),
  choix du profil selon le délai, 6ᵉ jeton côté Pi.
- Terrain (Serge, après flash) : ressenti démarrage/arrêt, STOP en continu,
  nouvelle campagne `--depuis 130` (le décrochage à 100 µs doit reculer si
  l'hypothèse du pic d'accélération est juste).
