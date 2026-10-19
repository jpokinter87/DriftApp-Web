#!/usr/bin/env python3
"""
╔══════════════════════════════════════════════════════════════════════════════╗
║                    TEST B SEUL - VIA MOTOR SERVICE v2                        ║
║                                                                              ║
║  Ce script teste UNIQUEMENT le comportement du moteur via Motor Service.     ║
║                                                                              ║
║  Prérequis:                                                                  ║
║      Le Motor Service doit être lancé AVANT ce script:                       ║
║      sudo ./start_web.sh start                                               ║
║                                                                              ║
║  Usage:                                                                      ║
║      python3 test_motor_service_seul.py                                      ║
║      (pas besoin de sudo car n'accède pas directement aux GPIO)             ║
║                                                                              ║
║  Date: Décembre 2025 - v2 (fix détection Motor Service)                      ║
╚══════════════════════════════════════════════════════════════════════════════╝
"""

import json
import subprocess
import sys
import time
from pathlib import Path

# Fichiers IPC
COMMAND_FILE = Path("/dev/shm/motor_command.json")
STATUS_FILE = Path("/dev/shm/motor_status.json")
ENCODER_FILE = Path("/dev/shm/ems22_position.json")


def print_ok(msg):
    print(f"  ✅ {msg}")


def print_error(msg):
    print(f"  ❌ {msg}")


def print_warning(msg):
    print(f"  ⚠️  {msg}")


def print_info(msg):
    print(f"  ℹ️  {msg}")


def verifier_motor_service() -> bool:
    """
    Vérifie si le Motor Service est actif.

    Méthode 1: Vérifier si le processus tourne (pgrep)
    Méthode 2: Vérifier si le fichier status existe et est récent
    """
    # Méthode 1: pgrep (plus fiable)
    try:
        result = subprocess.run(["pgrep", "-f", "motor_service.py"], capture_output=True, text=True)
        if result.returncode == 0:
            return True
    except Exception:
        pass

    # Méthode 2: fichier status (backup)
    if STATUS_FILE.exists():
        try:
            # Vérifier que le fichier a été modifié récemment (< 10 secondes)
            mtime = STATUS_FILE.stat().st_mtime
            age = time.time() - mtime
            if age < 10:
                return True
        except Exception:
            pass

    return False


def lire_status() -> dict:
    """Lit le status complet du Motor Service."""
    try:
        return json.loads(STATUS_FILE.read_text())
    except Exception:
        return {}


def lire_position() -> float:
    """Lit la position actuelle depuis le Motor Service."""
    status = lire_status()
    return status.get("position", 0)


def lire_etat() -> str:
    """Lit l'état actuel (idle, moving, tracking, etc.)."""
    status = lire_status()
    return status.get("status", "unknown")


def envoyer_commande(command: dict) -> bool:
    """Envoie une commande au Motor Service."""
    command["id"] = f"test_{int(time.time() * 1000)}"
    try:
        COMMAND_FILE.write_text(json.dumps(command))
        return True
    except Exception as e:
        print_error(f"Erreur envoi commande: {e}")
        return False


def attendre_debut_mouvement(timeout: float = 5) -> bool:
    """Attend que le mouvement commence."""
    start = time.time()
    while time.time() - start < timeout:
        if lire_etat() == "moving":
            return True
        time.sleep(0.1)
    return False


def attendre_fin_mouvement(timeout: float = 60) -> bool:
    """Attend que le mouvement soit terminé."""
    start = time.time()
    while time.time() - start < timeout:
        if lire_etat() == "idle":
            return True
        time.sleep(0.1)
    return False


def test_goto(angle_delta: float, description: str) -> int:
    """
    Effectue un test GOTO et demande l'observation.

    Returns:
        int: Observation (1-4) ou 0 si erreur
    """
    position_initiale = lire_position()
    angle_cible = (position_initiale + angle_delta) % 360

    print()
    print(f"  ▶ {description}")
    print(f"    Position actuelle: {position_initiale:.1f}°")
    print(f"    Cible: {angle_cible:.1f}° (delta: {angle_delta:+.1f}°)")
    print()

    input("    ⏎ Appuyez sur ENTRÉE pour lancer le mouvement...")

    print()
    print("  ╔════════════════════════════════════════════════════════════╗")
    print("  ║  👀 OBSERVEZ LE MOTEUR MAINTENANT !                        ║")
    print("  ║     Écoutez le son pendant qu'il tourne...                 ║")
    print("  ╚════════════════════════════════════════════════════════════╝")
    print()

    # Envoyer la commande
    if not envoyer_commande({"command": "goto", "angle": angle_cible}):
        print_error("Impossible d'envoyer la commande")
        return 0

    # Attendre le début du mouvement
    print("    Attente du mouvement...", end=" ", flush=True)
    if not attendre_debut_mouvement(timeout=5):
        print("⚠️ pas de réponse")
        # Continuer quand même, le mouvement a peut-être déjà eu lieu
    else:
        print("🔄 en cours...")

    # Attendre la fin du mouvement
    if attendre_fin_mouvement(timeout=60):
        print_ok("Mouvement terminé")
    else:
        print_warning("Timeout - le mouvement a peut-être échoué")

    position_finale = lire_position()
    erreur = abs(position_finale - angle_cible)
    if erreur > 180:
        erreur = 360 - erreur

    print(f"    Position finale: {position_finale:.1f}° (erreur: {erreur:.2f}°)")

    # Demander observation
    print()
    print("    ╭──────────────────────────────────────────╮")
    print("    │ Comment était le mouvement du moteur ?   │")
    print("    ├──────────────────────────────────────────┤")
    print("    │ 1 = Fluide et régulier                   │")
    print("    │ 2 = Légères saccades                     │")
    print("    │ 3 = Saccades marquées (2-3/sec)          │")
    print("    │ 4 = Très saccadé                         │")
    print("    ╰──────────────────────────────────────────╯")

    while True:
        try:
            obs = int(input("    Votre observation (1-4): "))
            if 1 <= obs <= 4:
                return obs
        except ValueError:
            pass
        print("    Entrez un nombre entre 1 et 4")


def afficher_status_services():
    """Affiche l'état des services."""
    print()
    print("  ┌─────────────────────────────────────────┐")
    print("  │         ÉTAT DES SERVICES               │")
    print("  ├─────────────────────────────────────────┤")

    # Motor Service
    if verifier_motor_service():
        etat = lire_etat()
        pos = lire_position()
        print("  │ Motor Service: ✅ EN COURS             │")
        print(f"  │   État: {etat:<10} Position: {pos:>6.1f}°  │")
    else:
        print("  │ Motor Service: ❌ ARRÊTÉ               │")

    # Daemon encodeur
    if ENCODER_FILE.exists():
        try:
            data = json.loads(ENCODER_FILE.read_text())
            angle = data.get("angle", 0)
            print("  │ Daemon encodeur: ✅ EN COURS           │")
            print(f"  │   Position: {angle:>6.1f}°                   │")
        except Exception:
            print("  │ Daemon encodeur: ⚠️ ERREUR LECTURE     │")
    else:
        print("  │ Daemon encodeur: ❌ ARRÊTÉ             │")

    print("  └─────────────────────────────────────────┘")


def main():
    print()
    print("╔══════════════════════════════════════════════════════════════════╗")
    print("║                                                                  ║")
    print("║         🔧 TEST MOTOR SERVICE - Diagnostic Saccades 🔧          ║")
    print("║                            v2                                    ║")
    print("╚══════════════════════════════════════════════════════════════════╝")

    # Afficher l'état des services
    afficher_status_services()

    # Vérifier que le Motor Service tourne
    print()
    print("  Vérification du Motor Service...")

    if not verifier_motor_service():
        print_error("Le Motor Service n'est pas actif!")
        print()
        print_info("Lancez d'abord les services avec:")
        print("       sudo ./start_web.sh start")
        print()
        print_info("Puis relancez ce script:")
        print("       python3 test_motor_service_seul.py")
        sys.exit(1)

    print_ok("Motor Service actif")
    print_info(f"Position actuelle: {lire_position():.1f}°")
    print_info(f"État: {lire_etat()}")

    print()
    print("  ════════════════════════════════════════════════════════════")
    print("  Ce test va effectuer 3 mouvements GOTO")
    print("  Observez attentivement le comportement du moteur à chaque fois")
    print("  ════════════════════════════════════════════════════════════")

    input("\n  ⏎ Appuyez sur ENTRÉE pour commencer les tests...")

    observations = []

    # Test 1
    obs = test_goto(10, "TEST 1/3 - GOTO +10°")
    if obs:
        observations.append(("Test 1 (+10°)", obs))

    time.sleep(1)

    # Test 2
    obs = test_goto(10, "TEST 2/3 - GOTO +10°")
    if obs:
        observations.append(("Test 2 (+10°)", obs))

    time.sleep(1)

    # Test 3
    obs = test_goto(-20, "TEST 3/3 - GOTO -20° (retour)")
    if obs:
        observations.append(("Test 3 (-20°)", obs))

    # Rapport
    print()
    print("  ════════════════════════════════════════════════════════════")
    print("                    RÉSUMÉ DES OBSERVATIONS")
    print("  ════════════════════════════════════════════════════════════")

    labels = {
        1: "Fluide ✅",
        2: "Légères saccades ⚠️",
        3: "Saccades marquées ❌",
        4: "Très saccadé ❌❌",
    }

    print()
    for nom, obs in observations:
        print(f"    {nom}: {labels[obs]}")

    if observations:
        moyenne = sum(o[1] for o in observations) / len(observations)
        print()
        print("  ────────────────────────────────────────────────────────────")

        if moyenne <= 1.5:
            print()
            print_ok("DIAGNOSTIC: Le Motor Service fonctionne correctement")
            print_info("Le mouvement est fluide via Motor Service.")
            print_info("Si des saccades apparaissent ailleurs, vérifiez le FeedbackController.")

        elif moyenne <= 2.5:
            print()
            print_warning("DIAGNOSTIC: Légères saccades détectées")
            print_info("Le problème vient probablement du contexte Motor Service.")
            print_info("Voir CLAUDE.md section 'Saccades moteur' pour les solutions.")

        else:
            print()
            print_error("DIAGNOSTIC: Saccades importantes via Motor Service!")
            print()
            print_info("Le TEST A (mode isolé) était OK, donc le problème vient")
            print_info("du contexte d'exécution du Motor Service.")
            print()
            print("  Solutions à essayer:")
            print("    1. Désactiver le FileHandler du logging")
            print("    2. Ajouter gc.disable() pendant les mouvements")
            print("    3. Réduire la fréquence d'écriture du status")
            print()
            print_info("Voir CLAUDE.md pour les détails d'implémentation.")

    print()
    print("  ════════════════════════════════════════════════════════════")
    print("  👋 Test terminé")
    print("  ════════════════════════════════════════════════════════════")
    print()


if __name__ == "__main__":
    main()
