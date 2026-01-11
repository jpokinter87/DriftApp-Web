"""
Module de détection automatique du matériel (Raspberry Pi, démon encodeur, moteur).
VERSION DAEMON : Détecte le démon encodeur au lieu du singleton.
"""

import fcntl
import json
import logging
import platform
import subprocess
import time
from pathlib import Path
from typing import Tuple, Optional

logger = logging.getLogger(__name__)


class HardwareDetector:
    """Détecte la présence du matériel de l'observatoire."""

    @staticmethod
    def is_raspberry_pi() -> bool:
        """
        Détecte si le code s'exécute sur un Raspberry Pi.

        Returns:
            True si sur Raspberry Pi, False sinon
        """
        # Méthode 1: Vérifier le fichier /proc/cpuinfo
        cpuinfo_path = Path("/proc/cpuinfo")
        if cpuinfo_path.exists():
            try:
                with open(cpuinfo_path, "r") as f:
                    cpuinfo = f.read().lower()
                    if "raspberry pi" in cpuinfo or "bcm" in cpuinfo:
                        return True
            except Exception:
                pass

        # Méthode 2: Vérifier le fichier device-tree model
        model_path = Path("/proc/device-tree/model")
        if model_path.exists():
            try:
                with open(model_path, "r") as f:
                    model = f.read().lower()
                    if "raspberry pi" in model:
                        return True
            except Exception:
                pass

        # Méthode 3: Vérifier la plateforme ARM
        machine = platform.machine().lower()
        if machine in ["armv7l", "armv6l", "aarch64"]:
            if platform.system().lower() == "linux":
                return True

        return False

    @staticmethod
    def check_gpio_available() -> Tuple[bool, Optional[str]]:
        """
        Vérifie si les GPIO sont disponibles (nécessaire pour le moteur).
        Support RPi.GPIO (Pi 1-4) et gpiod/lgpio (Pi 5).

        Returns:
            Tuple (is_available, error_message)
        """
        # Essayer RPi.GPIO (Pi 1-4)
        try:
            import RPi.GPIO as GPIO
            try:
                GPIO.setmode(GPIO.BCM)
                GPIO.setwarnings(False)
                return True, None
            except RuntimeError as e:
                return False, f"Erreur GPIO: {str(e)}"
        except ImportError:
            pass

        # Essayer lgpio (Raspberry Pi 5)
        try:
            import lgpio
            try:
                h = lgpio.gpiochip_open(0)
                lgpio.gpiochip_close(h)
                return True, None
            except Exception as e:
                return False, f"Erreur lgpio: {str(e)}"
        except ImportError:
            pass

        # Essayer gpiod (alternative)
        try:
            import gpiod
            try:
                chip = gpiod.Chip('gpiochip0')
                chip.close()
                return True, None
            except Exception as e:
                return False, f"Erreur gpiod: {str(e)}"
        except ImportError:
            pass

        # Vérifier si le device GPIO existe
        gpio_devices = ["/dev/gpiochip0", "/dev/gpiochip4", "/sys/class/gpio"]
        for device in gpio_devices:
            if Path(device).exists():
                return True, "GPIO device présent mais bibliothèque Python manquante"

        return False, "Aucune bibliothèque GPIO disponible (RPi.GPIO, lgpio, gpiod)"

    @staticmethod
    def check_encoder_daemon() -> Tuple[bool, Optional[str], Optional[float]]:
        """
        Vérifie si le démon encodeur EMS22A est disponible et fonctionnel.

        Returns:
            Tuple (is_available, error_message, test_position)
        """
        daemon_json = Path("/dev/shm/ems22_position.json")
        
        # Vérifier si le fichier existe
        if not daemon_json.exists():
            return False, "Démon encodeur non actif (fichier JSON absent)", None
        
        try:
            # Lire le fichier JSON avec verrou fcntl
            with open(daemon_json, "r") as f:
                fcntl.flock(f.fileno(), fcntl.LOCK_SH | fcntl.LOCK_NB)
                try:
                    data = json.load(f)
                finally:
                    fcntl.flock(f.fileno(), fcntl.LOCK_UN)

            # Vérifier le statut
            status = data.get("status", "UNKNOWN")
            angle = data.get("angle", None)
            timestamp = data.get("ts", 0)
            
            # Vérifier que le fichier est récent (< 5 secondes)
            age = time.time() - timestamp
            if age > 5:
                return False, f"Démon encodeur inactif (dernière mise à jour: {age:.1f}s)", None
            
            if status == "OK":
                if angle is not None and 0 <= angle <= 360:
                    return True, None, float(angle)
                else:
                    return False, f"Position invalide: {angle}°", None
            else:
                return False, f"Démon encodeur en erreur: {status}", angle if angle else None
                
        except BlockingIOError:
            return False, "Fichier démon verrouillé, réessayer", None
        except json.JSONDecodeError as e:
            return False, f"Erreur lecture JSON démon: {str(e)}", None
        except Exception as e:
            return False, f"Erreur accès démon: {str(e)}", None

    @staticmethod
    def check_spi_devices() -> dict:
        """
        Vérifie la présence du bus SPI (utilisé par l'encodeur EMS22A).

        Returns:
            Dict avec les informations SPI
        """
        spi_info = {
            "spi_available": False,
            "spi_devices": []
        }

        # Vérifier les devices SPI
        spi_paths = ["/dev/spidev0.0", "/dev/spidev0.1", "/dev/spidev1.0", "/dev/spidev1.1"]
        for path in spi_paths:
            if Path(path).exists():
                spi_info["spi_available"] = True
                spi_info["spi_devices"].append(path)

        # Vérifier si le module SPI est chargé
        try:
            result = subprocess.run(["lsmod"], capture_output=True, text=True, timeout=2)
            if "spi_bcm" in result.stdout:
                spi_info["spi_module"] = "loaded"
            else:
                spi_info["spi_module"] = "not loaded"
        except (subprocess.TimeoutExpired, subprocess.SubprocessError, OSError):
            spi_info["spi_module"] = "unknown"

        return spi_info

    @staticmethod
    def check_daemon_process() -> bool:
        """
        Vérifie si le processus démon ems22d_calibrated tourne.

        Returns:
            True si le démon tourne
        """
        try:
            result = subprocess.run(
                ["ps", "aux"],
                capture_output=True,
                text=True,
                timeout=2
            )
            return "ems22d_calibrated" in result.stdout
        except (subprocess.TimeoutExpired, subprocess.SubprocessError, OSError):
            return False

    @staticmethod
    def test_motor_pins() -> Tuple[bool, Optional[str]]:
        """
        Test basique de connectivité des pins du moteur.
        NOTE: Test désactivé car nécessite config.json.

        Returns:
            Tuple (pins_ok, error_message)
        """
        return False, "Test désactivé (constructeur nécessite config.json)"

    @staticmethod
    def detect_hardware() -> Tuple[bool, dict]:
        """
        Détecte tous les composants matériels disponibles.

        Returns:
            Tuple (is_production_mode, hardware_info)
        """
        is_rpi = HardwareDetector.is_raspberry_pi()
        rpi_model = HardwareDetector.get_raspberry_pi_model() if is_rpi else None

        gpio_ok, gpio_error = (False, "Non testé") if not is_rpi else HardwareDetector.check_gpio_available()
        encoder_ok, encoder_error, encoder_pos = HardwareDetector.check_encoder_daemon()
        motor_ok, motor_error = (False, "Non testé") if not is_rpi else HardwareDetector.test_motor_pins()

        spi_info = HardwareDetector.check_spi_devices() if is_rpi else {}
        daemon_running = HardwareDetector.check_daemon_process()

        hardware_info = {
            "raspberry_pi": is_rpi,
            "rpi_model": rpi_model,
            "gpio": gpio_ok,
            "gpio_error": gpio_error,
            "encoder_daemon": encoder_ok,
            "encoder_error": encoder_error,
            "encoder_position": encoder_pos,
            "daemon_process": daemon_running,
            "motor": motor_ok,
            "motor_error": motor_error,
            "spi_available": spi_info.get("spi_available", False),
            "spi_devices": spi_info.get("spi_devices", []),
            "platform": platform.platform(),
            "machine": platform.machine(),
            "system": platform.system(),
        }

        # Mode production si Raspberry Pi + GPIO fonctionnel
        # Le démon encodeur est optionnel (fallback sur position logicielle)
        is_production_mode = is_rpi and gpio_ok

        return is_production_mode, hardware_info

    @staticmethod
    def get_raspberry_pi_model() -> Optional[str]:
        """Détecte le modèle exact du Raspberry Pi."""
        model_path = Path("/proc/device-tree/model")
        if model_path.exists():
            try:
                with open(model_path, "r") as f:
                    return f.read().strip().replace('\x00', '')
            except Exception:
                pass
        return None

    @staticmethod
    def get_hardware_summary(hardware_info: dict) -> str:
        """
        Génère un résumé textuel de la détection matérielle.

        Args:
            hardware_info: Dict retourné par detect_hardware()

        Returns:
            Résumé formaté
        """
        summary = []
        summary.append("╔" + "═" * 78 + "╗")
        summary.append("║" + " " * 25 + "DÉTECTION MATÉRIELLE" + " " * 33 + "║")
        summary.append("╚" + "═" * 78 + "╝")
        summary.append("")

        # Plateforme
        summary.append("PLATEFORME:")
        summary.append(f"  Système:      {hardware_info['system']}")
        summary.append(f"  Architecture: {hardware_info['machine']}")
        summary.append("")

        # Raspberry Pi
        summary.append("RASPBERRY PI:")
        if hardware_info['raspberry_pi']:
            summary.append(f"  Détecté:      ✓ OUI")
            if hardware_info['rpi_model']:
                summary.append(f"  Modèle:       {hardware_info['rpi_model']}")
        else:
            summary.append(f"  Détecté:      ✗ NON")
        summary.append("")

        # GPIO
        summary.append("GPIO:")
        if hardware_info['gpio']:
            summary.append(f"  Disponible:   ✓ OUI")
        else:
            summary.append(f"  Disponible:   ✗ NON")
            if hardware_info['gpio_error']:
                summary.append(f"  Info:         {hardware_info['gpio_error']}")
        summary.append("")

        # SPI
        if hardware_info.get('spi_available'):
            summary.append("BUS SPI:")
            summary.append(f"  Disponible:   ✓ OUI")
            if hardware_info.get('spi_devices'):
                summary.append(f"  Devices:      {', '.join(hardware_info['spi_devices'])}")
            summary.append("")

        # Démon Encodeur
        summary.append("DÉMON ENCODEUR EMS22A:")
        if hardware_info['encoder_daemon']:
            summary.append(f"  Actif:        ✓ OUI")
            if hardware_info['encoder_position'] is not None:
                summary.append(f"  Position:     {hardware_info['encoder_position']:.2f}°")
        else:
            summary.append(f"  Actif:        ✗ NON")
            if hardware_info['encoder_error']:
                summary.append(f"  Info:         {hardware_info['encoder_error']}")
            
        if hardware_info.get('daemon_process'):
            summary.append(f"  Processus:    ✓ Trouvé (ems22d_calibrated)")
        else:
            summary.append(f"  Processus:    ✗ Non trouvé")
            summary.append(f"  → Lancer:     sudo python3 ems22d_calibrated.py &")
        summary.append("")

        # Moteur
        summary.append("MOTEUR COUPOLE:")
        if hardware_info['motor']:
            summary.append(f"  Disponible:   ✓ OUI")
        else:
            summary.append(f"  Disponible:   ✗ NON")
            if hardware_info['motor_error']:
                summary.append(f"  Info:         {hardware_info['motor_error']}")
        summary.append("")

        # Conclusion
        summary.append("─" * 80)
        if hardware_info['raspberry_pi'] and hardware_info['gpio']:
            summary.append("→ MODE PRODUCTION ACTIVÉ")
            summary.append("  Le système peut piloter la coupole physiquement.")
            if not hardware_info['encoder_daemon']:
                summary.append("  ⚠️  Démon encodeur inactif : mode position logicielle")
                summary.append("     Lancer: sudo python3 ems22d_calibrated.py &")
        else:
            summary.append("→ MODE SIMULATION ACTIVÉ")
            summary.append("  Raisons:")
            if not hardware_info['raspberry_pi']:
                summary.append("    - Raspberry Pi non détecté")
            if not hardware_info['gpio']:
                summary.append("    - GPIO non disponible")
            summary.append("  Le système fonctionnera en mode développement.")
        summary.append("─" * 80)

        return "\n".join(summary)

    @staticmethod
    def save_detection_report(hardware_info: dict, filepath: str = "logs/hardware_detection.txt"):
        """Sauvegarde un rapport de détection dans un fichier."""
        try:
            import time
            Path(filepath).parent.mkdir(parents=True, exist_ok=True)

            with open(filepath, "w", encoding="utf-8") as f:
                f.write(f"Rapport de détection matérielle\n")
                f.write(f"Date: {time.strftime('%Y-%m-%d %H:%M:%S')}\n")
                f.write(f"Architecture: DAEMON\n\n")
                f.write(HardwareDetector.get_hardware_summary(hardware_info))
                f.write("\n\nDétails JSON:\n")
                
                import json
                f.write(json.dumps(hardware_info, indent=2, ensure_ascii=False))

            return True
        except Exception as e:
            logger.error(f"Erreur sauvegarde rapport: {e}")
            return False


# Test si exécuté directement
if __name__ == "__main__":
    print("\n" + "="*80)
    print("TEST DE DÉTECTION MATÉRIELLE - ARCHITECTURE DAEMON")
    print("="*80 + "\n")

    is_prod, hw_info = HardwareDetector.detect_hardware()

    print(HardwareDetector.get_hardware_summary(hw_info))
    print()

    if HardwareDetector.save_detection_report(hw_info):
        print("✓ Rapport sauvegardé dans logs/hardware_detection.txt")

    print(f"\nRésultat: Mode {'PRODUCTION' if is_prod else 'SIMULATION'}")
