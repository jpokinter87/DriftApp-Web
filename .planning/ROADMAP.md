# Roadmap: DriftApp Web v5.0

## Overview

Ce milestone transforme DriftApp d'une application fonctionnelle vers une application optimisee pour la fluidite moteur. Le parcours commence par comprendre le code existant (review, refactoring), puis mesurer les performances reelles (profiling), appliquer des optimisations timing (busy-wait, isolation CPU), et enfin creer une architecture GPIO flexible permettant des backends optimises par plateforme (lgpio Pi 5, pigpio Pi 4).

## Phases

**Phase Numbering:**
- Integer phases (1, 2, 3): Planned milestone work
- Decimal phases (2.1, 2.2): Urgent insertions (marked with INSERTED)

Decimal phases appear between their surrounding integers in numeric order.

- [ ] **Phase 1: Code Review** - Analyser la qualite du code et identifier les problemes
- [ ] **Phase 2: Refactoring** - Appliquer les corrections du code review
- [ ] **Phase 3: Profiling Baseline** - Mesurer le jitter reel avant optimisation
- [ ] **Phase 4: Timing Optimizations** - Implementer busy-wait et isolation CPU
- [ ] **Phase 5: Optimization Validation** - Mesurer et valider les ameliorations
- [ ] **Phase 6: GPIO Protocol** - Definir l'abstraction GPIO et extraire lgpio
- [ ] **Phase 7: Alternative Backends** - Implementer pigpio et mock backends
- [ ] **Phase 8: Backend Integration** - Factory, configuration, et tests complets

## Phase Details

### Phase 1: Code Review
**Goal**: Comprendre le code existant et identifier tous les problemes de qualite
**Depends on**: Nothing (first phase)
**Requirements**: REVIEW-01, REVIEW-02, REVIEW-03, REVIEW-04
**Success Criteria** (what must be TRUE):
  1. Toutes les bare exceptions (`except:` et `except Exception:`) sont documentees avec leur localisation
  2. Un rapport SOLID existe identifiant les violations dans core/ avec severite
  3. Tout code duplique est identifie avec estimation d'effort de correction
  4. Les fonctions publiques sans docstrings/type hints sont listees par module
**Plans**: 3 plans (Wave 1 - parallel)

Plans:
- [ ] 01-01-PLAN.md - Scanner et classifier les exceptions (ruff E722, BLE001)
- [ ] 01-02-PLAN.md - Analyser SOLID via complexite (radon) et revue manuelle
- [ ] 01-03-PLAN.md - Identifier violations DRY et couverture documentation (interrogate)

### Phase 2: Refactoring
**Goal**: Corriger les problemes identifies par le code review sans regression
**Depends on**: Phase 1
**Requirements**: REFACT-01, REFACT-02
**Success Criteria** (what must be TRUE):
  1. Tous les 315+ tests existants passent apres les modifications
  2. Les bare exceptions sont remplacees par des exceptions specifiques
  3. Le code duplique critique est factorise
  4. Les changements sont documentes dans un CHANGELOG
**Plans**: TBD

Plans:
- [ ] 02-01: Corriger les exceptions
- [ ] 02-02: Appliquer refactoring structurel

### Phase 3: Profiling Baseline
**Goal**: Etablir une mesure objective du jitter moteur avant optimisation
**Depends on**: Phase 2
**Requirements**: OPTIM-01
**Success Criteria** (what must be TRUE):
  1. Un script de profiling mesure le jitter en microsecondes sur Pi 5
  2. Les mesures couvrent differentes vitesses moteur (lent, normal, rapide)
  3. Un rapport baseline documente le jitter moyen, min, max, et percentiles
  4. Les conditions de mesure sont reproductibles (charge CPU, etc.)
**Plans**: TBD

Plans:
- [ ] 03-01: Script de profiling jitter moteur

### Phase 4: Timing Optimizations
**Goal**: Reduire le jitter moteur par optimisations software
**Depends on**: Phase 3
**Requirements**: OPTIM-02, OPTIM-03, OPTIM-04
**Success Criteria** (what must be TRUE):
  1. Le busy-wait hybride remplace time.sleep() dans les pulses critiques
  2. Le Motor Service peut etre configure pour CPU affinity (isolation core)
  3. Les delais minimums sont calibres selon les mesures de Phase 3
  4. Les optimisations sont activables/desactivables via config.json
**Plans**: TBD

Plans:
- [ ] 04-01: Implementer busy-wait hybride
- [ ] 04-02: Implementer isolation CPU
- [ ] 04-03: Calibrer delais et exposer configuration

### Phase 5: Optimization Validation
**Goal**: Verifier que les optimisations ameliorent la fluidite sans regression
**Depends on**: Phase 4
**Requirements**: OPTIM-05, OPTIM-06
**Success Criteria** (what must be TRUE):
  1. Le jitter mesure est significativement reduit (comparaison quantitative avec baseline)
  2. La fluidite est validee auditivement sur hardware reel (moins de claquements)
  3. La vitesse maximum atteignable est documentee
  4. Le suivi astronomique fonctionne sans regression
**Plans**: TBD

Plans:
- [ ] 05-01: Mesurer jitter apres optimisation
- [ ] 05-02: Validation fluidite et vitesse max en conditions reelles

### Phase 6: GPIO Protocol
**Goal**: Creer une abstraction permettant des backends GPIO interchangeables
**Depends on**: Phase 5
**Requirements**: ARCH-01, ARCH-02
**Success Criteria** (what must be TRUE):
  1. Un Protocol Python definit l'interface GPIO (setup, output, cleanup)
  2. Le code lgpio existant est extrait vers une classe LgpioBackend
  3. MoteurCoupole utilise le backend via injection de dependance
  4. Tous les tests moteur passent avec LgpioBackend
**Plans**: TBD

Plans:
- [ ] 06-01: Definir GPIO Protocol et extraire LgpioBackend

### Phase 7: Alternative Backends
**Goal**: Implementer des backends GPIO additionnels pour flexibilite
**Depends on**: Phase 6
**Requirements**: ARCH-03, ARCH-04
**Success Criteria** (what must be TRUE):
  1. PigpioBackend implemente le Protocol avec wave chains pour Pi 4
  2. MockBackend permet les tests sans hardware
  3. Chaque backend passe les tests d'interface
  4. PigpioBackend documente clairement qu'il ne fonctionne pas sur Pi 5
**Plans**: TBD

Plans:
- [ ] 07-01: Implementer PigpioBackend
- [ ] 07-02: Implementer MockBackend

### Phase 8: Backend Integration
**Goal**: Integrer les backends avec selection automatique et tests complets
**Depends on**: Phase 7
**Requirements**: ARCH-05, ARCH-06
**Success Criteria** (what must be TRUE):
  1. Une factory function selectionne le backend selon config.json et hardware
  2. La detection automatique choisit lgpio sur Pi 5, pigpio sur Pi 4
  3. Les tests couvrent tous les backends (lgpio, pigpio, mock)
  4. La documentation explique comment configurer le backend
**Plans**: TBD

Plans:
- [ ] 08-01: Factory et selection automatique
- [ ] 08-02: Tests et documentation backends

## Progress

**Execution Order:**
Phases execute in numeric order: 1 -> 2 -> 3 -> 4 -> 5 -> 6 -> 7 -> 8

| Phase | Plans Complete | Status | Completed |
|-------|----------------|--------|-----------|
| 1. Code Review | 0/3 | Planned | - |
| 2. Refactoring | 0/2 | Not started | - |
| 3. Profiling Baseline | 0/1 | Not started | - |
| 4. Timing Optimizations | 0/3 | Not started | - |
| 5. Optimization Validation | 0/2 | Not started | - |
| 6. GPIO Protocol | 0/1 | Not started | - |
| 7. Alternative Backends | 0/2 | Not started | - |
| 8. Backend Integration | 0/2 | Not started | - |

---
*Roadmap created: 2026-01-25*
*Last updated: 2026-01-25*
