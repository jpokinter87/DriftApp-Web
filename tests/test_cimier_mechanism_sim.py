"""Tests du mécanisme virtuel cimier (core/hardware/cimier_mechanism_sim.py)."""
from __future__ import annotations

from core.hardware.cimier_mechanism_sim import CimierMechanismSim


def test_initial_closed():
    m = CimierMechanismSim(initial_state="closed")
    assert m.position == 0.0
    assert m.closed_switch is True
    assert m.open_switch is False


def test_initial_open():
    m = CimierMechanismSim(initial_state="open")
    assert m.position == 1.0
    assert m.open_switch is True
    assert m.closed_switch is False


def test_initial_mid_no_switch():
    m = CimierMechanismSim(initial_state="mid")
    assert m.position == 0.5
    assert m.open_switch is False
    assert m.closed_switch is False


def test_motor_off_does_not_move():
    m = CimierMechanismSim(initial_state="closed", full_travel_s=10.0)
    m.set_direction(open_direction=True)
    m.advance(5.0)  # moteur éteint
    assert m.position == 0.0


def test_opening_advances_to_open_switch():
    m = CimierMechanismSim(initial_state="closed", full_travel_s=10.0)
    m.set_direction(open_direction=True)
    m.set_motor(True)
    m.advance(4.0)
    assert 0.39 <= m.position <= 0.41
    assert m.open_switch is False
    m.advance(10.0)  # dépasse la course
    assert m.position == 1.0
    assert m.open_switch is True


def test_closing_advances_to_closed_switch():
    m = CimierMechanismSim(initial_state="open", full_travel_s=10.0)
    m.set_direction(open_direction=False)
    m.set_motor(True)
    m.advance(10.0)
    assert m.position == 0.0
    assert m.closed_switch is True


def test_position_clamped_no_overshoot():
    m = CimierMechanismSim(initial_state="closed", full_travel_s=2.0)
    m.set_direction(open_direction=True)
    m.set_motor(True)
    m.advance(100.0)
    assert m.position == 1.0  # jamais > 1.0


def test_force_both_switches_fault():
    m = CimierMechanismSim(initial_state="closed", force_both_switches=True)
    assert m.open_switch is True
    assert m.closed_switch is True
