#!/usr/bin/env python3
"""Vérifie qu'un message s'affichera proprement dans WhatsApp, puis le copie.

Usage :
    python3 .claude/skills/message-user/scripts/message_whatsapp.py MESSAGE.txt

Signale, ligne par ligne, ce que WhatsApp montre tel quel au lieu de le mettre en
forme (tableau, titre #, **gras** Markdown, lien [x](y), filet ---). S'il n'y a
rien à corriger, copie le texte dans le presse-papiers (wl-copy sous Wayland,
xclip sinon) pour un Ctrl+V direct dans WhatsApp. Code de sortie 1 s'il reste un
défaut (rien n'est copié), 0 sinon.
"""

from __future__ import annotations

import argparse
import os
import re
import shutil
import subprocess
import sys
from pathlib import Path

DEFAUTS = [
    (re.compile(r"^\s*\|.*\|\s*$"), "tableau : WhatsApp n'en affiche pas, passer en puces •"),
    (re.compile(r"^\s*#{1,6}\s"), "titre # : écrire le titre en *gras* sur sa ligne"),
    (re.compile(r"\*\*[^*\n]+\*\*"), "**double astérisque** : le gras WhatsApp est *simple*"),
    (re.compile(r"__[^_\n]+__"), "__double souligné__ : l'italique WhatsApp est _simple_"),
    (re.compile(r"\[[^\]\n]+\]\([^)\s]+\)"), "lien [texte](url) : écrire l'adresse en clair"),
    (re.compile(r"^\s*-{3,}\s*$"), "filet --- : laisser une ligne vide à la place"),
]


def verifier(texte: str) -> list[tuple[int, str]]:
    """Défauts de mise en forme, en (numéro de ligne, explication). Hors blocs ```."""
    defauts = []
    dans_bloc = False
    for numero, ligne in enumerate(texte.splitlines(), start=1):
        if ligne.strip().startswith("```"):
            dans_bloc = not dans_bloc
            continue
        if dans_bloc:
            continue
        for motif, explication in DEFAUTS:
            if motif.search(ligne):
                defauts.append((numero, explication))
                break
    return defauts


def copier(texte: str) -> str | None:
    """Copie dans le presse-papiers ; renvoie l'outil utilisé, None s'il n'y en a pas."""
    if os.environ.get("WAYLAND_DISPLAY") and shutil.which("wl-copy"):
        commande = ["wl-copy"]
    elif shutil.which("xclip"):
        commande = ["xclip", "-selection", "clipboard"]
    else:
        return None
    subprocess.run(commande, input=texte, text=True, check=True)
    return commande[0]


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("fichier", type=Path, help="message au format WhatsApp (.txt)")
    args = parser.parse_args(argv)

    texte = args.fichier.read_text(encoding="utf-8")
    defauts = verifier(texte)
    if defauts:
        for numero, explication in defauts:
            print(f"ligne {numero} : {explication}")
        print(f"{len(defauts)} défaut(s) : corriger avant envoi, rien n'a été copié.")
        return 1

    outil = copier(texte)
    if outil:
        print(f"Message propre, copié dans le presse-papiers ({outil}) : Ctrl+V dans WhatsApp.")
    else:
        print(
            "Message propre, mais aucun outil de presse-papiers : "
            "sudo apt install wl-clipboard (Wayland) ou xclip."
        )
    return 0


if __name__ == "__main__":
    sys.exit(main())
