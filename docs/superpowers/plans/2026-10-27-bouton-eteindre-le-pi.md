# Plan — bouton « Éteindre le Pi »

Spec : `docs/superpowers/specs/2026-10-27-bouton-eteindre-le-pi.md`.

1. **Script** `scripts/shutdown_pi.sh` (exécutable) + tests dans
   `tests/test_shutdown_pi.py` (bac à sable avec faux `systemctl`, comme
   `tests/test_ota_restart.py`) → vérifier : refus hors Raspberry Pi, `poweroff` appelé
   sur un Pi, ligne dans `logs/shutdown.log`.
2. **Sudoers** : ligne `slenk ALL=(root) NOPASSWD: /home/slenk/DriftApp/scripts/shutdown_pi.sh`
   → vérifier : test whitelist, aucun `systemctl` générique.
3. **Vue** `shutdown_pi` (GET : `{allowed, reason}` ; POST : revérifie puis lance le
   script) + route `shutdown/` dans `web/health/urls.py`, tests dans
   `tests/test_health_views.py` (patch `health.views.*`) → vérifier : chaque refus,
   autorisation, sudo non appelé en cas de refus, erreur sudo remontée.
4. **UI** : bouton à la fin du bloc `status_indicator` de `dashboard.html`, fenêtre sur
   le modèle `parking-confirm-modal`, overlay « Arrêt en cours », style rouge 44 px →
   vérifier en dev (Chrome headless) : refus pendant un suivi, confirmation au repos.
5. **Finition** : ruff, suite complète, CHANGELOG 6.29.0, registre « À valider sur le
   terrain », commit + push.

Risques : arrêt avant l'envoi de la réponse HTTP (délai de 3 s en arrière-plan) ; essai
en dev qui éteindrait le PC (garde Raspberry Pi dans le script).
