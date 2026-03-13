# Roadmap: DriftApp

## Overview
DriftApp v4.4 est en production à l'Observatoire Ubik. Ce milestone vise à consolider la qualité du code, corriger les bugs terrain, mettre en place des tests automatisés et une infrastructure CI/CD pour faciliter le développement à distance et le déploiement sur le Raspberry Pi.

## Current Milestone
**v5.0 Qualité & Infrastructure** (v5.0.0)
Status: In progress
Phases: 1 of 6 complete

## Phases

| Phase | Name | Plans | Status | Completed |
|-------|------|-------|--------|-----------|
| 1 | Code Review & Audit | 4 | Complete | 2026-03-13 |
| 1.5 | Tests Exhaustifs | 6 | Not started | - |
| 2 | Refactoring & Corrections | TBD | Not started | - |
| 2.1 | Bug Fixes Terrain | TBD | Not started | - |
| 3 | Tests Complémentaires | TBD | Not started | - |
| 4 | CI/CD & Versioning | TBD | Not started | - |

## Phase Details

### Phase 1: Code Review & Audit ✅
**Goal:** Revue exhaustive du code — failles, bugs latents, simplifications, dette technique
**Status:** Complete (88 findings : 6C, 22H, 35M, 25L)

**Plans:**
- [x] 01-01: Review Core (config, hardware, feedback, moteur)
- [x] 01-02: Review Tracking & Observatoire
- [x] 01-03: Review Services & Web
- [x] 01-04: Review Scripts & Synthèse globale

### Phase 1.5: Tests Exhaustifs [INSERTED]
**Goal:** Couverture pytest maximale de tous les modules AVANT tout refactoring — zéro régression
**Depends on:** Phase 1 (review terminée, code stable connu)
**Research:** Likely (mocking GPIO/SPI, fixtures simulation)

**Scope:**
- Tests unitaires exhaustifs pour chaque module
- Edge cases (0°/360°, limites, erreurs, timeouts)
- Mocking du hardware (GPIO, SPI, fichiers /dev/shm/)
- Fixtures de simulation
- Couverture cible : maximum possible (>80%)
- Les tests documentent le comportement ACTUEL (même les bugs connus)

**Plans:**
- [ ] 1.5-01: Setup pytest + Tests angle_utils + config_loader
- [ ] 1.5-02: Tests hardware (moteur, moteur_simule, feedback_controller, encoder)
- [ ] 1.5-03: Tests tracking (abaque_manager, adaptive_tracking, tracker)
- [ ] 1.5-04: Tests observatoire (calculations, ephemerides, catalogue)
- [ ] 1.5-05: Tests services (motor_service) + IPC
- [ ] 1.5-06: Tests web (Django views, API endpoints)

### Phase 2: Refactoring & Corrections
**Goal:** Appliquer les corrections et simplifications identifiées en Phase 1
**Depends on:** Phase 1.5 (tests en place pour protéger contre les régressions)
**Research:** Unlikely

**Scope:**
- Corrections de failles et bugs latents
- Simplifications de code (sans modification fonctionnelle)
- Élimination de code mort
- Harmonisation des patterns
- Chaque refactoring vérifié par les tests existants

**Plans:**
- [ ] TBD (définis après Phase 1.5)

### Phase 2.1: Bug Fixes Terrain [INSERTED]
**Goal:** Corriger les bugs remontés par l'utilisateur sur site
**Depends on:** Phase 2 (code refactoré et stabilisé)
**Reason:** Bugs terrain à traiter sur une base de code propre

**Plans:**
- [ ] TBD (bugs à fournir par l'utilisateur)

### Phase 3: Tests Complémentaires
**Goal:** Compléter la couverture après refactoring, tests d'intégration
**Depends on:** Phase 2.1 (bugs corrigés)

**Scope:**
- Tests d'intégration IPC (3 processus)
- Tests end-to-end en mode simulation
- Tests de régression pour les bugs terrain corrigés

**Plans:**
- [ ] TBD (définis après Phase 2.1)

### Phase 4: CI/CD & Versioning
**Goal:** Pipeline GitHub Actions, versioning sémantique, déploiement automatisé vers le Pi
**Depends on:** Phase 3 (tests complets)
**Research:** Likely (déploiement SSH vers Raspberry Pi)

**Scope:**
- GitHub Actions workflow (lint, test, build)
- Versioning sémantique automatique
- Script de déploiement vers Raspberry Pi
- Tags et releases automatiques

**Plans:**
- [ ] TBD (définis après Phase 3)

---
*Roadmap created: 2026-03-13*
*Last updated: 2026-03-13*
