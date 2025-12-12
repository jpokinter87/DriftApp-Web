#!/usr/bin/env python3
# ems22d_calibrated_with_switch.py - VERSION CORRIGÉE
"""
Daemon EMS22A + switch de recalage (VERSION CORRIGÉE)
- Lecture SPI (EMS22A) avec méthode INCRÉMENTALE
- Recalage automatique via microswitch SS-5GL (GPIO27)
- Publie angle CALIBRÉ dans /dev/shm/ems22_position.json
- Compatible Raspberry Pi 5 (lgpio)

CORRECTIONS APPLIQUÉES (5 décembre 2025):
1. Port TCP changé (5555 → 5556) pour éviter conflit
2. CALIBRATION_FACTOR corrigé (0.031354 → 0.010851)
3. Méthode INCRÉMENTALE (accumulation) au lieu d'absolue
4. Filtre anti-saut assoupli (5° → 30°)
5. Logique switch : recale total_counts pour cohérence
6. Anti-rebond switch (2s) - ignore calibrations successives trop rapprochées (6 déc 2025)
"""

import json
import logging
import socket
import threading
import time
from logging.handlers import RotatingFileHandler
from pathlib import Path

import lgpio

try:
    import spidev
    SPIDEV = True
except Exception:
    SPIDEV = False
    spidev = None

# ----------------------------------------------------
# CONFIGURATION
# ----------------------------------------------------
JSON_OUT = Path("/dev/shm/ems22_position.json")
TCP_PORT = 5556  # ✅ CORRIGÉ : Port différent de l'ancien démon (5555)
POLL_HZ = 50
MEDIAN_WINDOW = 5

SPI_BUS = 0
SPI_DEVICE = 0
SPI_SPEED_HZ = 500_000
SPI_MODE = 0

SWITCH_GPIO = 27         # GPIO connecté au microswitch SS-5GL
SWITCH_CALIB_ANGLE = 45  # Angle auquel se recale la couronne
SWITCH_DEBOUNCE_SEC = 2.0  # Délai minimum entre calibrations (anti-rebond)

COUNTS_PER_REV = 1024
CALIBRATION_FACTOR = 0.01077 / 0.9925  # ✅ CORRIGÉ : = 0.010851 (était 0.031354)
ROTATION_SIGN = -1

MAX_CONSECUTIVE_SPI_ERRORS = 5
WRITE_TMP = JSON_OUT.with_suffix(".tmp")

# Configuration logging : fichier + console
LOG_DIR = Path(__file__).parent / "logs"
LOG_DIR.mkdir(exist_ok=True)
LOG_FILE = LOG_DIR / "ems22d.log"

logger = logging.getLogger("ems22d")
logger.setLevel(logging.INFO)

# Format commun
formatter = logging.Formatter("[ems22d] %(asctime)s %(levelname)s %(message)s")

# Handler 1 : Fichier rotatif (10 MB max, 3 backups)
file_handler = RotatingFileHandler(
    LOG_FILE,
    maxBytes=10*1024*1024,  # 10 MB
    backupCount=3,
    encoding='utf-8'
)
file_handler.setLevel(logging.INFO)
file_handler.setFormatter(formatter)
logger.addHandler(file_handler)

# Handler 2 : Console (pour mode foreground)
console_handler = logging.StreamHandler()
console_handler.setLevel(logging.INFO)
console_handler.setFormatter(formatter)
logger.addHandler(console_handler)


# ----------------------------------------------------
# DAEMON
# ----------------------------------------------------
class EMS22Daemon:
    def __init__(self):
        self.spi = None
        self.running = False
        self.lock = threading.Lock()

        self.spi_errors = 0
        self.last_valid_angle = None
        self.angle_history = []

        # ✅ AJOUT : Méthode incrémentale (comme script qui fonctionne)
        self.prev_raw = None
        self.total_counts = 0

        # Gestion du switch
        self.hchip = lgpio.gpiochip_open(0)
        lgpio.gpio_claim_input(self.hchip, SWITCH_GPIO, lgpio.SET_PULL_UP)
        # Lire l'état réel au démarrage (évite calibration fantôme si coupole sur switch)
        self.switch_last_state = lgpio.gpio_read(self.hchip, SWITCH_GPIO)
        self.last_calibration_time = 0  # Anti-rebond : timestamp dernière calibration
        self.calibrated = False  # Flag: true après premier passage sur switch
        logger.info(f"Switch GPIO {SWITCH_GPIO} configuré (pull-up) - état initial : {self.switch_last_state}")

    # ------------------------------------------------
    # SPI
    # ------------------------------------------------
    def open_spi(self):
        if not SPIDEV:
            raise RuntimeError("spidev absent")
        if self.spi:
            try:
                self.spi.close()
            except Exception:
                pass
        self.spi = spidev.SpiDev()
        self.spi.open(SPI_BUS, SPI_DEVICE)
        self.spi.max_speed_hz = SPI_SPEED_HZ
        self.spi.mode = SPI_MODE
        logger.info(f"SPI opened {SPI_BUS}.{SPI_DEVICE} @ {SPI_SPEED_HZ} Hz")

    def close_spi(self):
        if self.spi:
            try:
                self.spi.close()
            except Exception:
                pass
        self.spi = None

    def read_raw(self):
        """Lit la valeur brute 10 bits du EMS22A."""
        if not self.spi:
            raise RuntimeError("SPI not opened")
        data = self.spi.xfer2([0x00, 0x00])
        raw = ((data[0] & 0x3F) << 4) | (data[1] >> 4)
        return raw & 0x3FF

    # ------------------------------------------------
    # ✅ MÉTHODE INCRÉMENTALE (comme script qui fonctionne)
    # ------------------------------------------------
    def update_counts(self, raw):
        """
        Méthode INCRÉMENTALE - Accumule les changements.
        Permet de suivre les mouvements de la coupole.
        """
        if self.prev_raw is None:
            # Première lecture : initialiser
            self.prev_raw = raw
            return self.total_counts

        # Calculer delta avec gestion wrapping 0-1023
        diff = raw - self.prev_raw
        if diff > 512:
            diff -= 1024
        elif diff < -512:
            diff += 1024

        # Accumulation des changements
        self.total_counts += diff
        self.prev_raw = raw

        return self.total_counts

    def raw_to_calibrated(self, raw):
        """
        Convertit raw → angle couronne calibré.
        Utilise la méthode INCRÉMENTALE (total_counts).
        """
        counts = self.update_counts(raw)
        wheel_degrees = (counts / COUNTS_PER_REV) * 360.0
        ring_deg = wheel_degrees * CALIBRATION_FACTOR * ROTATION_SIGN
        return ring_deg % 360.0

    # ------------------------------------------------
    # Microswitch
    # ------------------------------------------------
    def read_switch(self):
        """Retourne 1 (ouvert) / 0 (pressé)."""
        return lgpio.gpio_read(self.hchip, SWITCH_GPIO)

    def process_switch(self, angle):
        """
        Détection du front descendant du microswitch.
        Recale l'angle ET total_counts pour cohérence avec méthode incrémentale.

        Front descendant (1→0) = coupole physiquement à 45°.
        """
        state = self.read_switch()

        # DEBUG: Log les transitions pour diagnostiquer
        if state != self.switch_last_state:
            logger.info(f"[DEBUG] Switch transition: {self.switch_last_state}→{state}")

        if self.switch_last_state == 1 and state == 0:
            # ✅ Anti-rebond : vérifier délai depuis dernière calibration
            now = time.time()
            time_since_last_calib = now - self.last_calibration_time

            if time_since_last_calib < SWITCH_DEBOUNCE_SEC:
                logger.info(f"⏭️  Rebond ignoré (délai={time_since_last_calib:.2f}s < {SWITCH_DEBOUNCE_SEC}s)")
            else:
                logger.info(f"🔄 Microswitch activé → recalage à {SWITCH_CALIB_ANGLE}°")

                # ✅ CORRECTION : Recalculer total_counts pour correspondre à SWITCH_CALIB_ANGLE
                # Formule inverse :
                # angle = (total_counts / 1024) * 360 * CALIBRATION_FACTOR * ROTATION_SIGN
                # → total_counts = angle / (CALIBRATION_FACTOR * ROTATION_SIGN) / 360 * 1024

                target_wheel_deg = SWITCH_CALIB_ANGLE / (CALIBRATION_FACTOR * ROTATION_SIGN)
                self.total_counts = int((target_wheel_deg / 360.0) * COUNTS_PER_REV)

                logger.info(f"   → total_counts recalé à {self.total_counts}")
                logger.info(f"   → angle affiché : {SWITCH_CALIB_ANGLE}°")

                # Réinitialiser historique pour éviter artefacts du filtre médian
                self.angle_history = []
                self.last_valid_angle = SWITCH_CALIB_ANGLE

                # Mettre à jour timestamp pour anti-rebond
                self.last_calibration_time = now

                # ✅ Marquer comme calibré
                self.calibrated = True

                angle = SWITCH_CALIB_ANGLE

        self.switch_last_state = state
        return angle

    # ------------------------------------------------
    # JSON
    # ------------------------------------------------
    def publish(self, angle, raw, status="OK"):
        """Publie la position encodeur avec flag de calibration."""
        payload = {
            "ts": time.time(),
            "angle": float(angle),
            "raw": int(raw),
            "status": status,
            "calibrated": self.calibrated
        }
        try:
            WRITE_TMP.write_text(json.dumps(payload))
            WRITE_TMP.replace(JSON_OUT)
        except Exception as e:
            logger.error("Erreur écriture JSON: %s", e)

    # ------------------------------------------------
    # TCP server
    # ------------------------------------------------
    def tcp_worker(self):
        s = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        s.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        try:
            s.bind(("127.0.0.1", TCP_PORT))
            s.listen(1)
            logger.info(f"TCP en écoute 127.0.0.1:{TCP_PORT}")
        except OSError as e:
            logger.error(f"❌ Impossible de démarrer TCP sur port {TCP_PORT}: {e}")
            logger.error(f"   Un autre démon utilise probablement ce port.")
            logger.error(f"   Arrêtez l'ancien démon : sudo pkill -f ems22d_calibrated")
            return

        while self.running:
            try:
                conn, _ = s.accept()
                with conn:
                    req = conn.recv(32).decode().strip()
                    if req.upper() == "GET":
                        try:
                            data = json.loads(JSON_OUT.read_text())
                            conn.send(f"{data.get('angle', 0.0):.3f}\n".encode())
                        except Exception:
                            conn.send(b"ERR\n")
                    else:
                        conn.send(b"OK\n")
            except Exception:
                time.sleep(0.05)
        s.close()

    # ------------------------------------------------
    # MAIN LOOP
    # ------------------------------------------------
    def run(self):
        logger.info("=" * 70)
        logger.info("Daemon EMS22D avec Switch de Calibration - VERSION CORRIGÉE")
        logger.info("=" * 70)
        logger.info(f"Port TCP : {TCP_PORT}")
        logger.info(f"CALIBRATION_FACTOR : {CALIBRATION_FACTOR:.6f}")
        logger.info(f"Switch GPIO : {SWITCH_GPIO} (recalage à {SWITCH_CALIB_ANGLE}°)")
        logger.info(f"Méthode : INCRÉMENTALE (accumulation)")
        logger.info("=" * 70)

        self.running = True

        try:
            self.open_spi()
        except Exception as e:
            logger.error("Impossible d'ouvrir SPI: %s", e)
            self.spi = None

        threading.Thread(target=self.tcp_worker, daemon=True).start()

        period = 1.0 / POLL_HZ

        while self.running:
            t0 = time.time()

            try:
                if not self.spi:
                    try:
                        self.open_spi()
                        self.spi_errors = 0
                    except Exception as e:
                        self.publish(0.0, 0, status=f"SPI OPEN ERROR {e}")
                        time.sleep(0.5)
                        continue

                raw = self.read_raw()
                angle = self.raw_to_calibrated(raw)

                # ✅ Filtre anti-saut assoupli (30° au lieu de 5°)
                if self.last_valid_angle is not None:
                    diff = abs(angle - self.last_valid_angle)
                    diff = min(diff, 360 - diff)  # Chemin le plus court

                    if diff > 30:  # ✅ CORRIGÉ : Seuil 30° (était 5°)
                        logger.warning(f"Jump aberrant détecté: {diff:.1f}° - ignoré")
                        angle = self.last_valid_angle
                    else:
                        self.last_valid_angle = angle
                else:
                    self.last_valid_angle = angle

                # Filtre médian sur 5 lectures
                self.angle_history.append(angle)
                if len(self.angle_history) > MEDIAN_WINDOW:
                    self.angle_history.pop(0)

                if len(self.angle_history) >= 3:
                    angle = sorted(self.angle_history)[len(self.angle_history) // 2]

                # ✅ Gestion microswitch avec recalage total_counts
                angle = self.process_switch(angle)

                self.spi_errors = 0
                self.publish(angle, raw)

            except Exception as e:
                logger.warning(f"SPI error: {e}")
                self.spi_errors += 1
                self.publish(0.0, 0, status=f"SPI ERROR {e}")

                if self.spi_errors >= MAX_CONSECUTIVE_SPI_ERRORS:
                    logger.warning("Réinitialisation SPI…")
                    try:
                        self.close_spi()
                        time.sleep(0.1)
                        self.open_spi()
                        self.spi_errors = 0
                    except Exception:
                        time.sleep(0.5)

            # Sleep précis
            dt = time.time() - t0
            rem = period - dt
            if rem > 0:
                time.sleep(rem)

        self.close_spi()
        lgpio.gpiochip_close(self.hchip)
        logger.info("Daemon arrêté proprement")

    def stop(self):
        self.running = False


# ----------------------------------------------------
# Lancement direct
# ----------------------------------------------------
if __name__ == "__main__":
    logger.info("")
    logger.info("🔧 Démarrage du démon EMS22A avec switch de calibration")
    logger.info("   Pour arrêter : Ctrl+C")
    logger.info("")

    d = EMS22Daemon()
    try:
        d.run()
    except KeyboardInterrupt:
        logger.info("\n⏸️  Interruption utilisateur")
        d.stop()
    except Exception as e:
        logger.error(f"❌ Erreur fatale : {e}")
        import traceback
        traceback.print_exc()
