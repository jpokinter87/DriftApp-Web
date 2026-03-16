---
phase: 03-bugs-connus
plan: 01
subsystem: api
tags: [catalogue, routes, stubs, objectlist]

requires:
  - phase: none
    provides: bugs déferrés depuis v5.1
provides:
  - Méthode get_objets_disponibles() dans GestionnaireCatalogue
  - Routes stub park/calibrate/end-session (501 Not Implemented)
affects: []

tech-stack:
  added: []
  patterns: []

key-files:
  created: []
  modified:
    - core/observatoire/catalogue.py
    - web/hardware/views.py
    - web/hardware/urls.py
    - tests/test_web_views.py

key-decisions:
  - "get_objets_disponibles() retourne self.objets.values() — lecture cache uniquement"
  - "Routes stub 501 au lieu de 404 — indique fonctionnalité prévue mais pas encore implémentée"

patterns-established: []

duration: ~5min
completed: 2026-03-16
---

# Phase 3 Plan 01: Bugs Connus — Summary

**get_objets_disponibles() implémenté + 3 routes stub 501 — 771 tests verts.**

## Performance

| Metric | Value |
|--------|-------|
| Duration | ~5 min |
| Completed | 2026-03-16 |
| Tasks | 3 completed |
| Files modified | 4 |
| Tests | 771 (4 tests existants adaptés) |

## Acceptance Criteria Results

| Criterion | Status | Notes |
|-----------|--------|-------|
| AC-1: ObjectListView retourne la liste | Pass | 50 objets retournés depuis le cache |
| AC-2: Routes stub retournent 501 | Pass | park, calibrate, end-session → 501 |
| AC-3: Tests couvrent les corrections | Pass | 34/34 tests web views verts |

## Accomplishments

- `get_objets_disponibles()` ajouté à GestionnaireCatalogue — retourne `list(self.objets.values())` depuis le cache local
- 3 vues stub (ParkView, CalibrateView, EndSessionView) retournant 501 Not Implemented
- 3 routes ajoutées dans hardware/urls.py
- 4 tests existants adaptés (3 de 404→501, 1 de AttributeError→200 avec assertions)

## Files Created/Modified

| File | Change | Purpose |
|------|--------|---------|
| `core/observatoire/catalogue.py` | Modified | Ajout `get_objets_disponibles()` + import List |
| `web/hardware/views.py` | Modified | 3 vues stub (ParkView, CalibrateView, EndSessionView) |
| `web/hardware/urls.py` | Modified | 3 routes (park/, calibrate/, end-session/) |
| `tests/test_web_views.py` | Modified | 4 tests adaptés (TestStubRoutes, TestObjectListView) |

## Decisions Made

| Decision | Rationale | Impact |
|----------|-----------|--------|
| Cache local uniquement | Pas de requête SIMBAD pour lister — performance et offline | Retourne seulement les objets déjà recherchés |
| 501 au lieu de 404 | Sémantique HTTP correcte : fonctionnalité prévue mais pas implémentée | Frontend peut afficher un message adapté |

## Deviations from Plan

### Summary

| Type | Count | Impact |
|------|-------|--------|
| Auto-fixed | 1 | 4 tests existants adaptés aux nouvelles réponses |
| Deferred | 0 | — |

**Total impact:** Minimal.

### Auto-fixed Issues

**1. Tests existants attendaient 404/AttributeError au lieu de 501/200**
- **Found during:** Task 3
- **Issue:** 3 tests TestNonExistentRoutes attendaient 404, 1 test attendait AttributeError
- **Fix:** Renommé en TestStubRoutes (501), test ObjectListView vérifie 200 + structure
- **Verification:** 34/34 tests verts

## Issues Encountered

None.

## Next Phase Readiness

**Ready:**
- Les 2 issues déferrées depuis v5.1 sont résolues
- Phase 4 (Programme Tests Terrain) peut démarrer

**Concerns:**
- None

**Blockers:**
- None

---
*Phase: 03-bugs-connus, Plan: 01*
*Completed: 2026-03-16*
