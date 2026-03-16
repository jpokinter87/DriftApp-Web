---
phase: 02-bug-retournement-meridien
plan: 01
subsystem: tracking
tags: [watchdog, systemd, meridian-flip, feedback-controller, encoder-sync]

requires:
  - phase: 01-persistance-logs
    provides: logs persistés 7 jours pour diagnostic post-flip
provides:
  - Watchdog thread dédié survivant aux rotations bloquantes
  - Détection et logging explicite des transits méridien
  - Re-synchronisation encodeur après grands mouvements
  - Fix tuple unpacking TrackingHandler.start()
affects: [04-programme-tests-terrain]

tech-stack:
  added: []
  patterns:
    - "Thread daemon dédié pour watchdog systemd (indépendant de la boucle principale)"
    - "Re-sync encoder_offset après correction > 30°"
    - "Logging explicite des transits méridien dans goto_log"

key-files:
  created:
    - tests/test_meridian_flip.py
  modified:
    - services/motor_service.py
    - services/command_handlers.py
    - core/tracking/tracking_corrections_mixin.py

key-decisions:
  - "Thread daemon watchdog au lieu de callback dans FeedbackController — non-invasif"
  - "Re-sync encodeur uniquement pour delta > 30° — évite surcharge sur petites corrections"
  - "Seuil 30° existant réutilisé pour détection transit — pas de nouveau paramètre"

patterns-established:
  - "Watchdog systemd sur thread dédié pour survivre aux opérations bloquantes longues"
  - "Logging transit méridien : reason='meridian_transit' dans goto_log"

duration: ~20min
completed: 2026-03-16
---

# Phase 2 Plan 01: Bug Retournement Méridien — Summary

**Watchdog thread dédié corrigeant le kill systemd pendant les rotations méridien, + 4 fixes tracking et 18 tests.**

## Performance

| Metric | Value |
|--------|-------|
| Duration | ~20 min |
| Completed | 2026-03-16 |
| Tasks | 3 completed |
| Files modified | 4 (3 production + 1 test créé) |
| Tests | 754 → 771 (+18 nouveaux, dont 1 échec pré-existant health_views) |

## Acceptance Criteria Results

| Criterion | Status | Notes |
|-----------|--------|-------|
| AC-1: Watchdog survit aux longues rotations | Pass | Thread daemon heartbeat indépendant, test confirme survie pendant 0.5s de blocage |
| AC-2: TrackingHandler.start() décompacte le tuple | Pass | `success, message = session.start()` — échec correctement détecté |
| AC-3: Normalisation position_relative sans feedback | Pass | 350° + 15° = 5° (pas 365°), 10° - 15° = 355° (pas -5°) |
| AC-4: Re-sync encodeur et détection transit | Pass | offset recalculé après delta > 30°, log "TRANSIT MÉRIDIEN détecté", goto_log entry |
| AC-5: Tests de traversée méridien | Pass | 18/18 tests verts |

## Accomplishments

- **Cause racine corrigée** : Thread watchdog dédié dans motor_service.py — le heartbeat systemd continue pendant les rotations bloquantes de 100+ secondes (flip méridien), évitant le kill à 30s qui causait la perte de session
- **Bug tuple unpacking** corrigé dans TrackingHandler.start() — `(False, "erreur")` est truthy en Python, le succès n'était jamais vérifié
- **position_relative normalisée** dans le chemin sans feedback via `% 360` (aligné avec le chemin feedback)
- **Re-sync encoder_offset** après grands mouvements — évite la dérive progressive post-méridien
- **Détection transit méridien** avec log INFO explicite et enregistrement dans goto_log (reason='meridian_transit')
- **18 tests dédiés** couvrant watchdog, unpacking, normalisation, re-sync, détection, flag lifecycle, timeout acceptable

## Files Created/Modified

| File | Change | Purpose |
|------|--------|---------|
| `services/motor_service.py` | Modified | Thread watchdog dédié `_start_watchdog_thread()`, heartbeat retiré de la boucle principale |
| `services/command_handlers.py` | Modified | `success, message = session.start()` — tuple correctement décompacté |
| `core/tracking/tracking_corrections_mixin.py` | Modified | Normalisation `% 360`, re-sync encodeur, flag lifecycle, détection transit, `_resync_encoder_offset()` |
| `tests/test_meridian_flip.py` | Created | 18 tests : watchdog (4), unpacking (2), normalisation (3), re-sync (2), transit (3), flag (2), timeout (2) |

## Decisions Made

| Decision | Rationale | Impact |
|----------|-----------|--------|
| Thread daemon watchdog | Non-invasif, ne modifie ni FeedbackController ni tracking — seul motor_service touché | Le watchdog ne détecte plus les freezes du main thread, mais un freeze réel serait visible via status stale |
| Re-sync uniquement pour delta > 30° | Les petites corrections n'ont pas de dérive significative d'offset | Pas de surcharge I²C sur corrections normales |
| Réutilisation du seuil 30° existant | LARGE_MOVEMENT_THRESHOLD est déjà le bon critère de détection | Pas de nouveau paramètre de config à gérer |

## Deviations from Plan

### Summary

| Type | Count | Impact |
|------|-------|--------|
| Auto-fixed | 1 | Fixture test adaptée (MotorConfig dict vs class) |
| Deferred | 0 | — |

**Total impact:** Minimal — adaptation fixture uniquement.

### Auto-fixed Issues

**1. Fixture tracking_session avec mauvais type de config moteur**
- **Found during:** Task 3 (tests)
- **Issue:** `MoteurSimule(MotorConfig())` rejeté par `parse_motor_config` qui attend un dataclass avec `gpio_pins` ou un dict
- **Fix:** Utilisation de `load_config()` réelle + `MoteurSimule()` sans argument (pattern test_tracker_unit)
- **Verification:** 18/18 tests verts

## Issues Encountered

| Issue | Resolution |
|-------|------------|
| `timestamp` variable inutilisée dans tracking_corrections_mixin.py:55 | Pré-existant, hors scope — lint warning documenté |
| test_check_update_success échoue (771 pass, 1 fail) | Pré-existant — vérifie si git update dispo, non lié aux changements |

## Next Phase Readiness

**Ready:**
- Watchdog thread protège le motor_service pendant les longues rotations
- Transit méridien détecté et loggé pour diagnostic terrain
- Le fix est déployable sur le Pi de production via git pull + restart service

**Concerns:**
- Le watchdog thread ne détecte plus les freezes du main thread (compromis accepté)
- Le fix doit être testé sur le terrain au prochain transit méridien pour confirmer

**Blockers:**
- None

---
*Phase: 02-bug-retournement-meridien, Plan: 01*
*Completed: 2026-03-16*
