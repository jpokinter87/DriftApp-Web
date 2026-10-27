# Plan — alerte « site de l'ASIAIR faux »

Spec : `docs/superpowers/specs/2026-10-27-alerte-site-asiair.md`.

1. `core/hardware/asiair_client.py` : `EtatMonture` gagne `lst_h` et `lu_a` (horodatage
   epoch de la lecture), remplis par `lire_etat_monture`.
   → vérifier : `tests/test_asiair_client.py` (temps sidéral et heure de lecture rendus).
2. `core/tracking/tracker.py` : `_flip_wait_status` ajoute `asiair_site_alert` (écart au
   temps sidéral du site calculé à `lu_a`, seuil 2 min) ; WARNING/INFO aux transitions.
   → vérifier : nouveau `tests/test_tracking_alerte_site_asiair.py` (site correct → None,
   valeurs du 27/10 → −12,3 min et 2,15° E, journal une seule fois, retour à la normale).
3. `services/command_handlers.py` : relayer `asiair_site_alert` dans `tracking_info`.
   → vérifier : test du relais.
4. Dashboard : ligne `#tracking-site-alert` sous `#tracking-pier`, `updatePierDisplay`.
   → vérifier : rendu dans la stack dev avec un faux ASIAIR décalé.
5. Ruff, tests ciblés, `docs/chantiers.md`, CHANGELOG, bump 6.30.0, commit + push.
