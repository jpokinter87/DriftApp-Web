"""Tests de VoltageMonitor (cartouche Tensions, 6.31.0)."""

from __future__ import annotations

import pytest

from core.config.config_loader import VoltagesConfig
from core.hardware.shelly_rpc import ShellyRpcError
from core.hardware.voltage_monitor import VoltageMonitor


class FakeShellies:
    """Tensions programmables par hôte ; None = injoignable."""

    def __init__(self, volts):
        self.volts = dict(volts)
        self.calls = []

    def __call__(self, host, voltmeter_id, timeout_s):
        self.calls.append((host, voltmeter_id, timeout_s))
        value = self.volts.get(host)
        if value is None:
            raise ShellyRpcError("Shelly unreachable: timed out")
        return value


class Journal:
    def __init__(self):
        self.lines = []

    def __call__(self, event, **fields):
        self.lines.append((event, fields))


def make(volts, **cfg):
    params = dict(
        battery_host="bat",
        battery_id=100,
        charger_host="chg",
        charger_id=100,
        timeout_s=2.0,
        read_interval_s=60.0,
        journal_interval_s=300.0,
    )
    params.update(cfg)
    shellies = FakeShellies(volts)
    journal = Journal()
    monitor = VoltageMonitor(VoltagesConfig(**params), reader=shellies, journal=journal)
    return monitor, shellies, journal


def test_disabled_when_no_host():
    monitor, shellies, journal = make({}, battery_host="", charger_host="")
    assert monitor.enabled is False
    monitor.tick(0.0)
    assert shellies.calls == []
    assert journal.lines == []


def test_first_tick_reads_both_and_journals():
    monitor, shellies, journal = make({"bat": 12.43, "chg": 13.6})
    monitor.tick(0.0)
    assert shellies.calls == [("bat", 100, 2.0), ("chg", 100, 2.0)]
    assert journal.lines == [("voltages", {"battery": 12.43, "charger": 13.6, "reason": "start"})]
    d = monitor.describe()
    assert d["battery"]["voltage"] == 12.43
    assert d["charger"]["voltage"] == 13.6
    assert d["battery"]["error"] == ""
    assert d["battery_good_v"] == pytest.approx(12.4)
    assert d["battery_low_v"] == pytest.approx(12.0)


def test_reads_at_interval_only():
    monitor, shellies, _ = make({"bat": 12.4, "chg": 13.6})
    monitor.tick(0.0)
    monitor.tick(30.0)
    assert len(shellies.calls) == 2
    monitor.tick(60.0)
    assert len(shellies.calls) == 4


def test_periodic_journal_every_journal_interval():
    monitor, _, journal = make({"bat": 12.4, "chg": 13.6})
    for t in range(0, 601, 60):
        monitor.tick(float(t))
    reasons = [f["reason"] for _, f in journal.lines]
    assert reasons == ["start", "periodic", "periodic"]


def test_unreachable_battery_is_null_with_error():
    monitor, _, journal = make({"chg": 13.6})
    monitor.tick(0.0)
    d = monitor.describe()
    assert d["battery"]["voltage"] is None
    assert "unreachable" in d["battery"]["error"]
    assert journal.lines[-1][1]["battery"] is None


def test_battery_appearing_journals_immediately():
    monitor, shellies, journal = make({"chg": 13.6})
    monitor.tick(0.0)
    shellies.volts["bat"] = 12.5
    monitor.tick(60.0)
    assert journal.lines[-1] == ("voltages", {"battery": 12.5, "charger": 13.6, "reason": "change"})
    del shellies.volts["bat"]
    monitor.tick(120.0)
    assert journal.lines[-1][1]["reason"] == "change"
    assert journal.lines[-1][1]["battery"] is None


def test_charger_only_skips_battery():
    monitor, shellies, _ = make({"chg": 13.6}, battery_host="")
    monitor.tick(0.0)
    assert shellies.calls == [("chg", 100, 2.0)]
    assert "battery" not in monitor.describe()
