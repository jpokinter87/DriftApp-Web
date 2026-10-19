"""Tests pour services/motor_ipc_writer.py (v6.0 Phase 3 sub-plan 03-01)."""

from __future__ import annotations

import json
from pathlib import Path
from unittest.mock import patch

import pytest

from services.motor_ipc_writer import MotorIpcWriter


@pytest.fixture
def writer(tmp_path):
    return MotorIpcWriter(command_file=tmp_path / "motor_command.json")


def _read_cmd(path: Path) -> dict:
    return json.loads(path.read_text())


def test_send_goto_writes_correct_payload(writer, tmp_path):
    ok = writer.send_goto(45.0)
    assert ok is True
    cmd = _read_cmd(tmp_path / "motor_command.json")
    assert cmd["command"] == "goto"
    assert cmd["angle"] == 45.0
    assert "id" in cmd and len(cmd["id"]) > 0


def test_send_jog_writes_correct_payload(writer, tmp_path):
    ok = writer.send_jog(1.0)
    assert ok is True
    cmd = _read_cmd(tmp_path / "motor_command.json")
    assert cmd["command"] == "jog"
    assert cmd["delta"] == 1.0
    assert "id" in cmd


def test_send_tracking_stop_writes_correct_payload(writer, tmp_path):
    ok = writer.send_tracking_stop()
    assert ok is True
    cmd = _read_cmd(tmp_path / "motor_command.json")
    assert cmd["command"] == "tracking_stop"
    assert "id" in cmd
    # Pas de params autres que id+command
    assert set(cmd.keys()) == {"id", "command"}


def test_send_stop_writes_correct_payload(writer, tmp_path):
    ok = writer.send_stop()
    assert ok is True
    cmd = _read_cmd(tmp_path / "motor_command.json")
    assert cmd["command"] == "stop"
    assert "id" in cmd


def test_each_send_generates_new_uuid(writer, tmp_path):
    writer.send_goto(45.0)
    cmd1 = _read_cmd(tmp_path / "motor_command.json")
    writer.send_goto(45.0)
    cmd2 = _read_cmd(tmp_path / "motor_command.json")
    assert cmd1["id"] != cmd2["id"]


def test_send_creates_file_if_missing(tmp_path):
    target = tmp_path / "motor_command.json"
    assert not target.exists()
    writer = MotorIpcWriter(command_file=target)
    assert writer.send_jog(0.5) is True
    assert target.exists()
    cmd = json.loads(target.read_text())
    assert cmd["command"] == "jog" and cmd["delta"] == 0.5


def test_failed_send_does_not_corrupt_previous_command(writer, tmp_path, monkeypatch):
    """Écriture atomique tmp+rename : un échec en cours d'écriture ne doit
    pas tronquer/corrompre la dernière commande valide du fichier cible."""
    import services.motor_ipc_writer as m

    target = tmp_path / "motor_command.json"
    assert writer.send_goto(45.0) is True

    def _boom(*args):
        raise OSError("flock failed")

    monkeypatch.setattr(m.fcntl, "flock", _boom)
    assert writer.send_jog(1.0) is False
    # La commande précédente reste intacte et parsable.
    cmd = json.loads(target.read_text())
    assert cmd["command"] == "goto"
    assert cmd["angle"] == 45.0


def test_send_leaves_file_world_writable(writer, tmp_path):
    """Le fichier cible doit rester mode 666 après chaque write : les services
    tournent en root (systemd) mais Django (non-root) écrit aussi dedans."""
    import os

    target = tmp_path / "motor_command.json"
    # umask restrictif simulant un service root (umask 022 → 644 par défaut).
    old_umask = os.umask(0o022)
    try:
        assert writer.send_goto(45.0) is True
    finally:
        os.umask(old_umask)
    assert (target.stat().st_mode & 0o777) == 0o666


def test_send_falls_back_to_in_place_write_when_rename_refused(writer, tmp_path, monkeypatch):
    """Django (slenk) ne peut pas remplacer par rename le motor_command.json
    créé par motor_service (root) : sticky bit de /dev/shm → EPERM. Le bouton
    « Parking session » n'arrêtait ni le suivi ni ne parquait la coupole."""
    target = tmp_path / "motor_command.json"
    assert writer.send_goto(10.0) is True

    def _eperm(self, _target):
        raise PermissionError(1, "Operation not permitted")

    monkeypatch.setattr(Path, "rename", _eperm)
    assert writer.send_tracking_stop() is True
    assert _read_cmd(target)["command"] == "tracking_stop"
    assert not target.with_suffix(".tmp").exists()


def test_send_returns_false_on_ioerror(writer):
    """Patch open pour lever OSError → False, pas d'exception remontée au caller."""
    with patch("builtins.open", side_effect=OSError("disk full")):
        ok = writer.send_goto(45.0)
    assert ok is False


def test_send_jog_with_negative_delta(writer, tmp_path):
    ok = writer.send_jog(-2.5)
    assert ok is True
    cmd = _read_cmd(tmp_path / "motor_command.json")
    assert cmd["delta"] == -2.5


def test_motor_ipc_writer_has_no_django_import():
    """Vérifie module Python pur — pas d'import Django."""
    import services.motor_ipc_writer as m

    src_text = Path(m.__file__).read_text()
    # Pas de "from django" ni "import django" dans le module
    assert "from django" not in src_text
    assert "import django" not in src_text


class TestIsParked:
    """Coupole immobile au parking d'après motor_status.json (v6.21.2)."""

    def _writer(self, tmp_path, status):
        status_file = tmp_path / "motor_status.json"
        if status is not None:
            status_file.write_text(json.dumps(status))
        return MotorIpcWriter(command_file=tmp_path / "motor_command.json", status_file=status_file)

    def test_idle_at_target(self, tmp_path):
        assert self._writer(tmp_path, {"status": "idle", "position": 44.6}).is_parked(45.0)

    def test_idle_across_zero(self, tmp_path):
        assert self._writer(tmp_path, {"status": "idle", "position": 359.5}).is_parked(0.2)

    def test_idle_elsewhere(self, tmp_path):
        """GOTO raté à 18° (terrain 14/10) : pas au parking."""
        assert not self._writer(tmp_path, {"status": "idle", "position": 18.2}).is_parked(45.0)

    def test_moving_through_target(self, tmp_path):
        assert not self._writer(tmp_path, {"status": "moving", "position": 45.0}).is_parked(45.0)

    def test_status_unreadable(self, tmp_path):
        assert not self._writer(tmp_path, None).is_parked(45.0)
