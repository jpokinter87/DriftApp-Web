#!/usr/bin/env python3
"""
Motor Service - Processus dédié pour le contrôle moteur RP2040.

Ce service tourne dans un processus séparé avec son propre GIL,
garantissant un timing optimal pour les pulses GPIO sans interférence
avec l'interface web Django.

Communication:
- Reçoit commandes via /dev/shm/motor_command.json
- Publie état via /dev/shm/motor_status.json
- Lit position encodeur via /dev/shm/ems22_position.json (daemon existant)

Usage:
    sudo python3 services/motor_service.py

Date: Décembre 2025
Version: 4.4 - Refactoring en modules
"""

from collections import deque
import logging
import os
import signal
import sys
import threading
import time
from datetime import datetime
from pathlib import Path
from typing import Dict, Any, Optional

# Import conditionnel pour sdnotify (Raspberry Pi uniquement)
try:
    import sdnotify

    SDNOTIFY_AVAILABLE = True
except ImportError:
    SDNOTIFY_AVAILABLE = False

# Ajouter le répertoire parent au path pour les imports
sys.path.insert(0, str(Path(__file__).parent.parent))

from core.config.config_loader import ConfigLoader
from core.hardware.daemon_encoder_reader import get_daemon_reader, set_daemon_reader
from core.hardware.moteur_rp2040 import MoteurRP2040
from core.hardware.moteur_simule import MoteurSimule
from core.hardware.serial_simulator import SerialSimulator
from core.hardware.hardware_detector import HardwareDetector
from core.hardware.feedback_controller import FeedbackController
from core.tracking.adaptive_tracking import AdaptiveTrackingManager

from services.ipc_manager import IpcManager
from services.simulation import SimulatedDaemonReader
from services.command_handlers import GotoHandler, JogHandler, ContinuousHandler, TrackingHandler

# Configuration logging - fichier horodaté par session (cycle démarrage du service)
LOGS_DIR = Path(__file__).parent.parent / "logs"
LOGS_DIR.mkdir(exist_ok=True)

# Rétention des fichiers de log par âge (en jours)
MAX_LOG_AGE_DAYS = 7
# Fallback de sécurité : nombre max absolu de fichiers
MAX_LOG_FILES_SAFETY = 200


def cleanup_old_logs(prefix: str = "motor_service_"):
    """Supprime les fichiers de log plus anciens que MAX_LOG_AGE_DAYS."""
    cutoff = time.time() - (MAX_LOG_AGE_DAYS * 86400)
    log_files = sorted(
        LOGS_DIR.glob(f"{prefix}*.log"), key=lambda f: f.stat().st_mtime, reverse=True
    )
    for log_file in log_files:
        try:
            if log_file.stat().st_mtime < cutoff:
                logger_name = log_file.name
                log_file.unlink()
                logging.getLogger(__name__).info(f"Log expiré supprimé: {logger_name}")
        except OSError:
            pass
    # Fallback de sécurité : si trop de fichiers malgré la rétention
    remaining = sorted(
        LOGS_DIR.glob(f"{prefix}*.log"), key=lambda f: f.stat().st_mtime, reverse=True
    )
    for old_file in remaining[MAX_LOG_FILES_SAFETY:]:
        try:
            old_file.unlink()
        except OSError:
            pass


# Nettoyage des vieux logs au démarrage
cleanup_old_logs()

# Créer un fichier de log horodaté pour cette session
_startup_timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
_startup_log_path = LOGS_DIR / f"motor_service_{_startup_timestamp}.log"

# Handler de fichier pour cette session
_current_file_handler = logging.FileHandler(_startup_log_path, mode="w")
_current_file_handler.setFormatter(
    logging.Formatter("%(asctime)s - %(name)s - %(levelname)s - %(message)s")
)

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
    handlers=[logging.StreamHandler(), _current_file_handler],
)
logger = logging.getLogger(__name__)


def rotate_log_for_tracking(object_name: str) -> str:
    """
    Crée un nouveau fichier de log pour la session de suivi.

    Args:
        object_name: Nom de l'objet suivi (ex: "M31", "NGC 3079")

    Returns:
        str: Chemin du nouveau fichier de log créé
    """
    global _current_file_handler

    # Nettoyer le nom de l'objet pour le nom de fichier
    # Remplacer tous les caractères problématiques pour les systèmes de fichiers
    safe_name = object_name
    for char in ' /\\*?:"<>|':
        safe_name = safe_name.replace(char, "_")
    # Supprimer les underscores multiples et en début/fin
    while "__" in safe_name:
        safe_name = safe_name.replace("__", "_")
    safe_name = safe_name.strip("_")

    # Générer le nouveau nom de fichier avec horodatage
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    new_log_filename = f"motor_service_{timestamp}_{safe_name}.log"
    new_log_path = LOGS_DIR / new_log_filename

    # Récupérer le root logger
    root_logger = logging.getLogger()

    # Fermer et retirer l'ancien handler de fichier
    if _current_file_handler:
        logger.info(f"=== Rotation log vers: {new_log_filename} ===")
        _current_file_handler.close()
        root_logger.removeHandler(_current_file_handler)

    # Créer le nouveau handler
    _current_file_handler = logging.FileHandler(new_log_path, mode="w")
    _current_file_handler.setFormatter(
        logging.Formatter("%(asctime)s - %(name)s - %(levelname)s - %(message)s")
    )
    _current_file_handler.setLevel(logging.INFO)
    root_logger.addHandler(_current_file_handler)

    # Premier message dans le nouveau fichier
    logger.info("=" * 60)
    logger.info(f"NOUVELLE SESSION DE SUIVI: {object_name}")
    logger.info(f"Fichier: {new_log_filename}")
    logger.info(f"Démarrage: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    logger.info("=" * 60)

    return str(new_log_path)


class MotorService:
    """
    Service de contrôle moteur avec boucle de suivi intégrée.

    Ce service gère:
    - Les commandes GOTO manuelles
    - Les rotations relatives (jog)
    - Le suivi automatique d'objets célestes
    - Le feedback encodeur en boucle fermée
    """

    # Durée après laquelle un état 'error' est automatiquement remis à 'idle'
    ERROR_RECOVERY_TIMEOUT = 10.0  # secondes

    # Intervalle watchdog (en secondes) - doit être < WatchdogSec/2 dans systemd
    # Avec WatchdogSec=30 dans le .service, 10s laisse 2 heartbeats manqués avant kill.
    # Le heartbeat tourne sur un thread dédié pour survivre aux rotations bloquantes
    # (ex: flip méridien 134° ≈ 100s en mode CONTINUOUS).
    WATCHDOG_INTERVAL = 10.0

    def __init__(self):
        """Initialise le service moteur."""
        self.running = False
        self._watchdog_thread = None

        # Initialiser le notifier systemd (si disponible)
        self._init_systemd_notifier()

        # Charger la configuration
        self.config = ConfigLoader().load()

        # Détection automatique du matériel
        is_production, hw_info = HardwareDetector.detect_hardware()
        self.simulation_mode = not is_production

        logger.info(HardwareDetector.get_hardware_summary(hw_info))

        # Initialiser le matériel
        self._init_hardware()

        # Initialiser les gestionnaires
        self._init_managers()

        # Lock pour protéger current_status des accès concurrents
        # (main thread + ContinuousHandler daemon thread)
        self.status_lock = threading.Lock()

        # Initialiser les handlers de commandes
        self._init_handlers()

        # État actuel - créer et écrire IMMÉDIATEMENT pour éviter
        # que le frontend ne lise un état "tracking" d'une session précédente
        self.current_status = self._create_initial_status()
        self._cleanup_on_startup()

        # Logs de suivi pour l'interface web (deque avec taille max automatique)
        self.recent_tracking_logs = deque(maxlen=20)

        mode_str = "SIMULATION" if self.simulation_mode else "PRODUCTION"
        logger.info(f"Motor Service initialisé en mode {mode_str}")

    def _init_hardware(self):
        """Initialise le matériel (moteur RP2040 et encodeur)."""
        if self.simulation_mode:
            logger.info("MODE SIMULATION ACTIVÉ - RP2040 (simulation serie)")
            serial_sim = SerialSimulator()
            self.moteur = MoteurRP2040(self.config.motor, serial_sim)
            # Injecter le lecteur simulé comme instance globale
            self.daemon_reader = SimulatedDaemonReader()
            set_daemon_reader(self.daemon_reader)
            self.feedback_controller = FeedbackController(
                self.moteur,
                self.daemon_reader,
                protection_threshold=self.config.thresholds.feedback_protection_deg,
            )
        else:
            logger.info("MODE PRODUCTION - RP2040 serie")
            serial_port = self._open_serial_port()
            if serial_port is None:
                raise RuntimeError(
                    "Port serie RP2040 indisponible. "
                    "Verifiez que le Pi Pico est branche sur USB."
                )
            self.moteur = MoteurRP2040(self.config.motor, serial_port)
            # Réutiliser l'instance globale du lecteur daemon
            self.daemon_reader = get_daemon_reader()
            self.feedback_controller = FeedbackController(
                self.moteur,
                self.daemon_reader,
                protection_threshold=self.config.thresholds.feedback_protection_deg,
            )

    def _open_serial_port(self):
        """
        Ouvre le port serie pour le RP2040.

        Returns:
            serial.Serial ou None si echec
        """
        cfg = self.config.motor_driver.serial
        try:
            import serial
            port = serial.Serial(
                port=cfg.port,
                baudrate=cfg.baudrate,
                timeout=cfg.timeout,
            )
            logger.info(f"Port serie ouvert: {cfg.port} @ {cfg.baudrate} bauds")
            return port
        except ImportError:
            logger.warning("pyserial non installe — impossible d'ouvrir le port serie")
            return None
        except Exception as e:
            logger.warning(f"Erreur ouverture port serie {cfg.port}: {e}")
            return None

    def _init_managers(self):
        """Initialise les gestionnaires."""
        self.ipc = IpcManager()
        self.adaptive_manager = AdaptiveTrackingManager(
            base_interval=self.config.tracking.intervalle_verification_sec,
            base_threshold=self.config.tracking.seuil_correction_deg,
            adaptive_config=self.config.adaptive,
        )

    def _init_handlers(self):
        """Initialise les handlers de commandes."""
        self.goto_handler = GotoHandler(
            self.moteur,
            self.daemon_reader,
            self.feedback_controller,
            self.config,
            self.simulation_mode,
            self._write_status,
        )
        self.jog_handler = JogHandler(
            self.moteur, self.daemon_reader, self.config, self.simulation_mode, self._write_status
        )
        self.continuous_handler = ContinuousHandler(
            self.moteur,
            self.daemon_reader,
            self.config,
            self.simulation_mode,
            self._write_status,
            status_lock=self.status_lock,
        )
        self.tracking_handler = TrackingHandler(
            self.moteur,
            self.feedback_controller,
            self.config,
            self.simulation_mode,
            self._write_status,
            self._add_tracking_log,
        )

    def _cleanup_on_startup(self):
        """
        Nettoie l'état IPC au démarrage pour éviter les états "fantômes".

        Problème résolu: Si le service est redémarré alors qu'un suivi était actif,
        le fichier /dev/shm/motor_status.json peut contenir un ancien état 'tracking'.
        Le frontend verrait alors "suivi actif" et désactiverait le bouton Démarrer.

        Solution: Écrire immédiatement un état 'idle' propre au démarrage.
        """
        self.ipc.write_status(self.current_status)
        logger.info("État IPC initialisé (cleanup au démarrage)")

    def _init_systemd_notifier(self):
        """
        Initialise le notifier systemd pour le watchdog.

        Le watchdog permet à systemd de redémarrer automatiquement le service
        en cas de freeze ou deadlock. Le service doit envoyer un heartbeat
        régulier (WATCHDOG=1) sinon systemd le redémarre.
        """
        if SDNOTIFY_AVAILABLE:
            self._systemd_notifier = sdnotify.SystemdNotifier()
            self._watchdog_enabled = True
            logger.info("Watchdog systemd initialisé")
        else:
            self._systemd_notifier = None
            self._watchdog_enabled = False
            logger.debug("sdnotify non disponible - watchdog désactivé")

    def _notify_systemd(self, message: str):
        """
        Envoie une notification à systemd (si disponible).

        Messages courants:
        - READY=1: Service prêt à recevoir des commandes
        - WATCHDOG=1: Heartbeat, prouve que le service est vivant
        - STOPPING=1: Service en cours d'arrêt
        - STATUS=<text>: Statut lisible par l'humain
        """
        if self._systemd_notifier:
            try:
                self._systemd_notifier.notify(message)
            except Exception as e:
                logger.debug(f"Erreur notification systemd: {e}")

    def _start_watchdog_thread(self):
        """
        Démarre un thread dédié pour le heartbeat watchdog systemd.

        Le heartbeat tourne indépendamment de la boucle principale pour
        survivre aux opérations bloquantes longues (ex: rotation feedback
        de 100+ secondes lors d'un flip méridien).
        """
        if not self._watchdog_enabled:
            return

        def _watchdog_loop():
            while self.running:
                self._notify_systemd("WATCHDOG=1")
                time.sleep(self.WATCHDOG_INTERVAL)

        self._watchdog_thread = threading.Thread(
            target=_watchdog_loop, daemon=True, name="watchdog-heartbeat"
        )
        self._watchdog_thread.start()
        logger.info("Thread watchdog démarré (heartbeat indépendant)")

    def _create_initial_status(self) -> Dict[str, Any]:
        """Crée l'état initial."""
        return {
            "status": "idle",
            "position": 0.0,
            "target": None,
            "progress": 0,
            "mode": "idle",
            "tracking_object": None,
            "error": None,
            "simulation": self.simulation_mode,
            "last_update": datetime.now().isoformat(),
            "tracking_logs": [],
        }

    def _write_status(self, status: Optional[Dict[str, Any]] = None):
        """Écrit l'état via IPC."""
        if status is None:
            status = self.current_status
        self.ipc.write_status(status)

    def _add_tracking_log(self, message: str, log_type: str = "info"):
        """Ajoute un log de suivi pour l'interface web."""
        log_entry = {"time": datetime.now().isoformat(), "message": message, "type": log_type}
        self.recent_tracking_logs.append(log_entry)
        # deque avec maxlen gère automatiquement la taille
        self.current_status["tracking_logs"] = list(self.recent_tracking_logs)[-10:]

    def read_encoder_position(self) -> Optional[float]:
        """Lit la position de l'encodeur."""
        try:
            return self.daemon_reader.read_angle(timeout_ms=100)
        except RuntimeError:
            return None

    def _check_error_recovery(self):
        """
        Vérifie si un état 'error' doit être remis à 'idle'.

        Si le statut est 'error' depuis plus de ERROR_RECOVERY_TIMEOUT secondes,
        remet automatiquement le statut à 'idle' pour permettre de nouvelles commandes.
        """
        if self.current_status.get("status") != "error":
            return

        error_timestamp = self.current_status.get("error_timestamp")
        if error_timestamp is None:
            return

        elapsed = time.time() - error_timestamp
        if elapsed > self.ERROR_RECOVERY_TIMEOUT:
            logger.info(
                f"Recovery automatique après erreur "
                f"({elapsed:.1f}s > {self.ERROR_RECOVERY_TIMEOUT}s)"
            )
            self.current_status["status"] = "idle"
            self.current_status["error"] = None
            self.current_status["error_timestamp"] = None
            self._write_status()

    # =========================================================================
    # COMMANDES
    # =========================================================================

    def handle_stop(self):
        """Arrête immédiatement tout mouvement."""
        logger.info("STOP demandé")

        self.continuous_handler.stop()
        self.feedback_controller.request_stop()
        self.moteur.request_stop()

        if self.tracking_handler.is_active:
            self.tracking_handler.stop(self.current_status)

        self.current_status["status"] = "idle"
        self.current_status["tracking_object"] = None
        self._write_status()

    def process_command(self, command: Dict[str, Any]):
        """Traite une commande reçue."""
        cmd_type = command.get("command", command.get("type"))

        if not cmd_type:
            logger.warning(f"Commande invalide: {command}")
            return

        if cmd_type == "goto":
            angle = command.get("angle", 0)
            speed = command.get("speed")
            logger.info(f"ipc_command | type=goto angle={angle} speed={speed}")
            self.current_status = self.goto_handler.execute(angle, self.current_status, speed)

        elif cmd_type == "jog":
            delta = command.get("delta", 0)
            speed = command.get("speed")
            logger.info(f"ipc_command | type=jog delta={delta} speed={speed}")
            self.current_status = self.jog_handler.execute(delta, self.current_status, speed)

        elif cmd_type == "stop":
            logger.info("ipc_command | type=stop")
            self.handle_stop()

        elif cmd_type == "continuous":
            direction = command.get("direction", "cw")
            logger.info(f"ipc_command | type=continuous direction={direction}")
            if self.tracking_handler.is_active:
                self.handle_stop()
            self.continuous_handler.start(direction, self.current_status)

        elif cmd_type == "tracking_start":
            object_name = command.get("object", command.get("name"))
            skip_goto = command.get("skip_goto", False)
            logger.info(f"ipc_command | type=tracking_start object={object_name} skip_goto={skip_goto}")
            if object_name:
                self.tracking_handler.start(object_name, self.current_status, skip_goto=skip_goto)
            else:
                logger.warning("ipc_command | type=tracking_start error=missing_object")

        elif cmd_type == "tracking_stop":
            logger.info("ipc_command | type=tracking_stop")
            self.tracking_handler.stop(self.current_status)

        elif cmd_type == "status":
            pass  # Juste mettre à jour

        else:
            logger.warning(f"ipc_command | type={cmd_type} error=unknown_command")

        self.ipc.clear_command()

    # =========================================================================
    # BOUCLE PRINCIPALE
    # =========================================================================

    def run(self):
        """Boucle principale du service."""
        self.running = True
        logger.info("Motor Service démarré - En attente de commandes...")

        # Lire la position initiale
        pos = self.read_encoder_position()
        if pos is not None:
            self.current_status["position"] = pos
            logger.info(f"Position initiale: {pos:.1f}°")

        self._write_status()

        # Notifier systemd que le service est prêt
        self._notify_systemd("READY=1")
        self._notify_systemd("STATUS=Motor Service prêt")

        # Démarrer le thread watchdog dédié (survit aux rotations bloquantes)
        self._start_watchdog_thread()

        last_tracking_update = time.time()
        tracking_interval = 1.0
        service_start_time = time.time()
        last_heartbeat_time = time.time()
        last_ipc_snapshot_time = time.time()
        cmd_count_since_heartbeat = 0

        while self.running:
            try:
                # Vérifier si recovery automatique d'erreur nécessaire
                self._check_error_recovery()

                # Lire et traiter les commandes
                command = self.ipc.read_command()
                if command:
                    self.process_command(command)
                    cmd_count_since_heartbeat += 1

                # Mettre à jour le suivi si actif
                now = time.time()
                if (
                    self.tracking_handler.is_active
                    and (now - last_tracking_update) >= tracking_interval
                ):
                    self.tracking_handler.update(self.current_status)
                    last_tracking_update = now
                    self._write_status()

                # Mettre à jour la position depuis l'encodeur
                pos = self.read_encoder_position()
                if pos is not None and not self.tracking_handler.is_active:
                    self.current_status["position"] = pos

                # Heartbeat toutes les 10 secondes
                if now - last_heartbeat_time >= self.WATCHDOG_INTERVAL:
                    uptime = int(now - service_start_time)
                    is_active = self.tracking_handler.is_active
                    obj = self.current_status.get("tracking_object", "none") or "none"
                    tracking_info = self.current_status.get("tracking_info", {})
                    corrections = tracking_info.get("total_corrections", 0) if is_active else 0
                    enc = "ok" if pos is not None else "lost"
                    logger.info(
                        f"heartbeat | uptime={uptime} tracking={is_active} "
                        f"object={obj} corrections={corrections} "
                        f"encoder={enc} cmds={cmd_count_since_heartbeat}"
                    )
                    cmd_count_since_heartbeat = 0
                    last_heartbeat_time = now

                # Snapshot IPC toutes les 60 secondes pendant tracking
                if self.tracking_handler.is_active and now - last_ipc_snapshot_time >= 60.0:
                    s = self.current_status
                    ti = s.get("tracking_info", {})
                    logger.info(
                        f"ipc_snapshot | status={s.get('status', 'unknown')} "
                        f"position={s.get('position', 0):.1f} "
                        f"target={s.get('target', 'none')} "
                        f"mode={s.get('mode', 'unknown')} "
                        f"encoder_angle={pos if pos is not None else 'none'} "
                        f"encoder_calibrated={ti.get('encoder_offset', 'n/a')} "
                        f"tracking_object={s.get('tracking_object', 'none')}"
                    )
                    last_ipc_snapshot_time = now

                time.sleep(0.05)  # 20Hz de polling

            except KeyboardInterrupt:
                logger.info("Interruption clavier - Arrêt du service")
                break
            except Exception as e:
                logger.error(f"Erreur boucle principale: {e}")
                self.current_status["status"] = "error"
                self.current_status["error"] = str(e)
                self.current_status["error_timestamp"] = time.time()
                self._write_status()
                time.sleep(1)

        self.cleanup()

    def cleanup(self):
        """Nettoie les ressources à l'arrêt."""
        self.running = False
        logger.info("Nettoyage des ressources...")

        # Notifier systemd que le service s'arrête
        self._notify_systemd("STOPPING=1")
        self._notify_systemd("STATUS=Arrêt en cours")

        if self.tracking_handler.session:
            self.tracking_handler.session.stop()

        if self.moteur:
            self.moteur.nettoyer()

        self.current_status["status"] = "stopped"
        self._write_status()

        logger.info("Motor Service arrêté proprement")

    def signal_handler(self, signum, frame):
        """Gestionnaire de signaux pour arrêt propre."""
        logger.info(f"Signal {signum} reçu - Arrêt en cours...")
        self.running = False


def main():
    """Point d'entrée principal."""
    # Créer le répertoire de logs si nécessaire
    logs_dir = Path(__file__).parent.parent / "logs"
    logs_dir.mkdir(exist_ok=True)

    # Détection automatique du matériel
    is_production, _ = HardwareDetector.detect_hardware()

    # En production, vérifier les permissions
    if is_production and os.geteuid() != 0:
        print("ERREUR: Ce service nécessite les privilèges root (sudo) sur Raspberry Pi")
        print("Usage: sudo python3 services/motor_service.py")
        sys.exit(1)

    # Créer et lancer le service
    service = MotorService()

    # Installer les gestionnaires de signaux
    signal.signal(signal.SIGTERM, service.signal_handler)
    signal.signal(signal.SIGINT, service.signal_handler)

    # Lancer la boucle principale
    service.run()


if __name__ == "__main__":
    main()
