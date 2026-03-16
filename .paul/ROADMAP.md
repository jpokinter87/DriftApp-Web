# Roadmap: Dome_web_v4_6

## Overview
Application web Django embarquee sur Raspberry Pi pour le controle d'une coupole astronomique.

## Current Milestone
**v5.2 Stabilité Terrain**
Status: In Progress
Phases: 2 of 4 complete

| Phase | Name | Plans | Status | Completed |
|-------|------|-------|--------|-----------|
| 1 | Persistance Logs | 1 | Complete ✓ | 2026-03-15 |
| 2 | Bug Retournement Méridien | 1 | Complete ✓ | 2026-03-16 |
| 3 | Bugs Connus | TBD | Not started | - |
| 4 | Programme Tests Terrain | TBD | Not started | - |

### Phase 1: Persistance Logs

Focus: Fichier log par cible (nom+timestamp), rétention 7 jours, pas d'écrasement entre cibles d'une même nuit
Plans: TBD (defined during /paul:plan)

### Phase 2: Bug Retournement Méridien

Focus: Analyse du flux tracking au flip de la monture, correction de la perte de suivi post-retournement
Plans: TBD (defined during /paul:plan)

### Phase 3: Bugs Connus

Focus: ObjectListView.get_objets_disponibles() bug, routes park/calibrate/end-session non implémentées
Plans: TBD (defined during /paul:plan)

### Phase 4: Programme Tests Terrain

Focus: Fonction de test de jour simulant des positions critiques (méridien, zénith, pôle) et vérifiant les décisions tracking+moteur
Plans: TBD (defined during /paul:plan)

## Completed Milestones

<details>
<summary>v5.1 Synchronisation & Qualité - 2026-03-14 (6 phases)</summary>

| Phase | Name | Plans | Completed |
|-------|------|-------|-----------|
| 1 | Sync Production | 2 | 2026-03-14 |
| 2 | Audit Code | 2 | 2026-03-14 |
| 3 | Refactoring Core | 2 | 2026-03-14 |
| 4 | Refactoring Services | 2 | 2026-03-14 |
| 5 | Tests | 2 | 2026-03-14 |
| 6 | Validation | 1 | 2026-03-14 |

</details>

<details>
<summary>v5.0 Interface Moderne - 2026-02-22 (5 phases)</summary>

| Phase | Name | Plans | Completed |
|-------|------|-------|-----------|
| 1 | Foundation & Stack Setup | 2 | 2026-02-22 |
| 2 | Dashboard Modernization | 3 | 2026-02-22 |
| 3 | System Page Modernization | 2 | 2026-02-22 |
| 4 | Session Page Modernization | 2 | 2026-02-22 |
| 5 | Polish & Responsive | 2 | 2026-02-22 |

</details>

---
*Roadmap created: 2026-02-22*
*Last updated: 2026-03-15 — Phase 1 complete*
