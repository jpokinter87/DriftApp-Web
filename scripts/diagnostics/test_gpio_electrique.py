#!/usr/bin/env python3
"""
Test GPIO ELECTRIQUE - Verification des signaux physiques.

Ce script verifie si les signaux sortent VRAIMENT sur les pins GPIO.
Utilisez un multimetre ou une LED pour verifier.

IMPORTANT: Le moteur n'a pas besoin d'etre connecte pour ce test.
On verifie juste que les pins GPIO changent d'etat electrique.

Usage:
    sudo python3 scripts/diagnostics/test_gpio_electrique.py
"""

import sys
import time

STEP_PIN = 18  # GPIO 18 = Pin physique 12
DIR_PIN = 17   # GPIO 17 = Pin physique 11

def test_gpio():
    print("=" * 60)
    print("  TEST GPIO ELECTRIQUE - Raspberry Pi 5")
    print("=" * 60)
    print()
    print("Ce test verifie si les signaux GPIO sortent physiquement.")
    print("Utilisez un multimetre entre GPIO et GND pour mesurer.")
    print()
    print(f"  STEP = GPIO {STEP_PIN} (pin physique 12)")
    print(f"  DIR  = GPIO {DIR_PIN} (pin physique 11)")
    print(f"  GND  = pin physique 6, 9, 14, 20, 25, 30, 34, 39")
    print()

    # Essayer d'importer lgpio
    try:
        import lgpio
        print("lgpio importe avec succes")
    except ImportError:
        print("ERREUR: lgpio non disponible!")
        print("Installez avec: sudo apt install python3-lgpio")
        sys.exit(1)

    # Lister les chips GPIO disponibles
    print()
    print("-" * 60)
    print("Chips GPIO disponibles:")
    import os
    chips = sorted([f for f in os.listdir('/dev') if f.startswith('gpiochip')])
    for chip in chips:
        print(f"  /dev/{chip}")

    # Essayer d'ouvrir le chip
    print()
    print("-" * 60)
    print("Tentative d'ouverture du chip GPIO...")

    h = None
    chip_used = None

    # Essayer chip 4 (Pi 5 standard)
    try:
        h = lgpio.gpiochip_open(4)
        chip_used = 4
        print(f"  Chip 4 ouvert avec succes (handle={h})")
    except Exception as e:
        print(f"  Chip 4 echec: {e}")

        # Essayer chip 0 (fallback)
        try:
            h = lgpio.gpiochip_open(0)
            chip_used = 0
            print(f"  Chip 0 ouvert avec succes (handle={h})")
        except Exception as e2:
            print(f"  Chip 0 echec: {e2}")
            print()
            print("ERREUR: Impossible d'ouvrir un chip GPIO!")
            sys.exit(1)

    # Configurer les pins en sortie
    print()
    print("-" * 60)
    print("Configuration des pins en sortie...")

    try:
        lgpio.gpio_claim_output(h, STEP_PIN)
        print(f"  GPIO {STEP_PIN} (STEP) configure en sortie")
    except Exception as e:
        print(f"  ERREUR GPIO {STEP_PIN}: {e}")
        lgpio.gpiochip_close(h)
        sys.exit(1)

    try:
        lgpio.gpio_claim_output(h, DIR_PIN)
        print(f"  GPIO {DIR_PIN} (DIR) configure en sortie")
    except Exception as e:
        print(f"  ERREUR GPIO {DIR_PIN}: {e}")
        lgpio.gpiochip_close(h)
        sys.exit(1)

    # TEST 1: Etat statique HIGH
    print()
    print("=" * 60)
    print("TEST 1: ETAT STATIQUE")
    print("=" * 60)
    print()
    print("Les deux pins vont passer a HIGH (3.3V) pendant 10 secondes.")
    print("Mesurez avec un multimetre:")
    print(f"  - Entre GPIO {STEP_PIN} et GND: devrait etre ~3.3V")
    print(f"  - Entre GPIO {DIR_PIN} et GND: devrait etre ~3.3V")
    print()
    input("Appuyez sur ENTREE pour commencer le test...")

    lgpio.gpio_write(h, STEP_PIN, 1)
    lgpio.gpio_write(h, DIR_PIN, 1)
    print()
    print(">>> PINS A HIGH - Mesurez maintenant! (10 secondes)")

    for i in range(10, 0, -1):
        print(f"  {i}...", end=" ", flush=True)
        time.sleep(1)
    print()

    lgpio.gpio_write(h, STEP_PIN, 0)
    lgpio.gpio_write(h, DIR_PIN, 0)
    print(">>> PINS A LOW")
    print()

    # TEST 2: Clignotement visible
    print("=" * 60)
    print("TEST 2: CLIGNOTEMENT LENT")
    print("=" * 60)
    print()
    print("GPIO STEP va clignoter 10 fois (0.5s HIGH, 0.5s LOW).")
    print("Si vous avez une LED, elle devrait clignoter.")
    print()
    input("Appuyez sur ENTREE pour commencer...")

    for i in range(10):
        lgpio.gpio_write(h, STEP_PIN, 1)
        print(f"  Cycle {i+1}/10: HIGH", flush=True)
        time.sleep(0.5)
        lgpio.gpio_write(h, STEP_PIN, 0)
        print(f"  Cycle {i+1}/10: LOW", flush=True)
        time.sleep(0.5)

    print()

    # TEST 3: Pulses rapides (comme le moteur)
    print("=" * 60)
    print("TEST 3: PULSES RAPIDES (simulation moteur)")
    print("=" * 60)
    print()
    print("1000 pulses a 1ms - Le multimetre devrait montrer ~1.6V (moyenne)")
    print()
    input("Appuyez sur ENTREE pour commencer...")

    start = time.time()
    for i in range(1000):
        lgpio.gpio_write(h, STEP_PIN, 1)
        time.sleep(0.0005)
        lgpio.gpio_write(h, STEP_PIN, 0)
        time.sleep(0.0005)
    elapsed = time.time() - start

    print(f"  1000 pulses en {elapsed:.3f}s")
    print(f"  Frequence: {1000/elapsed:.0f} Hz")
    print()

    # Nettoyage
    lgpio.gpiochip_close(h)

    print("=" * 60)
    print("RESULTATS")
    print("=" * 60)
    print()
    print("Si le multimetre a montre des changements de tension:")
    print("  -> Les GPIO fonctionnent, le probleme est ailleurs")
    print("     (cablage, driver, alimentation)")
    print()
    print("Si le multimetre est reste a 0V ou n'a pas change:")
    print("  -> Probleme lgpio/GPIO sur ce Pi 5")
    print("     Essayez: sudo apt update && sudo apt upgrade")
    print("     Ou verifiez /boot/config.txt")
    print()
    print(f"Chip GPIO utilise: {chip_used}")
    print()


if __name__ == "__main__":
    test_gpio()
