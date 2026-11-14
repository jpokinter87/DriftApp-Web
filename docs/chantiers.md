# Chantiers DriftApp

Registre unique des chantiers ouverts, tenu par le skill `/chantiers`. Un chantier fini
sort du registre : son histoire est dans `CHANGELOG.md`, les specs et plans
(`docs/superpowers/`) et git. Dates au format JJ/MM/AAAA, versions = `pyproject.toml`.

## À valider sur le terrain

Code livré et poussé, jamais vu fonctionner sur le Pi (ou une partie seulement).

### Bascule de la coupole sur le côté du pied ASIAIR
- **Ouvert le** 21/10/2026. Livré en 6.24.0 (monture en retard : la coupole attend le
  feu vert de l'ASIAIR) et en 6.26.0 (monture retournée en avance : cible = abaque au
  méridien DriftApp + 30 s, tenue jusqu'au transit).
- **État** : la règle 6.24 a fonctionné le 23/10 à 23:17 (attente de 72 s, arrivée en
  même temps que la monture). Le chemin 6.26 « monture en avance » n'a jamais été
  exercé (aucune ligne `dome_flip_early_*`).
- **Prochaine étape** : à chaque nuit avec retournement, chercher `dome_flip_*` dans la
  chronologie (`/analyse-nuit`). Le méridien DriftApp tombe environ 55 s avant celui de
  l'ASIAIR.
- **En cours** : à partir du 26/10/2026, Serge profite de la pleine lune (pas de photo
  possible) pour enchaîner des passages au méridien. Les zips de ces nuits serviront à
  juger l'algorithme de bascule : retard entre la coupole et la monture à chaque passage,
  cas `dome_flip_early_*` éventuels, décalage DriftApp/ASIAIR (55 s, à rapprocher de
  l'angle horaire décalé de +82 s noté dans « Plus tard »).
- **Nuit du 26/10** : un seul passage (cible ASIAIR à 80° de hauteur). La règle 6.24 a
  encore fonctionné (`dome_flip_wait_end reason=pierside waited_s=66` à 19:36:33). Mais
  la bascule s'est faite en deux temps, −97,3° puis −38,4° : l'abaque interpolait entre
  les colonnes 180° et 182°, de part et d'autre du saut. Corrigé en 6.28.5 : passé 180°,
  la branche d'après est prise.
- **Nuit du 27/10** (NGC 7354, Déc +61°, 72,6° de hauteur) : 6.28.5 **validé**, une seule
  ligne `meridian_transit delta=+83.2` (313,4° → 36,6°). Règle 6.24 OK une 3e fois :
  `dome_flip_wait_start` 20:54:51, retournement ASIAIR 21:07:51, côté du pied changé
  21:08:04 (`dome_flip_wait_end reason=pierside waited_s=793`), coupole arrivée 21:09:00
  (`resync` écart +0,4°), monture de nouveau en suivi 21:09:09. Attente longue due au
  site faux de la monture (voir « Alerte méridien de l'ASIAIR décalé »).
- **Nuits du 31/10 et du 2/11** (zip `logs/terrain/2026-11-02.zip`) : règle 6.24 OK deux
  fois de plus, attentes revenues à la normale : `dome_flip_wait_end reason=pierside
  waited_s=56` le 31/10 à 22:19:30, `waited_s=36` le 3/11 à 02:50:40, puis
  `meridian_transit delta=+62.8` (336,0° → 38,8°) en un seul mouvement et `resync` écart
  +0,1°. Toujours aucun `dome_flip_early_*`.
- **Réf.** : specs `2026-10-21-bascule-coupole-signal-asiair.md`, `2026-10-23-monture-retournee-en-avance.md`.

### Cimier bloqué : arrêt anticipé du moteur (6.31.4)
- **Ouvert le** 07/11/2026. Nuit du 06/11 (zip `logs/terrain/2026-11-06.zip`), 4 °C,
  humide : 9 fermetures manuelles (05:54 → 06:05) puis 27 relances auto (06:41 →
  08:51) en `cycle_timeout`. `open_switch=true` sur tout le cycle : le cimier n'a jamais
  quitté la butée haute, moteur 26 s « à vide » (Serge : aucun claquement des rouages).
  Relance n° 27 réussie à 08:56:35 (butée libérée en < 1 s, course de 22 s) une fois
  réchauffé. Hypothèse mécanique : transmission qui patine (accouplement humide/gelé),
  pas un blocage dur. La relance de fermeture (6.21.0 → 6.24.1) est **validée** par
  cette nuit (`automation_close_confirmed retries=27`) ; limite connue : la relance est
  oubliée si `cimier_service` redémarre.
- **6.31.4** : butée de départ encore enfoncée après `cimier.departure_timeout_s` (5 s ;
  terrain : libérée en 0,05 à 0,61 s sur tous les cycles normaux d'oct.–nov.) → moteur et
  24 V coupés, `poll_stalled`, `cycle_end result=stalled error=cimier_stalled`, dashboard
  « Bloqué : le moteur tourne mais le cimier n'a pas quitté sa butée ». Rythme des
  relances inchangé (choix JP). Dev : `curl "http://127.0.0.1:8001/dev/stall?on=1"`.
- **Prochaine étape** : à la prochaine nuit froide, chercher `poll_stalled` et
  `result=stalled` ; vérifier qu'aucun cycle normal n'est coupé à tort (aucun
  `poll_stalled` suivi d'une course réussie à la relance suivante en < 1 s).
  Inspection de la transmission (pignon, accouplement, vis sur l'axe) demandée à Serge le
  07/11 avec l'annonce de la 6.31.5 : photo attendue.

### Revue critique du 15/10 (6.21.3 → 6.21.7)
- **État** : tout est livré : suivi en UTC (changement d'heure du 25/10), STOP pendant un
  GOTO, offset encodeur borné à 5°, GOTO raté visible, resynchronisation série et
  accélération bornée (firmware flashé sur le Pico le 16/10, confirmé par JP).
- **Changement d'heure du 25/10** : pas vérifié sur le terrain, il pleuvait (JP, 27/10 ;
  aucun suivi dans les logs de la nuit du 24 au 25). Les deux sens sont couverts par
  `tests/test_tracking_dst.py` (horloge fictive) : recul du 25/10/2026 sur M31, avance
  du 28/03/2027 sur M13 (une heure d'erreur y décalerait l'azimut de 14,6°).
- **Prochaine étape** : nuit du 27 au 28/03/2027 (2 h → 3 h), si Serge suit un objet à
  ce moment-là, selon la météo : vérifier dans la chronologie que les corrections
  continuent sans trou et que l'azimut reste cohérent.

### Automatisation du cimier (modes semi et full)
- **État** : code complet depuis la 6.3 (scheduler astropy, modes `manual` / `semi` /
  `full`). Serge tourne en `semi` : la fermeture de fin de nuit a déjà fonctionné. Le mode
  `full` (ouverture au crépuscule) n'a jamais été validé.
- **Prochaine étape** : une nuit en `full` quand Serge le voudra.

### Interface 6.27.0 : mode nuit rouge, STOP dans la fenêtre GOTO
- **Ouvert le** 25/10/2026, livré en 6.27.0 (sélecteur Auto/Nuit/Jour par écran, nuit
  sous −6° de hauteur solaire ; tout en rouge pur la nuit, filtre `feColorMatrix` sur
  `<html>` ; bouton STOP dans la modale GOTO ; cibles tactiles 44 px ; dépendances
  locales dans `web/static/vendor/`).
- **État** : vérifié seulement en dev, dans Chrome headless 1280×720 (aucun pixel
  vert ou bleu en nuit sur les 4 pages, calcul solaire JS à 0,007° d'astropy, Échap et
  Tab dans les modales). Jamais vu dans Firefox ni sur le Pi. Annonce envoyée à Serge
  le 25/10.
- **Prochaine étape** : retour de Serge ou zip de nuit. À vérifier : bascule en rouge le
  soir (heure), rien de blanc, vert ou bleu dans Firefox kiosque, fluidité (le filtre
  plein écran coûte au GPU du Pi : s'il y a des saccades, appliquer le filtre aux seuls
  canvas et SVG), STOP visible et efficace pendant un vrai GOTO initial, boutons au doigt.
- **Réf.** : spec `docs/superpowers/specs/2026-10-25-mode-nuit-rouge.md`, `DESIGN.md`,
  `PRODUCT.md`, commits c929bcf → 4ccec06.

### Thème de jour « carnet d'observation » (6.28.x)
- **Ouvert le** 25/10/2026, livré en 6.28.0 (sélecteur Auto · Nuit · Crép. · Jour ; Jour =
  thème clair papier/graphite, Crép. = l'ancien bois sombre) ; seuils Auto en 6.28.1 :
  Jour au-dessus de +6°, Crépuscule jusqu'à −6°, Nuit en dessous.
- **État** : vérifié seulement en dev, Chrome headless 1280×720 : Crépuscule identique à
  6.27.0 (styles calculés des 4 pages, boussole au pixel), Nuit sans pixel vert ni bleu,
  textes du Jour ≥ 4,5:1, bascule à chaud de la boussole et des graphiques Session.
  Jamais vu dans Firefox ni sur le Pi. Annonce WhatsApp à Serge prête le 25/10.
- **Prochaine étape** : retour de Serge. À vérifier : écran clair lisible en plein jour
  dans la coupole (rien de pâle) ; en Auto, Jour → Crépuscule vers 17 h 00 et
  Crépuscule → Nuit vers 18 h 10, le matin Nuit → Crépuscule vers 6 h 40 et
  Crépuscule → Jour vers 7 h 50 (calcul pour le 26/10 à Ubik) ; thème clair sur le
  portable ; aucune zone restée sombre en Jour (couleur écrite en dur oubliée → la
  surcharger dans `theme.css`).
- **Réf.** : spec `docs/superpowers/specs/2026-10-25-theme-jour-carnet.md`, plan du même
  nom, prévisualisation https://claude.ai/artifact/GAVfYwm3wRuTDZpGgh7Az8, commits
  0847dd4 → 7c52387, puis 6.28.1.

### Services démarrés à l'heure juste (`time-sync.target`)
- **Ouvert le** 27/10/2026, livré en 6.28.6 (les 5 services attendent la mise à l'heure
  NTP, au plus 90 s, via `systemd-time-wait-sync` et le délai
  `setup/time-wait-sync-timeout.conf`).
- **État** : nuit du 26/10, Pi éteint en coupant le courant (octets nuls en fin de logs),
  redémarré à l'heure du dernier enregistrement puis recalé par NTP environ 25 s après le
  démarrage des services (saut de +89,6 min le soir, d'où `encoder_stale
  age_ms=5376579` à 18:15:55 ; de 08:34 à 11:57 le matin). L'ancien script installe la
  6.28.6 : les unités sont copiées, mais le délai et l'activation n'arrivent qu'à la mise
  à jour suivante (sans eux, `time-sync.target` passe tout de suite, comportement
  inchangé). Vérifié en dev : `sysinit.target` a `DefaultDependencies=no`, l'attente ne
  retarde donc que nos services ; sans le délai, `TimeoutStartSec=infinity`.
- **27/10** : mise à jour 6.28.4 → 6.29.0 à 14:31 par l'ancien script, donc pas de ligne
  « Attente de l'heure » dans `update.log` (attendu). Saut d'heure encore vu au
  redémarrage : services lancés à 14:38 (horloge restaurée), `encoder_stale
  age_ms=16464186` à 19:12:54 (+4 h 34 min). Le délai arrivera à la prochaine mise à jour.
- **29/10** : mise à jour en 6.30.0, `update.log` montre « Attente de l'heure : délai
  installé » à 20:07:49. Possible effet de bord : voir « Navigateur au démarrage du Pi ».
- **Prochaine étape** : vérifier sur un zip qu'il n'y a plus de saut d'heure dans les logs
  des services au démarrage, et aucun WARN timesyncd. Au démarrage
  suivant, plus de saut d'heure dans les logs des services. Modèle du Pi demandé à Serge
  le 27/10 : si c'est un Pi 5, une pile sur le connecteur BAT garde l'heure même sans
  internet. **13/11** : c'est un Pi 5, et Serge a posé la pile RTC officielle (charge à
  activer par `dtparam=rtc_bbat_vchg=3000000`). Le saut d'heure au démarrage devrait
  disparaître ; à confirmer sur un zip.

### Bouton « Éteindre » du dashboard
- **Ouvert le** 27/10/2026, livré en 6.29.0 (extinction propre du Pi depuis l'en-tête du
  dashboard, refusée tant que le suivi tourne ou que le cimier est ouvert).
- **État** : vérifié en dev seulement. Les fenêtres de confirmation, de refus et
  d'« Arrêt en cours » s'affichent en Crépuscule, Jour et Nuit, et Échap ferme la fenêtre.
  En dev, la confirmation échoue proprement : pas de sudoers, et le script refuse hors
  Raspberry Pi. L'OTA copie le sudoers depuis le dépôt tiré : le bouton marche dès la
  mise à jour en 6.29.0.
- **27/10, extinction validée** : deux essais (14:31:58 et 14:37:40 dans `shutdown.log`),
  services arrêtés par signal 15 proprement, logs Django terminés sans octets nuls.
- **Prochaine étape** : essayer pendant un suivi ou cimier ouvert : la fenêtre doit
  refuser. Puis clore.
- **Réf.** : spec et plan `2026-10-27-bouton-eteindre-le-pi.md`.

### Alerte site ASIAIR sur le dashboard
- **Ouvert le** 27/10/2026, livré en 6.30.0 (pendant le suivi, temps sidéral de la monture
  comparé à celui du site de `config.json` ; au-delà de 2 min, ligne rouge dans « Suivi
  actif » avec la longitude que croit avoir la monture).
- **État** : vérifié en dev seulement, faux ASIAIR à la longitude du 27/10 : alerte
  « −12,2 min, ≈ 2,17° E » en Nuit, Crépuscule et Jour, `asiair_site_mismatch` écrit une
  fois. Ne marche qu'avec `asiair.dome_flip_on_pierside` (le watcher du pied). Latitude
  fausse seule invisible (l'ASIAIR ne donne pas son site).
- **Nuit du 2/11 (site correct)** : aucun `asiair_site_mismatch` sur quatre suivis, la
  moitié « pas de fausse alerte » est validée.
- **Prochaine étape** : reste le cas site faux. Si le site du téléphone revient dans
  l'ASIAIR → ligne rouge dès le début du suivi, puis clore.
- **Réf.** : spec et plan `2026-10-27-alerte-site-asiair.md`.

### Corrections 6.30.1 (nuits du 31/10 et du 2/11)
- **Ouvert le** 03/11/2026, livré en 6.30.1 (commit `1b31a2a`).
- **Import ASIAIR refusé pendant un GOTO** : le 2/11 à 19:39:04, lecture en plein GOTO
  (début 19:38:28, `ScopeGoto complete` 19:39:21) → RA 17h44 au lieu de 21h03, DEC déjà
  arrivée, coupole au mauvais azimut. `lire_coordonnees` demande aussi
  `scope_get_track_state` (False pendant tout le GOTO) et refuse.
- **Nom d'objet périmé** : le 2/11 à 23:03, IC 391 importé avec les bonnes coordonnées
  mais le nom de la cible précédente (« ASIAIR RA 4h09m23.6s… »). L'ancien nom resté dans
  le champ après l'arrêt passait pour un nom tapé (`state.lastObjectName`, `dashboard.js`).
- **Parking pluie unique** : le 31/10 de 08:03 à 08:37, pluie armée et Shelly Uni+
  injoignable (répéteur tombé) → cimier « unknown », 221 GOTO 45° (un toutes les 5 s)
  qui écrasaient les GOTO manuels de Serge, jusqu'au désarmement. Désormais un seul
  parking par épisode (clos au retour au sec, pas par un trou de lecture du capteur),
  ensuite seule la fermeture du cimier est relancée.
- **Prochaine étape** : import ASIAIR cliqué pendant un GOTO → message « la monture ne
  suit pas l'objet » dans les logs du dashboard ; deux objets ASIAIR enchaînés → noms
  distincts dans `ipc_command | type=tracking_start` ; à la prochaine pluie armée avec
  Uni+ injoignable, un seul `session_close reason=rain` par épisode. Puis clore.

### Navigateur au démarrage du Pi : « Try Again » systématique
- **Ouvert le** 03/11/2026, livré en 6.30.2 (`scripts/kiosk.sh` attend Django 5 min au
  plus avant d'ouvrir Firefox ; `scripts/install_kiosk.sh` le branche au démarrage).
- **État** : Serge (3/11) doit cliquer « Try Again » à chaque démarrage. Cause : depuis la
  6.30.0 (29/10), les services attendent l'heure NTP jusqu'à 90 s ; le lanceur de juin
  (`~/kiosk.sh` d'après `rasp_kiosk.txt`, relu le 17/10) n'attendait Django que 60 s. JP
  (4/11) : `~/kiosk.sh` n'existe plus sur le Pi, ni de copie sur la machine de dev ; le
  plein écran marche pourtant, par un lanceur inconnu. `install_kiosk.sh` le cherche dans
  `~/.config/autostart/*.desktop`, `~/.config/labwc/autostart`, `~/.config/wayfire.ini` et
  `~/.config/lxsession/LXDE-pi/autostart` et y remplace la commande firefox/chromium.
- **Prochaine étape** : Serge met à jour en 6.30.2, tape `cd ~/DriftApp` puis
  `./scripts/install_kiosk.sh`, photographie la sortie, redémarre : la page doit s'ouvrir
  seule. Si le script dit « Aucun ancien lancement trouvé » et que deux fenêtres s'ouvrent
  ou que l'erreur revient, le lanceur est ailleurs (service utilisateur systemd,
  `/etc/xdg/…`) : lui demander `grep -rl firefox ~/.config /etc/xdg 2>/dev/null`.

## En attente d'un événement

### Capteur 45° : remplacement du microswitch par un capteur optique ou inductif
- **Ouvert le** 04/11/2026. Serge veut remplacer le microswitch SS-5GL (GPIO27, pull-up,
  1 au repos, front 1→0 = 45°, `ems22d_calibrated.py`) par un Omron E3Z-D61 NPN
  (réflexion directe, 12-24 V). Aucun changement de code si sortie NPN en mode L-ON.
- **Conseillé (message du 04/11)** : alim 12/24 V permanente, 0 V commun avec le Pi,
  sortie vers GPIO27 via diode 1N5819 (cathode côté capteur) + 10 kΩ vers 3,3 V ; viser
  hors passage, cible étroite, sensibilité réduite (risque : fausse détection = faux
  recalage à 45°). Alternative proposée : inductif LJ12A3-4-Z/BX.
- **05/11, question 1N4148** : déconseillée (Vf ≈ 0,6 V, niveau bas lu à la limite du
  seuil 0,8 V du Pi) ; 1N5819 à commander, ou pas de diode si E3Z-D61 NPN + 10 kΩ vers
  3,3 V. Serge doit renvoyer GPIO27 au multimètre (< 0,6 V cible devant, ≈ 3,3 V sans)
  ou `pinctrl get 27` (lo / hi). 1N5819 commandée par Serge ; on attend la réception,
  le montage et les premiers tests. Schéma de montage remis :
  `docs/schema_capteur_45_E3Z-D61.pdf` (généré par `scripts/diagnostics/gen_schema_capteur_45_pdf.py`).
- **11/11, questions de Serge (réponses données)** : le pull-up interne du Pi est déjà
  activé par le logiciel (GPIO27 ≈ 3,3 V au repos, microswitch actuel compris). La 10 kΩ
  externe n'est pas indispensable : elle durcit la ligne contre le pull-up interne faible
  (≈ 50 kΩ), car câble long près du moteur = parasites (faux recalage), courant de fuite
  de la sortie NPN et de la diode, ligne tenue dès le boot avant `ems22d`. Courant cible
  devant ≈ 0,33 mA. **Compatibilité** : résistance + diode posées, le microswitch se
  branche entre la cathode de la 1N5819 (côté fil noir) et la masse du Pi, sans 12 V ;
  attendu broche 13 / broche 14 : relâché ≈ 3,3 V, appuyé ≈ 0,2-0,3 V. Puis passage au
  capteur : noir à la place du microswitch, marron +12 V, bleu 0 V **relié à la masse du
  Pi** (sinon GPIO27 ne descend jamais), sélecteur sur L (L-ON).
- **Prochaine étape** : après la pose, contrôle des niveaux ci-dessus (d'abord avec le
  microswitch derrière la diode, puis avec le capteur), puis zip des logs avec des franchissements dans les deux
  sens ; lire `recalage | source=switch avant=… ecart=…`. Si l'écart dépend du sens
  au-delà de 0,3°, recaler au milieu de la cible (démon encodeur). Mettre à jour le PDF de
  description technique de la coupole.

### Pi bloqué LED rouge au démarrage (13/11)
- **Ouvert le** 13/11/2026. Serge vient de poser une batterie de sauvegarde pour le Pi et un
  convertisseur 12 V pour la cellule E3Z-D61 (la diode 1N5819 n'est pas encore arrivée).
  À 16h27 puis à 17h37, après extinction et rallumage : LED rouge, le Pi ne démarre pas. Il
  repart après débranchement de tous les fils. Aucun log, le Pi n'ayant pas démarré.
- **Réponses de Serge (13/11)** : c'est un **Pi 5**. La « batterie » est la pile RTC
  officielle (rechargeable) sur le connecteur BAT : elle ne garde que l'heure. Elle ne
  peut pas maintenir le Pi en veille, donc la piste batterie est écartée. Le convertisseur
  12 V est alimenté par le 36 V, il est donc hors de cause. LED rouge fixe au démarrage
  raté comme après extinction ; elle reste rouge « des plombes » après extinction (veille
  normale du Pi 5 tant que son alimentation est branchée). Peu probable : le fil moteur
  arraché (DM860T sur 36 V séparé). Conseillé : pas de fil noir de la cellule sur GPIO27
  avant la diode. Charge de la pile conseillée : `dtparam=rtc_bbat_vchg=3000000` dans
  `/boot/firmware/config.txt` (sans rapport avec la panne).
- **Suspect n°1 (13/11, 3e échange)** : alimentation officielle 27 W. Seules nouveautés :
  la pile RTC et un **convertisseur DC-DC buck-boost** ajouté sur l'alimentation 3,3 V de
  l'encodeur EMS22A, avec une 2e sortie prévue pour le pull-up de GPIO27 (en l'air pour
  l'instant). Son entrée est inconnue. Si elle est prise sur le Pi : appel de courant à la
  mise sous tension, le PMIC du Pi 5 reste en veille. Si elle vient d'une autre
  alimentation : l'encodeur reste alimenté Pi éteint et renvoie du courant dans le Pi par
  ses broches. Le convertisseur est inutile : encodeur sur le 3,3 V du Pi comme avant, et
  10 kΩ sur la broche 1 (schéma `docs/schema_capteur_45_E3Z-D61.pdf`).
- **Prochaine étape** : Serge retire le convertisseur, remet l'encodeur comme avant, et
  fait 4-5 cycles extinction/allumage : tous doivent démarrer. **14/11** : Serge retire le
  convertisseur. Montage conseillé : encodeur sur la broche 1 (3,3 V Pi), 10 kΩ entre la
  broche 17 (3,3 V Pi) et la broche 13 ; jamais de 3,3 V extérieur sur ce qui touche une
  broche du Pi.

### Alerte « méridien de l'ASIAIR décalé » (site ou heure de la monture faux)
- **Ouvert le** 27/10/2026. Nuit du 27/10, NGC 7354 (Céphée, Déc +61°, culmine au nord
  vers 73°) : l'ASIAIR annonce le retournement à 21h07, DriftApp le méridien à 20h54
  (astropy : 20h55m40s au site). Réglage ASIAIR « Flip Timing after Meridian » = 0 (JP).
  Les nuits précédentes, l'écart n'était que d'environ 55 s (voir « Bascule de la
  coupole ») : le décalage est nouveau.
- **Cause confirmée** (capture ASIAIR de Serge, 27/10 à 21:35, Mount → Mount information) :
  la monture a pour site **E 02°10'02", N 48°48'21"**, la position GPS du téléphone de
  l'utilisateur en région parisienne, et non celle de l'observatoire. L'appli ASIAIR
  pousse la position du téléphone vers la monture (section « Location info », bouton
  « Sync to Mount »). Écart de longitude 3,06° × 4 min = 12,25 min : 20h55m40s + 12 min
  = 21h07, l'heure annoncée. La latitude est aussi fausse de 4,7° (48,8° au lieu de
  44,15°). Tout usage à distance de l'observatoire expose au même piège.
- **Exclu** : les coordonnées de l'objet (DriftApp lit l'AD/Déc de la monture via
  `/api/tracking/asiair/`, même AD des deux côtés) ; `data/config.json` (lu par DriftApp
  seul, l'ASIAIR a son propre site). Le méridien ASIAIR = AD monture − `sidereal_time`
  de `scope_get_info` : seul le temps sidéral de la monture peut porter l'écart.
- **Chiffré sur le zip du 27/10** : à 22:15:36, temps sidéral de la monture 23h49m10s
  (`asiair_monitor.log`) ; astropy donne 23h49m15s à la longitude E 2°10'02" et 0h01m30s
  au site : la monture retarde de **12 min 20 s**, à 5 s près celui de Paris. Même
  écart dans les `Align Sync lst=` d'INDI. Retournement ASIAIR à 21:07:51, coupole
  basculée 21:09:00 après 793 s d'attente (sous `max_wait_minutes`). Seuil d'alerte :
  1 min laisse une marge large.
- **Prochaine étape** : côté ASIAIR, consignes envoyées à Serge le 27/10 (voir
  ci-dessous) ; à confirmer sur le terrain que la localisation refusée fait bien
  demander une saisie manuelle, sans retomber sur la dernière position connue (la capture
  de 21:35 montrait encore le site du téléphone, consignes envoyées après).
- **Recherche du 27/10 (forum ZWO, rien d'officiel)** : aucun réglage ASIAIR ne verrouille
  le site ni ne coupe l'envoi de la position du téléphone. Le site circule de l'appli
  vers la monture seulement (« Sync to Mount », et d'après un relevé USB aussi
  automatiquement à la connexion). La saisie manuelle existe (depuis 1.0.8) mais ne
  survit pas à un redémarrage selon plusieurs utilisateurs. Cas identique sans réponse de
  ZWO : observatoire distant au Texas piloté depuis l'Utah
  (bbs.zwoastro.com/d/22077). Parade retenue : retirer la permission de localisation à
  l'appli sur le téléphone de pilotage, saisir le site à la main, contrôler Mount →
  Mount information **en début de nuit avant tout plate-solve**, ne jamais toucher
  « Sync to Mount » à distance. L'alerte DriftApp (ci-dessous) est donc le seul garde-fou
  automatique possible. Le paquet ASIAIR décompilé le 20/10 n'est plus dans le dépôt :
  pas de vérification côté firmware.
- **31/10 et 2/11** : attentes au méridien de 56 s et 36 s (contre 793 s le 27/10) : le
  site de la monture est redevenu juste, la parade tient pour l'instant.
- **Code** : alerte livrée en 6.30.0, voir « Alerte site ASIAIR sur le dashboard » dans
  « À valider ». Le biais +82 s ne joue pas : il touche le méridien affiché, pas le
  temps sidéral comparé.

### Remplacement du capteur de pluie par un Kemo M152K
- **Ouvert le** 24/10/2026. L'actuel MH-RD s'oxyde, rate la pluie fine et a vu
  « wet » toute la soirée claire du 23/10 (3 fermetures à tort). Le M152K a été commandé
  par Serge ; il est capacitif et chauffé, et se branche en contact sur l'entrée du
  Shelly Plus Uni sans changer de code (contact fermé = pluie, `invert=false`).
- **Posé le 26/10/2026** par Serge. La résistance chauffante est retirée (le boîtier du
  M152K est moulé dans la résine, elle n'y loge pas). Le capteur est alimenté par le
  Shelly 1 .78 (ex-chauffage) ; le Shelly Uni+ .87 reste sous tension. Serge a
  remis l'auto_off de 5 min sur le .78. Essai positif : une goutte → relais + LED.
- **Conséquence** : **garder** `rain_heater_switch` et le keepalive (le plan de retrait
  est abandonné). Le .78 alimente le capteur : `cimier_service` arrêté depuis plus
  de 5 min → capteur hors tension → lu « sec ». 6.28.3 : la pastille dit
  « Capteur de pluie : ON » au lieu de « Chauffage : ON » (clés de config inchangées).
- **31/10 – 3/11 : « wet » au démarrage du Pi, jamais Pi allumé.** Les matins du 31/10
  (`rain_transition from=unreachable to=wet` à 08:03:38, sec à 08:45:04) et du 1/11
  (08:17:02), le Pi avait été éteint la nuit (`shutdown.log` : 30/10 18:58, 1/11 00:44).
  Le .78 coupe alors le capteur (auto_off 5 min) : sans courant, pas de chauffage, le
  capteur se couvre de rosée et il est mouillé dès qu'il est rallumé. On ne peut pas dater la
  mouillure (capteur hors tension, lu « sec »). Nuit du 2 au 3/11, Pi allumé : sec de
  bout en bout (dernière lecture avant le trou de 10:24). Serge a collé l'ancienne plaque
  chauffante contre le réseau de détection (3/11).
- **Reste à valider** : détection sous vraie pluie (et pluie fine), plus de « wet » au
  démarrage du matin avec la plaque chauffante, puis clore.

## Plus tard

- **Une correction de suivi sur deux ne bouge pas la coupole** (nuit du 27/10 : 52 sur
  106 en `0 iter`) : le seuil de correction est 0,3° (`SINGLE_SPEED_CORRECTION_THRESHOLD_DEG`),
  mais la rotation avec feedback a une tolérance de 0,5° (`tolerance=0.5`,
  `core/tracking/tracking_corrections_mixin.py:350`). Un écart de 0,33 à 0,41° déclenche
  donc une correction qui se déclare réussie sans bouger ; elle est quand même comptée et
  `position_relative` avance. La coupole traîne de 0,3 à 0,8° (capture du 27/10 à 20:43 :
  ENC 314,46°, cible 314,11°). Sans effet sur la photo (fente large), mais les stats de
  corrections sont fausses. Piste : aligner la tolérance sous le seuil. Décision JP en
  attente.
- **Sortie Tailwind compilée en retard sur les gabarits** (`tailwind-output.css`, date du
  03/05) : des classes écrites dans les gabarits n'y sont pas (`sr-only`,
  `border-accent-red`, `opacity-50`, `text-white`, `h-24`…), donc sans effet.
  Recompiler (`scripts/build_css.sh`) change le rendu à plusieurs endroits : à faire avec
  captures avant/après.
- **Angle horaire décalé de +82 s** (`convertir_j2000_vers_jnow` passe par CIRS, alors que
  l'angle horaire attend TETE) : le méridien affiché est environ 82 s trop tôt et
  l'azimut décalé de 0,2 à 0,35°. Corriger retarde d'autant la bascule de la coupole ;
  la règle 6.26 en était le préalable. Décision JP en attente.
- **Ligne 75° de l'abaque** : le saut du retournement y tombe entre 165° et 180° (valeur
  à 180° déjà « après », 124°) au lieu de 180°–182° comme aux autres hauteurs. Entre 75°
  et 80° de hauteur, peu avant le méridien, la cible mélange donc encore les deux
  branches. Question posée à Serge le 27/10 : remesurer, monture pas encore
  retournée, ou à défaut mettre ~230° (entre 226° à 72,5° et 235° à 77,5°).
- **Artefact de l'abaque vers 40° de hauteur** (passage inférieur, objets proches du pôle) :
  saut d'environ 17° entre les lignes 30° et 45°. Tout correctif doit distinguer passage
  inférieur et passage supérieur (le saut nord au-dessus de 53° est voulu).
- **Cimier, résidus de la revue du 11/06** : erreur de preflight écrasée par `idle` au tick
  suivant ; factoriser le HTTP Shelly (3 copies) puis ajouter des relances ; lecture des
  deux butées non atomique ; mineurs (modales countdown dupliquées, `sleep` bloquant dans
  `ParkingSessionView`, `boot_poll_timeout_s` legacy, XSS latent `renderConfigDiffPanel`).
- **Cimier « INCONNU » dans l'UI après un redémarrage du service**, jusqu'au premier cycle
  (le scheduler et la pluie relisent déjà les butées) : rafraîchir les butées au repos.
- **Traçabilité des commandes Django** (incident GOTO 45° du 24/04) : middleware d'audit
  des POST `/api/hardware/*` et `/api/tracking/*`, logs Django doublés vers journald.
- **Calibration testable en dev** : le simulateur saute la routine (`status=simulated`) ;
  ajouter un scénario réaliste (`running` puis `ok` / `degraded`).
- **Filtre anti-saut de 30° d'`ems22d`** pouvant se figer (revue du 15/10) : jamais vu sur le
  terrain, décision JP en attente.

## Écartés (ne pas re-proposer)

- Mode dégradé sans encodeur (JP, 21/10/2026).
- Fenêtre fixe de ±10 min autour du méridien pour interroger l'ASIAIR (21/10) : la règle
  sur le côté du pied la couvre déjà.
- Modèle géométrique de la coupole façon NINA et remesure de l'abaque (17/10) : les
  abaques sont bonnes, seul le moment du retournement posait problème.
- Inclinomètre sur l'axe AD (retiré en 6.26.1, remplacé par le côté du pied ASIAIR).
- Facteurs d'échelle séparés par sens de rotation (24/10) : la correction finale suffit.
