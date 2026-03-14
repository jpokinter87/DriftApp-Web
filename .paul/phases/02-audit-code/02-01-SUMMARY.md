---
phase: 02-audit-code
plan: 01
subsystem: core
tags: [audit, code-review, quality, bugs]

provides:
  - Rapport d'audit core/ avec 37 issues priorisées
affects: [03-refactoring-core]

key-decisions:
  - "5 Critical, 10 High, 14 Medium, 8 Low identifiés dans core/"

completed: 2026-03-14
---

# Phase 2 Plan 01: Audit core/ Summary

**37 issues identifiées dans core/ — 5 critiques dont log_to_web() manquant et moyenne d'angles incorrecte**

## Acceptance Criteria Results

| Criterion | Status | Notes |
|-----------|--------|-------|
| AC-1: Couverture complète | Pass | config, hardware, tracking, observatoire, utils couverts |
| AC-2: Issues classifiées | Pass | 5C + 10H + 14M + 8L |
| AC-3: Issues actionnables | Pass | Fichier, ligne, description, correction pour chaque |

## Top 5 Critical

1. [C-20] log_to_web() jamais définie — AttributeError en mode dégradé
2. [C-10] Moyenne arithmétique d'angles près de 0°/360°
3. [C-11] Race condition lecture JSON sans verrou fcntl
4. [C-07] bare except masque SystemExit/KeyboardInterrupt
5. [C-01] Chemins relatifs → échec si CWD différent

## Deviations

None — audit en lecture seule comme prévu.

---
*Completed: 2026-03-14*
