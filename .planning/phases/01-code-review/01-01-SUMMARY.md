---
phase: 01-code-review
plan: 01
subsystem: code-quality
tags: [ruff, exceptions, linting, error-handling, bare-except, BLE001, E722]

# Dependency graph
requires: []
provides:
  - "Catalogue complet des 67 exceptions du codebase"
  - "Classification intentionnel/a-corriger pour chaque exception"
  - "15 recommandations prioritaires pour ameliorer exception handling"
affects: [02-motor-optimization, 08-quality]

# Tech tracking
tech-stack:
  added: []
  patterns:
    - "Ruff exception rules (E722, BLE001, B904) pour analyse statique"

key-files:
  created:
    - ".planning/phases/01-code-review/reports/exceptions-report.md"
  modified: []

key-decisions:
  - "52 exceptions intentionnelles (daemon, hardware, diagnostics) - pas de modification requise"
  - "15 exceptions a corriger dans core/ avec types specifiques"
  - "Recommandation: creer core/exceptions.py avec EncoderError, MotorError, AbaqueError"

patterns-established:
  - "Daemon code: except Exception acceptable pour resilience"
  - "Core business logic: utiliser exceptions specifiques"

# Metrics
duration: 8min
completed: 2026-01-25
---

# Phase 1 Plan 01: Exception Scanner Summary

**Analyse complete des 67 exceptions du codebase: 52 intentionnelles (daemon/hardware), 15 a corriger dans core/ avec types specifiques**

## Performance

- **Duration:** 8 min
- **Started:** 2026-01-25T17:30:00Z
- **Completed:** 2026-01-25T17:38:00Z
- **Tasks:** 2
- **Files created:** 1

## Accomplishments

- Scan complet avec ruff (E722, BLE001, B904) sur 100% du codebase
- Classification de chaque exception en intentionnel/a-corriger
- Identification de 15 exceptions critiques dans core/ business logic
- Recommandations priorisees par impact (quick wins vs refactoring)

## Task Commits

1. **Task 1-2: Configure ruff + classify exceptions** - `7168b41` (docs)

**Note:** Taches 1 et 2 ont ete commitees ensemble car le rapport contient a la fois les resultats du scan et la classification.

## Files Created

- `.planning/phases/01-code-review/reports/exceptions-report.md` - Rapport complet avec 67 exceptions cataloguees

## Decisions Made

1. **52 exceptions intentionnelles (sans modification):**
   - `ems22d_calibrated.py` (12): Daemon doit rester actif malgre erreurs
   - `scripts/diagnostics/` (34): Scripts de probe hardware avec fallback silencieux
   - `core/hardware/hardware_detector.py` (7): Detection hardware graceful degradation
   - `core/hardware/moteur.py` (1): GPIO cleanup sans crash

2. **15 exceptions a corriger dans core/:**
   - `core/tracking/` (7): Remplacer par `RuntimeError` pour DaemonEncoderReader
   - `core/observatoire/catalogue.py` (3): Utiliser `json.JSONDecodeError`, `OSError`, exceptions reseau
   - `core/tracking/abaque_manager.py` (3): Utiliser exceptions pandas specifiques
   - `core/config/config.py` (1): `json.JSONDecodeError, OSError`
   - `core/hardware/daemon_encoder_reader.py` (1): Ajouter `from e` pour chaining

3. **Recommandation architecture:** Creer `core/exceptions.py` avec `DriftAppError`, `EncoderError`, `MotorError`, `AbaqueError`

## Deviations from Plan

None - plan executed exactly as written.

## Issues Encountered

None - ruff scan et classification ont fonctionne comme prevu.

## User Setup Required

None - no external service configuration required.

## Next Phase Readiness

- Rapport pret pour implementation dans phase 02 (motor-optimization)
- Les 15 corrections peuvent etre integrees lors du refactoring moteur
- Pattern d'exceptions custom recommande pour ameliorer debuggabilite

---
*Phase: 01-code-review*
*Completed: 2026-01-25*
