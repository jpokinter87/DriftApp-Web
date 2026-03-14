---
phase: 04-cicd-versioning
plan: 01
subsystem: infra, web
tags: [github-actions, ci, versioning, deploy, version-display]

provides:
  - GitHub Actions CI pipeline
  - Version 5.0.0
  - Version dynamique affichée dans l'UI web
  - Script de déploiement SSH

key-files:
  created: [.github/workflows/ci.yml, scripts/deploy.sh]
  modified: [pyproject.toml, core/config/config_loader.py, services/motor_service.py, web/templates/dashboard.html, web/static/js/dashboard.js]

completed: 2026-03-14
duration: ~12min
---

# Phase 4 Plan 01: CI/CD & Versioning — Summary

**GitHub Actions CI, version 5.0.0, version dynamique dans l'UI, script de déploiement. 451 tests passent.**

## Acceptance Criteria Results

| Criterion | Status | Notes |
|-----------|--------|-------|
| AC-1: GitHub Actions CI | Pass | Lint + tests + couverture sur push/PR |
| AC-2: Version 5.0.0 | Pass | pyproject.toml + get_version() dynamique |
| AC-3: Script de déploiement | Pass | rsync + restart services |
| (bonus) Version dans l'UI | Pass | Header + footer dynamiques via motor status |

## Files Created/Modified

| File | Change | Purpose |
|------|--------|---------|
| `.github/workflows/ci.yml` | Created | Pipeline CI (ruff + pytest + coverage) |
| `scripts/deploy.sh` | Created | Déploiement SSH vers Pi |
| `pyproject.toml` | Modified | Version 4.4.0 → 5.0.0 |
| `core/config/config_loader.py` | Modified | get_version() lit pyproject.toml |
| `services/motor_service.py` | Modified | Version dans current_status |
| `web/templates/dashboard.html` | Modified | Affiche version header + footer |
| `web/static/js/dashboard.js` | Modified | Lit version depuis motor status |

---
*Phase: 04-cicd-versioning, Plan: 01*
*Completed: 2026-03-14*
