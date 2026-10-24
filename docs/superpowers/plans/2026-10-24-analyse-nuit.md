# Plan — analyse d'une nuit terrain

Spec : `docs/superpowers/specs/2026-10-24-analyse-nuit.md`.

1. Tests `tests/test_chronologie_nuit.py` sur un zip synthétique (structures à plat et
   rangée, nuit midi → midi, bruit filtré, `×N`, synthèse) → vérifier : ils échouent.
2. `scripts/diagnostics/chronologie_nuit.py` → vérifier : tests verts, ruff propre.
3. Essai sur `~/Downloads/logs (2).zip` → vérifier : chronologie lisible, rien d'utile perdu.
4. Skill `.claude/skills/analyse-nuit/SKILL.md`, mention dans `CLAUDE.md` (tableau des
   skills) → vérifier : le skill apparaît dans la liste.
5. Bump, CHANGELOG, commit + push (`/pre-push`).
