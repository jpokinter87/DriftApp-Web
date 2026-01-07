#!/usr/bin/env python3
"""
Test direct du moteur sans passer par le Motor Service.

Ce script permet de vérifier si le problème est matériel (GPIO, driver, moteur)
ou logiciel (Motor Service, IPC).

Usage:
    sudo python3 scripts/diagnostics/test_moteur_direct.py

IMPORTANT: Arrêter le Motor Service avant d'exécuter ce script:
    sudo systemctl stop driftapp_web
"""

import sys
import time

# Configuration GPIO (depuis config.json)
DIR_PIN = 17
STEP_PIN = 18


def test_gpio():
    """Test direct des GPIO avec lgpio (Pi 5)."""
    try:
        import lgpio
    except ImportError:
        print("Erreur: lgpio non disponible. Installez-le avec: sudo apt install python3-lgpio")
        sys.exit(1)

    print("=" * 60)
    print("  TEST DIRECT MOTEUR - GPIO Pi 5")
    print("=" * 60)
    print()
    print(f"Configuration: DIR=GPIO{DIR_PIN}, STEP=GPIO{STEP_PIN}")
    print()

    # Ouvrir le chip GPIO du Pi 5
    try:
        h = lgpio.gpiochip_open(4)  # Chip 4 pour Pi 5
        print("Chip GPIO 4 ouvert (Raspberry Pi 5)")
    except Exception as e:
        try:
            h = lgpio.gpiochip_open(0)  # Fallback Pi 1-4
            print("Chip GPIO 0 ouvert (Raspberry Pi 1-4)")
        except Exception as e2:
            print(f"Erreur ouverture GPIO: {e2}")
            sys.exit(1)

    # Configurer les pins en sortie
    try:
        lgpio.gpio_claim_output(h, DIR_PIN)
        lgpio.gpio_claim_output(h, STEP_PIN)
        print(f"Pins GPIO {DIR_PIN} et {STEP_PIN} configurés en sortie")
    except Exception as e:
        print(f"Erreur configuration pins: {e}")
        lgpio.gpiochip_close(h)
        sys.exit(1)

    print()
    print("-" * 60)

    # Test 1: Pulses lents (visible au multimètre)
    print()
    print("TEST 1: 10 pulses lents (100ms chacun)")
    print("        Vérifiez avec un multimètre sur GPIO18")
    input("        Appuyez sur Entrée pour commencer...")

    lgpio.gpio_write(h, DIR_PIN, 1)  # Direction horaire
    for i in range(10):
        lgpio.gpio_write(h, STEP_PIN, 1)
        time.sleep(0.05)
        lgpio.gpio_write(h, STEP_PIN, 0)
        time.sleep(0.05)
        print(f"  Pulse {i+1}/10")

    print("  Terminé")

    # Test 2: Pulses rapides (devrait faire bouger le moteur)
    print()
    print("TEST 2: 500 pulses rapides (1ms chacun)")
    print("        Le moteur devrait bouger d'environ 0.1 degré")
    input("        Appuyez sur Entrée pour commencer...")

    lgpio.gpio_write(h, DIR_PIN, 1)  # Direction horaire
    for i in range(500):
        lgpio.gpio_write(h, STEP_PIN, 1)
        time.sleep(0.0005)
        lgpio.gpio_write(h, STEP_PIN, 0)
        time.sleep(0.0005)

    print("  Terminé - Le moteur a-t-il bougé ?")

    # Test 3: Plus de pulses dans l'autre sens
    print()
    print("TEST 3: 5000 pulses (sens inverse)")
    print("        Le moteur devrait bouger d'environ 1 degré")
    input("        Appuyez sur Entrée pour commencer...")

    lgpio.gpio_write(h, DIR_PIN, 0)  # Direction anti-horaire
    for i in range(5000):
        lgpio.gpio_write(h, STEP_PIN, 1)
        time.sleep(0.0005)
        lgpio.gpio_write(h, STEP_PIN, 0)
        time.sleep(0.0005)
        if i % 1000 == 0:
            print(f"  {i}/5000 pulses...")

    print("  Terminé")

    # Nettoyage
    lgpio.gpio_write(h, DIR_PIN, 0)
    lgpio.gpio_write(h, STEP_PIN, 0)
    lgpio.gpiochip_close(h)

    print()
    print("=" * 60)
    print("  DIAGNOSTIC")
    print("=" * 60)
    print()
    print("Si le moteur N'A PAS bougé:")
    print("  1. Vérifiez les connexions GPIO -> Driver DM556T")
    print("  2. Vérifiez l'alimentation 24V du driver")
    print("  3. Vérifiez les dip switches du driver (courant)")
    print("  4. Testez le moteur avec un autre driver si possible")
    print()
    print("Si le moteur A bougé:")
    print("  Le problème est dans le Motor Service, pas le matériel.")
    print()


if __name__ == "__main__":
    if len(sys.argv) > 1 and sys.argv[1] == "--help":
        print(__doc__)
        sys.exit(0)

    test_gpio()
