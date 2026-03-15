# Project State

## Project Reference

See: .paul/PROJECT.md (updated 2026-03-15)

**Core value:** Maintenir automatiquement le cimier de la coupole face a l'ouverture du telescope pendant toute la duree d'une session d'astrophotographie.
**Current focus:** v5.2 Stabilité Terrain — Phase 2 Bug Retournement Méridien

## Current Position

Milestone: v5.2 Stabilité Terrain
Phase: 2 of 4 (Bug Retournement Méridien)
Plan: Not started
Status: Ready to plan
Last activity: 2026-03-15 — Phase 1 complete, transitioned to Phase 2

Progress:
- v5.2 Stabilité Terrain: [██░░░░░░░░] 25%
- Phase 1: [██████████] 100% ✓

## Loop Position

Current loop state:
```
PLAN ──▶ APPLY ──▶ UNIFY
  ○        ○        ○     [Ready for next PLAN]
```

## Accumulated Context

### Decisions
- Rétention 7 jours + fallback sécurité (200/500 fichiers max)
- Sauvegarde session robuste : try/except + fallback _save_session_to_file
- Source de vérité: DriftApp_v4_6 (production Pi)
- Tests alignés sur API production (pas de modification code prod)

### Deferred Issues
- ObjectListView.get_objets_disponibles() bug production (web/tracking/views.py:100) → Phase 3
- Routes /api/hardware/park/, calibrate/, end-session/ non implémentées → Phase 3

### Blockers/Concerns
None.

### Git State
Last commit: 9157f51
Branch: main

## Session Continuity

Last session: 2026-03-15
Stopped at: Phase 1 complete, ready to plan Phase 2
Next action: /paul:plan for Phase 2
Resume file: .paul/ROADMAP.md
Resume context: Logs persistés 7j, sauvegarde robuste, 754 tests verts

---
*STATE.md — Updated after every significant action*
