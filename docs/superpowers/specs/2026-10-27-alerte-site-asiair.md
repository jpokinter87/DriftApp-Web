# Alerte « site de l'ASIAIR faux » (27/10/2026)

## Besoin

Nuit du 27/10 : l'appli ASIAIR a poussé vers la monture la position GPS du téléphone
(E 2°10', N 48°48') au lieu du site de l'observatoire (E 5,23°, N 44,15°). Le temps
sidéral de la monture retardait de 12 min 20 s, le retournement est parti 12 min après le
vrai méridien et la coupole a attendu 793 s. Rien ne l'a signalé à l'utilisateur. Aucun
réglage ASIAIR ne verrouille le site : DriftApp est le seul garde-fou possible.

## Ce qu'on peut mesurer

Le port 4400 ne donne pas le site de la monture : `scope_get_info` renvoie `RA`, `Dec` et
`sidereal_time`, rien d'autre (5 nuits de journaux, aucune trace dans les messages INDI).
On compare donc le temps sidéral de la monture à celui que DriftApp calcule pour
`site.longitude` de `data/config.json`, **à l'instant de la lecture**. L'écart est celui
du retournement : longitude fausse, ou horloge de l'ASIAIR fausse (indiscernables). Une
latitude fausse seule reste invisible.

Écart relevé : +30 s le 23/10, +32 s le 26/10 (site correct), −12 min 20 s le 27/10.
Seuil retenu : **2 min** (0,5° de longitude, environ 40 km).

## Comportement

- Pendant le suivi, avec `asiair.dome_flip_on_pierside` (le watcher du côté du pied tourne
  déjà et lit `scope_get_info` toutes les 5 s) : choix de JP le 27/10, pas de nouveau
  fichier IPC.
- Au-delà du seuil : le statut du suivi porte `asiair_site_alert = {"offset_min",
  "lon_deg"}` (écart en minutes, > 0 = monture en avance ; longitude que la monture croit
  avoir = longitude du site + écart × 15). Sinon `None`.
- Dashboard : ligne d'alerte rouge dans le cartouche « Suivi actif », toujours visible
  (écran tactile, pas de survol) : « ASIAIR : méridien décalé de −12,3 min (longitude
  monture ≈ 2,15° E au lieu de 5,23° E). Vérifier le site dans l'ASIAIR. »
- Journal moteur : `asiair_site_mismatch | offset_min=… lon_monture=… lon_site=…` en
  WARNING à l'apparition, `asiair_site_ok` en INFO à la disparition.
- Lecture seule : rien n'est écrit vers l'ASIAIR. Le suivi ne change pas (la coupole
  attend déjà le côté du pied réel).

## Hors périmètre

Alerte hors suivi (service `asiair_monitor`), détection de la latitude, correction du
biais +82 s du méridien affiché (« Plus tard »).
