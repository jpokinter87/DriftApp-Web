#!/usr/bin/env python3
"""
Point d'entrée principal du système de suivi de coupole.

VERSION MODIFIÉE : Configure le logging Python au démarrage pour capturer
tous les logs (moteur, tracker, encodeur, etc.) dans un fichier unique.
"""

import time
import sys
from pathlib import Path

# Ajouter le répertoire parent au path si nécessaire
sys.path.insert(0, str(Path(__file__).parent))

from core.config.logging_config import setup_logging, log_system_info, close_logging
from core.hardware.hardware_detector import HardwareDetector
from core.config.config_loader import load_config
from core.ui.main_screen import DriftApp


def main():
    """Lance l'application après configuration du logging et affichage du résumé matériel."""
    
    # === 1. CONFIGURATION DU LOGGING ===
    # Ceci DOIT être fait en premier pour capturer tous les logs
    try:
        log_file = setup_logging(
            log_dir="logs",
            log_level="DEBUG",  # niveau de détails croissants : INFO / WARNING / DEBUG
            max_bytes=10 * 1024 * 1024,  # 10 MB par fichier
            backup_count=5
        )
        print(f"📝 Logging configuré : {log_file}")
    except Exception as e:
        print(f"⚠️  Erreur configuration logging : {e}")
        print("L'application continuera sans logging dans fichier")
    
    # === 2. AFFICHAGE CONSOLE ===
    print("\n" + "=" * 60)
    print("OBSERVATOIRE - SUIVI COUPOLE")
    print("=" * 60)

    # === 3. CHARGEMENT CONFIGURATION ===
    try:
        config = load_config()
        print(f"✅ Configuration chargée : {config.site.nom}")
    except Exception as e:
        print(f"❌ Erreur chargement config : {e}")
        return

    # === 4. DÉTECTION MATÉRIELLE ===
    is_prod, hw_info = HardwareDetector.detect_hardware()

    if is_prod:
        print("✓ PRODUCTION")
        print(f"  {hw_info.get('rpi_model', 'RPi')}")
    else:
        print("⚠ SIMULATION")
        print(f"  {hw_info['system']}/{hw_info['machine']}")

    print("\n" + "=" * 60 + "\n")

    # === 5. LOG DES INFORMATIONS SYSTÈME ===
    try:
        log_system_info()
    except Exception as e:
        print(f"⚠️  Erreur log système : {e}")

    time.sleep(0.5)

    # === 6. LANCEMENT DE L'APPLICATION ===
    try:
        app = DriftApp(config)
        app.run()
    except KeyboardInterrupt:
        print("\n\n⏸️  Application interrompue par l'utilisateur")
    except Exception as e:
        print(f"\n❌ Erreur fatale : {e}")
        import traceback
        traceback.print_exc()
    finally:
        # === 6. FERMETURE PROPRE DU LOGGING ===
        try:
            close_logging()
            print("\n✅ Logging fermé proprement")
        except Exception as e:
            print(f"\n⚠️  Erreur fermeture logging : {e}")


if __name__ == "__main__":
    main()
