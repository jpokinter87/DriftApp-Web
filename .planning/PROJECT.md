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

<!-- Scope de ce milestone -->

- [ ] **REVIEW-01**: Code review complet du codebase
- [ ] **REFACT-01**: Refactoring selon recommandations du review (si nécessaire)
- [ ] **MOTOR-01**: Backend pigpio implémenté en parallèle de lgpio
- [ ] **MOTOR-02**: Abstraction commune GPIO (interface/protocol) pour lgpio et pigpio
- [ ] **MOTOR-03**: Switch configurable entre backends via config.json
- [ ] **MOTOR-04**: Tests de performance comparatifs lgpio vs pigpio
- [ ] **MOTOR-05**: Validation fluidité et vitesse max avec pigpio

### Out of Scope

- Modification du câblage hardware — les deux backends utilisent les mêmes GPIOs
- Changement d'architecture IPC — fonctionne bien, pas de régression
- Nouvelles fonctionnalités astronomiques — focus sur qualité et moteur
- Migration vers un contrôleur externe (Arduino, Tic) — solution software first

## Context

**Situation actuelle:**
- L'application fonctionne en production à l'Observatoire Ubik
- Le suivi astronomique (vitesses lentes) est satisfaisant
- Les déplacements rapides (GOTO, méridien) présentent des à-coups audibles
- La console constructeur (code fermé) obtient ~1.5x la vitesse max et plus de fluidité
- Cause probable : lgpio utilise du software timing, sensible au scheduler Linux

**Hypothèse technique:**
- pigpio utilise le DMA du Raspberry Pi pour un timing hardware des pulses
- Devrait éliminer les micro-variations de timing causant les à-coups
- Même câblage GPIO, changement uniquement côté software

**Codebase existant:**
- ~315 tests passants
- Architecture bien documentée (.planning/codebase/)
- Patterns établis : Singleton, Mixins, Strategy

## Constraints

- **Production active**: L'observatoire utilise le système → rollback possible obligatoire
- **Hardware fixe**: Raspberry Pi 4/5, moteur NEMA, driver DM556T, encodeur EMS22A
- **Compatibilité**: Le backend lgpio doit rester fonctionnel après les changements
- **Tests**: Pas de régression sur les 315+ tests existants

## Key Decisions

| Decision | Rationale | Outcome |
|----------|-----------|---------|
| Backend switchable par config | Permet de tester pigpio sans casser la prod | — Pending |
| Abstraction GPIO commune | Évite duplication de code entre backends | — Pending |
| Code review avant refactoring | Identifier les vrais problèmes avant de changer | — Pending |

---
*Last updated: 2026-01-25 after initialization*
