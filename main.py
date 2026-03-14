#!/usr/bin/env python3
"""
Point d'entrée principal du système de suivi de coupole (TUI Textual).
"""

import sys
from pathlib import Path

# Ajouter le répertoire parent au path si nécessaire
sys.path.insert(0, str(Path(__file__).parent))

from core.config.logging_config import setup_logging, log_system_info, close_logging
from core.hardware.hardware_detector import HardwareDetector
from core.config.config_loader import load_config


def bootstrap(app_class, title: str = "SUIVI COUPOLE", log_level: str = "DEBUG"):
    """Bootstrap commun pour les points d'entrée DriftApp."""
    # 1. Logging
    try:
        log_file = setup_logging(
            log_dir="logs", log_level=log_level,
            max_bytes=10 * 1024 * 1024, backup_count=5
        )
        print(f"📝 Logging configuré : {log_file}")
    except Exception as e:
        print(f"⚠️  Erreur configuration logging : {e}")

    # 2. Banner
    print("\n" + "=" * 60)
    print(f"OBSERVATOIRE - {title}")
    print("=" * 60)

    # 3. Config
    try:
        config = load_config()
        print(f"✅ Configuration chargée : {config.site.nom}")
    except Exception as e:
        print(f"❌ Erreur chargement config : {e}")
        return

    # 4. Hardware
    is_prod, hw_info = HardwareDetector.detect_hardware()
    if is_prod:
        print("✓ PRODUCTION")
        print(f"  {hw_info.get('rpi_model', 'RPi')}")
    else:
        print("⚠ SIMULATION")
        print(f"  {hw_info['system']}/{hw_info['machine']}")
    print("\n" + "=" * 60 + "\n")

    # 5. System info
    try:
        log_system_info()
    except Exception as e:
        print(f"⚠️  Erreur log système : {e}")

    # 6. Run
    try:
        app = app_class(config)
        app.run()
    except KeyboardInterrupt:
        print("\n\n⏸️  Application interrompue par l'utilisateur")
    except Exception as e:
        print(f"\n❌ Erreur fatale : {e}")
        import traceback
        traceback.print_exc()
    finally:
        try:
            close_logging()
            print("\n✅ Logging fermé proprement")
        except Exception as e:
            print(f"\n⚠️  Erreur fermeture logging : {e}")


def main():
    """Lance l'application TUI (Textual)."""
    from core.ui.main_screen import DriftApp
    bootstrap(DriftApp, "SUIVI COUPOLE", "DEBUG")


if __name__ == "__main__":
    main()
