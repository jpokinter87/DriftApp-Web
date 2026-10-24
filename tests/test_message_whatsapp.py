"""Tests de .claude/skills/message-user/scripts/message_whatsapp.py (format WhatsApp)."""

from __future__ import annotations

import importlib.util
from pathlib import Path

# Le script vit dans le skill (pas un package) → import par chemin.
_SPEC = importlib.util.spec_from_file_location(
    "message_whatsapp",
    Path(__file__).resolve().parents[1]
    / ".claude"
    / "skills"
    / "message-user"
    / "scripts"
    / "message_whatsapp.py",
)
message_whatsapp = importlib.util.module_from_spec(_SPEC)
_SPEC.loader.exec_module(message_whatsapp)

BON = """\
*Mise à jour 6.26.10* ✅

Bonsoir Serge,
• le suivi reprend seul après une coupure ;
• _rien à faire_ de ton côté.

👉 Ce soir à 21:30, tape `cd ~/DriftApp` puis :
```
./scripts/logs.sh
```
1. Ouvre un terminal (Ctrl+Alt+T).
2. Envoie-moi le fichier *logs.zip*.
"""


def test_texte_whatsapp_correct_sans_defaut():
    assert message_whatsapp.verifier(BON) == []


def test_defauts_signales_avec_numero_de_ligne():
    texte = "\n".join(
        [
            "# Compte rendu",
            "| heure | fait |",
            "|-------|------|",
            "Le **moteur** a tourné.",
            "Voir [le guide](https://example.org).",
            "---",
            "C'est __important__.",
        ]
    )
    lignes = [ligne for ligne, _ in message_whatsapp.verifier(texte)]
    assert lignes == [1, 2, 3, 4, 5, 6, 7]


def test_main_refuse_et_ne_copie_pas_un_texte_fautif(tmp_path, monkeypatch, capsys):
    fichier = tmp_path / "msg.txt"
    fichier.write_text("## Titre\nTexte.\n", encoding="utf-8")
    copies = []
    monkeypatch.setattr(message_whatsapp, "copier", lambda texte: copies.append(texte) or "test")
    assert message_whatsapp.main([str(fichier)]) == 1
    assert copies == []
    assert "ligne 1" in capsys.readouterr().out


def test_main_copie_un_texte_correct(tmp_path, monkeypatch):
    fichier = tmp_path / "msg.txt"
    fichier.write_text(BON, encoding="utf-8")
    copies = []
    monkeypatch.setattr(message_whatsapp, "copier", lambda texte: copies.append(texte) or "test")
    assert message_whatsapp.main([str(fichier)]) == 0
    assert copies == [BON]


def test_copier_sans_outil_le_dit(monkeypatch):
    monkeypatch.setattr(message_whatsapp.shutil, "which", lambda _: None)
    assert message_whatsapp.copier("x") is None
