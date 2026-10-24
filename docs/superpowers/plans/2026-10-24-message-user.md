# Plan — skill `message-user`

Spec : `docs/superpowers/specs/2026-10-24-message-user.md`.

1. Tests `tests/test_message_whatsapp.py` (défauts détectés, faux positifs évités, code de
   sortie et copie) → vérifier : ils échouent sans le script.
2. Script `.claude/skills/message-user/scripts/message_whatsapp.py` → vérifier : tests verts,
   ruff propre.
3. `SKILL.md` (déclencheurs, quatre sortes de messages, règles de format, livraison) →
   vérifier : relu, cohérent avec `/analyse-nuit` et `/diag-terrain`.
4. Raccords : `/analyse-nuit` §4 renvoie à `/message-user`, table des skills de
   `CLAUDE.md`, ligne `CHANGELOG.md`, bump 6.26.10 → vérifier : `/pre-push`.
5. Essai réel avec presse-papiers (wl-clipboard installé par JP) → vérifier : `wl-paste`
   rend le message.
