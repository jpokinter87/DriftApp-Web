"""Tests du module capteurs cimier_controller (pivot Shelly v6.x).

Le Pico W ne pilote plus le moteur : ce module ne fait que dériver l'état
du cimier depuis les 2 fins de course. Tests purs (CPython), via un mock
d'adapter hardware.
"""
from __future__ import annotations

import sys
from dataclasses import dataclass
from pathlib import Path

_FIRMWARE_DIR = Path(__file__).resolve().parents[1] / "firmware" / "cimier"
sys.path.insert(0, str(_FIRMWARE_DIR))

import cimier_controller as cc  # noqa: E402


@dataclass
class FakeSwitchAdapter:
    """Mock capteurs : état des 2 fins de course."""
    open_triggered: bool = False
    closed_triggered: bool = False

    def read_open_switch(self) -> bool:
        return self.open_triggered

    def read_closed_switch(self) -> bool:
        return self.closed_triggered


def make_controller(open_triggered=False, closed_triggered=False):
    hw = FakeSwitchAdapter(open_triggered=open_triggered, closed_triggered=closed_triggered)
    return cc.CimierController(hw), hw


# --- dérivation d'état au boot --------------------------------------------
def test_init_state_unknown_when_no_switch():
    ctrl, _ = make_controller()
    assert ctrl.state == cc.STATE_UNKNOWN


def test_init_state_closed_when_closed_switch():
    ctrl, _ = make_controller(closed_triggered=True)
    assert ctrl.state == cc.STATE_CLOSED


def test_init_state_open_when_open_switch():
    ctrl, _ = make_controller(open_triggered=True)
    assert ctrl.state == cc.STATE_OPEN


def test_init_state_error_when_both_switches():
    ctrl, _ = make_controller(open_triggered=True, closed_triggered=True)
    assert ctrl.state == cc.STATE_ERROR


# --- l'état se rafraîchit quand les switches changent ----------------------
def test_state_refreshes_on_read():
    ctrl, hw = make_controller(closed_triggered=True)
    assert ctrl.state == cc.STATE_CLOSED
    hw.closed_triggered = False
    hw.open_triggered = True
    assert ctrl.state == cc.STATE_OPEN


# --- sérialisation REST ----------------------------------------------------
def test_to_status_dict_format():
    ctrl, _ = make_controller(closed_triggered=True)
    status = ctrl.to_status_dict()
    assert set(status.keys()) == {"state", "open_switch", "closed_switch", "error_message"}
    assert status["state"] == cc.STATE_CLOSED
    assert status["closed_switch"] is True
    assert status["open_switch"] is False
    assert status["error_message"] == ""


def test_to_status_dict_error_message_on_both():
    ctrl, _ = make_controller(open_triggered=True, closed_triggered=True)
    status = ctrl.to_status_dict()
    assert status["state"] == cc.STATE_ERROR
    assert status["error_message"] == "both_switches_triggered"


def test_to_info_dict_format():
    ctrl, _ = make_controller()
    info = ctrl.to_info_dict()
    assert set(info.keys()) == {"firmware_version", "protocol_version", "role"}
    assert info["firmware_version"] == cc.FIRMWARE_VERSION
    assert info["role"] == "sensor"
    assert info["protocol_version"] == cc.FIRMWARE_PROTOCOL_VERSION
