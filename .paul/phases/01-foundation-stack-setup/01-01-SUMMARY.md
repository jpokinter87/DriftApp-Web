---
phase: 01-foundation-stack-setup
plan: 01
subsystem: ui
tags: [tailwindcss, alpinejs, django-templates, css-theme]

requires:
  - phase: none
    provides: first plan
provides:
  - Tailwind CSS v4.2.0 integrated (standalone CLI)
  - Alpine.js v3 loaded via CDN
  - Django base template with inheritance
  - Observatory dark theme palette in Tailwind @theme
affects: [02-dashboard, 03-system, 04-session]

tech-stack:
  added: [tailwindcss-v4.2.0-standalone, alpinejs-v3-cdn]
  patterns: [css-theme-via-tailwind-@theme, django-template-inheritance]

key-files:
  created: [web/templates/base.html, web/static/css/tailwind-input.css, scripts/build_css.sh]
  modified: [.gitignore]

key-decisions:
  - "Tailwind v4 @theme instead of v3 tailwind.config.js"
  - "Standalone CLI instead of npm (Raspberry Pi simplicity)"
  - "Fonts: JetBrains Mono (display) + IBM Plex Sans (body)"

patterns-established:
  - "Color naming: obs-dark, obs-panel, accent-amber, status-ok"
  - "Component class: .panel for card-like containers"
  - "Build: scripts/build_css.sh for Tailwind compilation"

duration: ~20min
completed: 2026-02-22
---

# Phase 1 Plan 01: Setup Tailwind CSS + Alpine.js + Base Template

**Tailwind CSS v4.2.0 standalone CLI + Alpine.js v3 CDN integres dans Django avec base template et palette observatory complete.**

## Performance

| Metric | Value |
|--------|-------|
| Duration | ~20 min |
| Completed | 2026-02-22 |
| Tasks | 3 completed (2 auto + 1 checkpoint) |
| Files modified | 4 |

## Acceptance Criteria Results

| Criterion | Status | Notes |
|-----------|--------|-------|
| AC-1: Tailwind compile | Pass | v4.2.0, 17KB minifie output |
| AC-2: Alpine.js fonctionnel | Pass | x-data, x-show, x-on verifies visuellement |
| AC-3: Heritage Django | Pass | 7 blocks (title, content, extra_css, extra_js, extra_head, status_indicator, nav_items, footer_extra, version) |
| AC-4: Palette migree | Pass | 20+ tokens de couleur dans @theme |

## Accomplishments

- Tailwind CSS v4 integre sans Node.js (standalone CLI ~50MB)
- Template de base Django avec header sticky, nav ambre, footer horloge
- Palette observatory complete: surfaces, textes, accents, status, shadows, animations
- Composants de base: .panel, .status-dot-ok/warn/error

## Files Created/Modified

| File | Change | Purpose |
|------|--------|---------|
| `web/templates/base.html` | Created | Template de base Django avec heritage |
| `web/static/css/tailwind-input.css` | Created | Source Tailwind avec @theme + composants |
| `scripts/build_css.sh` | Created | Script build/watch Tailwind |
| `.gitignore` | Modified | Exclusion binary tailwindcss et CSS genere |

## Decisions Made

| Decision | Rationale | Impact |
|----------|-----------|--------|
| Tailwind v4 @theme au lieu de v3 config.js | v4 est la version courante, config CSS-native | Pas de fichier config JS separé |
| Standalone CLI au lieu de npm | Pas de Node.js sur Raspberry Pi | Binary unique ~50MB |
| JetBrains Mono + IBM Plex Sans | Monospace technique + sans-serif lisible | Charge via Google Fonts CDN |

## Deviations from Plan

| Type | Count | Impact |
|------|-------|--------|
| Auto-fixed | 1 | Positif — meilleure approche |
| Scope additions | 0 | - |
| Deferred | 0 | - |

**1. Tailwind v4 au lieu de v3**
- **Found during:** Task 1
- **Issue:** Plan prevoyait tailwind.config.js (v3), CLI telecharge est v4.2.0
- **Fix:** Utilise @theme dans CSS au lieu de config JS
- **Impact:** Positif — approche plus moderne, moins de fichiers

## Skill Audit

| Expected | Invoked | Notes |
|----------|---------|-------|
| /frontend-design | ✓ | Charge avant creation base.html |
| /code-review | - | N/A (trigger: fin de phase) |
| /refactor-code | - | N/A (creation, pas modification) |

## Next Phase Readiness

**Ready:**
- Tailwind CSS compile et sert le CSS
- base.html pret pour {% extends %} par toutes les pages
- Palette complete pour commencer les migrations

**Concerns:**
- Plan 01-02 (migration tokens de design) prevu dans ROADMAP — la palette est deja migree dans 01-01, verifier si 01-02 reste necessaire

**Blockers:** None

---
*Phase: 01-foundation-stack-setup, Plan: 01*
*Completed: 2026-02-22*
