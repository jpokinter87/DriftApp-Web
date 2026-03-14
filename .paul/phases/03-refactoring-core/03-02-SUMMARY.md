---
phase: 03-refactoring-core
plan: 02
subsystem: core
tags: [dead-code, duplication, angle-utils, observatoire, tracking]

requires:
  - phase: 03-refactoring-core/01
    provides: Critical et High issues corrigées dans core/
provides:
  - Code mort supprimé (6 méthodes/variables)
  - Duplication angle centralisée dans angle_utils
  - Issues Medium/Low observatoire corrigées
affects: [phase-04-services, phase-05-tests]

tech-stack:
  added: []
  patterns:
    - "Délégation angle_utils pour toute normalisation/distance angulaire"
    - "Séparation compteurs/métadonnées dans mode_time tracking"

key-files:
  created: []
  modified:
    - core/hardware/moteur.py
    - core/config/config_loader.py
    - core/tracking/adaptive_tracking.py
    - core/tracking/tracking_state_mixin.py
    - core/tracking/tracker.py
    - core/observatoire/calculations.py
    - core/observatoire/catalogue.py
    - core/observatoire/ephemerides.py
    - core/utils/angle_utils.py
    - tests/test_moteur.py
    - tests/test_calculations.py

key-decisions:
  - "Méthodes _normaliser_angle conservées comme wrappers pour compatibilité tests"
  - "to_dict() implémenté via dataclasses.asdict() au lieu de suppression"
  - "Test -180°/180° adapté (cas limite équivalent)"

patterns-established:
  - "Toute normalisation d'angle passe par angle_utils (pas de réimplémentation)"
  - "PlanetaryEphemerides instanciée une seule fois par session de tracking"

duration: ~15min
started: 2026-03-14T00:00:00Z
completed: 2026-03-14T00:15:00Z
---

# Phase 3 Plan 02: Issues Medium/Low dans core/ — Summary

**Correction de ~16 issues Medium/Low : code mort supprimé, duplication angle centralisée, qualité observatoire améliorée.**

## Performance

| Metric | Value |
|--------|-------|
| Duration | ~15 min |
| Tasks | 1 complétée |
| Files modified | 11 (9 production + 2 tests) |

## Acceptance Criteria Results

| Criterion | Status | Notes |
|-----------|--------|-------|
| AC-1: Code mort supprimé | Pass | _valider_config, _init_parametres_rampe, _calculer_delai_rampe, gpio_handle global, to_dict NotImplementedError, if angle<0 mort |
| AC-2: Duplication angles centralisée | Pass | calculations.py délègue à angle_utils, verify_shortest_path simplifié, while→modulo |
| AC-3: Issues Medium observatoire corrigées | Pass | C-29 config, C-30 code mort, C-33 logging exception |
| AC-4: Pas de régression | Pass | 406 tests verts (1 test mort supprimé, 1 adapté) |

## Accomplishments

- 6 méthodes/variables mortes supprimées dans moteur.py (C-15, C-17, C-18, C-19)
- Centralisation complète des calculs d'angles via angle_utils (C-25, C-36, C-37)
- verify_shortest_path réduit de 43 lignes → 15 lignes (délégation angle_utils)
- shortest_angular_distance optimisé (while loops → modulo)
- PlanetaryEphemerides instanciée 1x par session (C-22)
- catalogue.py utilise SITE_LATITUDE/SITE_LONGITUDE et self.simbad (C-29, C-34)
- ephemerides.py logge les exceptions avant retour None (C-33)
- mode_time_tracker séparé compteurs/métadonnées (C-26)
- Couplage inverse web.session documenté (C-27)
- Protection heures >= 24 dans calculer_heure_passage_meridien (C-31)
- to_dict() implémenté via dataclasses.asdict() (C-05)

## Files Created/Modified

| File | Change | Purpose |
|------|--------|---------|
| `core/hardware/moteur.py` | Modified | Suppression _valider_config, _init_parametres_rampe, _calculer_delai_rampe, gpio_handle global |
| `core/config/config_loader.py` | Modified | to_dict() implémenté via asdict() |
| `core/utils/angle_utils.py` | Modified | shortest_angular_distance : while→modulo |
| `core/observatoire/calculations.py` | Modified | _normaliser_angle délègue à angle_utils, protection h>=24 |
| `core/observatoire/catalogue.py` | Modified | SITE_LATITUDE/LONGITUDE, self.simbad réutilisé |
| `core/observatoire/ephemerides.py` | Modified | Logger exception avant retour None |
| `core/tracking/adaptive_tracking.py` | Modified | verify_shortest_path délègue à angle_utils |
| `core/tracking/tracker.py` | Modified | PlanetaryEphemerides 1x, commentaire couplage web.session |
| `core/tracking/tracking_state_mixin.py` | Modified | Séparation compteurs/métadonnées mode_time |
| `tests/test_moteur.py` | Modified | Suppression test _calculer_delai_rampe |
| `tests/test_calculations.py` | Modified | Adaptation test -180°/180° |

## Decisions Made

| Decision | Rationale | Impact |
|----------|-----------|--------|
| Conserver _normaliser_angle comme wrappers | Tests existants les appellent via l'instance calc | Pas de cassure de tests |
| Implémenter to_dict() plutôt que supprimer | Plus utile qu'un NotImplementedError | Méthode fonctionnelle |
| Adapter test -180 → abs(180) | -180 et 180 sont le même angle, modulo produit 180 | Test plus robuste |

## Deviations from Plan

### Summary

| Type | Count | Impact |
|------|-------|--------|
| Auto-fixed | 1 | Test adapté (cas limite -180°) |
| Deferred | 0 | — |

**Total impact:** Minimal — correction de test frontière uniquement.

### Skill Audit

| Expected | Invoked | Notes |
|----------|---------|-------|
| /code-review | ○ | Phase de refactoring guidée par audit existant |
| /refactor-code | ○ | Corrections ciblées, pas de refactoring structurel |

## Issues Encountered

| Issue | Resolution |
|-------|------------|
| Test _normaliser_angle_180(-180) échoue après délégation à angle_utils | Adapté : abs() car -180°=180° |

## Next Phase Readiness

**Ready:**
- Phase 3 complète — 54 issues audit traitées (11 Critical/High en 03-01, ~16 Medium/Low en 03-02)
- core/ nettoyé et centralisé

**Concerns:**
- 12 fichiers tests extra avec erreurs d'import → Phase 5

**Blockers:**
- None

---
*Phase: 03-refactoring-core, Plan: 02*
*Completed: 2026-03-14*
