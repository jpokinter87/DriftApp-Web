# Requirements: DriftApp Web v5.0

**Defined:** 2026-01-25
**Core Value:** Le moteur doit pouvoir être piloté de manière fluide et rapide lors des GOTO, sans régression sur le suivi astronomique existant.

## v1 Requirements

Requirements pour ce milestone. Chaque requirement mappe vers une phase du roadmap.

### Code Review

- [ ] **REVIEW-01**: Identifier et corriger toutes les bare exceptions (`except:` et `except Exception:`)
- [ ] **REVIEW-02**: Vérifier l'adhérence aux principes SOLID dans les modules core/
- [ ] **REVIEW-03**: Identifier et éliminer les violations DRY (code dupliqué)
- [ ] **REVIEW-04**: Ajouter/améliorer docstrings et type hints sur les fonctions publiques

### Refactoring

- [ ] **REFACT-01**: Appliquer les corrections identifiées par le code review
- [ ] **REFACT-02**: Restructurer le code si le review révèle des problèmes architecturaux

### Optimisation Moteur

- [ ] **OPTIM-01**: Mesurer le jitter réel des pulses moteur (profiling avant optimisation)
- [ ] **OPTIM-02**: Implémenter busy-wait hybride pour remplacer time.sleep() dans les pulses critiques
- [ ] **OPTIM-03**: Configurer l'isolation CPU pour le Motor Service (CPU affinity)
- [ ] **OPTIM-04**: Calibrer les délais minimums selon les mesures de jitter
- [ ] **OPTIM-05**: Mesurer le jitter après optimisation (validation amélioration)
- [ ] **OPTIM-06**: Valider la fluidité et vitesse max en conditions réelles

### Architecture GPIO

- [ ] **ARCH-01**: Définir un Protocol Python pour l'abstraction GPIO backend
- [ ] **ARCH-02**: Extraire l'implémentation lgpio actuelle vers LgpioBackend
- [ ] **ARCH-03**: Implémenter PigpioBackend pour déploiements Raspberry Pi 4
- [ ] **ARCH-04**: Implémenter MockBackend pour tests sans hardware
- [ ] **ARCH-05**: Factory function pour sélection de backend via config.json
- [ ] **ARCH-06**: Tests unitaires couvrant tous les backends

## v2 Requirements

Différé pour milestone futur. Documenté mais pas dans le roadmap actuel.

### Contrôleur Externe

- **EXT-01**: Évaluer Raspberry Pi Pico comme générateur de pulses externe
- **EXT-02**: Définir protocole de communication Pi ↔ Pico
- **EXT-03**: Implémenter backend PicoBackend

### Monitoring Avancé

- **MON-01**: Dashboard temps réel du jitter moteur
- **MON-02**: Alertes si jitter dépasse seuil configurable
- **MON-03**: Historique des performances moteur

## Out of Scope

Exclusions explicites avec justification.

| Feature | Reason |
|---------|--------|
| pigpio sur Pi 5 | Incompatible avec architecture RP1 (recherche confirmée) |
| Contrôleur externe v1 | Évaluer seulement si optimisations software insuffisantes |
| Nouvelles features astro | Focus sur qualité et moteur pour ce milestone |
| Changement architecture IPC | Fonctionne bien, pas de besoin identifié |
| Migration Django version | Hors scope, stabilité prioritaire |

## Traceability

Mapping requirements → phases. Rempli lors de la création du roadmap.

| Requirement | Phase | Status |
|-------------|-------|--------|
| REVIEW-01 | — | Pending |
| REVIEW-02 | — | Pending |
| REVIEW-03 | — | Pending |
| REVIEW-04 | — | Pending |
| REFACT-01 | — | Pending |
| REFACT-02 | — | Pending |
| OPTIM-01 | — | Pending |
| OPTIM-02 | — | Pending |
| OPTIM-03 | — | Pending |
| OPTIM-04 | — | Pending |
| OPTIM-05 | — | Pending |
| OPTIM-06 | — | Pending |
| ARCH-01 | — | Pending |
| ARCH-02 | — | Pending |
| ARCH-03 | — | Pending |
| ARCH-04 | — | Pending |
| ARCH-05 | — | Pending |
| ARCH-06 | — | Pending |

**Coverage:**
- v1 requirements: 18 total
- Mapped to phases: 0
- Unmapped: 18 (awaiting roadmap)

---
*Requirements defined: 2026-01-25*
*Last updated: 2026-01-25 after initial definition*
