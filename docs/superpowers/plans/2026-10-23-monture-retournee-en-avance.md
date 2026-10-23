# Plan — monture retournée avant le méridien

Spec : `docs/superpowers/specs/2026-10-23-monture-retournee-en-avance.md`

1. **Règle** — dans `core/tracking/dome_flip_wait.py` (module pur) :
   `COTE_APRES_MERIDIEN = "pier_east"`, `monture_en_avance(etat, azimut_objet)`
   (côté Est, `|delta_h| < 6 h`, azimut < 180°), et
   `instant_meridien(azimut_a, maintenant, fenetre_s)` qui prend une fonction
   `t -> azimut` (recherche par pas de 60 s puis dichotomie à 5 s, `None` hors
   fenêtre).
   → vérifier : TDD `tests/test_dome_flip_wait.py` — côtés, avant/après méridien,
   `delta_h`, état `None` ; instant trouvé pour un passage au nord (2,7° → 359,8°)
   et au sud (179° → 181°), `None` hors fenêtre, précision ≤ 5 s.
2. **Suivi** — `TrackingCorrectionsMixin` : `_cible_monture_en_avance(azimut, now)`
   qui gère la tenue (début : cible = abaque à `t_méridien + 30 s` via
   `_calculate_current_coords` et `_calculate_target_position` ; fin sur
   `transit` ou `pierside` ; tenue maintenue si ASIAIR muet ; WARNING
   `dome_flip_early_out_of_window` une fois par épisode). Appel dans
   `check_and_correct` juste avant `_attendre_retournement` ; si une cible est
   tenue, elle remplace la cible abaque, le reste de la correction est inchangé.
   `_flip_wait_status` expose `flip_early`.
   → vérifier : TDD `tests/test_tracking_dome_flip_wait.py` avec watcher factice et
   horloge fictive — rejeu du 23/10 (bascule immédiate vers ~36°, pas de retour à
   315°, reprise sans saut après le méridien), ASIAIR muet pendant la tenue,
   `pier_west` frais pendant la tenue, méridien hors fenêtre, option inactive.
3. **Service** — `TrackingHandler` ajoute `flip_early` à `tracking_info`.
   → vérifier : test `command_handlers` sur le contenu de `tracking_info`.
4. **Dashboard** — `updatePierDisplay` : ligne « Monture retournée en avance —
   coupole tenue à X° jusqu'au méridien » et journal aux deux transitions.
   → vérifier : stack dev avec faux ASIAIR (côté Est forcé avant le méridien),
   rendu 1280×720.
5. **Livraison** — CLAUDE.md (changelog 6.26.0 ; mentionner qu'`asiair_monitor`
   s'installe avec cette MAJ, l'OTA 6.25.1 ayant été jouée par l'ancien script),
   bump 6.26.0, ruff format + check, suite complète, commit + push. Note pour
   Serge : réglage « Flip Timing after Meridian » de l'ASIAIR et heure de bascule
   affichée, `./scripts/asiair_sonde.sh etat` → journal `logs/asiair/` présent
   après la MAJ.
