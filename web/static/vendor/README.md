# Bibliothèques et polices auto-hébergées

L'interface ne charge rien depuis Internet : une coupure réseau pendant la nuit ne doit
pas casser le dashboard (Alpine absent = modales et badges inertes). Versions figées ;
mettre à jour = remplacer le fichier et le chemin dans le gabarit.

| Fichier | Source | Licence | Utilisé par |
|---|---|---|---|
| `alpinejs-3.17.5.min.js` | jsdelivr `alpinejs@3.17.5/dist/cdn.min.js` (version que servait `alpinejs@3` le 25/10/2026) | MIT | `base.html` |
| `chart-4.4.1.umd.min.js` | jsdelivr `chart.js@4.4.1/dist/chart.umd.min.js` | MIT | `session.html` |
| `fonts.css` + `fonts/*.woff2` | Google Fonts, IBM Plex Sans (300–700) et JetBrains Mono (400–700), sous-ensembles latin et latin étendu | SIL OFL 1.1 | `base.html` |
