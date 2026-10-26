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
- **Réf.** : specs `2026-10-21-bascule-coupole-signal-asiair.md`, `2026-10-23-monture-retournee-en-avance.md`.

### Surveillance ASIAIR permanente (`asiair_monitor`)
- **Ouvert le** 23/10/2026, livré en 6.25.0.
- **État** : l'OTA 6.24.2 → 6.25 a été jouée par l'ancien script, le service était
  « absent » le 23/10. Deux connexions simultanées au port 4400 (watcher du suivi et
  service) n'ont posé aucun problème le 23/10.
- **Prochaine étape** : vérifier la présence de `logs/asiair/` dans le prochain zip de Serge.
  Évolution possible : faire lire au watcher l'état publié par le service.
- **Réf.** : spec `2026-10-23-surveillance-asiair-permanente.md`.

### Synchronisation des dépendances pendant l'OTA (`uv sync`)
- **Ouvert le** 23/10/2026, corrigé en 6.26.1 (`uv` cherché dans `~slenk/.local/bin`).
- **Prochaine étape** : la correction n'agit qu'à la mise à jour suivante (c'est l'ancien
  script qui installe la 6.26.1). Vérifier dans `update.log` que l'étape `uv sync` a tourné.

### Calibration au démarrage et au passage manuel
- **Ouvert le** 24/10/2026. 6.26.4 : le premier passage manuel sur le switch 45° vaut
  calibration. 6.26.5 : le balayage `boot_calibration.fallback_sweep_deg` passe de 7 à 4
  dans le gabarit.
- **Prochaine étape** : Serge saisit 4 sur la page Configuration (le Pi est à 8). Vérifier
  `boot_calibration | status=ok` dans les logs.

### Fermeture du cimier : relance et fin de nuit
- **Ouvert le** 11/10/2026. 6.21.0 : relance de la fermeture automatique
  (`close_retry_interval_minutes`). 6.21.2 : fermeture de fin de nuit différée jusqu'à
  l'arrivée à 45°, droits du fichier de commande cimier. 6.24.1 : une seule fermeture par
  matin, pas de rejeu de la commande au démarrage.
- **Prochaine étape** : chercher `automation_close_*` et `cycle_end` dans les nuits à
  venir. Limite connue : la relance est oubliée si `cimier_service` redémarre.

### Revue critique du 15/10 (6.21.3 → 6.21.7)
- **État** : tout est livré : suivi en UTC (changement d'heure du 25/10), STOP pendant un
  GOTO, offset encodeur borné à 5°, GOTO raté visible, resynchronisation série et
  accélération bornée (firmware flashé sur le Pico le 16/10, confirmé par JP).
- **Prochaine étape** : point avec JP le 25/10 sur la nuit du 24 au 25/10 (changement
  d'heure). Il faut une session qui traverse 3 h → 2 h en suivi actif, selon la météo :
  vérifier dans la chronologie que les corrections continuent sans trou d'une heure et
  que l'azimut reste cohérent. Si la nuit n'est pas exploitable, ce point reste ouvert
  (le prochain changement d'heure est en mars).

### Automatisation du cimier (modes semi et full)
- **État** : code complet depuis la 6.3 (scheduler astropy, modes `manual` / `semi` /
  `full`). Serge tourne en `semi` : la fermeture de fin de nuit a déjà fonctionné. Le mode
  `full` (ouverture au crépuscule) n'a jamais été validé.
- **Prochaine étape** : une nuit en `full` quand Serge le voudra.

### Journal de nuit dans `logs/nuits/`
- **Ouvert le** 24/10/2026, livré en 6.26.12 (le journal pluie/décisions/cycles cimier
  s'écrit dans `logs/nuits/AAAA-MM-JJ.jsonl`, donc dans le zip de `logs/` ; au démarrage,
  `cimier_service` y déplace les anciens `data/nights/*.jsonl`, sans écraser).
- **État** : migration essayée en dev (7 journaux déplacés, page Session les voit,
  second passage sans effet). JP demande à Serge de mettre à jour en 6.26.12 le soir du
  24/10, avant de démarrer la session.
- **Prochaine étape** : dans le zip de la nuit du 24/10, vérifier : `update.log` montre
  6.26.12 ; `logs/nuits/` présent avec la nuit du 24 et les nuits antérieures déplacées ;
  la synthèse de `chronologie_nuit.py` n'affiche plus « Pas de journal de nuit ». Si
  `logs/nuits/` manque : chercher `night_journal_event=move_failed` dans
  `logs/cimier/cimier_service.log` (droits sur `logs/` ?).
- **Réf.** : spec `docs/superpowers/specs/2026-10-24-journal-nuit-dans-logs.md`, commit 2261805.

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

## En attente d'un événement

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
- **Reste à valider** : détection sous vraie pluie (et pluie fine), aucune fausse
  alerte par rosée sans chauffage, puis clore.

## Plus tard

- **Sortie Tailwind compilée en retard sur les gabarits** (`tailwind-output.css`, date du
  03/05) : des classes écrites dans les gabarits n'y sont pas (`sr-only`,
  `border-accent-red`, `opacity-50`, `text-white`, `h-24`…), donc sans effet.
  Recompiler (`scripts/build_css.sh`) change le rendu à plusieurs endroits : à faire avec
  captures avant/après.
- **Angle horaire décalé de +82 s** (`convertir_j2000_vers_jnow` passe par CIRS, alors que
  l'angle horaire attend TETE) : le méridien affiché est environ 82 s trop tôt et
  l'azimut décalé de 0,2 à 0,35°. Corriger retarde d'autant la bascule de la coupole ;
  la règle 6.26 en était le préalable. Décision JP en attente.
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
