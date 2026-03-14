---
phase: 02-refactoring-corrections
plan: 02
subsystem: hardware, catalogue, web
tags: [bugfix, circular-mean, timeout, planet-search, api]

requires:
  - phase: 02-refactoring-corrections
    provides: Config unifiée (plan 02-01)
provides:
  - read_angle() robuste avec timeout sur tout statut
  - read_stable() avec moyenne circulaire correcte à 0°/360°
  - Résultat planète normalisé (nom, is_planet, source)
  - ObjectListView fonctionnel
affects: [phase-2.1-bugs-terrain]

key-files:
  modified: [core/hardware/moteur.py, core/observatoire/catalogue.py, web/tracking/views.py, tests/test_daemon_encoder_reader.py, tests/test_catalogue.py, tests/test_web_views.py]

key-decisions:
  - "Moyenne circulaire via atan2(sin,cos) pour read_stable()"
  - "Statut inconnu → retour angle après timeout (pas d'exception)"
  - "Planètes : clé 'nom' + is_planet + source pour cohérence avec SIMBAD"

completed: 2026-03-14
duration: ~10min
---

# Phase 2 Plan 02: Bugs Latents — Summary

**4 bugs corrigés : read_angle() timeout (H-04), read_stable() moyenne circulaire (H-01), résultat planète normalisé (H-14), ObjectListView (M-27). 416 tests passent.**

## Performance

| Metric | Value |
|--------|-------|
| Duration | ~10 min |
| Tasks | 3/3 completed |
| Files modified | 6 |
| Tests | 416 passed (+5 nouveaux, 0 skipped) |

## Acceptance Criteria Results

| Criterion | Status | Notes |
|-----------|--------|-------|
| AC-1: read_angle() timeout sur statut inconnu | Pass | CALIBRATING, ERROR → retour après timeout |
| AC-2: read_stable() moyenne circulaire | Pass | [359.5, 0.2, 0.5] → ~0.07° |
| AC-3: Résultat planète normalisé | Pass | "nom", is_planet=True, source="ephemerides" |
| AC-4: ObjectListView ne crashe pas | Pass | catalogue.objets au lieu de méthode inexistante |

## Files Created/Modified

| File | Change | Purpose |
|------|--------|---------|
| `core/hardware/moteur.py` | Modified | H-04: timeout statut inconnu, H-01: moyenne circulaire |
| `core/observatoire/catalogue.py` | Modified | H-14: nom+is_planet+source dans résultat planète |
| `web/tracking/views.py` | Modified | M-27: catalogue.objets au lieu de get_objets_disponibles() |
| `tests/test_daemon_encoder_reader.py` | Modified | +5 tests (timeout, moyenne circulaire) |
| `tests/test_catalogue.py` | Modified | Test H-14 corrigé |
| `tests/test_web_views.py` | Modified | +1 test ObjectListView |

## Deviations from Plan

None — plan exécuté exactement comme spécifié.

## Next Phase Readiness

**Ready:**
- Bugs critiques hardware corrigés, base plus solide pour la suite
- 416 tests protègent contre les régressions

**Concerns:**
- None

**Blockers:**
- None

---
*Phase: 02-refactoring-corrections, Plan: 02*
*Completed: 2026-03-14*
