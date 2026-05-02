"""Tests pour services/cimier_scheduler.py (v6.0 Phase 3 sub-plan 03-01).

Tests offline avec injection complète : clock, sun_altitude_fn, sun_direction_fn,
mocks pour cimier_ipc + motor_ipc + weather_provider.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timedelta, timezone
from typing import Any, Dict, List

import pytest

from core.config.config_loader import CimierAutomationConfig, SiteConfig
from services.cimier_scheduler import (
    CimierScheduler,
    CIMIER_STATE_CLOSED,
    CIMIER_STATE_OPEN,
    CIMIER_STATE_CYCLE,
)


# ----------------------------------------------------------------------
# Fixtures / mocks
# ----------------------------------------------------------------------


def _site():
    return SiteConfig(latitude=44.15, longitude=5.23, altitude=800.0, nom="Test", fuseau="Europe/Paris")


def _automation(**overrides):
    cfg = CimierAutomationConfig(enabled=True)
    for k, v in overrides.items():
        setattr(cfg, k, v)
    return cfg


@dataclass
class FakeWeatherProvider:
    safe: bool = True
    call_count: int = 0

    def is_safe_to_open(self) -> bool:
        self.call_count += 1
        return self.safe

    def is_safe_to_keep_open(self) -> bool:
        return self.safe

    def describe(self) -> Dict[str, Any]:
        return {"provider": "fake", "safe": self.safe}


@dataclass
class FakeCimierIpc:
    commands: List[Dict[str, Any]] = field(default_factory=list)

    def write_command(self, command: Dict[str, Any]) -> None:
        self.commands.append(command)


@dataclass
class FakeMotorIpc:
    calls: List[tuple] = field(default_factory=list)

    def send_goto(self, angle: float) -> bool:
        self.calls.append(("goto", angle))
        return True

    def send_jog(self, delta: float) -> bool:
        self.calls.append(("jog", delta))
        return True

    def send_tracking_stop(self) -> bool:
        self.calls.append(("tracking_stop",))
        return True

    def send_stop(self) -> bool:
        self.calls.append(("stop",))
        return True


def _scheduler(automation, alt_fn, dir_fn, weather=None, clock_now=None):
    weather = weather or FakeWeatherProvider(safe=True)
    cimier = FakeCimierIpc()
    motor = FakeMotorIpc()
    if clock_now is None:
        clock_now = datetime(2026, 5, 15, 21, 0, tzinfo=timezone.utc)
    sched = CimierScheduler(
        automation_config=automation,
        site_config=_site(),
        weather_provider=weather,
        cimier_ipc=cimier,
        motor_ipc=motor,
        clock=lambda: clock_now,
        sun_altitude_fn=alt_fn,
        sun_direction_fn=dir_fn,
    )
    return sched, cimier, motor, weather


# ----------------------------------------------------------------------
# Tests
# ----------------------------------------------------------------------


def test_disabled_returns_skip_disabled():
    sched, cimier, motor, _ = _scheduler(
        automation=CimierAutomationConfig(enabled=False),
        alt_fn=lambda *a, **kw: -15.0,
        dir_fn=lambda *a, **kw: "descending",
    )
    decision = sched.maybe_trigger(CIMIER_STATE_CLOSED)
    assert decision.trigger == "skip:disabled"
    assert cimier.commands == []
    assert motor.calls == []


def test_descending_below_threshold_with_closed_cimier_triggers_open():
    sched, cimier, motor, weather = _scheduler(
        automation=_automation(),
        alt_fn=lambda *a, **kw: -12.5,
        dir_fn=lambda *a, **kw: "descending",
    )
    decision = sched.maybe_trigger(CIMIER_STATE_CLOSED)
    assert decision.trigger == "open"
    assert decision.sun_alt_deg == -12.5
    assert decision.direction == "descending"
    # Cimier IPC : commande open
    assert len(cimier.commands) == 1
    assert cimier.commands[0]["action"] == "open"
    assert "id" in cimier.commands[0]
    # Motor IPC : jog +1.0° (déparking)
    assert ("jog", 1.0) in motor.calls
    # WeatherProvider consulté
    assert weather.call_count == 1


def test_descending_with_unsafe_weather_skips_open():
    weather = FakeWeatherProvider(safe=False)
    sched, cimier, motor, _ = _scheduler(
        automation=_automation(),
        alt_fn=lambda *a, **kw: -15.0,
        dir_fn=lambda *a, **kw: "descending",
        weather=weather,
    )
    decision = sched.maybe_trigger(CIMIER_STATE_CLOSED)
    assert decision.trigger == "skip:weather"
    assert cimier.commands == []
    assert motor.calls == []
    assert weather.call_count == 1


def test_descending_with_open_cimier_skips_state():
    sched, cimier, motor, _ = _scheduler(
        automation=_automation(),
        alt_fn=lambda *a, **kw: -15.0,
        dir_fn=lambda *a, **kw: "descending",
    )
    decision = sched.maybe_trigger(CIMIER_STATE_OPEN)
    assert decision.trigger == "skip:state"
    assert cimier.commands == []
    assert motor.calls == []


def test_rising_with_open_cimier_triggers_close_three_ipc_in_order():
    """alt_future projeté à +15min ≥ -6° (target) + state=open → trigger="close"."""
    # Alt actuel = -10° (encore sous l'horizon), alt projeté à +15min = -5° (au-dessus du target -6°)
    alt_values = {0: -10.0, 1: -5.0}  # 0 = now, 1 = future (advance + safety)
    call_count = [0]

    def alt_fn(when, *a, **kw):
        idx = call_count[0]
        call_count[0] += 1
        return alt_values.get(idx, -10.0)

    sched, cimier, motor, _ = _scheduler(
        automation=_automation(),
        alt_fn=alt_fn,
        dir_fn=lambda *a, **kw: "rising",
    )
    decision = sched.maybe_trigger(CIMIER_STATE_OPEN)
    assert decision.trigger == "close"
    # Ordre IPC : tracking_stop → goto 45° → close cimier
    assert motor.calls == [("tracking_stop",), ("goto", 45.0)]
    assert len(cimier.commands) == 1
    assert cimier.commands[0]["action"] == "close"


def test_rising_with_closed_cimier_skips_state():
    alt_values = [-10.0, -5.0]
    call_count = [0]

    def alt_fn(*a, **kw):
        idx = call_count[0]
        call_count[0] += 1
        return alt_values[idx] if idx < 2 else -10.0

    sched, cimier, motor, _ = _scheduler(
        automation=_automation(),
        alt_fn=alt_fn,
        dir_fn=lambda *a, **kw: "rising",
    )
    decision = sched.maybe_trigger(CIMIER_STATE_CLOSED)
    assert decision.trigger == "skip:state"
    assert cimier.commands == []
    assert motor.calls == []


def test_open_idempotent_within_cooldown_window():
    sched, cimier, motor, _ = _scheduler(
        automation=_automation(),
        alt_fn=lambda *a, **kw: -15.0,
        dir_fn=lambda *a, **kw: "descending",
    )
    # 1er trigger : open
    d1 = sched.maybe_trigger(CIMIER_STATE_CLOSED)
    assert d1.trigger == "open"
    # 2e appel immédiat : cooldown actif (default 12h)
    # Cimier serait revenu à closed en théorie (test simplifié)
    d2 = sched.maybe_trigger(CIMIER_STATE_CLOSED)
    assert d2.trigger == "skip:cooldown"
    # Aucune nouvelle commande
    assert len(cimier.commands) == 1
    assert len([c for c in motor.calls if c[0] == "jog"]) == 1


def test_open_re_trigger_after_cooldown_window():
    """Après retrigger_cooldown_hours, le scheduler peut re-déclencher."""
    automation = _automation(retrigger_cooldown_hours=1)  # 1h pour test rapide
    weather = FakeWeatherProvider(safe=True)
    cimier = FakeCimierIpc()
    motor = FakeMotorIpc()

    # Clock variable pour avancer le temps entre triggers
    state = {"now": datetime(2026, 5, 15, 21, 0, tzinfo=timezone.utc)}

    sched = CimierScheduler(
        automation_config=automation,
        site_config=_site(),
        weather_provider=weather,
        cimier_ipc=cimier,
        motor_ipc=motor,
        clock=lambda: state["now"],
        sun_altitude_fn=lambda *a, **kw: -15.0,
        sun_direction_fn=lambda *a, **kw: "descending",
    )

    d1 = sched.maybe_trigger(CIMIER_STATE_CLOSED)
    assert d1.trigger == "open"

    # Avancer 2h (> cooldown 1h)
    state["now"] = state["now"] + timedelta(hours=2)
    d2 = sched.maybe_trigger(CIMIER_STATE_CLOSED)
    assert d2.trigger == "open"
    # 2 commandes émises
    assert len(cimier.commands) == 2


def test_close_idempotent_within_cooldown_window():
    alt_values = [-10.0, -5.0, -10.0, -5.0]
    call_count = [0]

    def alt_fn(*a, **kw):
        idx = call_count[0]
        call_count[0] += 1
        return alt_values[idx] if idx < len(alt_values) else -10.0

    sched, cimier, motor, _ = _scheduler(
        automation=_automation(),
        alt_fn=alt_fn,
        dir_fn=lambda *a, **kw: "rising",
    )
    d1 = sched.maybe_trigger(CIMIER_STATE_OPEN)
    assert d1.trigger == "close"
    d2 = sched.maybe_trigger(CIMIER_STATE_OPEN)
    assert d2.trigger == "skip:cooldown"
    assert len(cimier.commands) == 1


def test_flat_direction_returns_skip_state():
    sched, cimier, motor, _ = _scheduler(
        automation=_automation(),
        alt_fn=lambda *a, **kw: 30.0,
        dir_fn=lambda *a, **kw: "flat",
    )
    decision = sched.maybe_trigger(CIMIER_STATE_CLOSED)
    assert decision.trigger == "skip:state"
    assert cimier.commands == []
    assert motor.calls == []


def test_astropy_runtime_error_returns_skip_none():
    def raise_astropy(*a, **kw):
        raise RuntimeError("astropy requis")

    sched, cimier, motor, _ = _scheduler(
        automation=_automation(),
        alt_fn=raise_astropy,
        dir_fn=lambda *a, **kw: "descending",
    )
    decision = sched.maybe_trigger(CIMIER_STATE_CLOSED)
    assert decision.trigger == "skip:none"
    assert cimier.commands == []
    assert motor.calls == []


def test_close_trigger_in_cycle_state_works():
    """Cimier en cycle (cycle de fermeture précédent par exemple) → trigger close encore une fois ne devrait pas re-tenter."""
    alt_values = [-10.0, -5.0]
    call_count = [0]

    def alt_fn(*a, **kw):
        idx = call_count[0]
        call_count[0] += 1
        return alt_values[idx] if idx < 2 else -10.0

    sched, cimier, motor, _ = _scheduler(
        automation=_automation(),
        alt_fn=alt_fn,
        dir_fn=lambda *a, **kw: "rising",
    )
    decision = sched.maybe_trigger(CIMIER_STATE_CYCLE)
    # Pour cycle state, on accepte quand même un close (rebascule pending command)
    assert decision.trigger == "close"
    assert len(cimier.commands) == 1


def test_descending_above_threshold_no_trigger():
    """Sun descendant mais alt = -8° (au-dessus du seuil -12°) → pas de trigger."""
    sched, cimier, motor, _ = _scheduler(
        automation=_automation(),
        alt_fn=lambda *a, **kw: -8.0,
        dir_fn=lambda *a, **kw: "descending",
    )
    decision = sched.maybe_trigger(CIMIER_STATE_CLOSED)
    assert decision.trigger == "skip:state"
    assert cimier.commands == []
    assert motor.calls == []


def test_close_uses_configured_parking_azimuth():
    """Vérifie que le scheduler envoie GOTO vers parking_target_azimuth_deg configuré."""
    automation = _automation(parking_target_azimuth_deg=180.0)
    alt_values = [-10.0, -5.0]
    call_count = [0]

    def alt_fn(*a, **kw):
        idx = call_count[0]
        call_count[0] += 1
        return alt_values[idx] if idx < 2 else -10.0

    sched, cimier, motor, _ = _scheduler(
        automation=automation,
        alt_fn=alt_fn,
        dir_fn=lambda *a, **kw: "rising",
    )
    decision = sched.maybe_trigger(CIMIER_STATE_OPEN)
    assert decision.trigger == "close"
    assert ("goto", 180.0) in motor.calls
