# Mode nuit rouge

Branche `design/impeccable` (abandonnable si le résultat ne convient pas).

## Problème

L'écran tactile du kiosque est utilisé dans la coupole noire. L'interface actuelle
(texte presque blanc, vert, orange et rouge saturés, halos permanents) détruit la vision
nocturne, alors que PRODUCT.md la déclare impérative. Audit impeccable du 25/10 : P1-1
(pas de mode nuit), P1-3 (contraste des textes « cendre »), P2-1 (halos animés).

## Décisions

- **Thème nuit rouge intégral.** C'est une deuxième palette des mêmes tokens, en rouges
  purs (G = B = 0) sur un fond presque noir. Aucune lumière verte, bleue ou blanche ne
  sort de l'écran.
- **Filet de sécurité.** Un filtre SVG `feColorMatrix` sur `<html>` ne conserve que le
  canal rouge (R' = R + 0,6 G + 0,2 B). Il couvre ce qui est dessiné avec des couleurs
  écrites en dur : boussole (canvas), frise de nuit (SVG), graphiques Chart.js, styles
  inline, emoji. Il ne modifie pas les tokens nuit, qui sont déjà des rouges purs.
- **Les états se distinguent sans la teinte.**
  - L'alarme et STOP sont en aplat rouge vif avec du texte noir.
  - L'action principale est en contour.
  - Un voyant ok est un anneau, un voyant en panne un disque plein.
  - Le texte existant (« FERMÉ », « SEC », « Connecté ») porte le sens.
- **En nuit, pas de halo, pas d'animation, pas de dégradé de texte, pas de fond
  constellé.**
- **Contraste.** Le texte reste à au moins 4,5:1. En rouge pur, c'est réalisable
  seulement au-dessus de #ec0000 environ. Les niveaux de texte sont donc proches, et la
  hiérarchie repose sur la taille, la graisse et les capitales. Pour baisser la luminance
  globale, il faut régler la luminosité de l'écran (le navigateur ne la pilote pas).
- **Activation.** Un sélecteur à trois positions dans l'en-tête, sur toutes les pages,
  avec des cibles d'au moins 44 px :
  - **Auto** : nuit quand le Soleil est sous −6°, jour au-dessus ; réévalué chaque
    minute ;
  - **Nuit** et **Jour** : choix forcés.
- **Un réglage par écran**, stocké dans `localStorage` (`driftapp-theme`). Par défaut :
  Auto. Si `localStorage` est indisponible : Auto, sans mémorisation.
- **Calcul solaire en JS** (algorithme NOAA simplifié, environ 0,1° de précision), à
  partir de la latitude et de la longitude du site lues dans `data/config.json` via un
  context processor Django. Rien n'est écrit en dur.
- **Pas de flash au chargement.** Le thème est posé par un script bloquant dans
  `<head>`, avant le premier rendu.

## Hors périmètre

Thème de jour inchangé. Pas de réglage de luminosité. Cibles tactiles du reste de
l'interface (ce sera `/impeccable adapt`). Pas de mise en page nouvelle.

## Critères de succès

1. En nuit, une capture des 4 pages et d'une modale ne contient aucun pixel avec
   G > 0 ou B > 0.
2. Le thème de jour est inchangé, à l'exception du sélecteur ajouté dans l'en-tête.
3. Le calcul JS de l'altitude du Soleil est à moins de 0,5° d'astropy
   (`compute_sun_altitude`) sur un échantillon de dates et d'heures.
4. Le sélecteur bascule immédiatement et le choix survit à un rechargement.
5. Les tests pytest du context processor passent ; ruff est propre.
