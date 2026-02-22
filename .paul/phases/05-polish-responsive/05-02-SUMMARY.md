---
phase: 05-polish-responsive
plan: 02
subsystem: ui
tags: [legacy-cleanup, accessibility, aria, focus-ring]

requires:
  - phase: 05-01
    provides: Shared CSS factorized, responsive breakpoints, dead files removed
provides:
  - Legacy CSS cleaned from dashboard.css and tailwind-input.css
  - Accessibility baseline (aria landmarks, focus ring, dialog roles)
  - Milestone v5.0 complete
affects: []

tech-stack:
  added: []
  patterns: [focus-visible global rule, aria landmarks on base template]

key-files:
  modified:
    - web/static/css/dashboard.css
    - web/static/css/tailwind-input.css
    - web/templates/base.html
    - web/templates/dashboard.html
    - web/templates/session.html

key-decisions:
  - "Keep .mode-value.normal/.critical/.continuous (used by JS) but remove .mode-normal text color duplicates"
  - "Keep timer-widget in HTML/JS but remove CSS rule (HTML already has hidden class)"
  - "focus-visible with amber outline matches observatory theme"

patterns-established:
  - "All aria landmarks on base.html propagate to all pages"
  - "focus-visible global rule in @layer base for keyboard accessibility"

duration: ~8min
completed: 2026-02-22
---

# Phase 5 Plan 02: Legacy CSS Cleanup & Accessibility Summary

**Cleaned legacy CSS (fast_track, unused modals, duplicate classes) and added accessibility baseline (aria, focus ring, dialog roles)**

## Performance

| Metric | Value |
|--------|-------|
| Duration | ~8min |
| Completed | 2026-02-22 |
| Tasks | 2 completed + 1 checkpoint |
| Files modified | 5 |
| CSS output reduced | 37057 → 35342 bytes (-1.7KB) |

## Acceptance Criteria Results

| Criterion | Status | Notes |
|-----------|--------|-------|
| AC-1: Legacy CSS nettoye | Pass | fast_track, timer-widget, mode doublons, unused modals removed |
| AC-2: Accessibilite base.html | Pass | aria-label on nav, focus-visible global rule |
| AC-3: Accessibilite dashboard | Pass | aria on canvas, role="dialog" on modals |
| AC-4: Zero regression | Pass | Human verification approved |

## Accomplishments

- Removed legacy fast_track CSS (mode removed in v4.4)
- Removed unused .modal-overlay/.modal-content/.modal-header/.modal-footer from tailwind-input.css
- Removed duplicate .hidden, .mode-normal/.critical/.continuous, .timer-widget from dashboard.css
- Added aria-label on nav, canvas compass, chart canvases
- Added role="dialog" aria-modal="true" on GOTO and Update modals
- Added :focus-visible global rule with amber outline for keyboard navigation

## Files Created/Modified

| File | Change | Purpose |
|------|--------|---------|
| `web/static/css/dashboard.css` | Modified | Removed fast_track, timer-widget, mode doublons, .hidden |
| `web/static/css/tailwind-input.css` | Modified | Removed unused modal components, added focus-visible |
| `web/templates/base.html` | Modified | Added aria-label on nav |
| `web/templates/dashboard.html` | Modified | Added aria on canvas, role="dialog" on modals |
| `web/templates/session.html` | Modified | Added aria-label on chart canvases |

## Decisions Made

| Decision | Rationale | Impact |
|----------|-----------|--------|
| Keep .mode-value.* but remove .mode-* text duplicates | .mode-value used by JS, .mode-* duplicated from Tailwind components | Clean separation |
| focus-visible amber outline | Matches observatory theme, visible on dark backgrounds | Consistent accessibility |
| Semantic HTML already sufficient | header/main/footer already semantic, no role= needed | Minimal changes |

## Deviations from Plan

None — plan executed exactly as written.

## Skill Audit

| Expected | Invoked | Notes |
|----------|---------|-------|
| /frontend-design | ✓ | Already loaded from 05-01 session |

## Issues Encountered

None

## Next Phase Readiness

**This is the final plan of Milestone v5.0 Interface Moderne.**

All 5 phases complete:
1. Foundation & Stack Setup (Tailwind v4 + Alpine.js)
2. Dashboard Modernization (layout, panels, Alpine.store)
3. System Page Modernization (cards, IPC, Alpine.store)
4. Session Page Modernization (charts, tables, Alpine.store)
5. Polish & Responsive (factorization, responsive, accessibility)

---
*Phase: 05-polish-responsive, Plan: 02*
*Completed: 2026-02-22*
