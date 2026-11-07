# Plan — erreur cimier affichée jusqu'à acquittement (6.31.8)

Spec : `docs/superpowers/specs/2026-11-07-erreur-cimier-acquittee.md`.

1. Tests service `TestCimierAlert` (erreur → fichier, compteur, succès → rien,
   preflight) → vérifier : échouent, puis passent.
2. `cimier_service` : `ALERT_FILE`, paramètre `alert_file`, `_record_alert`.
3. Tests vues `TestCimierAlert` (status + alert, service arrêté, ack) puis
   `settings`, `cimier_client.alert_file` / `acknowledge_alert`, `AlertAckView`,
   route `alert/ack/`.
4. Dashboard : `store.cimierAlert` dérivé de `status.alert`, bouton → ack.
5. `.gitignore`, ruff, `tests/test_cimier_service.py` + `tests/test_web_cimier_views.py`,
   contrôle de bout en bout sur Django temporaire, bump, CHANGELOG, push.
