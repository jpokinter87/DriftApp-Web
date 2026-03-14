#!/usr/bin/env python3
"""
Point d'entrée GUI (Kivy) pour le système de suivi de coupole.

Cette version graphique est optimisée pour écran tactile (Raspberry Pi 5).
L'interface Textual (main.py) reste disponible pour un usage en terminal.
"""

import sys
from pathlib import Path

# Ajouter le répertoire parent au path
sys.path.insert(0, str(Path(__file__).parent))

from main import bootstrap


def main():
    """Lance l'application graphique (Kivy)."""
    from gui.app import DriftAppGUI
    bootstrap(DriftAppGUI, "SUIVI COUPOLE (GUI)", "INFO")


if __name__ == "__main__":
    main()
