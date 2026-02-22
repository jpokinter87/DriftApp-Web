# Roadmap: Dome_web_v4_6

## Overview
Modernisation de l'interface web de DriftApp avec Tailwind CSS et Alpine.js, en preservant toutes les fonctionnalites existantes de controle de coupole astronomique. Migration progressive page par page depuis le CSS custom et vanilla JS actuels.

## Current Milestone
**v5.0 Interface Moderne** (v5.0.0)
Status: In progress
Phases: 2 of 5 complete

## Phases

| Phase | Name | Plans | Status | Completed |
|-------|------|-------|--------|-----------|
| 1 | Foundation & Stack Setup | 2 | Complete | 2026-02-22 |
| 2 | Dashboard Modernization | 3 | Complete | 2026-02-22 |
| 3 | System Page Modernization | 2 | Not started | - |
| 4 | Session Page Modernization | 2 | Not started | - |
| 5 | Polish & Responsive | 2 | Not started | - |

## Phase Details

### Phase 1: Foundation & Stack Setup

**Goal:** Integrer Tailwind CSS + Alpine.js dans le projet Django et creer un template de base avec heritage
**Depends on:** Nothing (first phase)
**Research:** Likely (integration Tailwind standalone CLI avec Django)

**Scope:**
- Integration Tailwind CSS (standalone CLI, pas de Node.js)
- Integration Alpine.js (CDN)
- Creation du template de base Django (base.html) avec header/nav/footer
- Migration du systeme de CSS variables vers Tailwind config
- Preservation de la palette observatory dark theme

**Plans:**
- [x] 01-01: Setup Tailwind CSS v4 standalone + Alpine.js + base template Django
- [x] 01-02: Bibliotheque de composants reutilisables (38 classes)

### Phase 2: Dashboard Modernization

**Goal:** Redesign complet de la page dashboard (controle principal) avec Tailwind + Alpine.js
**Depends on:** Phase 1 (base template + stack)
**Research:** Unlikely (patterns internes)

**Scope:**
- Refonte du layout 2 colonnes (compass + controles)
- Modernisation des panels de controle (tracking, JOG, GOTO)
- Conservation du canvas compass (widget custom)
- Migration des modales (GOTO, update)
- Remplacement du JS polling par Alpine.js reactive

**Plans:**
- [x] 02-01: Layout principal et header/nav avec Tailwind
- [x] 02-02: Panels de controle (tracking, JOG, continuous, GOTO)
- [x] 02-03: Modales et logs temps reel avec Alpine.js

### Phase 3: System Page Modernization

**Goal:** Redesign de la page systeme/diagnostic
**Depends on:** Phase 2 (composants partages)
**Research:** Unlikely (patterns internes)

**Scope:**
- Cards composants (Motor Service, Encoder Daemon)
- Section IPC monitoring avec indicateurs de fraicheur
- Grille de configuration

**Plans:**
- [ ] 03-01: Cards composants et IPC monitoring
- [ ] 03-02: Section configuration et auto-refresh

### Phase 4: Session Page Modernization

**Goal:** Redesign de la page session/rapports
**Depends on:** Phase 2 (composants partages)
**Research:** Unlikely (patterns internes)

**Scope:**
- Selecteur de session (current/history)
- Integration Chart.js avec theme Tailwind
- Tables de corrections et GOTO logs
- Stats cards

**Plans:**
- [ ] 04-01: Layout session, selecteur et stats cards
- [ ] 04-02: Charts, tables de logs et mode distribution

### Phase 5: Polish & Responsive

**Goal:** Finitions responsive, animations, accessibilite et nettoyage CSS legacy
**Depends on:** Phases 2, 3, 4
**Research:** Unlikely

**Scope:**
- Tests responsive mobile/tablette
- Animations et transitions coherentes
- Suppression du CSS custom legacy
- Accessibilite de base (aria, focus states)

**Plans:**
- [ ] 05-01: Responsive breakpoints et animations
- [ ] 05-02: Nettoyage CSS legacy et accessibilite

---
*Roadmap created: 2026-02-22*
*Last updated: 2026-02-22 — Phase 2 complete*
