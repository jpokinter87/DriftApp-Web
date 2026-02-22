# Project: Dome_web_v4_6

## Description
Application web Django embarquee sur Raspberry Pi pour le controle d'une coupole astronomique. L'application fonctionne bien et l'objectif actuel est de moderniser l'interface utilisateur en adoptant des frameworks UI modernes.

## Core Value
Maintenir automatiquement le cimier de la coupole face a l'ouverture du telescope pendant toute la duree d'une session d'astrophotographie.

## Requirements

### Active
- [ ] Page Session modernisee (selecteur, charts, tables, stats)
- [ ] Responsive mobile/tablette + animations coherentes
- [ ] Nettoyage CSS legacy + accessibilite de base

### Validated
- ✓ Tailwind CSS v4 + Alpine.js integres dans Django — Phase 1
- ✓ Template de base avec heritage (base.html) — Phase 1
- ✓ 38 composants reutilisables (@layer components) — Phase 1
- ✓ Dashboard layout 2 colonnes (compass + controles) — Phase 2
- ✓ Panels observatory avec champ etoile SVG et glow effects — Phase 2
- ✓ Alpine.js store reactif pour modales, logs et tracking — Phase 2
- ✓ Zero regression fonctionnelle sur dashboard — Phase 2
- ✓ Page Systeme modernisee (cards, IPC, config, Alpine.store) — Phase 3

## Constraints
- Tailwind v4 standalone CLI (pas de Node.js)
- Alpine.js CDN (pas de build step)
- Preservation de toutes les fonctionnalites existantes
- Canvas compass reste en vanilla JS
- Polling et API calls restent en vanilla JS

## Key Decisions
| Decision | Phase | Rationale |
|----------|-------|-----------|
| Tailwind v4 CSS-based config (@theme) | 1 | Pas de tailwind.config.js, config directement dans CSS |
| Fonts: JetBrains Mono + IBM Plex Sans | 1 | Display + body distinctifs pour theme observatory |
| Champ etoile aleatoire (500 pts) SVG | 2 | Plus convaincant que des constellations pour public astronome |
| Alpine.store bridge pattern | 2 | Migration progressive: Alpine pour UI, vanilla JS pour logique |
| x-cloak pour anti-flash | 2 | Evite le flash de contenu non-initialise |
| Pages secondaires: inline CSS pour styles partages | 3 | dashboard.css non charge hors dashboard, duplication inline |
| Alpine.store('system') bridge | 3 | Meme pattern que dashboard pour status, badges, auto-refresh |
| TemplateView extra_context pour nav | 3 | active_tab pour highlighting nav sur pages statiques |

## Success Criteria
- Interface modernisee avec Tailwind CSS v4 + Alpine.js
- Fonctionnalites existantes preservees (controle moteur, tracking, sessions)
- Theme observatory dark coherent sur les 3 pages
- Responsive mobile/tablette

## Specialized Flows

See: .paul/SPECIAL-FLOWS.md

Quick Reference:
- /frontend-design → Creation et modernisation des composants UI web
- /code-review → Review de code et refactoring qualite
- /refactor-code → Refactoring et amelioration de la qualite du code

---
*Created: 2026-02-22*
*Last updated: 2026-02-22 after Phase 3*
