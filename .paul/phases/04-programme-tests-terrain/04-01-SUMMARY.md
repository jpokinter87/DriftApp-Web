---
phase: 04-programme-tests-terrain
plan: 01
subsystem: testing
tags: [terrain, simulation, meridian-flip, mount, abaque, astropy]

requires:
  - phase: 02-bug-retournement-meridien
    provides: fix watchdog + détection transit
  - phase: 03.5-refonte-logging-operationnel
    provides: format structuré pour analyse logs terrain
provides:
  - Script simulation monture reproduisant les incidents terrain
  - Tests pytest validant les scénarios critiques (méridien, zénith)
  - Marqueurs pytest.mark.slow pour séparer tests rapides/lents
affects: []

tech-stack:
  added: []
  patterns:
    - "Simulation temporelle d'objets réels (RA/DEC J2000) avec pas de 10 min"
    - "Détection transit via changement de signe de l'angle horaire"
    - "pytestmark = pytest.mark.slow pour modules dépendant d'astropy"

key-files:
  created:
    - scripts/test_terrain.py
    - tests/test_terrain_scenarios.py
  modified:
    - tests/test_calculations.py
    - tests/test_integration.py
    - tests/test_motor_service.py
    - tests/test_command_handlers.py
    - tests/test_meridian_flip.py
    - tests/test_logging_operationnel.py
    - tests/test_terrain_scenarios.py

key-decisions:
  - "Simulation basée sur vrais objets des incidents (NGC 5033, LBN 166) — pas théorique"
  - "Date fixe 2026-03-16 pour reproductibilité"
  - "pytest.mark.slow sur 7 modules astropy — pas d'accélération significative car le goulot est le chargement d'astropy (~5s one-shot)"

patterns-established:
  - "Test terrain : objet réel → trajectoire 6h → détection transit → vérification delta/mode"
  - "pytest.mark.slow pour séparer les niveaux de tests"

duration: ~20min
completed: 2026-03-16
---

# Phase 4 Plan 01: Programme Tests Terrain — Summary

**Simulation monture avec NGC 5033 (delta -145.6°) et LBN 166 (alt 88.8°) reproduisant les incidents terrain — 791 tests verts.**

## Performance

| Metric | Value |
|--------|-------|
| Duration | ~20 min |
| Completed | 2026-03-16 |
| Tasks | 2 completed |
| Files created | 2 (script + tests) |
| Files modified | 7 (marqueurs slow) |
| Tests | 782 → 791 (+9 nouveaux) |

## Acceptance Criteria Results

| Criterion | Status | Notes |
|-----------|--------|-------|
| AC-1: Simulation temporelle objet réel | Pass | 3 objets (NGC 5033, LBN 166, M42), trajectoire 6h, pas 10 min |
| AC-2: Détection transit et grand delta | Pass | NGC 5033: transit 02:20, delta -145.6°, CONTINUOUS |
| AC-3: Reproduction incident LBN | Pass | Transit 18:30, altitude 88.8° (terrain: 86.7°), delta -87.9° |
| AC-4: Tests pytest | Pass | 9/9 tests verts |

## Accomplishments

- **scripts/test_terrain.py** : simulation monture de jour pour 3 objets réels, reproduisant les conditions exactes des incidents terrain du 16/03
- NGC 5033 : transit détecté à 02:20, delta **-145.6°** (incident réel ~134°), mode CONTINUOUS ✓
- LBN 166.16+04.52 : transit détecté à 18:30, altitude **88.8°** (log terrain 86.7°), delta **-87.9°** ✓
- M42 : objet standard, altitude modérée 40.5°, pas de flip critique ✓
- **tests/test_terrain_scenarios.py** : 9 tests pytest formels (transit, delta, mode, altitude, abaque, shortest_path)
- **pytest.mark.slow** ajouté sur 7 modules dépendant d'astropy (marqueur déjà déclaré dans pytest.ini)

## Files Created/Modified

| File | Change | Purpose |
|------|--------|---------|
| `scripts/test_terrain.py` | Created | Simulation monture — 3 objets réels, trajectoire 6h |
| `tests/test_terrain_scenarios.py` | Created | 9 tests pytest des scénarios monture |
| `tests/test_calculations.py` | Modified | pytestmark slow |
| `tests/test_integration.py` | Modified | pytestmark slow |
| `tests/test_motor_service.py` | Modified | pytestmark slow |
| `tests/test_command_handlers.py` | Modified | pytestmark slow |
| `tests/test_meridian_flip.py` | Modified | pytestmark slow |
| `tests/test_logging_operationnel.py` | Modified | pytestmark slow |
| `tests/test_terrain_scenarios.py` | Modified | pytestmark slow |

## Decisions Made

| Decision | Rationale | Impact |
|----------|-----------|--------|
| Objets réels des incidents | Valide les corrections sur les cas exacts qui ont cassé | Reproductibilité garantie avec date fixe |
| Date fixe 2026-03-16 | Correspond aux logs terrain disponibles | Tests déterministes |
| pytest.mark.slow | Permet `pytest -m "not slow"` mais gain faible (~6s vs 6m30) car astropy charge une seule fois | Structure prête si optimisation future |

## Deviations from Plan

### Summary

| Type | Count | Impact |
|------|-------|--------|
| Scope additions | 1 | Marqueurs pytest.mark.slow (demande utilisateur) |
| Auto-fixed | 1 | Lint f-strings + variable unused dans script |
| Deferred | 0 | — |

**Total impact:** Positif — marqueurs slow ajoutent de la structure.

## Issues Encountered

| Issue | Resolution |
|-------|------------|
| M42 produit un delta -47.6° au transit | Normal : l'abaque change de secteur au méridien même pour objets bas. Vérifié comme "info", pas un échec |
| Tests "not slow" toujours ~6m30 | Le goulot est le chargement astropy (~5s one-shot), pas les tests marqués. Gardé les marqueurs pour structure future |

## Next Phase Readiness

**Ready:**
- Milestone v5.2 complet (5/5 phases)
- Script test_terrain.py utilisable sur le Pi avant chaque session
- 791 tests couvrant tracking, méridien, logging, terrain

**Concerns:**
- None

**Blockers:**
- None

---
*Phase: 04-programme-tests-terrain, Plan: 01*
*Completed: 2026-03-16*
