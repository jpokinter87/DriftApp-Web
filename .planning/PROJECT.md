# DriftApp Web v5.0 - Amélioration

## What This Is

Système de contrôle de coupole astronomique pour l'Observatoire Ubik. Application web Django pilotant un moteur pas-à-pas NEMA via Raspberry Pi 4/5, avec suivi astronomique automatique et architecture trois processus (Django, Motor Service, Encoder Daemon).

Ce milestone vise à améliorer la qualité du code existant et la fluidité du moteur lors des déplacements rapides.

## Core Value

**Le moteur doit pouvoir être piloté de manière fluide et rapide lors des GOTO, sans régression sur le suivi astronomique existant.**

## Requirements

### Validated

<!-- Fonctionnalités existantes, éprouvées en production -->

- ✓ **Architecture trois processus** — IPC via JSON en /dev/shm, découplage complet
- ✓ **Contrôle moteur lgpio** — Rotation, GOTO, JOG, modes adaptatifs
- ✓ **Rampe d'accélération S-curve** — Warm-up, accélération, décélération fluides
- ✓ **Suivi astronomique** — TrackingSession avec mixins, corrections périodiques
- ✓ **Modes adaptatifs** — NORMAL/CRITICAL/CONTINUOUS selon altitude
- ✓ **Lecture encodeur daemon** — DaemonEncoderReader singleton, 50 Hz
- ✓ **Interface web Django** — Dashboard, boussole, contrôles, historique sessions
- ✓ **Feedback controller** — Boucle fermée pour précision GOTO
- ✓ **Abaque interpolation** — Loi_coupole.xlsx, 275 points mesurés
- ✓ **Détection auto Pi 4/5** — hardware_detector.py
- ✓ **Mode simulation** — Développement sans matériel

### Active

<!-- Scope de ce milestone — révisé après recherche -->

- [ ] **REVIEW-01**: Code review complet du codebase
- [ ] **REFACT-01**: Refactoring selon recommandations du review (si nécessaire)
- [ ] **OPTIM-01**: Profiler le jitter réel des pulses moteur
- [ ] **OPTIM-02**: Remplacer time.sleep() par busy-wait hybride pour timing précis
- [ ] **OPTIM-03**: Isolation CPU du Motor Service (CPU core affinity)
- [ ] **OPTIM-04**: Validation fluidité et vitesse max après optimisations
- [ ] **ARCH-01**: Abstraction GPIO (Protocol) pour backends interchangeables
- [ ] **ARCH-02**: Backend pigpio pour déploiements Pi 4 (optionnel)

### Out of Scope

- Modification du câblage hardware — les backends utilisent les mêmes GPIOs
- Changement d'architecture IPC — fonctionne bien, pas de régression
- Nouvelles fonctionnalités astronomiques — focus sur qualité et moteur
- pigpio sur Pi 5 — incompatible avec architecture RP1 (recherche confirmée)
- Contrôleur externe (Pico, Arduino) — évaluer seulement si optimisations insuffisantes

## Context

**Situation actuelle:**
- L'application fonctionne en production à l'Observatoire Ubik
- Le suivi astronomique (vitesses lentes) est satisfaisant
- Les déplacements rapides (GOTO, méridien) présentent des à-coups audibles
- La console constructeur (code fermé) obtient ~1.5x la vitesse max et plus de fluidité

**Recherche effectuée (2026-01-25):**
- **Cause confirmée**: `time.sleep()` + scheduler Linux = jitter 100µs à plusieurs ms
- **pigpio incompatible Pi 5**: Le chip RP1 a changé l'architecture GPIO, pigpio ne fonctionne pas
- **Aucune lib DMA sur Pi 5**: Actuellement, aucune librairie ne fournit de timing DMA sur Pi 5
- **Solution recommandée**: Optimiser lgpio (busy-wait, isolation CPU) avant d'envisager hardware externe
- Détails: `.planning/research/`

**Codebase existant:**
- ~315 tests passants
- Architecture bien documentée (.planning/codebase/)
- Patterns établis : Singleton, Mixins, Strategy
- 17+ occurrences de bare `except:` à corriger (identifiées par recherche)

## Constraints

- **Production active**: L'observatoire utilise le système → rollback possible obligatoire
- **Hardware fixe**: Raspberry Pi 4/5, moteur NEMA, driver DM556T, encodeur EMS22A
- **Compatibilité**: Le backend lgpio doit rester fonctionnel après les changements
- **Tests**: Pas de régression sur les 315+ tests existants

## Key Decisions

| Decision | Rationale | Outcome |
|----------|-----------|---------|
| Optimiser lgpio d'abord | pigpio incompatible Pi 5, optimisation peut suffire | — Pending |
| Busy-wait au lieu de sleep | time.sleep() cause le jitter, busy-wait plus précis | — Pending |
| Abstraction GPIO (Protocol) | Permet backends interchangeables sans changer appelants | — Pending |
| Code review avant refactoring | Identifier les vrais problèmes avant de changer | — Pending |
| pigpio optionnel Pi 4 only | Incompatible Pi 5, mais utile si déploiement Pi 4 | — Pending |

---
*Last updated: 2026-01-25 after research phase*
