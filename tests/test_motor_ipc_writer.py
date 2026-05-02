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
