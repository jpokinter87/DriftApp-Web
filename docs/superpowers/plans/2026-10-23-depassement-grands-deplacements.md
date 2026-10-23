# Dépassement des grands déplacements — plan (étape 1, mesure)

Spec : `docs/superpowers/specs/2026-10-23-depassement-grands-deplacements.md`.

1. Log de recalage dans `ems22d_calibrated.py` : `_recaler(now, angle_avant, source)`
   journalise `recalage | source=switch|force avant=…° ecart=…°`.
   → vérifier : tests `tests/test_ems22d_force_calibration.py` (log présent,
   écart signé le plus court).
2. `scripts/diagnostics/mesure_tour_complet.py` :
   - fonctions pures `echelles_tour(sens, depart, avant_recalages, arrivee, commande)`
     et `facteurs_proposes(...)` ;
   - orchestration IPC (GOTO départ, JOG 385°, capture des recalages via
     `last_calibration_at`, attente de l'arrêt), réutilise les lectures IPC de
     `calibration_vitesse_encodeur.py` ;
   - `--dry-run`, Ctrl+C → STOP, confirmation `go`, rapport JSON.
   → vérifier : `tests/test_mesure_tour_complet.py` (cas parfait, pas trop
   longs de 2 %, encodeur trop court de 2 %, sens −, nombre de recalages ≠ 2).
3. Doc : CLAUDE.md (changelog 6.25.1), bump `pyproject.toml`, ruff, tests ciblés.
4. Protocole à transmettre à Serge (commande unique, résultat attendu).
