# Thème de jour « Carnet d'observation »

Branche `design/theme-jour`. Prévisualisation validée par JP le 25/10 (proposition B) :
https://claude.ai/artifact/GAVfYwm3wRuTDZpGgh7Az8

## Problème

Le jour, l'écran tactile de la coupole prend la lumière et les reflets, et le portable
sert dans un bureau éclairé. Le seul thème « Jour » actuel est le bois sombre de la salle
de veille : terne et peu lisible en pleine lumière.

## Décisions

- **Quatre thèmes, quatre choix.** Sélecteur de l'en-tête : **Auto · Nuit · Crép. ·
  Jour** (cibles de 44 px). Valeurs de `data-theme` : `night`, `dusk`, `day`.
  - `dusk` (« Crépuscule ») est le bois sombre actuel, **inchangé** : c'est le rendu par
    défaut des feuilles de style, aucune règle ne le cible.
  - `day` devient le nouveau thème clair.
- **Auto, deux seuils.** Soleil ≥ 0° → `day` ; entre 0° et −6° → `dusk` ; sous −6° →
  `night` (seuil inchangé, celui de la fermeture du cimier). Sans coordonnées du site :
  `dusk` (le rendu historique).
- **Choix mémorisés.** La clé `driftapp-theme` est conservée. Un écran réglé sur « Jour »
  passe au thème clair : c'est le sens voulu du mot.
- **Monde visuel du thème jour : le carnet d'observation.** Papier presque blanc, encre
  graphite, filets fins, aucune ombre ni halo ni fond constellé, l'ambre foncé en bronze
  pour rester lisible. Les titres de section perdent le dégradé feu au profit d'un texte
  graphite souligné d'un filet ambre de 2 px.
- **La boussole devient une carte du ciel imprimée** : disque papier, graticule et
  étoiles graphite, anneau de la coupole en ambre, flèche en vert foncé. La règle du ciel
  enclos tient : ces couleurs restent dans la boussole.
- **Les couleurs d'état gardent leur sens** (vert ok, orange attention, rouge arrêt), en
  versions foncées : badges en fond teinté + texte de la couleur. STOP : fond rose pâle,
  texte et contour rouges. Les états vivants (STOP, suivi actif, modale GOTO) passent par
  un contour coloré au lieu d'un halo, invisible en plein jour.
- **Les couleurs écrites hors des tokens** (canvas de la boussole, frise de nuit,
  graphiques Session, styles inline) sont lues dans des variables CSS du thème actif.
  Leurs valeurs par défaut sont celles d'aujourd'hui : le crépuscule ne change pas. Un
  événement `driftapp:themechange` permet de redessiner ce qui ne se redessine pas seul.

### Palette jour

| Rôle | Token | Valeur |
|------|-------|--------|
| Fond | `obs-dark` | `#efece6` |
| Panneau | `obs-panel` | `#fdfcf9` |
| Champ | `obs-input` | `#f3f0ea` |
| Surface, survol | `obs-surface`, `obs-hover` | `#f7f5f0`, `#e9e5dc` |
| Filets | `obs-border`, `obs-border-light` | `#d8d1c4`, `#c9c1b2` |
| Texte | `obs-text`, `-secondary`, `-muted` | `#1f1d1a`, `#4f4a42`, `#625c52` |
| Ambre | `accent-amber`, `-light`, `-dark` | `#8c5a14`, `#7a4e10`, `#6f470f` |
| États | vert, orange, rouge, violet | `#0f6b3b`, `#985000`, `#b0172f`, `#6a3d9a` |

Contrastes mesurés sur la surface la plus foncée (`obs-input`) : texte 14,4:1, texte
discret 5,7:1, ambre 5,0, vert 5,6, orange 5,2, rouge 6,0.

## Hors périmètre

Mise en page, libellés, comportement : inchangés. Thème nuit et crépuscule : inchangés.
Pas de réglage de luminosité.

## Critères de succès

1. **Crépuscule identique** : captures des 4 pages en `dusk` identiques au pixel près à
   celles de `main` en « Jour » (hors sélecteur de l'en-tête, qui gagne un bouton).
2. **Nuit intacte** : en `night`, aucune capture ne contient de pixel avec G > 0 ou B > 0.
3. **Jour lisible** : captures des 4 pages, de la modale GOTO et d'une modale de
   confirmation en `day` ; aucun reste de bois sombre ni de texte clair sur fond clair ;
   texte ≥ 4,5:1 (calcul sur les paires de tokens).
4. **Auto** : `resolveTheme(altitude)` renvoie `day` à +0,1°, `dusk` à −0,1° et −5,9°,
   `night` à −6,1° (test node) ; le sélecteur bascule immédiatement et le choix survit au
   rechargement.
5. Ruff propre, pytest ciblé vert (context processor, gabarits).
