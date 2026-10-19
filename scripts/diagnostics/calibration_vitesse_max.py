#!/usr/bin/env python3
"""
╔══════════════════════════════════════════════════════════════════════════════╗
║                    CALIBRATION VITESSE MAXIMALE MOTEUR                       ║
║                                                                              ║
║  Ce script teste différentes vitesses pour trouver la vitesse maximale      ║
║  atteignable de manière fluide (sans saccades).                              ║
║                                                                              ║
║  PRÉREQUIS:                                                                  ║
║  1. Appliquer le patch: python3 patch_motor_service.py                       ║
║  2. Redémarrer les services: sudo ./start_web.sh restart                     ║
║  3. Lancer ce script: python3 calibration_vitesse_max.py                     ║
║                                                                              ║
║  Le script utilise la commande 'test_speed' ajoutée par le patch.           ║
║                                                                              ║
║  Date: Décembre 2025                                                         ║
╚══════════════════════════════════════════════════════════════════════════════╝
"""

import json
import subprocess
import sys
import time
from datetime import datetime
from pathlib import Path

# =============================================================================
# CONFIGURATION
# =============================================================================

# Fichiers IPC
COMMAND_FILE = Path("/dev/shm/motor_command.json")
STATUS_FILE = Path("/dev/shm/motor_status.json")
ENCODER_FILE = Path("/dev/shm/ems22_position.json")

# Vitesses à tester (du plus lent au plus rapide)
# Format: (delay_seconds, description)
VITESSES_A_TESTER = [
    (0.00055, "0.55 ms - CRITICAL actuel"),
    (0.00045, "0.45 ms - Entre CRITICAL et rapide"),
    (0.00040, "0.40 ms - Rapide"),
    (0.00035, "0.35 ms - Très rapide"),
    (0.00030, "0.30 ms - Proche limite"),
    (0.00025, "0.25 ms - À la limite"),
    (0.00020, "0.20 ms - Probablement limite"),
    (0.00015, "0.15 ms - Très agressif"),
    (0.00012, "0.12 ms - CONTINUOUS actuel"),
]

# Angle de rotation pour chaque test
ANGLE_TEST = 5.0  # degrés

# Fichier de rapport (DRIFTAPP_DIR visait scripts/diagnostics/ depuis le
# déplacement du script : le rapport partait dans scripts/diagnostics/logs/)
sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
from core.utils.log_paths import logs_subdir  # noqa: E402

RAPPORT_FILE = (
    logs_subdir("diagnostics")
    / f"calibration_vitesse_{datetime.now().strftime('%Y%m%d_%H%M%S')}.txt"
)


# =============================================================================
# UTILITAIRES
# =============================================================================


def print_ok(msg):
    print(f"  ✅ {msg}")


def print_error(msg):
    print(f"  ❌ {msg}")


def print_warning(msg):
    print(f"  ⚠️  {msg}")


def print_info(msg):
    print(f"  ℹ️  {msg}")


def verifier_motor_service() -> bool:
    """Vérifie si le Motor Service est actif via pgrep."""
    try:
        result = subprocess.run(["pgrep", "-f", "motor_service.py"], capture_output=True, text=True)
        return result.returncode == 0
    except Exception:
        pass
    return False


def lire_status() -> dict:
    """Lit le status du Motor Service."""
    try:
        return json.loads(STATUS_FILE.read_text())
    except Exception:
        return {}


def lire_position() -> float:
    """Lit la position actuelle."""
    return lire_status().get("position", 0)


def lire_etat() -> str:
    """Lit l'état actuel."""
    return lire_status().get("status", "unknown")


def verifier_commande_test_speed() -> bool:
    """
    Vérifie si la commande test_speed est supportée.
    On envoie une micro-commande et on vérifie si elle est traitée.
    """
    # On vérifie simplement si last_test_result existe dans le status
    # après avoir envoyé une commande minimale

    # Envoyer une commande test_speed minimale
    command = {
        "id": f"verify_{int(time.time() * 1000)}",
        "command": "test_speed",
        "angle": 0.1,  # Très petit angle
        "motor_delay": 0.001,
    }

    try:
        COMMAND_FILE.write_text(json.dumps(command))
        time.sleep(2)  # Attendre le traitement

        new_status = lire_status()
        if "last_test_result" in new_status:
            return True

        # Si pas de last_test_result, vérifier si l'état a changé
        if new_status.get("status") == "idle":
            # La commande a peut-être été ignorée silencieusement
            return False

    except Exception as e:
        print_error(f"Erreur vérification: {e}")

    return False


def envoyer_commande_test_speed(angle: float, motor_delay: float) -> dict:
    """
    Envoie une commande test_speed au Motor Service.

    Returns:
        dict avec le résultat du test ou {'error': ...}
    """
    command = {
        "id": f"calib_{int(time.time() * 1000)}",
        "command": "test_speed",
        "angle": angle,
        "motor_delay": motor_delay,
    }

    try:
        # Nettoyer l'ancien résultat
        status = lire_status()
        if "last_test_result" in status:
            del status["last_test_result"]

        # Envoyer la commande
        COMMAND_FILE.write_text(json.dumps(command))

        # Attendre le début du mouvement
        timeout_start = time.time()
        while time.time() - timeout_start < 5:
            if lire_etat() == "moving":
                break
            time.sleep(0.05)

        # Attendre la fin du mouvement
        timeout_move = time.time()
        while time.time() - timeout_move < 30:
            status = lire_status()
            if status.get("status") == "idle":
                # Récupérer le résultat
                result = status.get("last_test_result", {})
                if result:
                    return result
                break
            time.sleep(0.05)

        return {"error": "Timeout ou pas de résultat"}

    except Exception as e:
        return {"error": str(e)}


def demander_observation() -> int:
    """Demande l'observation de l'utilisateur."""
    print()
    print("    ╭────────────────────────────────────────────────╮")
    print("    │ Comment était le mouvement ?                   │")
    print("    ├────────────────────────────────────────────────┤")
    print("    │ 1 = Parfaitement fluide ✅                     │")
    print("    │ 2 = Fluide avec micro-hésitations              │")
    print("    │ 3 = Légères saccades perceptibles ⚠️           │")
    print("    │ 4 = Saccades marquées ❌                       │")
    print("    │ 5 = Très saccadé / claquements ❌❌            │")
    print("    ╰────────────────────────────────────────────────╯")

    while True:
        try:
            obs = int(input("    Votre observation (1-5): "))
            if 1 <= obs <= 5:
                return obs
        except ValueError:
            pass
        print("    Entrez un nombre entre 1 et 5")


# =============================================================================
# TESTS DE VITESSE
# =============================================================================


def tester_vitesse(delay: float, description: str, direction: int) -> dict:
    """
    Teste une vitesse spécifique.

    Args:
        delay: Délai entre les pas en secondes
        description: Description de la vitesse
        direction: 1 pour +, -1 pour -

    Returns:
        dict avec les résultats du test
    """
    angle = ANGLE_TEST * direction

    print()
    print(f"  ▶ Test: {description}")
    print(f"    Délai: {delay * 1000:.2f} ms | Rotation: {angle:+.1f}°")
    print()

    input("    ⏎ Appuyez sur ENTRÉE pour lancer...")

    print()
    print("  ╔════════════════════════════════════════════════════════════╗")
    print("  ║  👀 OBSERVEZ ET ÉCOUTEZ LE MOTEUR !                        ║")
    print("  ╚════════════════════════════════════════════════════════════╝")
    print()

    # Envoyer la commande
    result = envoyer_commande_test_speed(angle, delay)

    if "error" in result:
        print_error(f"Erreur: {result['error']}")
        return {
            "delay_ms": delay * 1000,
            "description": description,
            "error": result["error"],
            "observation": 5,  # Considéré comme échec
        }

    duration = result.get("duration_sec", 0)
    vitesse = result.get("vitesse_deg_min", 0)

    print(f"    ✓ Terminé en {duration:.2f}s")
    print(f"    ✓ Vitesse mesurée: {vitesse:.1f} °/min")

    # Demander l'observation
    observation = demander_observation()

    return {
        "delay_ms": delay * 1000,
        "description": description,
        "duration_sec": duration,
        "vitesse_deg_min": vitesse,
        "observation": observation,
        "success": True,
    }


# =============================================================================
# RAPPORT
# =============================================================================


def generer_rapport(resultats: list):
    """Génère le rapport de calibration."""
    print()
    print("=" * 70)
    print("                    RAPPORT DE CALIBRATION")
    print("=" * 70)
    print()

    rapport = []
    rapport.append("=" * 70)
    rapport.append("RAPPORT DE CALIBRATION VITESSE MAXIMALE MOTEUR")
    rapport.append(f"Date: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    rapport.append("=" * 70)
    rapport.append("")

    # Tableau des résultats
    header = f"{'Délai (ms)':<12} {'Vitesse (°/min)':<16} {'Observation':<20} {'Verdict'}"
    rapport.append(header)
    rapport.append("-" * 70)
    print(f"  {header}")
    print("  " + "-" * 68)

    observations_labels = {
        1: ("Parfait ✅", "OPTIMAL"),
        2: ("Fluide", "OK"),
        3: ("Légères saccades", "LIMITE"),
        4: ("Saccades ❌", "TROP RAPIDE"),
        5: ("Très saccadé ❌❌", "TROP RAPIDE"),
    }

    vitesse_max_fluide = None
    delay_optimal = None

    for r in resultats:
        if "error" in r and r.get("observation", 5) == 5:
            ligne = f"{r['delay_ms']:<12.2f} {'ERREUR':<16} {r.get('error', '?'):<20}"
            rapport.append(ligne)
            print(f"  {ligne}")
            continue

        obs = r.get("observation", 5)
        label, verdict = observations_labels.get(obs, ("?", "?"))
        vitesse = r.get("vitesse_deg_min", 0)

        ligne = f"{r['delay_ms']:<12.2f} {vitesse:<16.1f} {label:<20} {verdict}"
        rapport.append(ligne)
        print(f"  {ligne}")

        # Trouver la vitesse max fluide (observation <= 2)
        if obs <= 2 and (vitesse_max_fluide is None or vitesse > vitesse_max_fluide):
            vitesse_max_fluide = vitesse
            delay_optimal = r["delay_ms"]

    rapport.append("")
    rapport.append("=" * 70)
    rapport.append("RECOMMANDATION")
    rapport.append("=" * 70)

    print()
    print("  " + "=" * 68)
    print("                         RECOMMANDATION")
    print("  " + "=" * 68)

    if delay_optimal:
        recommandation = f"""
  ✅ VITESSE MAXIMALE FLUIDE TROUVÉE
  
     Délai optimal     : {delay_optimal:.2f} ms ({delay_optimal / 1000:.5f} s)
     Vitesse atteinte  : {vitesse_max_fluide:.1f} °/min
     
  📋 MODIFICATION À FAIRE DANS config.json:
  
     "continuous": {{
         "motor_delay": {delay_optimal / 1000:.5f},
         ...
     }}
     
  💡 Cette valeur remplace l'ancienne (0.00012 s) qui causait des saccades.
"""
        rapport.append(recommandation)
        print(recommandation)
    else:
        msg = "  ❌ Aucune vitesse fluide trouvée parmi les tests effectués."
        rapport.append(msg)
        print(msg)
        print()
        print_info("Essayez avec des délais plus élevés (plus lents).")

    # Sauvegarder le rapport
    try:
        RAPPORT_FILE.write_text("\n".join(rapport))
        print()
        print_ok(f"Rapport sauvegardé: {RAPPORT_FILE}")
    except Exception as e:
        print_warning(f"Impossible de sauvegarder: {e}")


# =============================================================================
# PROGRAMME PRINCIPAL
# =============================================================================


def afficher_intro():
    print()
    print("╔══════════════════════════════════════════════════════════════════╗")
    print("║                                                                  ║")
    print("║       🔧 CALIBRATION VITESSE MAXIMALE MOTEUR 🔧                 ║")
    print("║                                                                  ║")
    print("║  Ce programme teste différentes vitesses pour trouver           ║")
    print("║  la vitesse maximale atteignable sans saccades.                  ║")
    print("║                                                                  ║")
    print("║  PRÉREQUIS:                                                      ║")
    print("║  1. Appliquer le patch: python3 patch_motor_service.py          ║")
    print("║  2. Redémarrer: sudo ./start_web.sh restart                      ║")
    print("║                                                                  ║")
    print("╚══════════════════════════════════════════════════════════════════╝")


def afficher_status_services():
    print()
    print("  ┌─────────────────────────────────────────┐")
    print("  │         ÉTAT DES SERVICES               │")
    print("  ├─────────────────────────────────────────┤")

    if verifier_motor_service():
        etat = lire_etat()
        pos = lire_position()
        print("  │ Motor Service: ✅ EN COURS             │")
        print(f"  │   État: {etat:<10} Position: {pos:>6.1f}°  │")
    else:
        print("  │ Motor Service: ❌ ARRÊTÉ               │")

    if ENCODER_FILE.exists():
        try:
            data = json.loads(ENCODER_FILE.read_text())
            angle = data.get("angle", 0)
            print(f"  │ Daemon encodeur: ✅ Position: {angle:>5.1f}°  │")
        except Exception:
            print("  │ Daemon encodeur: ⚠️  ERREUR            │")
    else:
        print("  │ Daemon encodeur: ❌ ARRÊTÉ             │")

    print("  └─────────────────────────────────────────┘")


def main():
    afficher_intro()
    afficher_status_services()

    # Vérifier que le Motor Service tourne
    print()
    print("  Vérification du Motor Service...")

    if not verifier_motor_service():
        print_error("Le Motor Service n'est pas actif!")
        print()
        print_info("Lancez: sudo ./start_web.sh start")
        sys.exit(1)

    print_ok("Motor Service actif")

    # Vérifier que la commande test_speed est supportée
    print()
    print("  Vérification de la commande test_speed...")
    print_info("Envoi d'une commande de test (0.1°)...")

    if not verifier_commande_test_speed():
        print()
        print_error("La commande 'test_speed' n'est pas supportée!")
        print()
        print("  ╔════════════════════════════════════════════════════════════╗")
        print("  ║  Le Motor Service n'a pas été patché.                      ║")
        print("  ║                                                            ║")
        print("  ║  Appliquez d'abord le patch:                               ║")
        print("  ║    python3 patch_motor_service.py                          ║")
        print("  ║                                                            ║")
        print("  ║  Puis redémarrez les services:                             ║")
        print("  ║    sudo ./start_web.sh restart                             ║")
        print("  ║                                                            ║")
        print("  ║  Et relancez ce script.                                    ║")
        print("  ╚════════════════════════════════════════════════════════════╝")
        sys.exit(1)

    print_ok("Commande test_speed supportée!")

    # Confirmation avant de commencer
    print()
    print("  ════════════════════════════════════════════════════════════")
    print(f"  {len(VITESSES_A_TESTER)} vitesses vont être testées")
    print(f"  Rotation de {ANGLE_TEST}° pour chaque test")
    print("  ════════════════════════════════════════════════════════════")

    input("\n  ⏎ Appuyez sur ENTRÉE pour commencer la calibration...")

    # Exécuter les tests
    resultats = []
    direction = 1  # Alterne +/-

    for i, (delay, description) in enumerate(VITESSES_A_TESTER):
        print()
        print("  ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━")
        print(f"                    TEST {i + 1}/{len(VITESSES_A_TESTER)}")
        print("  ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━")

        result = tester_vitesse(delay, description, direction)
        resultats.append(result)

        # Alterner la direction
        direction *= -1

        # Pause entre les tests
        time.sleep(0.5)

        # Permettre d'arrêter
        if i < len(VITESSES_A_TESTER) - 1:
            print()
            reponse = input("  Continuer avec la vitesse suivante? (o/n): ").strip().lower()
            if reponse in ["n", "non", "no"]:
                print_info("Calibration interrompue par l'utilisateur")
                break

    # Générer le rapport
    generer_rapport(resultats)

    print()
    print("  ════════════════════════════════════════════════════════════")
    print("  👋 Calibration terminée")
    print("  ════════════════════════════════════════════════════════════")
    print()


if __name__ == "__main__":
    try:
        main()
    except KeyboardInterrupt:
        print("\n\n  ⏹️  Calibration interrompue")
    except Exception as e:
        print(f"\n  ❌ Erreur: {e}")
        import traceback

        traceback.print_exc()
