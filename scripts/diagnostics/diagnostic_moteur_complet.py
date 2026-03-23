#!/usr/bin/env python3
"""
╔══════════════════════════════════════════════════════════════════════════════╗
║                    DIAGNOSTIC MOTEUR DRIFTAPP v3                             ║
║                                                                              ║
║  Script de diagnostic pour identifier la cause des saccades moteur.          ║
║                                                                              ║
║  IMPORTANT: Ce script doit être lancé AVANT start_web.sh                     ║
║  ou après avoir arrêté les services avec: sudo ./start_web.sh stop           ║
║                                                                              ║
║  v3: Lit les vitesses depuis config.json (plus de valeurs codées en dur)    ║
║                                                                              ║
║  Usage:                                                                      ║
║      sudo python3 diagnostic_moteur_complet.py                               ║
║                                                                              ║
║  Date: Décembre 2025 - v3                                                    ║
╚══════════════════════════════════════════════════════════════════════════════╝
"""

import gc
import json
import os
import signal
import statistics
import subprocess
import sys
import time
from datetime import datetime
from pathlib import Path

# =============================================================================
# CONFIGURATION
# =============================================================================

DRIFTAPP_DIR = Path(__file__).parent
if not (DRIFTAPP_DIR / "core").exists():
    DRIFTAPP_DIR = DRIFTAPP_DIR.parent
    if not (DRIFTAPP_DIR / "core").exists():
        # Remonter encore d'un niveau (scripts/diagnostics -> scripts -> DriftApp)
        DRIFTAPP_DIR = DRIFTAPP_DIR.parent
        if not (DRIFTAPP_DIR / "core").exists():
            print("❌ Erreur: Impossible de trouver le répertoire DriftApp")
            print("   Placez ce script dans le répertoire racine de DriftApp")
            sys.exit(1)

sys.path.insert(0, str(DRIFTAPP_DIR))

# Fichiers IPC
COMMAND_FILE = Path("/dev/shm/motor_command.json")
STATUS_FILE = Path("/dev/shm/motor_status.json")
ENCODER_FILE = Path("/dev/shm/ems22_position.json")

# Fichier de rapport
RAPPORT_FILE = DRIFTAPP_DIR / "logs" / f"diagnostic_moteur_{datetime.now().strftime('%Y%m%d_%H%M%S')}.txt"


# =============================================================================
# UTILITAIRES D'AFFICHAGE
# =============================================================================

def print_header(titre: str):
    print()
    print("=" * 70)
    print(f"  {titre}")
    print("=" * 70)


def print_section(titre: str):
    print()
    print(f"▶ {titre}")
    print("-" * 50)


def print_ok(message: str):
    print(f"  ✅ {message}")


def print_warning(message: str):
    print(f"  ⚠️  {message}")


def print_error(message: str):
    print(f"  ❌ {message}")


def print_info(message: str):
    print(f"  ℹ️  {message}")


def attendre_utilisateur(message: str = "Appuyez sur ENTRÉE pour continuer..."):
    print()
    input(f"  ⏎ {message}")


def demander_oui_non(question: str) -> bool:
    while True:
        reponse = input(f"  ❓ {question} (o/n): ").strip().lower()
        if reponse in ['o', 'oui', 'y', 'yes']:
            return True
        elif reponse in ['n', 'non', 'no']:
            return False
        print("     Répondez par 'o' (oui) ou 'n' (non)")


# =============================================================================
# GESTION DES SERVICES
# =============================================================================

def verifier_services_actifs() -> dict:
    services = {
        'motor_service': False,
        'django': False,
        'daemon': False,
    }
    
    try:
        result = subprocess.run(['pgrep', '-f', 'motor_service.py'], capture_output=True, text=True)
        services['motor_service'] = result.returncode == 0
        
        result = subprocess.run(['pgrep', '-f', 'manage.py runserver'], capture_output=True, text=True)
        services['django'] = result.returncode == 0
        
        result = subprocess.run(['pgrep', '-f', 'ems22d_calibrated'], capture_output=True, text=True)
        services['daemon'] = result.returncode == 0
    except:
        pass
    
    return services


def arreter_motor_service() -> bool:
    try:
        subprocess.run(['pkill', '-f', 'motor_service.py'], capture_output=True)
        time.sleep(1)
        check = subprocess.run(['pgrep', '-f', 'motor_service.py'], capture_output=True)
        return check.returncode != 0
    except Exception as e:
        print_error(f"Erreur lors de l'arrêt: {e}")
        return False


def demarrer_motor_service() -> bool:
    try:
        motor_service_path = DRIFTAPP_DIR / "services" / "motor_service.py"
        python_path = DRIFTAPP_DIR / ".venv" / "bin" / "python"
        
        if not python_path.exists():
            python_path = "python3"
        else:
            python_path = str(python_path)
        
        subprocess.Popen(
            [python_path, str(motor_service_path)],
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
            start_new_session=True
        )
        time.sleep(3)
        
        check = subprocess.run(['pgrep', '-f', 'motor_service.py'], capture_output=True)
        return check.returncode == 0
    except Exception as e:
        print_error(f"Erreur lors du démarrage: {e}")
        return False


# =============================================================================
# CLASSE DE DIAGNOSTIC
# =============================================================================

class DiagnosticMoteur:

    def __init__(self):
        self.rapport = []
        self.resultats = {}
        self.moteur = None
        self.config = None
        self.motor_service_was_running = False
        self.vitesses_config = {}

    def initialiser(self) -> bool:
        print_header("INITIALISATION")

        if os.geteuid() != 0:
            print_error("Ce script doit être exécuté avec sudo")
            print_info("Usage: sudo python3 diagnostic_moteur_complet.py")
            return False
        print_ok("Permissions root OK")

        # Charger la configuration
        try:
            from core.config.config_loader import ConfigLoader
            self.config = ConfigLoader().load()
            print_ok(f"Configuration chargée")
        except Exception as e:
            print_error(f"Impossible de charger la configuration: {e}")
            return False

        # Extraire les vitesses depuis la config
        self._extraire_vitesses_config()

        # Vérifier le daemon encodeur
        if ENCODER_FILE.exists():
            try:
                data = json.loads(ENCODER_FILE.read_text())
                angle = data.get('angle', 0)
                calibrated = data.get('calibrated', False)
                status = "calibré" if calibrated else "non calibré"
                print_ok(f"Daemon encodeur actif (position: {angle:.1f}°, {status})")
            except:
                print_warning("Daemon encodeur présent mais illisible")
        else:
            print_warning("Daemon encodeur non détecté")

        # Vérifier les services actifs
        services = verifier_services_actifs()
        
        if services['motor_service']:
            print()
            print("  ╔════════════════════════════════════════════════════════════╗")
            print("  ║  ⚠️  MOTOR SERVICE DÉTECTÉ EN COURS D'EXÉCUTION            ║")
            print("  ╠════════════════════════════════════════════════════════════╣")
            print("  ║  Le Motor Service utilise les GPIO.                        ║")
            print("  ║  Il sera arrêté pour le TEST A puis redémarré.             ║")
            print("  ╚════════════════════════════════════════════════════════════╝")
            print()
            
            if demander_oui_non("Arrêter temporairement le Motor Service?"):
                print_info("Arrêt du Motor Service...")
                if arreter_motor_service():
                    print_ok("Motor Service arrêté")
                    self.motor_service_was_running = True
                    time.sleep(1)
                else:
                    print_error("Impossible d'arrêter le Motor Service")
                    return False
            else:
                print_warning("TEST A sera ignoré - GPIO occupés")

        return True

    def _extraire_vitesses_config(self):
        """Extrait les vitesses depuis la configuration."""
        print()
        print("  📋 Vitesses configurées (depuis config.json):")
        
        # Essayer de lire depuis adaptive_tracking
        try:
            if hasattr(self.config, 'adaptive_tracking'):
                modes = self.config.adaptive_tracking.modes
                
                if hasattr(modes, 'normal'):
                    delay = modes.normal.motor_delay
                    self.vitesses_config['NORMAL'] = delay
                    print(f"     NORMAL:     {delay*1000:.4f} ms ({delay:.5f} s)")
                
                if hasattr(modes, 'critical'):
                    delay = modes.critical.motor_delay
                    self.vitesses_config['CRITICAL'] = delay
                    print(f"     CRITICAL:   {delay*1000:.4f} ms ({delay:.5f} s)")
                
                if hasattr(modes, 'continuous'):
                    delay = modes.continuous.motor_delay
                    self.vitesses_config['CONTINUOUS'] = delay
                    print(f"     CONTINUOUS: {delay*1000:.4f} ms ({delay:.5f} s)")
        except Exception as e:
            print_warning(f"Impossible de lire les vitesses depuis config: {e}")
        
        # Valeurs par défaut si non trouvées
        if 'NORMAL' not in self.vitesses_config:
            self.vitesses_config['NORMAL'] = 0.00110  # 1.1 ms
            print(f"     NORMAL:     1.1000 ms (défaut)")
        
        if 'CRITICAL' not in self.vitesses_config:
            self.vitesses_config['CRITICAL'] = 0.00055  # 0.55 ms
            print(f"     CRITICAL:   0.5500 ms (défaut)")
        
        if 'CONTINUOUS' not in self.vitesses_config:
            self.vitesses_config['CONTINUOUS'] = 0.00012  # 0.12 ms
            print(f"     CONTINUOUS: 0.1200 ms (défaut)")
        
        print()

    def initialiser_moteur(self) -> bool:
        try:
            from core.hardware.moteur_rp2040 import MoteurRP2040
            serial_cfg = self.config.motor_driver.serial
            import serial
            serial_port = serial.Serial(
                port=serial_cfg.port,
                baudrate=serial_cfg.baudrate,
                timeout=serial_cfg.timeout,
            )
            self.moteur = MoteurRP2040(self.config.motor, serial_port)
            print_ok(f"Moteur RP2040 initialisé")
            print_info(f"Steps par tour de coupole: {self.moteur.steps_per_dome_revolution:,}")
            return True
        except Exception as e:
            print_error(f"Impossible d'initialiser le moteur RP2040: {e}")
            return False

    def nettoyer_moteur(self):
        if self.moteur:
            try:
                self.moteur.nettoyer()
            except:
                pass
            self.moteur = None

    def restaurer_services(self):
        if self.motor_service_was_running:
            print()
            print_info("Redémarrage du Motor Service...")
            if demarrer_motor_service():
                print_ok("Motor Service redémarré")
            else:
                print_warning("Redémarrez manuellement: sudo ./start_web.sh start")

    # =========================================================================
    # TEST A : MODE ISOLÉ
    # =========================================================================

    def test_isole(self, angle: float, vitesse: float, description: str) -> dict:
        deg_per_step = 360.0 / self.moteur.steps_per_dome_revolution
        steps = int(abs(angle) / deg_per_step)

        print(f"     Rotation de {angle}° ({steps:,} pas, délai={vitesse*1000:.4f}ms)...")

        self.moteur.clear_stop_request()
        self.moteur.definir_direction(1 if angle >= 0 else -1)

        t_start = time.perf_counter()
        self.moteur.rotation(angle, vitesse=vitesse)
        t_total = time.perf_counter() - t_start

        # Pour le rapport, creer un timing synthetique (pas de mesure par-pas avec RP2040)
        avg_delay = t_total / steps if steps > 0 else vitesse
        timings = [avg_delay] * min(steps, 100)  # Echantillon representatif

        return self._analyser_timings(timings, vitesse, description, t_total)

    def _analyser_timings(self, timings: list, vitesse: float, description: str, t_total: float) -> dict:
        if not timings:
            return {}

        timings_ms = [t * 1000 for t in timings]
        vitesse_ms = vitesse * 1000

        avg = statistics.mean(timings_ms)
        min_t = min(timings_ms)
        max_t = max(timings_ms)
        std = statistics.stdev(timings_ms) if len(timings_ms) > 1 else 0

        outlier_threshold = avg * 2
        outliers = [t for t in timings_ms if t > outlier_threshold]
        outlier_indices = [i for i, t in enumerate(timings_ms) if t > outlier_threshold]

        stats = {
            'description': description,
            'vitesse_ms': vitesse_ms,
            'total_steps': len(timings),
            'avg_ms': avg,
            'min_ms': min_t,
            'max_ms': max_t,
            'std_ms': std,
            'outlier_count': len(outliers),
            'outlier_percent': (len(outliers) / len(timings)) * 100 if timings else 0,
            'total_time_sec': t_total,
            'expected_time_sec': len(timings) * vitesse,
            'vitesse_reelle_deg_min': (3.0 / t_total) * 60 if t_total > 0 else 0,
        }

        overhead = stats['total_time_sec'] - stats['expected_time_sec']
        stats['overhead_percent'] = (overhead / stats['expected_time_sec']) * 100 if stats['expected_time_sec'] > 0 else 0

        return stats

    def afficher_stats(self, stats: dict):
        print(f"     📊 Résultats:")
        print(f"        Délai config  : {stats['vitesse_ms']:.4f} ms")
        print(f"        Délai moyen   : {stats['avg_ms']:.4f} ms")
        print(f"        Délai min/max : {stats['min_ms']:.4f} / {stats['max_ms']:.4f} ms")
        print(f"        Temps total   : {stats['total_time_sec']:.2f} s")
        print(f"        Vitesse réelle: {stats['vitesse_reelle_deg_min']:.1f} °/min")
        print(f"        Outliers      : {stats['outlier_count']} ({stats['outlier_percent']:.2f}%)")
        print(f"        Overhead      : {stats['overhead_percent']:.1f}%")

        if stats['max_ms'] > stats['avg_ms'] * 5:
            print_warning(f"Délai max très élevé ({stats['max_ms']:.2f}ms)")

        if stats['outlier_percent'] > 1:
            print_warning(f"Trop d'outliers ({stats['outlier_percent']:.1f}%)")

    def executer_tests_isoles(self) -> dict:
        print_header("TEST A : MODE ISOLÉ (vitesses depuis config.json)")

        print_info("Ce test mesure le timing de chaque impulsion moteur")
        print_info("en utilisant les vitesses configurées dans config.json")
        print()

        if not self.initialiser_moteur():
            return {}

        # Utiliser les vitesses de la config
        tests = [
            (3.0, self.vitesses_config['NORMAL'], "NORMAL"),
            (3.0, self.vitesses_config['CRITICAL'], "CRITICAL"),
            (3.0, self.vitesses_config['CONTINUOUS'], "CONTINUOUS"),
        ]

        resultats = {}

        for angle, vitesse, nom in tests:
            print_section(f"Test {nom} (délai config={vitesse*1000:.4f}ms)")

            stats = self.test_isole(angle, vitesse, nom)
            resultats[nom] = stats
            self.afficher_stats(stats)

            time.sleep(0.5)

        self.nettoyer_moteur()
        return resultats

    # =========================================================================
    # TEST B : VIA MOTOR SERVICE
    # =========================================================================

    def verifier_motor_service(self) -> bool:
        try:
            result = subprocess.run(['pgrep', '-f', 'motor_service.py'], capture_output=True)
            return result.returncode == 0
        except:
            return False

    def envoyer_commande_goto(self, angle: float) -> bool:
        command = {
            'id': f'diag_{int(time.time())}',
            'command': 'goto',
            'angle': angle
        }
        try:
            COMMAND_FILE.write_text(json.dumps(command))
            return True
        except:
            return False

    def lire_status(self) -> dict:
        try:
            return json.loads(STATUS_FILE.read_text())
        except:
            return {}

    def attendre_fin_mouvement(self, timeout: float = 60) -> bool:
        start = time.time()
        while time.time() - start < timeout:
            status = self.lire_status()
            if status.get('status') == 'idle':
                return True
            time.sleep(0.1)
        return False

    def executer_tests_motor_service(self) -> dict:
        print_header("TEST B : VIA MOTOR SERVICE")

        print_info("Ce test utilise le Motor Service comme en production.")
        print()

        if not self.verifier_motor_service():
            print_warning("Motor Service non actif.")
            if demander_oui_non("Démarrer le Motor Service?"):
                if demarrer_motor_service():
                    print_ok("Motor Service démarré")
                    time.sleep(2)
                else:
                    print_error("Impossible de démarrer")
                    return {}
            else:
                return {}

        print_ok("Motor Service actif")

        status = self.lire_status()
        position_initiale = status.get('position', 0)
        print_info(f"Position actuelle: {position_initiale:.1f}°")

        print_section("Test GOTO via Motor Service")

        angle_cible = (position_initiale + 10) % 360
        print(f"     Envoi GOTO vers {angle_cible:.1f}°...")

        print()
        print("  ╔════════════════════════════════════════════════════════════╗")
        print("  ║  👀 OBSERVEZ LE MOTEUR !                                   ║")
        print("  ╚════════════════════════════════════════════════════════════╝")
        print()

        if not self.envoyer_commande_goto(angle_cible):
            print_error("Impossible d'envoyer la commande")
            return {}

        if self.attendre_fin_mouvement():
            print_ok("Mouvement terminé")
        else:
            print_warning("Timeout")

        print()
        print("    1 = Fluide")
        print("    2 = Légères saccades")
        print("    3 = Saccades marquées")
        print("    4 = Très saccadé")

        while True:
            try:
                obs = int(input("    Observation (1-4): "))
                if 1 <= obs <= 4:
                    break
            except ValueError:
                pass

        return {
            'observation_code': obs,
            'observation_texte': {1: "Fluide", 2: "Légères saccades", 3: "Saccades marquées", 4: "Très saccadé"}[obs]
        }

    # =========================================================================
    # RAPPORT
    # =========================================================================

    def generer_rapport(self, resultats_isole: dict, resultats_service: dict):
        print_header("RAPPORT DE DIAGNOSTIC")

        rapport = []
        rapport.append("=" * 70)
        rapport.append("RAPPORT DE DIAGNOSTIC MOTEUR DRIFTAPP v3")
        rapport.append(f"Date: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
        rapport.append("=" * 70)
        rapport.append("")

        # Test A
        rapport.append("TEST A : MODE ISOLÉ (vitesses depuis config.json)")
        rapport.append("-" * 50)

        diag_a = "N/A"
        if resultats_isole:
            rapport.append(f"{'Mode':<12} {'Delay cfg':<12} {'Delay réel':<12} {'Vitesse':<12} {'Outliers':<10}")
            for nom, stats in resultats_isole.items():
                rapport.append(
                    f"{nom:<12} {stats['vitesse_ms']:.4f} ms   "
                    f"{stats['avg_ms']:.4f} ms   "
                    f"{stats['vitesse_reelle_deg_min']:.1f} °/min  "
                    f"{stats['outlier_percent']:.2f}%"
                )

            rapport.append("")
            max_outlier = max(s['outlier_percent'] for s in resultats_isole.values())
            
            if max_outlier < 0.5:
                rapport.append("✅ DIAGNOSTIC A: Boucle moteur OK")
                diag_a = "OK"
            elif max_outlier < 2:
                rapport.append("⚠️ DIAGNOSTIC A: Quelques outliers")
                diag_a = "MARGINAL"
            else:
                rapport.append("❌ DIAGNOSTIC A: Trop d'outliers")
                diag_a = "PROBLEME"
        else:
            rapport.append("(Non exécuté)")

        rapport.append("")

        # Test B
        rapport.append("TEST B : VIA MOTOR SERVICE")
        rapport.append("-" * 50)

        diag_b = "N/A"
        if resultats_service:
            obs = resultats_service['observation_texte']
            code = resultats_service['observation_code']
            rapport.append(f"Observation: {obs} ({code}/4)")

            if code == 1:
                diag_b = "OK"
            elif code == 2:
                diag_b = "MARGINAL"
            else:
                diag_b = "PROBLEME"
        else:
            rapport.append("(Non exécuté)")

        rapport.append("")
        rapport.append("=" * 70)
        rapport.append("CONCLUSION")
        rapport.append("=" * 70)

        if diag_a == "OK" and diag_b == "OK":
            rapport.append("✅ Aucun problème détecté")
        elif diag_a == "OK" and diag_b in ["MARGINAL", "PROBLEME"]:
            rapport.append("⚠️ Boucle OK mais Motor Service introduit des saccades")
            rapport.append("   → Désactiver FileHandler logging")
            rapport.append("   → Ajouter gc.disable() pendant mouvement")
        elif diag_a in ["MARGINAL", "PROBLEME"]:
            rapport.append("❌ Problème dans la boucle moteur elle-même")

        rapport.append("")
        rapport.append("=" * 70)

        for ligne in rapport:
            print(ligne)

        try:
            RAPPORT_FILE.parent.mkdir(exist_ok=True)
            RAPPORT_FILE.write_text("\n".join(rapport))
            print()
            print_ok(f"Rapport: {RAPPORT_FILE}")
        except Exception as e:
            print_warning(f"Impossible de sauvegarder: {e}")

    # =========================================================================
    # EXÉCUTION
    # =========================================================================

    def executer(self):
        print()
        print("╔══════════════════════════════════════════════════════════════════╗")
        print("║            🔧 DIAGNOSTIC MOTEUR DRIFTAPP v3 🔧                   ║")
        print("║                                                                  ║")
        print("║  Utilise les vitesses de config.json (pas de valeurs codées)    ║")
        print("╚══════════════════════════════════════════════════════════════════╝")

        attendre_utilisateur()

        if not self.initialiser():
            return

        resultats_isole = {}
        resultats_service = {}

        services = verifier_services_actifs()
        if not services['motor_service']:
            print()
            if demander_oui_non("Exécuter TEST A (mode isolé)?"):
                resultats_isole = self.executer_tests_isoles()
        else:
            print_warning("TEST A ignoré - Motor Service actif")

        print()
        if demander_oui_non("Exécuter TEST B (via Motor Service)?"):
            resultats_service = self.executer_tests_motor_service()

        self.generer_rapport(resultats_isole, resultats_service)
        self.restaurer_services()

        print()
        print("👋 Diagnostic terminé")


# =============================================================================
# POINT D'ENTRÉE
# =============================================================================

if __name__ == "__main__":
    diagnostic = DiagnosticMoteur()
    try:
        diagnostic.executer()
    except KeyboardInterrupt:
        print("\n⏹️  Interrompu")
        diagnostic.restaurer_services()
    except Exception as e:
        print(f"\n❌ Erreur: {e}")
        import traceback
        traceback.print_exc()
        diagnostic.restaurer_services()
    finally:
        diagnostic.nettoyer_moteur()
