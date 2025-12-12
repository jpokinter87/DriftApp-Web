#!/usr/bin/env python3
"""
Test direct du microswitch GPIO 27
Affiche l'état du switch en temps réel
"""

import time
import sys

try:
    import lgpio
except ImportError:
    print("❌ Module lgpio non disponible")
    print("   Installez avec : sudo apt install python3-lgpio")
    sys.exit(1)

SWITCH_GPIO = 27

print("╔═══════════════════════════════════════════════════════════════════╗")
print("║  TEST MICROSWITCH GPIO 27 - SS-5GL                                ║")
print("╚═══════════════════════════════════════════════════════════════════╝")
print(f"\nGPIO {SWITCH_GPIO} configuré avec pull-up interne")
print("\nÉtats attendus :")
print("  🟢 1 = Switch OUVERT (repos, coupole PAS à 45°)")
print("  🔴 0 = Switch PRESSÉ (coupole À 45°)")
print("\nAppuyez sur Ctrl+C pour arrêter\n")
print("-" * 70)

try:
    # Ouvrir GPIO chip
    h = lgpio.gpiochip_open(0)
    lgpio.gpio_claim_input(h, SWITCH_GPIO, lgpio.SET_PULL_UP)

    last_state = None
    transition_count = 0

    while True:
        state = lgpio.gpio_read(h, SWITCH_GPIO)

        # Afficher uniquement lors des changements d'état
        if state != last_state and last_state is not None:
            transition_count += 1
            timestamp = time.strftime("%H:%M:%S")

            if state == 0:
                print(f"[{timestamp}] Transition #{transition_count:03d} : 1→0 | 🔴 PRESSÉ")
                print(f"             ✅ Front DESCENDANT détecté")
                print(f"             → Le daemon DEVRAIT calibrer à 45° maintenant\n")
            else:
                print(f"[{timestamp}] Transition #{transition_count:03d} : 0→1 | 🟢 RELÂCHÉ")
                print(f"             Front montant (ignoré par daemon)\n")

        # Affichage périodique toutes les 5 secondes
        elif last_state is None or int(time.time()) % 5 == 0:
            if state == 0:
                print(f"État actuel : 🔴 PRESSÉ (0) - Coupole devrait être à 45°")
            else:
                print(f"État actuel : 🟢 OUVERT (1) - Coupole ailleurs qu'à 45°")
            time.sleep(1)  # Éviter spam

        last_state = state
        time.sleep(0.05)  # 20 Hz

except KeyboardInterrupt:
    print("\n" + "-" * 70)
    print(f"✅ Test terminé - {transition_count} transitions détectées")
    lgpio.gpiochip_close(h)

except Exception as e:
    print(f"\n❌ Erreur : {e}")
    print("\nCauses possibles :")
    print("  1. Switch non connecté au GPIO 27")
    print("  2. Mauvais câblage (vérifier GND et signal)")
    print("  3. Conflit avec daemon (arrêtez d'abord : sudo pkill -f ems22d)")
    sys.exit(1)
