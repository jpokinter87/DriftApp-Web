# Plan — bascule de la coupole sur le signal de retournement de l'ASIAIR

Spec : `docs/superpowers/specs/2026-10-21-bascule-coupole-signal-asiair.md`

1. **Config** — `dome_flip_on_pierside` (false) et `max_wait_minutes` (30) dans la
   section `asiair` du template ; champs d'`AsiairConfig` + `_parse_asiair` ; aide
   dans `HELP_REGISTRY`.
   → vérifier : `test_config_loader.py` (défauts, section ancienne sans les clés),
   test de complétude de l'aide vert.
2. **Client** — `lire_etat_monture` + `EtatMonture(pier, delta_h)` dans
   `asiair_client.py` (deux requêtes : `scope_get_info`, `scope_get_pierside` ;
   `delta_h = range12(RA − sidereal_time)`).
   → vérifier : TDD contre le serveur TCP local de `test_asiair_client.py`
   (nominal, `delta_h` autour de 0 h et de 24 h, côté inconnu → `None`, erreurs).
3. **Règle** — fonction pure `monture_en_retard(etat, azimut_objet)`
   (module `core/tracking/dome_flip_wait.py`), plus l'état d'attente (début,
   délai écoulé, levée par timeout).
   → vérifier : tests unitaires de la spec (côtés, avant/après méridien, `|delta_h| ≥ 6 h`, état périmé,
   délai maximal, pas de relance après timeout).
4. **Watcher** — `core/hardware/asiair_watcher.py` (`AsiairPierWatcher`, thread
   démon, 5 s, `etat_frais(30)`, `stop()`).
   → vérifier : contre un faux ASIAIR TCP — état frais, état périmé quand le
   serveur se tait, aucune exception propagée, arrêt propre.
5. **Suivi** — `TrackingSession` reçoit le watcher ; `check_and_correct` suspend
   les corrections pendant l'attente, logs `dome_flip_wait_start/end`, correction
   immédiate au changement de côté ; anticipation non armée si watcher présent ;
   `get_status` expose `asiair_pier` et `flip_wait`.
   → vérifier : tests avec watcher factice (rejeu de la chronologie du 21/10 :
   attente après le méridien, bascule au passage à `pier_east`) ; option inactive →
   tests existants inchangés.
6. **Service** — `TrackingHandler` crée/arrête le watcher selon la config, ajoute
   `asiair_pier`/`flip_wait` à `tracking_info`.
   → vérifier : tests `command_handlers` (watcher créé seulement si option + host,
   arrêté au stop).
7. **Dashboard** — ligne dans le cartouche « Suivi actif » + journal aux
   transitions.
   → vérifier : stack dev avec faux ASIAIR (côté basculé à la main), rendu 1280×720.
8. **Livraison** — CLAUDE.md (changelog ; au passage 6.23.4 « validé terrain » et
   1628 → 1627 tests), bump 6.24.0, ruff, suite complète, commit + push ; note pour
   Serge (activer l'option, essai avec `Flip Timing after Meridian` à 0 puis 5).
