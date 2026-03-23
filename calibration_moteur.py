#!/usr/bin/env python3
"""
🎛️ OUTIL DE CALIBRATION MOTEUR - Mode Interactif

Permet de tester et calibrer les vitesses du moteur pour déterminer
les valeurs optimales de motor_delay pour chaque mode de suivi.

Usage:
    python calibration_moteur.py
"""

import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

from core.config.config_loader import load_config
from core.hardware.moteur_rp2040 import MoteurRP2040


class MotorCalibrator:
    def __init__(self):
        self.config = load_config()
        serial_cfg = self.config.motor_driver.serial
        import serial
        serial_port = serial.Serial(
            port=serial_cfg.port,
            baudrate=serial_cfg.baudrate,
            timeout=serial_cfg.timeout,
        )
        self.moteur = MoteurRP2040(self.config.motor, serial_port)

        # Valeurs actuelles du config
        self.modes_config = {
            'normal': self.config.adaptive.modes['normal'],
            'critical': self.config.adaptive.modes['critical'],
            'continuous': self.config.adaptive.modes['continuous']
        }

        # Historique des mesures
        self.mesures = []

    def calculer_vitesse_theorique(self, motor_delay):
        """Calcule la vitesse théorique en °/min."""
        steps_per_degree = self.moteur.steps_per_dome_revolution / 360.0
        degrees_per_second = 1.0 / (motor_delay * steps_per_degree)
        return degrees_per_second * 60.0

    def executer_rotation(self, angle_deg, motor_delay):
        """Exécute une rotation et mesure la vitesse réelle."""
        print(f"\n⏳ Rotation de {angle_deg}° avec delay={motor_delay}s...")

        vitesse_theo = self.calculer_vitesse_theorique(motor_delay)
        print(f"   Vitesse théorique: {vitesse_theo:.1f}°/min")

        start = time.time()
        self.moteur.rotation(angle_deg, vitesse=motor_delay)
        duree = time.time() - start

        # AJOUT : pause pour stabilisation électromagnétique
        time.sleep(0.2)

        vitesse_reelle = (angle_deg / duree) * 60
        ecart = abs(vitesse_reelle - vitesse_theo) / vitesse_theo * 100

        print(f"   ✅ Durée: {duree:.1f}s")
        print(f"   ✅ Vitesse réelle: {vitesse_reelle:.1f}°/min")
        print(f"   ✅ Écart: {ecart:.1f}%")

        self.mesures.append({
            'angle': angle_deg,
            'delay': motor_delay,
            'vitesse_theo': vitesse_theo,
            'vitesse_reelle': vitesse_reelle,
            'ecart': ecart
        })

        return vitesse_reelle

    def afficher_config_actuelle(self):
        """Affiche la config actuelle."""
        print("\n" + "=" * 70)
        print("📋 CONFIGURATION ACTUELLE (config.json)")
        print("=" * 70)
        print(f"\n{'Mode':<15} {'Delay (s)':<15} {'Vitesse théo':<15}")
        print("-" * 70)

        for nom, mode in self.modes_config.items():
            vitesse = self.calculer_vitesse_theorique(mode.motor_delay)
            print(f"{nom.upper():<15} {mode.motor_delay:<15.6f} {vitesse:>6.1f}°/min")

        print("\n💡 Note: On ajuste UNIQUEMENT motor_delay (autres paramètres fixés)")

    def afficher_parametres_systeme(self):
        """Affiche les paramètres système (lecture seule)."""
        print("\n" + "=" * 70)
        print("📊 PARAMÈTRES SYSTÈME (lecture seule)")
        print("=" * 70)
        
        print(f"\n🔧 Moteur NEMA:")
        print(f"  Steps/revolution    : {self.config.motor.steps_per_revolution}")
        print(f"  Microsteps          : {self.config.motor.microsteps}")
        print(f"  → Steps moteur/tour : {self.config.motor.steps_per_revolution * self.config.motor.microsteps}")
        
        print(f"\n⚙️  Mécanique:")
        print(f"  Gear ratio          : {self.config.motor.gear_ratio:.1f}:1")
        print(f"  Correction factor   : {self.config.motor.steps_correction_factor:.5f}")
        
        print(f"\n📐 Résultat final:")
        print(f"  Steps/tour coupole  : {self.moteur.steps_per_dome_revolution:,}")
        precision = 360 / self.moteur.steps_per_dome_revolution
        print(f"  Précision           : {precision:.6f}°/step")
        print(f"                      = {precision * 60:.4f}'/step")
        print(f"                      = {precision * 3600:.2f}''/step")
        
        print(f"\n⚠️  Ces paramètres sont FIXES (calibrés sur site)")
        print(f"   → Modifier gear_ratio ou correction_factor casserait le positionnement")
        print(f"   → Seul motor_delay est ajustable pour changer la vitesse")

    def menu_principal(self):
        """Menu interactif principal."""
        while True:
            print("\n" + "=" * 70)
            print("🎛️  MENU CALIBRATION MOTEUR")
            print("=" * 70)
            print("\n1. Afficher config actuelle")
            print("2. Test rapide (3° à différentes vitesses)")
            print("3. Test personnalisé (choisir angle + delay)")
            print("4. Proposer valeurs optimales")
            print("5. Historique des mesures")
            print("6. Paramètres système (lecture seule)")
            print("0. Quitter")

            choix = input("\n▶️  Votre choix: ").strip()

            if choix == '0':
                break
            elif choix == '1':
                self.afficher_config_actuelle()
            elif choix == '2':
                self.test_rapide()
            elif choix == '3':
                self.test_personnalise()
            elif choix == '4':
                self.proposer_valeurs()
            elif choix == '5':
                self.afficher_historique()
            elif choix == '6':
                self.afficher_parametres_systeme()

    def test_rapide(self):
        """Test rapide avec valeurs prédéfinies."""
        print("\n🚀 TEST RAPIDE")
        tests = [
            (0.002, "NORMAL"),
            (0.001, "CRITICAL (actuel)"),
            (0.0005, "Vitesse moyenne"),
            (0.00015, "CONTINUOUS (actuel)")
        ]

        for delay, desc in tests:
            print(f"\n➡️  {desc}")
            self.executer_rotation(3.0, delay)
            input("   [Appuyez sur ENTRÉE pour continuer]")

    def test_personnalise(self):
        """Test avec paramètres personnalisés."""
        print("\n🔧 TEST PERSONNALISÉ")

        try:
            angle = float(input("Angle à parcourir (°): "))
            delay = float(input("motor_delay (s, ex: 0.001): "))

            if angle <= 0 or delay <= 0:
                print("❌ Valeurs invalides")
                return

            vitesse_theo = self.calculer_vitesse_theorique(delay)
            print(f"\n📊 Vitesse théorique: {vitesse_theo:.1f}°/min")

            confirm = input("Lancer le test? (o/N): ").lower()
            if confirm == 'o':
                self.executer_rotation(angle, delay)

        except ValueError:
            print("❌ Entrée invalide")

    def proposer_valeurs(self):
        """Analyse les mesures et propose des valeurs optimales."""
        if not self.mesures:
            print("\n⚠️  Aucune mesure disponible. Effectuez des tests d'abord.")
            return

        print("\n" + "=" * 70)
        print("💡 PROPOSITION VALEURS OPTIMALES")
        print("=" * 70)

        # Objectifs de vitesse
        objectifs = {
            'normal': 5.0,  # 5°/min
            'critical': 18.0,  # ~18°/min
            'continuous': 41.0  # ~41°/min
        }

        print("\n🎯 Objectifs de vitesse:")
        for mode, vitesse in objectifs.items():
            print(f"   {mode.upper():<12} {vitesse:>5.1f}°/min")

        print("\n📐 Valeurs recommandées (motor_delay):")
        for mode, vitesse_cible in objectifs.items():
            # Trouver delay pour obtenir cette vitesse
            steps_per_degree = self.moteur.steps_per_dome_revolution / 360.0
            delay_optimal = 60.0 / (vitesse_cible * steps_per_degree)

            print(f"   {mode.upper():<12} {delay_optimal:.6f}s → {vitesse_cible:.1f}°/min")

        print("\n📝 À mettre dans config.json > adaptive > modes:")
        print('   "normal": {"motor_delay": 0.002000, ...}')
        print('   "critical": {"motor_delay": 0.000550, ...}')
        print('   "continuous": {"motor_delay": 0.000240, ...}')

    def afficher_historique(self):
        """Affiche l'historique des mesures."""
        if not self.mesures:
            print("\n⚠️  Aucune mesure")
            return

        print("\n" + "=" * 70)
        print("📊 HISTORIQUE DES MESURES")
        print("=" * 70)
        print(f"\n{'Delay (s)':<12} {'Angle (°)':<10} {'Vitesse réelle':<15}")
        print("-" * 70)

        for m in self.mesures:
            print(f"{m['delay']:<12.6f} {m['angle']:<10.1f} {m['vitesse_reelle']:>6.1f}°/min")


def main():
    print("=" * 70)
    print("🎛️  CALIBRATION MOTEUR - Mode Interactif")
    print("=" * 70)
    print("\nCet outil permet de tester différentes vitesses et de déterminer")
    print("les valeurs optimales de motor_delay pour chaque mode de suivi.\n")

    try:
        calibrator = MotorCalibrator()
        calibrator.menu_principal()

    except KeyboardInterrupt:
        print("\n\n⏸️  Calibration interrompue")
    except Exception as e:
        print(f"\n❌ Erreur: {e}")
        import traceback
        traceback.print_exc()
    finally:
        try:
            calibrator.moteur.nettoyer()
        except:
            pass

    print("\n👋 Calibration terminée")


if __name__ == "__main__":
    main()