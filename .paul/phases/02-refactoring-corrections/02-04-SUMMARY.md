---
phase: 02-refactoring-corrections
plan: 04
subsystem: web, security
tags: [django-security, secret-key, debug, allowed-hosts, input-validation]

requires:
  - phase: 02-refactoring-corrections
    provides: MotorServiceClient unifié (plan 02-03)
provides:
  - Django settings sécurisé (env vars)
  - Validation speed dans API views
  - Admin retiré (surface d'attaque réduite)
affects: [phase-4-cicd]

key-files:
  modified: [web/driftapp_web/settings.py, web/driftapp_web/urls.py, web/hardware/views.py, tests/test_web_views.py]

key-decisions:
  - "ALLOWED_HOSTS='*' en DEBUG, restreint en production — Django ne supporte pas wildcards IP"
  - "Speed borné 0.00001-0.01 (limites physiques du moteur)"
  - "DRIFTAPP_DEBUG=1 dans tests pour ALLOWED_HOSTS compatible"

completed: 2026-03-14
duration: ~12min
---

# Phase 2 Plan 04: Sécurité Django — Summary

**Django settings sécurisé (SECRET_KEY/DEBUG/ALLOWED_HOSTS via env vars), validation speed dans API, admin retiré. 412 tests passent.**

## Performance

| Metric | Value |
|--------|-------|
| Duration | ~12 min |
| Tasks | 3/3 completed |
| Files modified | 4 |
| Tests | 412 passed (+3 nouveaux) |

## Acceptance Criteria Results

| Criterion | Status | Notes |
|-----------|--------|-------|
| AC-1: SECRET_KEY sécurisé | Pass | Via DJANGO_SECRET_KEY env var, fallback dev |
| AC-2: DEBUG et ALLOWED_HOSTS configurables | Pass | DRIFTAPP_DEBUG=1 pour activer, hosts restreints en prod |
| AC-3: Validation speed dans API views | Pass | Type + bornes (0.00001-0.01), 400 sinon |
| AC-4: Admin retiré | Pass | Route et import supprimés |

## Files Created/Modified

| File | Change | Purpose |
|------|--------|---------|
| `web/driftapp_web/settings.py` | Modified | SECRET_KEY, DEBUG, ALLOWED_HOSTS via env vars + mkdir logs |
| `web/driftapp_web/urls.py` | Modified | Admin retiré |
| `web/hardware/views.py` | Modified | Validation speed (type + bornes) dans GotoView/JogView |
| `tests/test_web_views.py` | Modified | +3 tests validation speed + DRIFTAPP_DEBUG=1 |

## Deviations from Plan

| Type | Description |
|------|-------------|
| Auto-fixed | ALLOWED_HOSTS avec wildcards IP (`192.168.1.*`) invalide en Django — remplacé par `*` en DEBUG, restreint en prod |
| Auto-fixed | Tests web nécessitaient DRIFTAPP_DEBUG=1 — ajouté dans le setup des tests |

## Next Phase Readiness

**Ready:**
- Django sécurisé, API validée, prêt pour la suite
- 412 tests protègent contre les régressions

**Concerns:**
- En production sur le Pi, il faudra définir DJANGO_SECRET_KEY et éventuellement DJANGO_ALLOWED_HOSTS

**Blockers:**
- None

---
*Phase: 02-refactoring-corrections, Plan: 04*
*Completed: 2026-03-14*
