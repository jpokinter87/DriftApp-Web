"""Tests de la séquence de parking fin de session (cimier auto semi/full).

Bug terrain 08-09/08/2026 (logs Serge, `motor_service_20260809_001457_NGC_7640.log`) :
`CimierScheduler._trigger_close()` écrivait `tracking_stop` puis `goto 45°` dans le
même slot IPC (`/dev/shm/motor_command.json`) en moins d'1 ms. Le motor_service ne
lit ce slot qu'à 20 Hz : le `goto` écrasait le `tracking_stop`, jamais consommé.
Conséquence : le suivi restait actif après le parking, redéclenchait un slew
d'anticipation méridien depuis 45° et faisait dériver la coupole 4h30 durant
(position finale ~80° au lieu de 45°).

Ces tests instancient un VRAI `MotorIpcWriter` et un consommateur qui mime la
boucle de `motor_service.run()` (lecture 20 Hz, dédup par id, `clear_command()`
après traitement) pour vérifier que les deux commandes arrivent bien à
destination.
"""

from __future__ import annotations

import json
import threading
import time
from dataclasses import dataclass, field
from typing import Any, Dict, List

import pytest

from core.config.config_loader import CimierAutomationConfig, SiteConfig
from services.cimier_scheduler import CimierScheduler
from services.motor_ipc_writer import MotorIpcWriter


@dataclass
class _FakeCimierIpc:
    commands: List[Dict[str, Any]] = field(default_factory=list)

    def write_command(self, command: Dict[str, Any]) -> None:
        self.commands.append(command)


class _MotorServiceConsumer:
    """Mime la boucle principale de `motor_service.run()`.

    Lecture du slot IPC à 20 Hz, déduplication par `id` (cf. `IpcManager`),
    puis `clear_command()` (troncature du fichier) après traitement — ce qui
    reproduit les DEUX courses possibles : écrasement de la 1ʳᵉ commande, et
    effacement d'une commande arrivée pendant le traitement de la précédente.
    """

    POLL_INTERVAL_S = 0.05
    # Coût réaliste d'un `tracking_stop` : session.stop() sérialise la session
    # de la nuit sur disque avant que le status ne repasse à idle.
    TRACKING_STOP_COST_S = 0.15

    def __init__(self, command_file, status_file):
        self.command_file = command_file
        self.status_file = status_file
        self.consumed: List[str] = []
        self._stop = threading.Event()
        self._thread = threading.Thread(target=self._loop, daemon=True)

    def start(self):
        self._thread.start()

    def stop(self):
        self._stop.set()
        self._thread.join(timeout=5.0)

    def _loop(self):
        last_id = None
        while not self._stop.is_set():
            command = None
            try:
                text = self.command_file.read_text()
                if text.strip():
                    command = json.loads(text)
            except (OSError, json.JSONDecodeError):
                command = None

            if command and command.get("id") != last_id:
                last_id = command["id"]
                cmd_type = command.get("command")
                self.consumed.append(cmd_type)
                if cmd_type == "tracking_stop":
                    time.sleep(self.TRACKING_STOP_COST_S)
                    self._publish_status(status="idle", tracking_object=None)
                # clear_command() : le fichier est tronqué après traitement.
                self.command_file.write_text("")

            time.sleep(self.POLL_INTERVAL_S)

    def _publish_status(self, status: str, tracking_object):
        self.status_file.write_text(
            json.dumps({"status": status, "tracking_object": tracking_object})
        )


@pytest.fixture
def ipc_files(tmp_path):
    command_file = tmp_path / "motor_command.json"
    status_file = tmp_path / "motor_status.json"
    command_file.write_text("")
    # État de départ : une session de suivi tourne depuis le début de la nuit.
    status_file.write_text(json.dumps({"status": "tracking", "tracking_object": "NGC 7640"}))
    return command_file, status_file


def _scheduler(command_file, status_file):
    writer = MotorIpcWriter(command_file=command_file, status_file=status_file)
    return (
        CimierScheduler(
            automation_config=CimierAutomationConfig(mode="semi"),
            site_config=SiteConfig(
                latitude=44.15, longitude=5.23, altitude=800.0, nom="Test", fuseau="Europe/Paris"
            ),
            weather_provider=None,
            cimier_ipc=_FakeCimierIpc(),
            motor_ipc=writer,
        ),
        writer,
    )


def test_trigger_close_delivers_tracking_stop_and_goto_to_a_20hz_consumer(ipc_files):
    """Les deux commandes de fin de session doivent atteindre le motor_service.

    Repro du bug terrain : avec deux écritures consécutives sans attente, le
    consommateur 20 Hz ne voyait QUE le `goto` — le suivi restait actif et
    reprenait la main sur la coupole juste après le parking.
    """
    command_file, status_file = ipc_files
    consumer = _MotorServiceConsumer(command_file, status_file)
    consumer.start()
    try:
        scheduler, _ = _scheduler(command_file, status_file)
        scheduler._trigger_close()
        time.sleep(0.3)  # laisse le consommateur drainer le dernier slot
    finally:
        consumer.stop()

    assert consumer.consumed == ["tracking_stop", "goto"], (
        f"commandes réellement consommées : {consumer.consumed}"
    )


def test_trigger_close_sends_goto_even_if_tracking_stop_is_never_confirmed(ipc_files):
    """Le parking reste best-effort : sans motor_service pour confirmer l'arrêt
    du suivi, le GOTO doit tout de même partir (protection de la coupole)."""
    command_file, status_file = ipc_files  # personne ne consomme, status figé
    scheduler, writer = _scheduler(command_file, status_file)
    writer.tracking_stop_confirm_timeout_s = 0.2

    scheduler._trigger_close()

    assert json.loads(command_file.read_text())["command"] == "goto"


def test_wait_tracking_stopped_returns_true_once_tracking_object_cleared(ipc_files):
    command_file, status_file = ipc_files
    writer = MotorIpcWriter(command_file=command_file, status_file=status_file)

    assert writer.wait_tracking_stopped(timeout_s=0.2) is False

    status_file.write_text(json.dumps({"status": "idle", "tracking_object": None}))
    assert writer.wait_tracking_stopped(timeout_s=0.2) is True
