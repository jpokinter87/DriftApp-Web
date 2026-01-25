# Requirements: DriftApp Web v5.0

**Defined:** 2026-01-25
**Core Value:** Le moteur doit pouvoir etre pilote de maniere fluide et rapide lors des GOTO, sans regression sur le suivi astronomique existant.

## v1 Requirements

Requirements pour ce milestone. Chaque requirement mappe vers une phase du roadmap.

### Code Review

- [x] **REVIEW-01**: Identifier et corriger toutes les bare exceptions (`except:` et `except Exception:`)
- [x] **REVIEW-02**: Verifier l'adherence aux principes SOLID dans les modules core/
- [x] **REVIEW-03**: Identifier et eliminer les violations DRY (code duplique)
- [x] **REVIEW-04**: Ajouter/ameliorer docstrings et type hints sur les fonctions publiques

### Refactoring

- [ ] **REFACT-01**: Appliquer les corrections identifiees par le code review
- [ ] **REFACT-02**: Restructurer le code si le review revele des problemes architecturaux

### Optimisation Moteur

- [ ] **OPTIM-01**: Mesurer le jitter reel des pulses moteur (profiling avant optimisation)
- [ ] **OPTIM-02**: Implementer busy-wait hybride pour remplacer time.sleep() dans les pulses critiques
- [ ] **OPTIM-03**: Configurer l'isolation CPU pour le Motor Service (CPU affinity)
- [ ] **OPTIM-04**: Calibrer les delais minimums selon les mesures de jitter
- [ ] **OPTIM-05**: Mesurer le jitter apres optimisation (validation amelioration)
- [ ] **OPTIM-06**: Valider la fluidite et vitesse max en conditions reelles

### Architecture GPIO

- [ ] **ARCH-01**: Definir un Protocol Python pour l'abstraction GPIO backend
- [ ] **ARCH-02**: Extraire l'implementation lgpio actuelle vers LgpioBackend
- [ ] **ARCH-03**: Implementer PigpioBackend pour deploiements Raspberry Pi 4
- [ ] **ARCH-04**: Implementer MockBackend pour tests sans hardware
- [ ] **ARCH-05**: Factory function pour selection de backend via config.json
- [ ] **ARCH-06**: Tests unitaires couvrant tous les backends

## v2 Requirements

Differe pour milestone futur. Documente mais pas dans le roadmap actuel.

### Controleur Externe

- **EXT-01**: Evaluer Raspberry Pi Pico comme generateur de pulses externe
- **EXT-02**: Definir protocole de communication Pi <-> Pico
- **EXT-03**: Implementer backend PicoBackend

### Monitoring Avance

- **MON-01**: Dashboard temps reel du jitter moteur
- **MON-02**: Alertes si jitter depasse seuil configurable
- **MON-03**: Historique des performances moteur

## Out of Scope

Exclusions explicites avec justification.

| Feature | Reason |
|---------|--------|
| pigpio sur Pi 5 | Incompatible avec architecture RP1 (recherche confirmee) |
| Controleur externe v1 | Evaluer seulement si optimisations software insuffisantes |
| Nouvelles features astro | Focus sur qualite et moteur pour ce milestone |
| Changement architecture IPC | Fonctionne bien, pas de besoin identifie |
| Migration Django version | Hors scope, stabilite prioritaire |

## Traceability

Mapping requirements -> phases.

| Requirement | Phase | Status |
|-------------|-------|--------|
| REVIEW-01 | Phase 1: Code Review | Complete |
| REVIEW-02 | Phase 1: Code Review | Complete |
| REVIEW-03 | Phase 1: Code Review | Complete |
| REVIEW-04 | Phase 1: Code Review | Complete |
| REFACT-01 | Phase 2: Refactoring | Pending |
| REFACT-02 | Phase 2: Refactoring | Pending |
| OPTIM-01 | Phase 3: Profiling Baseline | Pending |
| OPTIM-02 | Phase 4: Timing Optimizations | Pending |
| OPTIM-03 | Phase 4: Timing Optimizations | Pending |
| OPTIM-04 | Phase 4: Timing Optimizations | Pending |
| OPTIM-05 | Phase 5: Optimization Validation | Pending |
| OPTIM-06 | Phase 5: Optimization Validation | Pending |
| ARCH-01 | Phase 6: GPIO Protocol | Pending |
| ARCH-02 | Phase 6: GPIO Protocol | Pending |
| ARCH-03 | Phase 7: Alternative Backends | Pending |
| ARCH-04 | Phase 7: Alternative Backends | Pending |
| ARCH-05 | Phase 8: Backend Integration | Pending |
| ARCH-06 | Phase 8: Backend Integration | Pending |

**Coverage:**
- v1 requirements: 18 total
- Mapped to phases: 18
- Unmapped: 0

---
*Requirements defined: 2026-01-25*
*Last updated: 2026-01-25 - Phase 1 complete (REVIEW-01 to REVIEW-04)*
