# Plan : thème de jour « Carnet d'observation »

Spec : `docs/superpowers/specs/2026-10-25-theme-jour-carnet.md`.

0. **Captures de référence** sur `main` (4 pages, thème « Jour » actuel, et nuit) avant
   toute modification. → vérifier : fichiers présents dans le scratchpad.
1. **`web/static/js/theme.js`** : choix `auto/night/dusk/day`, `resolveTheme(alt)` pur
   et exporté pour node (seuils 0° et −6°), repli `dusk` sans coordonnées, événement
   `driftapp:themechange` quand le thème résolu change. → vérifier : test node des seuils.
2. **`web/templates/base.html`** : quatrième bouton « Crép. » dans le sélecteur. →
   vérifier : le sélecteur reste sur une ligne à 1280 px.
3. **Variables de dessin** dans `theme.css` (`:root`) : `--sky-*` (boussole), `--frieze-*`
   (frise), `--chart-*` (Session), valeurs d'aujourd'hui. Branchement dans
   `dashboard.js` (boussole, décompte), `night_frieze.js`, `session.js` (et mise à jour
   des graphiques sur `driftapp:themechange`), légende de `session.html`. → vérifier :
   crépuscule identique au pixel près.
4. **Bloc `html[data-theme="day"]`** dans `theme.css` : tokens, titres soulignés, sans
   halo ni pulsation ni constellations, STOP et badges, surcharges des couleurs en dur de
   `dashboard.css` et des styles de `session.html`, `system.html`, `configuration.html`,
   voiles de modale, barres de défilement, sélection. → vérifier : captures jour des
   4 pages et des modales.
5. **Vérification croisée** : crépuscule identique à l'étape 0, nuit sans pixel G/B,
   contrastes des paires de tokens jour ≥ 4,5:1.
6. **DESIGN.md** (section des thèmes), ruff, pytest ciblé, commit sur
   `design/theme-jour`. Bump, CHANGELOG et push au moment de la fusion.
