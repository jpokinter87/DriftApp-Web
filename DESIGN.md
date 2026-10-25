---
name: DriftApp
description: Poste de pilotage nocturne de la coupole de l'Observatoire Ubik
colors:
  night-hearth: "#1a1612"
  walnut-panel: "#241e18"
  smoked-oak-input: "#2d261e"
  oak-surface: "#342c22"
  oak-hover: "#3d3428"
  bronze-seam: "#4a3d2e"
  bronze-seam-light: "#5a4d3e"
  parchment-text: "#e8e4df"
  dusk-taupe: "#a09080"
  ember-ash: "#9e8b77"
  lantern-amber: "#d4a055"
  lantern-amber-light: "#e8b870"
  lantern-amber-dark: "#b08040"
  beacon-green: "#00d26a"
  beacon-green-dim: "#00a855"
  signal-orange: "#ffa502"
  alarm-red: "#ff4757"
  alarm-red-dim: "#cc3a47"
  correction-violet: "#b46cf8"
  status-info-blue: "#3b82f6"
  sky-navy: "#1a1a2e"
  sky-graticule: "#4a6a8a"
  sky-star-blue: "#5a8ab8"
  dome-green: "#4ade80"
typography:
  display:
    fontFamily: "JetBrains Mono, SF Mono, Fira Code, ui-monospace, monospace"
    fontSize: "1.125rem"
    fontWeight: 700
    letterSpacing: "-0.025em"
  headline:
    fontFamily: "JetBrains Mono, SF Mono, Fira Code, ui-monospace, monospace"
    fontSize: "1rem"
    fontWeight: 700
    letterSpacing: "0.05em"
  title:
    fontFamily: "JetBrains Mono, SF Mono, ui-monospace, monospace"
    fontSize: "1.5rem"
    fontWeight: 700
  body:
    fontFamily: "IBM Plex Sans, SF Pro Text, system-ui, sans-serif"
    fontSize: "0.875rem"
    fontWeight: 400
    lineHeight: 1.43
  label:
    fontFamily: "JetBrains Mono, SF Mono, ui-monospace, monospace"
    fontSize: "0.65rem"
    fontWeight: 400
    letterSpacing: "0.025em"
  mono:
    fontFamily: "JetBrains Mono, SF Mono, ui-monospace, monospace"
    fontSize: "0.75rem"
    fontWeight: 400
rounded:
  badge: "0.375rem"
  button: "0.5rem"
  panel: "0.625rem"
  modal: "16px"
  full: "9999px"
spacing:
  panel: "1rem"
  section: "1.5rem"
  gap: "0.5rem"
components:
  button-primary:
    backgroundColor: "{colors.lantern-amber}"
    textColor: "{colors.night-hearth}"
    rounded: "{rounded.button}"
    padding: "8px 16px"
  button-primary-hover:
    backgroundColor: "{colors.lantern-amber-light}"
  button-secondary:
    backgroundColor: "{colors.smoked-oak-input}"
    textColor: "{colors.parchment-text}"
    rounded: "{rounded.button}"
    padding: "8px 16px"
  button-secondary-hover:
    backgroundColor: "{colors.oak-hover}"
  button-danger:
    backgroundColor: "{colors.alarm-red}"
    textColor: "#ffffff"
    rounded: "{rounded.button}"
    padding: "8px 16px"
  button-stop:
    textColor: "{colors.alarm-red}"
    rounded: "{rounded.button}"
    padding: "12px 0"
  button-jog:
    backgroundColor: "{colors.smoked-oak-input}"
    textColor: "{colors.parchment-text}"
    rounded: "{rounded.button}"
    padding: "12px 0"
  input-field:
    backgroundColor: "{colors.smoked-oak-input}"
    textColor: "{colors.parchment-text}"
    rounded: "{rounded.button}"
    padding: "8px 12px"
  panel:
    backgroundColor: "{colors.walnut-panel}"
    rounded: "{rounded.panel}"
    padding: "{spacing.panel}"
  info-item:
    backgroundColor: "{colors.smoked-oak-input}"
    rounded: "{rounded.button}"
    padding: "8px"
  badge-amber:
    textColor: "{colors.lantern-amber}"
    rounded: "{rounded.badge}"
    padding: "2px 8px"
  tab-item-active:
    backgroundColor: "{colors.walnut-panel}"
    textColor: "{colors.lantern-amber}"
    rounded: "{rounded.badge}"
    padding: "6px 12px"
---

# Design System: DriftApp

## Overview

**Creative North Star: "La salle de veille"**

DriftApp ressemble à un poste de contrôle de nuit. Les surfaces sont en bois sombre et en bronze. La seule lumière chaude est l'ambre d'une lanterne, et les voyants ne s'allument que lorsqu'ils ont quelque chose à dire. Tout est posé sur un fond brun presque noir, jamais sur du gris neutre ni du bleu d'application. Les panneaux, les champs et les survols sont de simples paliers de ce même bois, chacun un peu plus clair que le précédent. La couleur vive est réservée aux états : vert pour un suivi actif ou un service en marche, orange pour une attente ou un avertissement, rouge pour STOP et l'alarme, ambre pour l'action principale et la marque.

L'écriture est celle d'un instrument. JetBrains Mono sert aux titres, aux boutons, aux valeurs et aux journaux ; IBM Plex Sans ne porte que le texte courant. Les titres de section sont en capitales, avec un dégradé « feu » qui va de l'orange vif à l'ambre. Un motif de constellations très discret tapisse les grands panneaux. La boussole est la seule zone froide : un disque bleu nuit qui figure le ciel au milieu du bois.

L'écran est dense, mais chaque bloc répond à une seule question (où est la coupole, que suit-on, comment reprendre la main, dans quel état est le cimier, que s'est-il passé). Ce sont les halos et les pulsations qui signalent les états vivants, bien plus que la typographie.

**Key Characteristics:**
- Bois chaud presque noir, en couches tonales ; aucun gris froid dans le cadre de l'interface.
- L'ambre de lanterne est l'unique couleur de marque et d'action principale.
- Les couleurs vives sont réservées aux états (vert, orange, rouge) et aux halos.
- Mono partout où il y a une donnée ou une commande ; sans-serif seulement pour le texte courant.
- La boussole bleu nuit est une exception voulue : c'est le ciel.

## Colors

Une palette « foyer » : bruns chauds en paliers, un ambre de lanterne pour la marque et l'action, et des signaux saturés réservés aux états.

### Primary
- **Ambre de lanterne** (`lantern-amber`) : action principale (Ouvrir, Démarrer), logo, contour du focus, onglet actif, badges ambre, texte du statut cimier. Sa variante claire (`lantern-amber-light`) sert au survol, sa variante sombre (`lantern-amber-dark`) aux appuis et aux bords.

### Secondary
- **Vert balise** (`beacon-green`) : suivi actif, service connecté, encodeur calibré, état « SEC ». Il s'accompagne toujours d'un halo vert. Sa variante atténuée (`beacon-green-dim`) sert aux états secondaires.
- **Orange signal** (`signal-orange`) : avertissement, attente, mouvement en cours, données périmées (STALE), bordure de la modale GOTO.
- **Rouge alarme** (`alarm-red`) : STOP, parking, erreur, service indisponible, pluie. `alarm-red-dim` sert au survol du bouton danger.

### Tertiary
- **Violet correction** (`correction-violet`) : uniquement le compteur et le total des corrections de suivi.
- **Bleu info** (`status-info-blue`) : badges d'information, rarement utilisé.

### Neutral
- **Foyer de nuit** (`night-hearth`) : fond de la page, du journal et des onglets ; aussi le texte posé sur l'ambre.
- **Panneau de noyer** (`walnut-panel`) : panneaux, en-tête, cartes de statistiques, onglet actif.
- **Chêne fumé** (`smoked-oak-input`) : champs, boutons secondaires et de JOG, cases d'information.
- **Chêne** (`oak-surface`) et **chêne clair** (`oak-hover`) : surfaces surélevées et survol.
- **Joint de bronze** (`bronze-seam`, `bronze-seam-light`) : bordures, séparateurs, barres de défilement.
- **Parchemin** (`parchment-text`) : texte principal.
- **Taupe crépuscule** (`dusk-taupe`) : texte secondaire, liens de navigation inactifs.
- **Cendre** (`ember-ash`) : libellés en capitales, texte d'attente (placeholder), métadonnées.

### Ciel (exception de la boussole)
Ces couleurs sont dessinées directement dans le canvas de la boussole (`web/static/js/dashboard.js`) et n'apparaissent nulle part ailleurs.
- **Bleu nuit** (`sky-navy`) : fond du disque de la boussole.
- **Graticule** (`sky-graticule`) et **étoile bleue** (`sky-star-blue`) : graduations, repères cardinaux, étoiles.
- **Vert coupole** (`dome-green`) : flèche et cible de la coupole sur la boussole.

### Named Rules
**La règle de la lanterne unique.** L'ambre est la seule couleur de marque. On ne la dilue pas avec une deuxième couleur d'accent décorative ; toute autre couleur vive doit correspondre à un état.

**La règle des signaux.** Le vert, l'orange et le rouge veulent toujours dire, dans cet ordre : actif ou ok, attention, arrêt ou danger. Jamais de décoration.

**La règle du ciel enclos.** Le froid (bleu nuit, graticule) ne sort pas de la boussole.

## Typography

**Display Font :** JetBrains Mono (repli : SF Mono, Fira Code, ui-monospace)
**Body Font :** IBM Plex Sans (repli : SF Pro Text, system-ui)
**Label/Mono Font :** JetBrains Mono

**Character :** une mono technique qui sonne comme un instrument porte presque toute l'interface ; une sans-serif sobre lui sert de voix de lecture. Le mono domine.

### Hierarchy
- **Display** (700, 1.125rem) : nom « DriftApp » dans l'en-tête, avec le dégradé feu.
- **Headline** (700, 1rem, capitales, interlettrage 0.05em) : titres de section (« POSITION COUPOLE », « CONTRÔLE MANUEL »), avec le dégradé feu.
- **Title** (700, 1.5rem, mono) : grandes valeurs des cartes de statistiques (page Session), en ambre.
- **Body** (400, 0.875rem) : texte courant, champs et boutons (les boutons sont en mono 500).
- **Label** (400, 0.65rem, capitales, interlettrage large) : libellés des cases d'information (ENC, CIBLE, MODE AUTO).
- **Mono** (0.75rem) : journal, fichiers IPC, valeurs numériques.

### Named Rules
**La règle de l'instrument.** Toute valeur mesurée, commande ou entrée de journal est en mono. Seul le texte que l'on lit comme une phrase passe en IBM Plex Sans.

**La règle du feu réservé.** Le dégradé feu (`#ff6b00` → `#c09050`) ne s'applique qu'au nom de l'application et aux titres de section. Il ne s'étire jamais sur une largeur plus grande que son texte (`width: fit-content`).

## Layout

Le contenu tient dans une largeur maximale de 1536 px (`max-w-screen-2xl`), sous un en-tête collant de 56 px. Sur le dashboard, une grille à deux colonnes à partir de `lg` : 350 px pour la position de la coupole (boussole, cimier, encodeur, corrections) et le reste pour les panneaux d'action empilés (suivi, contrôle manuel, cimier). Le journal occupe toute la largeur en bas. Sous `lg`, tout passe en une seule colonne.

Le rythme est serré : 1 rem de marge interne dans les panneaux, 1 rem entre panneaux, 0,5 rem entre boutons. Les rangées de boutons (`button-group`) donnent la même largeur à chaque bouton. Un mode compact (`max-height: 760px`) resserre marges et intervalles pour que l'écran tactile 720p de l'observatoire affiche tout sans défilement ; la boussole descend à 200 px sous 800 px de haut.

## Elevation & Depth

Le relief vient d'abord des paliers de bois : foyer, puis noyer, puis chêne fumé, puis chêne clair. Une seule ombre portée discrète sous les panneaux sert d'ancrage. Le reste de la profondeur, c'est de la lumière : des halos colorés signalent un état vivant (STOP et parking en rouge, suivi actif en vert pulsé, voyant connecté, modale GOTO en orange, survol d'un panneau en ambre). Les modales flottent sur un voile noir à 80 % flouté à 4 px.

### Shadow Vocabulary
- **Ancrage de panneau** (`box-shadow: 0 2px 8px rgba(0,0,0,0.3), 0 1px 3px rgba(0,0,0,0.2)`) : tous les panneaux.
- **Halo ambre** (`0 0 12px rgba(212,160,85,0.25)`) : focus et éléments de marque ; au survol d'un panneau, `0 0 15px rgba(212,160,85,0.15), 0 0 30px rgba(212,160,85,0.05)`.
- **Halo vert** (`0 0 12px rgba(0,210,106,0.25)`) : voyant ok ; la bordure du suivi actif pulse sur 3 s.
- **Halo rouge** (`0 0 8px rgba(255,71,87,0.4), 0 0 20px rgba(255,71,87,0.15)`) : STOP, en permanence.
- **Halo de modale** (`0 0 30px rgba(255,165,2,0.3), 0 0 60px rgba(255,165,2,0.1)`) : modale GOTO.

### Named Rules
**La règle de la lumière qui parle.** Un halo ou une pulsation annonce un état vivant ou une commande critique. Un élément au repos n'a pas de halo.

## Shapes

Les angles sont doucement arrondis et suivent une échelle courte : 6 px pour les badges et les onglets, 8 px pour les boutons, les champs et les cases d'information, 10 px pour les panneaux, 16 px pour les modales. Les voyants sont des pastilles rondes de 8 px. Les bordures font 1 px en bronze ; elles passent à 2 px colorés quand un état est porté par le contour (suivi actif en vert, encodeur, carte de composant en erreur ou périmée, modale GOTO). Les séparateurs internes sont des filets dégradés : transparent, bronze, ambre au centre, bronze, transparent.

## Components

### Buttons
Des boutons d'instrument, en mono et larges, faits pour le doigt.
- **Shape :** coins doucement arrondis (8 px), mono 500, 14 px.
- **Primary :** ambre de lanterne et texte foyer en 600, pour l'action principale du panneau (Ouvrir, Démarrer le suivi).
- **Secondary :** chêne fumé, texte parchemin, bordure bronze ; c'est le bouton par défaut (Rechercher, Fermer, GOTO).
- **Danger / Stop :** STOP utilise un rouge translucide à 20 % avec texte rouge gras et un halo rouge permanent. Le parking reprend le même traitement. Le bouton danger plein (rouge, texte blanc) est réservé aux confirmations.
- **JOG :** chêne fumé, 12 px de marge verticale, tous de même largeur sur la rangée.
- **Continu actif :** fond ambre à 20 %, texte ambre, bordure ambre à 30 %.
- **Hover / Focus :** un palier plus clair au survol, transition de 200 ms ; focus en contour ambre de 2 px décalé de 2 px. Bouton désactivé : opacité 50 %.

### Chips (badges)
- **Style :** pastille arrondie à 6 px, mono 12 px 500, fond de la couleur d'état à 15 % et texte de la même couleur (STALE en orange, UNAVAILABLE en rouge, SEC et chauffage en vert).
- **Statut cimier :** badge encadré d'ambre avec pictogramme (« ○ FERMÉ »).

### Cards / Containers
- **Corner Style :** 10 px.
- **Background :** panneau de noyer ; motif de constellations (`constellations-pattern.svg`, tuile de 400 px) sur les panneaux principaux (`panel-astro`).
- **Shadow Strategy :** ancrage de panneau, plus un halo ambre au survol des panneaux constellés (voir Elevation & Depth).
- **Border :** 1 px bronze.
- **Internal Padding :** 1 rem.
- **Cases d'information :** chêne fumé, 8 px de rayon, libellé en capitales cendre à gauche, valeur mono à droite.

### Inputs / Fields
- **Style :** chêne fumé, bordure bronze de 1 px, 8 px de rayon, mono 14 px, placeholder cendre.
- **Focus :** la bordure passe à l'ambre (200 ms).

### Navigation
- **Style :** onglets texte de 14 px 500 en taupe dans l'en-tête. L'onglet actif a un fond ambre à 15 % et un texte ambre ; au survol, le texte passe en parchemin sur chêne clair. À droite de l'en-tête : état du cimier, bouton MAJ et voyant de connexion.

### Boussole (composant signature)
Un disque bleu nuit dessiné en canvas, avec des étoiles, des repères N/E/S/O, l'anneau ambre de la coupole et l'ouverture de la fente, la flèche verte de la coupole, la cible et le repère de parking « P ». C'est l'unique fenêtre froide de l'interface ; elle se réduit à 200 px sur les écrans bas.

### Modale GOTO
Elle s'ouvre avec un fondu et une légère mise à l'échelle (300 ms) sur un voile flouté. Contenu en dégradé noyer vers foyer, bordure orange de 2 px avec halo orange. On y voit la position de départ et l'arrivée, des chevrons animés dans le sens de rotation et une barre de progression.

### Journal
Un bloc creusé dans le foyer, en mono 12 px, une entrée par ligne séparée par un filet bronze. Chaque entrée prend la couleur de son état (rouge erreur, vert succès ou suivi, orange avertissement, ambre correction).

## Do's and Don'ts

### Do:
- **Do** poser chaque nouvelle surface sur les paliers de bois existants (`night-hearth` → `walnut-panel` → `smoked-oak-input` → `oak-hover`), jamais sur un gris neutre.
- **Do** réserver le vert, l'orange et le rouge aux états, avec le même sens partout (règle des signaux).
- **Do** écrire en JetBrains Mono les valeurs, commandes et journaux.
- **Do** garder STOP visible et lumineux (halo rouge) dans toutes les vues où quelque chose peut bouger.
- **Do** prévoir des cibles tactiles d'au moins la hauteur d'un bouton JOG (≈ 44 px) et un mode compact pour l'écran 720p.
- **Do** garder une aide toujours visible ou affichée au toucher ; le dashboard tourne sur un écran tactile.
- **Do** respecter `prefers-reduced-motion`, que le système applique déjà globalement.

### Don't:
- **Don't** sortir le bleu nuit ou le graticule de la boussole.
- **Don't** utiliser le dégradé feu ailleurs que sur le nom de l'application et les titres de section.
- **Don't** mettre un halo ou une pulsation sur un élément au repos.
- **Don't** introduire une deuxième couleur de marque à côté de l'ambre.
- **Don't** faire dépendre une information du survol (`title`, tooltip au hover).

### Trois thèmes
Le bois sombre décrit plus haut est le thème **Crépuscule** : c'est le rendu par défaut des feuilles de style, aucune règle ne le cible. `web/static/css/theme.css` ajoute le thème **Jour** (clair) et le thème **Nuit** (rouge). `theme.js` pose `data-theme` (`day`, `dusk`, `night`) sur `<html>` d'après le sélecteur Auto/Nuit/Crép./Jour de l'en-tête. En Auto : jour quand le Soleil est au-dessus de +6°, crépuscule entre +6° et −6°, nuit en dessous. Un changement de thème émet l'événement `driftapp:themechange`.

Les dessins (canvas de la boussole, frise de nuit SVG, graphiques Chart.js) lisent leurs couleurs dans les variables `--sky-*`, `--frieze-*` et `--chart-*` de `theme.css`, définies pour chaque thème.
- **Do** donner à toute nouvelle couleur une valeur dans chaque thème, ou la faire passer par un token ; une couleur écrite en dur reste sombre en Jour.

### Thème jour « carnet d'observation »
Pour l'écran tactile en pleine lumière et le portable au bureau : papier presque blanc (`#fdfcf9` sur un fond `#efece6`), encre graphite (`#1f1d1a`), filets fins, ambre foncé en bronze (`#8c5a14`) pour rester lisible. Les états gardent leur sens, en versions foncées (vert `#0f6b3b`, orange `#985000`, rouge `#b0172f`).
- Pas d'ombre, de halo, de pulsation néon ni de constellations : invisibles en pleine lumière. Un état vivant se lit au **contour** (STOP : fond rose pâle, texte et contour rouges ; suivi actif : contour vert).
- Les titres de section perdent le dégradé feu : encre graphite soulignée d'un filet ambre de 2 px. Le nom de l'application reste en ambre, en aplat.
- La boussole devient une carte du ciel imprimée : disque papier, graticule et étoiles graphite, anneau de la coupole en ambre. La règle du ciel enclos tient toujours.
- Texte sur l'ambre : blanc (5,9:1). Tout texte ≥ 4,5:1 sur `obs-input`, la surface la plus foncée.
- **Don't** surcharger une règle `!important` de `@layer components` depuis un fichier hors layer : un `!important` hors layer perd. Poser la surcharge dans `@layer base` (voir les titres dans `theme.css`).

### Thème nuit rouge
La nuit, `web/static/css/theme.css` remplace tous les tokens par des rouges purs (G = B = 0) posés sur un fond presque noir. Un filtre `feColorMatrix` posé sur `<html>` ne laisse passer que le canal rouge, ce qui couvre la boussole, la frise, les graphiques et les styles inline.
- **Do** donner à toute nouvelle couleur une valeur nuit en rouge pur dans `theme.css` ; le filtre n'est qu'un filet de sécurité.
- **Do** distinguer les états par la forme : aplat pour l'alarme et STOP, contour pour l'action principale, anneau pour un voyant ok, disque plein pour un voyant en panne.
- **Don't** compter sur la teinte pour porter un sens : en nuit, le vert et l'orange deviennent rouges.
- **Don't** descendre un texte sous #f00000 en nuit : c'est la limite des 4,5:1 en rouge pur. Pour baisser la luminance, on règle la luminosité de l'écran.
