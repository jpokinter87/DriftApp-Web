#!/usr/bin/env python3
"""
Test rapide de lecture GPIO 27 avec lgpio
Pour vérifier que lgpio fonctionne dans le contexte daemon
"""

import lgpio
import time

SWITCH_GPIO = 27

print("=" * 70)
print("TEST LGPIO - Lecture GPIO 27")
print("=" * 70)
print()

try:
    # Configuration identique au daemon
    h = lgpio.gpiochip_open(0)
    print("✅ gpiochip_open(0) réussi")

    lgpio.gpio_claim_input(h, SWITCH_GPIO, lgpio.SET_PULL_UP)
    print(f"✅ gpio_claim_input(GPIO {SWITCH_GPIO}, PULL_UP) réussi")
    print()

    # Lecture état initial
    state = lgpio.gpio_read(h, SWITCH_GPIO)
    print(f"État initial GPIO {SWITCH_GPIO} : {state}")
    print()

    if state == 1:
        print("🟢 État 1 = Switch OUVERT (repos, coupole PAS à 45°)")
    else:
        print("🔴 État 0 = Switch PRESSÉ (coupole À 45°)")

    print()
    print("Lecture continue pendant 10 secondes...")
    print("Bougez la coupole sur le switch pour tester la détection")
    print()

    last_state = state
    transition_count = 0

    start_time = time.time()
    while time.time() - start_time < 10:
        state = lgpio.gpio_read(h, SWITCH_GPIO)

        if state != last_state:
            transition_count += 1
            timestamp = time.strftime("%H:%M:%S")

            print(f"[{timestamp}] Transition #{transition_count:03d} : {last_state}→{state}")

            if last_state == 1 and state == 0:
                print(f"           ✅ FRONT DESCENDANT (1→0) - C'EST CE QUE LE DAEMON CHERCHE!")
            elif last_state == 0 and state == 1:
                print(f"           ⬆️  Front montant (0→1) - Ignoré par daemon")

            last_state = state

        time.sleep(0.02)  # 50 Hz comme le daemon

    print()
    print("=" * 70)
    print(f"✅ Test terminé - {transition_count} transitions détectées")
    print()

    if transition_count == 0:
        print("⚠️  AUCUNE transition détectée !")
        print("   Vérifications :")
        print("   1. Le switch est-il connecté à GPIO 27 ?")
        print("   2. Avez-vous bougé la coupole pendant le test ?")
        print("   3. Le câblage est-il correct (signal + GND) ?")
    else:
        print("✅ lgpio fonctionne correctement dans ce contexte")
        print("   Si daemon ne détecte pas, le problème est ailleurs")

    lgpio.gpiochip_close(h)

except Exception as e:
    print()
    print(f"❌ ERREUR : {e}")
    print()
    print("Causes possibles :")
    print("  1. lgpio non installé (sudo apt install python3-lgpio)")
    print("  2. Pas lancé avec sudo (nécessaire pour GPIO)")
    print("  3. Conflit avec autre processus (arrêtez daemon et test_switch_direct)")
    exit(1)
