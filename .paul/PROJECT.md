# Project: Dome_web_v4_6

## Description
Application web Django embarquee sur Raspberry Pi pour le controle d'une coupole astronomique. L'application fonctionne bien et l'objectif actuel est de moderniser l'interface utilisateur en adoptant des frameworks UI modernes.

## Core Value
Maintenir automatiquement le cimier de la coupole face a l'ouverture du telescope pendant toute la duree d'une session d'astrophotographie.

## Requirements

### Active
- [x] Correction bug retournement méridien (perte de suivi post-flip) — v5.2 Phase 2
- [x] Correction bugs connus (ObjectListView, routes manquantes) — v5.2 Phase 3
- [ ] Programme de tests terrain de jour (positions critiques simulées) — v5.2 Phase 4

### Validated
- ✓ core/ et services/ synchronisés sur production DriftApp_v4_6 — v5.1 Phase 1
- ✓ Code review complète : 54 issues identifiées (7C, 15H, 20M, 12L) — v5.1 Phase 2
- ✓ Refactoring core : 27 issues corrigées, code mort supprimé, angle_utils centralisé — v5.1 Phase 3
- ✓ Refactoring services : 11 issues corrigées (thread safety, validation, IPC, zombie detection, simulation) — v5.1 Phase 4
- ✓ Suite de tests alignée (738 tests, 0 échecs) et couverture étendue (health, session, storage) — v5.1 Phase 5
- ✓ Validation cross-couche (Django ↔ IPC ↔ MotorService), 746 tests verts — v5.1 Phase 6
- ✓ Rétention logs 7 jours + sauvegarde session robuste, 754 tests verts — v5.2 Phase 1
- ✓ Watchdog thread + fix méridien (normalisation, re-sync, détection transit), 771 tests — v5.2 Phase 2
- ✓ get_objets_disponibles() + routes stub park/calibrate/end-session (501) — v5.2 Phase 3
- ✓ Logging structuré clé=valeur, heartbeat 10s, snapshot IPC 60s, milestone 5min, 782 tests — v5.2 Phase 3.5
- ✓ Tailwind CSS v4 + Alpine.js integres dans Django — Phase 1
- ✓ Template de base avec heritage (base.html) — Phase 1
- ✓ 38 composants reutilisables (@layer components) — Phase 1
- ✓ Dashboard layout 2 colonnes (compass + controles) — Phase 2
- ✓ Panels observatory avec champ etoile SVG et glow effects — Phase 2
- ✓ Alpine.js store reactif pour modales, logs et tracking — Phase 2
- ✓ Zero regression fonctionnelle sur dashboard — Phase 2
- ✓ Page Systeme modernisee (cards, IPC, config, Alpine.store) — Phase 3
- ✓ Page Session modernisee (selecteur, charts, tables, stats, Alpine.store) — Phase 4
- ✓ Responsive mobile/tablette + breakpoints mobile-first — Phase 5
- ✓ CSS legacy nettoye + accessibilite de base (aria, focus ring) — Phase 5
- ✓ Styles partages factorises (panel-astro, section-title-fire) — Phase 5

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
| Alpine.store('session') bridge | 4 | Meme pattern que system pour status, tabs, auto-refresh |
| Chart.js theme colors adapted | 4 | Grid/tick colors matching observatory theme |
| session.css retire | 4 | 3eme page 100% Tailwind + inline CSS |
| Shared components factorises | 5 | panel-astro, section-title-fire, shared-pulse dans tailwind-input.css |
| Mobile-first grid (grid-cols-1 lg:) | 5 | Standard Tailwind pattern pour responsive |
| prefers-reduced-motion global | 5 | Accessibilite pour troubles vestibulaires |
| focus-visible amber outline | 5 | Navigation clavier avec theme observatory |
| Délégation angle_utils pour normalisation | v5.1 P3 | Centralise toute logique angulaire, évite duplication |
| PlanetaryEphemerides singleton par session | v5.1 P3 | Évite instanciation répétée à chaque correction |
| status_lock pour accès concurrent | v5.1 P4 | Protège current_status entre main thread et ContinuousHandler |
| Pas de threading GOTO/JOG | v5.1 P4 | Trop risqué pour refactoring, à évaluer dans milestone dédié |
| Simulation fidèle au matériel | v5.1 P4 | Délais I2C simulés pour réduire allers-retours dev/terrain |
| Tests alignés sur API production | v5.1 P5 | Corriger tests plutôt que production — tests reflètent la réalité |
| APIRequestFactory pour mocks vues | v5.1 P5 | Contourne dispatch Django pour injecter mocks motor_client |
| Patch double IPC pour tests cross-couche | v5.1 P6 | ipc_manager + Django settings vers memes fichiers tmp_path |
| Rétention par âge au lieu de par nombre | v5.2 P1 | 7 jours au lieu de MAX_FILES=20/100 — préserve les logs terrain |
| Sauvegarde session robuste (fallback) | v5.2 P1 | Garantit la persistance même si stop() échoue |
| Thread daemon watchdog systemd | v5.2 P2 | Heartbeat indépendant de la boucle principale — survit aux rotations bloquantes |
| Re-sync encodeur après delta > 30° | v5.2 P2 | Évite dérive offset post-méridien sans surcharger les petites corrections |

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

## Current State

| Field | Value |
|-------|-------|
| Version | 5.1.0 |
| Last milestone | v5.1 Synchronisation & Qualité (2026-03-14) |
| Current milestone | v5.2 Stabilité Terrain |
| Status | In Progress |

---
*Created: 2026-02-22*
*Last updated: 2026-03-15 — Phase 1 (Persistance Logs) complete*
