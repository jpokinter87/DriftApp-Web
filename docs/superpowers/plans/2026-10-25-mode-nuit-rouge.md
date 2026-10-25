# Plan : mode nuit rouge

Spec : `docs/superpowers/specs/2026-10-25-mode-nuit-rouge.md`.

1. **Context processor `site_coords`** (`web/driftapp_web/context_processors.py`) :
   `SITE_LAT` et `SITE_LON` lus depuis `core.config.config`, puis enregistrés dans
   `settings.py`. → vérifier : test pytest (les valeurs viennent de la config).
2. **`web/static/js/theme.js`** : `sunAltitude(date, lat, lon)`, résolution
   auto/nuit/jour, pose de `data-theme` sur `<html>`, réévaluation toutes les 60 s,
   branchement du sélecteur. → vérifier : comparaison node contre astropy sur 12 dates,
   écart inférieur à 0,5°.
3. **`base.html`** : `data-site-lat` et `data-site-lon` sur `<html>`, `theme.js`
   chargé de façon bloquante dans `<head>`, filtre SVG `night-red`, `night.css` chargé
   en dernier, sélecteur Auto/Nuit/Jour dans l'en-tête. → vérifier : rendu de jour
   identique.
4. **`web/static/css/night.css`** : tokens rouges, filtre sur `html`, suppression des
   halos, des animations, des dégradés et du fond constellé, distinction des états
   (aplat, contour, anneau), barre de défilement, sélection, curseur de saisie. →
   vérifier : captures des 4 pages et d'une modale en nuit, aucun pixel G/B, contraste
   du texte d'au moins 4,5:1.
5. Ruff, pytest ciblé, puis commit sur `design/impeccable`. Pas de bump tant que la
   branche n'est pas fusionnée.
