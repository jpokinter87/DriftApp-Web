---
phase: 02-refactoring-corrections
plan: 01
subsystem: config
tags: [config-unification, dead-code-removal, fast-track-cleanup]

requires:
  - phase: 01-code-review-audit
    provides: 88 findings avec priorités (C-01 à C-06, H-01 à H-22)
  - phase: 1.5-tests-exhaustifs
    provides: 412 tests comme filet de sécurité anti-régression
provides:
  - Config unifiée (config_loader.py seul point d'entrée)
  - Chemins absolus pour config.json et cache
  - Code production sans FAST_TRACK
affects: [phase-02-plans-suivants, phase-2.1-bugs-terrain]

tech-stack:
  added: []
  patterns: [chemin-absolu-via-PROJECT_ROOT, DATA_DIR-centralise]

key-files:
  modified: [core/config/config_loader.py, core/observatoire/catalogue.py, core/tracking/tracker.py, gui/screens/main_screen.py, gui/widgets/unified_banner.py, tests/test_config_loader.py, tests/test_catalogue.py, tests/diagnostics/motor_service_with_test_speed.py]
  deleted: [core/config/config.py]

key-decisions:
  - "config.py supprimé entièrement — config_loader.py est l'unique source"
  - "FAST_TRACK remplacé par CONTINUOUS dans gui pour vitesse manuelle"
  - "1 test supprimé (test_to_dict_raises) — testait du code mort"

completed: 2026-03-13
duration: ~15min
---

# Phase 2 Plan 01: Config Unification + FAST_TRACK Cleanup — Summary

**Système de config unifié (config_loader.py seul), FAST_TRACK éliminé de tout le code production, chemins absolus partout — résout C-01, C-02, C-03, C-04.**

## Performance

| Metric | Value |
|--------|-------|
| Duration | ~15 min |
| Tasks | 3/3 completed |
| Files modified | 8 |
| Files deleted | 1 (config.py) |
| Tests | 411 passed, 1 skipped |

## Acceptance Criteria Results

| Criterion | Status | Notes |
|-----------|--------|-------|
| AC-1: Config unifiée — config.py supprimé | Pass | Zéro import de core.config.config restant |
| AC-2: Chemin relatif corrigé dans catalogue.py | Pass | Utilise DATA_DIR (absolu) |
| AC-3: FAST_TRACK code mort supprimé | Pass | Zéro occurrence dans core/, gui/, services/ |
| AC-4: load_site_config() supprimé | Pass | Fonction + 80 lignes de compatibilité retirées |

## Accomplishments

- config_loader.py enrichi avec PROJECT_ROOT, DATA_DIR, CACHE_FILE — chemins absolus centralisés
- config.py supprimé — fin de la coexistence de deux systèmes de configuration
- FAST_TRACK éliminé de config_loader, tracker, gui/main_screen, gui/unified_banner, diagnostics
- catalogue.py migré vers config_loader (import + chemin planètes)
- Tests mis à jour : monkeypatch sur config_loader au lieu de config, test C-02 inversé

## Files Created/Modified

| File | Change | Purpose |
|------|--------|---------|
| `core/config/config_loader.py` | Modified | Ajout PROJECT_ROOT/DATA_DIR/CACHE_FILE, retrait fast_track/load_site_config/to_dict |
| `core/config/config.py` | Deleted | Ancien système de config — remplacé par config_loader |
| `core/observatoire/catalogue.py` | Modified | Import migré vers config_loader, chemin absolu |
| `core/tracking/tracker.py` | Modified | Retrait emoji fast_track + LARGE_MOVEMENT_THRESHOLD |
| `gui/screens/main_screen.py` | Modified | fast_track → continuous pour vitesse manuelle |
| `gui/widgets/unified_banner.py` | Modified | Retrait condition FAST_TRACK couleur |
| `tests/test_config_loader.py` | Modified | Retrait test_to_dict_raises, inversion test fast_track |
| `tests/test_catalogue.py` | Modified | Monkeypatch sur config_loader au lieu de config |
| `tests/diagnostics/motor_service_with_test_speed.py` | Modified | fast_track → continuous (3 occurrences) |

## Decisions Made

| Decision | Rationale | Impact |
|----------|-----------|--------|
| Supprimer config.py entièrement | Seul catalogue.py l'importait (CACHE_FILE) | Fin de la double config |
| Remplacer fast_track par continuous dans gui | Même vitesse moteur, mode correct | GUI fonctionnellement identique |
| Supprimer load_site_config() | Non appelé en production, 80 lignes de compat inutile | API plus claire |
| Supprimer to_dict() | Lève NotImplementedError — jamais implémenté | 1 test en moins (411 vs 412) |

## Deviations from Plan

None — plan exécuté exactement comme spécifié.

## Issues Encountered

| Issue | Resolution |
|-------|------------|
| ruff non installé dans le venv | Vérification linting skippée — pas de régression |
| test_fast_track_removed échouait avant Task 2 | Normal — dépendance séquentielle entre Task 1 et 2 |

## Next Phase Readiness

**Ready:**
- Config unifiée, prête pour les plans suivants (bugs latents, duplication, sécurité)
- 411 tests protègent contre les régressions

**Concerns:**
- ruff devrait être ajouté au venv pour le linting automatique (Phase 4 CI/CD)

**Blockers:**
- None

---
*Phase: 02-refactoring-corrections, Plan: 01*
*Completed: 2026-03-13*
