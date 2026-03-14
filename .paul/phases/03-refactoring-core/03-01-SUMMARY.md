---
phase: 03-refactoring-core
plan: 01
subsystem: core
tags: [bugfix, critical, high, thread-safety, angles]

provides:
  - 5 issues Critical corrigées
  - 6 issues High corrigées
affects: [03-02-refactoring-core]

completed: 2026-03-14
---

# Phase 3 Plan 01: Critical + High fixes Summary

**11 issues corrigées (5 Critical + 6 High) — 407 tests verts**

## Acceptance Criteria Results

| Criterion | Status | Notes |
|-----------|--------|-------|
| AC-1: 5 Critical corrigées | Pass | C-20, C-10, C-11, C-07, C-01 |
| AC-2: High prioritaires | Pass | C-02, C-08, C-09, C-13, C-14, C-16 |
| AC-3: Pas de régression | Pass | 407 tests passent |

## Corrections appliquées

| Issue | Fichier | Correction |
|-------|---------|------------|
| C-20 | tracking_corrections_mixin.py | log_to_web() → logger.warning() |
| C-10 | daemon_encoder_reader.py | Moyenne circulaire (sin/cos) |
| C-11 | daemon_encoder_reader.py | Verrou fcntl LOCK_SH sur read_raw() |
| C-07 | moteur.py | bare except → except OSError |
| C-01 | config.py, config_loader.py | Chemins absolus via __file__ |
| C-02 | config.py | Logger warning sur erreur config |
| C-08 | moteur.py | bare except → except Exception dans nettoyer() |
| C-09 | moteur.py | Cache _lgpio_write dans _init_gpio() |
| C-13 | moteur_simule.py | stop_requested vérifié en boucle 50ms |
| C-14 | daemon_encoder_reader.py | Double-checked locking avec threading.Lock |
| C-16 | acceleration_ramp.py | Garde accel_end == 0 |

## Tests adaptés

- test_config.py: test_data_dir et test_logs_dir adaptés pour chemins absolus

---
*Completed: 2026-03-14*
