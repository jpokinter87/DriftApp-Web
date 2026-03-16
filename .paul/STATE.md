# Project State

## Project Reference

See: .paul/PROJECT.md (updated 2026-03-15)

**Core value:** Maintenir automatiquement le cimier de la coupole face a l'ouverture du telescope pendant toute la duree d'une session d'astrophotographie.
**Current focus:** v5.2 Stabilité Terrain — Phase 2 complete, ready for Phase 3

## Current Position

Milestone: v5.2 Stabilité Terrain
Phase: 2 of 4 (Bug Retournement Méridien) — Complete ✓
Plan: 02-01 complete
Status: Ready for next PLAN
Last activity: 2026-03-16 — Phase 2 complete, transitioned to Phase 3

Progress:
- v5.2 Stabilité Terrain: [█████░░░░░] 50%
- Phase 1: [██████████] 100% ✓
- Phase 2: [██████████] 100% ✓

## Loop Position

Current loop state:
```
PLAN ──▶ APPLY ──▶ UNIFY
  ✓        ✓        ✓     [Loop complete — ready for next PLAN]
```

## Accumulated Context

### Decisions
- Rétention 7 jours + fallback sécurité (200/500 fichiers max)
- Sauvegarde session robuste : try/except + fallback _save_session_to_file
- Source de vérité: DriftApp_v4_6 (production Pi)
- Tests alignés sur API production (pas de modification code prod)
- Thread daemon watchdog (non-invasif, seul motor_service touché)
- Re-sync encodeur uniquement pour delta > 30°

### Deferred Issues
- ObjectListView.get_objets_disponibles() bug production (web/tracking/views.py:100) → Phase 3
- Routes /api/hardware/park/, calibrate/, end-session/ non implémentées → Phase 3

### Blockers/Concerns
None.

### Git State
Last commit: 25b3f4c
Branch: main

## Session Continuity

Last session: 2026-03-16
Stopped at: Phase 2 complete, ready to plan Phase 3
Next action: /paul:plan for Phase 3
Resume file: .paul/ROADMAP.md
Resume context: Watchdog thread + 4 fixes méridien, 771 tests verts

---
*STATE.md — Updated after every significant action*
