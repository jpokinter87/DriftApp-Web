"""Tests du simulateur HTTP Pico W cimier capteur-only (core/hardware/cimier_simulator.py)."""
from __future__ import annotations

import json
import socket
import threading
import time
import urllib.error
import urllib.request

import pytest

from core.hardware.cimier_simulator import CimierSimulator


def _free_port():
    s = socket.socket()
    s.bind(("127.0.0.1", 0))
    port = s.getsockname()[1]
    s.close()
    return port


def _http(method, url, timeout=2.0):
    req = urllib.request.Request(url, method=method)
    with urllib.request.urlopen(req, timeout=timeout) as resp:
        return resp.status, json.loads(resp.read().decode("utf-8"))


@pytest.fixture
def simulator():
    sim = CimierSimulator(port=_free_port(), boot_delay_s=0.0, initial_state="closed")
    sim.start()
    assert sim.wait_ready(timeout=2.0), "simulator did not become ready"
    yield sim
    sim.stop()


# --- 1. Boot lifecycle -----------------------------------------------------
def test_is_ready_false_before_start():
    sim = CimierSimulator(port=_free_port(), boot_delay_s=10.0)
    try:
        assert sim.is_ready() is False
    finally:
        sim.stop()


def test_is_ready_true_after_boot():
    sim = CimierSimulator(port=_free_port(), boot_delay_s=0.0)
    sim.start()
    try:
        assert sim.wait_ready(timeout=2.0)
        assert sim.is_ready() is True
    finally:
        sim.stop()


@pytest.mark.slow
def test_connection_refused_during_boot_delay():
    sim = CimierSimulator(port=_free_port(), boot_delay_s=0.5)
    sim.start()
    try:
        with pytest.raises((urllib.error.URLError, ConnectionRefusedError)):
            urllib.request.urlopen(sim.url + "/status", timeout=0.2)
        assert sim.wait_ready(timeout=1.5)
        status, _ = _http("GET", sim.url + "/status")
        assert status == 200
    finally:
        sim.stop()


# --- 2. Endpoints capteurs -------------------------------------------------
def test_get_status_schema_closed(simulator):
    status, payload = _http("GET", simulator.url + "/status")
    assert status == 200
    assert set(payload.keys()) == {"state", "open_switch", "closed_switch", "error_message"}
    assert payload["state"] == "closed"
    assert payload["closed_switch"] is True
    assert payload["open_switch"] is False


def test_get_info_schema(simulator):
    status, info = _http("GET", simulator.url + "/info")
    assert status == 200
    for key in ("firmware_version", "protocol_version", "role",
                "wifi_rssi", "wifi_ip", "free_memory"):
        assert key in info, "champ {} manquant".format(key)
    assert info["role"] == "sensor"
    assert info["wifi_ip"] == "127.0.0.1"


def test_get_unknown_path_returns_404(simulator):
    with pytest.raises(urllib.error.HTTPError) as excinfo:
        urllib.request.urlopen(simulator.url + "/does-not-exist", timeout=2.0)
    assert excinfo.value.code == 404


def test_post_any_path_returns_404(simulator):
    """Firmware capteur-only : plus aucun POST supporté."""
    req = urllib.request.Request(simulator.url + "/open", data=b"", method="POST")
    with pytest.raises(urllib.error.HTTPError) as excinfo:
        urllib.request.urlopen(req, timeout=2.0)
    assert excinfo.value.code == 404


# --- 3. État piloté par le mécanisme --------------------------------------
def test_initial_open_reflected_in_status():
    sim = CimierSimulator(port=_free_port(), boot_delay_s=0.0, initial_state="open")
    sim.start()
    try:
        assert sim.wait_ready(timeout=2.0)
        _, payload = _http("GET", sim.url + "/status")
        assert payload["state"] == "open"
        assert payload["open_switch"] is True
    finally:
        sim.stop()


def test_mechanism_movement_changes_status(simulator):
    """En pilotant le mécanisme directement (comme le fera le Shelly simulé),
    le /status reflète la nouvelle fin de course."""
    m = simulator.mechanism
    m.set_direction(open_direction=True)
    m.set_motor(True)
    m.advance(1000.0)  # course complète
    _, payload = _http("GET", simulator.url + "/status")
    assert payload["state"] == "open"
    assert payload["open_switch"] is True


# --- 4. Threading & arrêt propre ------------------------------------------
def test_stop_releases_port():
    port = _free_port()
    sim = CimierSimulator(port=port, boot_delay_s=0.0)
    sim.start()
    assert sim.wait_ready(timeout=2.0)
    sim.stop()
    probe = socket.socket()
    try:
        probe.bind(("127.0.0.1", port))
    finally:
        probe.close()


def test_no_thread_leak_after_stop():
    sim = CimierSimulator(port=_free_port(), boot_delay_s=0.0)
    sim.start()
    sim.wait_ready(timeout=2.0)
    sim.stop()
    time.sleep(0.05)
    leaks = [t for t in threading.enumerate()
             if t.name.startswith("cimier-sim-") and t.is_alive()]
    assert leaks == [], "threads non termines: {}".format(leaks)


def test_two_simulators_in_parallel():
    sim_a = CimierSimulator(port=_free_port(), boot_delay_s=0.0)
    sim_b = CimierSimulator(port=_free_port(), boot_delay_s=0.0)
    sim_a.start()
    sim_b.start()
    try:
        assert sim_a.wait_ready(timeout=2.0)
        assert sim_b.wait_ready(timeout=2.0)
        status_a, _ = _http("GET", sim_a.url + "/status")
        status_b, _ = _http("GET", sim_b.url + "/status")
        assert status_a == 200 and status_b == 200
    finally:
        sim_a.stop()
        sim_b.stop()


# --- 5. Latence simulée ----------------------------------------------------
@pytest.mark.slow
def test_boot_delay_is_observable():
    boot_delay = 0.4
    sim = CimierSimulator(port=_free_port(), boot_delay_s=boot_delay)
    t0 = time.monotonic()
    sim.start()
    try:
        assert not sim.is_ready()
        sim.wait_ready(timeout=boot_delay + 1.0)
        elapsed = time.monotonic() - t0
        assert elapsed >= boot_delay * 0.8, "boot trop rapide ({:.3f}s)".format(elapsed)
        assert sim.is_ready()
    finally:
        sim.stop()
