"""Tests du double SimMotorShelly (core/hardware/sim_motor_shelly.py)."""
from __future__ import annotations

from core.hardware.cimier_mechanism_sim import CimierMechanismSim
from core.hardware.sim_motor_shelly import SimMotorShelly


def test_turn_on_starts_mechanism_motor():
    m = CimierMechanismSim(initial_state="closed")
    shelly = SimMotorShelly(m)
    shelly.turn_on(timer_s=90.0)
    assert m.motor_on is True
    assert shelly.last_timer_s == 90.0


def test_turn_off_stops_mechanism_motor():
    m = CimierMechanismSim(initial_state="mid")
    shelly = SimMotorShelly(m)
    shelly.turn_on()
    shelly.turn_off()
    assert m.motor_on is False


def test_set_direction_propagates_to_mechanism():
    m = CimierMechanismSim(initial_state="mid", full_travel_s=10.0)
    shelly = SimMotorShelly(m)
    shelly.set_direction(open_direction=False)
    shelly.turn_on()
    m.advance(1.0)
    assert m.position < 0.5  # a bien fermé (descendu)


def test_calls_are_recorded_in_order():
    m = CimierMechanismSim(initial_state="closed")
    shelly = SimMotorShelly(m)
    shelly.set_direction(open_direction=True)
    shelly.turn_on(timer_s=90.0)
    shelly.turn_off()
    assert shelly.calls == [
        ("set_direction", True),
        ("turn_on", 90.0),
        ("turn_off", None),
    ]
