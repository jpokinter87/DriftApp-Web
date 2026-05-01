"""Tests du simulateur HTTP Pico W cimier (core/hardware/cimier_simulator.py).

Le simulateur reutilise tel quel le module pur ``cimier_controller`` du
firmware ; les tests ici couvrent uniquement les apports du simulateur :
endpoints HTTP, latence boot, threading, perte d'invert au reset.
"""

from __future__ import annotations

import json
import socket
import threading
import time
import urllib.error
import urllib.request

import pytest

from core.hardware.cimier_simulator import (
    CimierSimulator,
    _VirtualHardwareAdapter,
)


# ----------------------------------------------------------------------
# Helpers
# ----------------------------------------------------------------------

def _free_port():
    s = socket.socket()
    s.bind(("127.0.0.1", 0))
    port = s.getsockname()[1]
    s.close()
    return port


def _http(method, url, body=None, timeout=2.0):
    data = None
    if body is not None:
        data = body if isinstance(body, (bytes, bytearray)) else json.dumps(body).encode("utf-8")
    req = urllib.request.Request(url, data=data, method=method)
    if data is not None:
        req.add_header("Content-Type", "application/json")
    with urllib.request.urlopen(req, timeout=timeout) as resp:
        payload = json.loads(resp.read().decode("utf-8"))
        return resp.status, payload


def _wait_state(sim, expected, timeout=2.0):
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        status_code, payload = _http("GET", sim.url + "/status")
        if payload["state"] == expected:
            return payload
        time.sleep(0.01)
    raise AssertionError(
        "etat {} jamais atteint (dernier: {})".format(expected, payload["state"])
    )


@pytest.fixture
def simulator():
    port = _free_port()
    sim = CimierSimulator(
        port=port,
        boot_delay_s=0.0,
        steps_per_cycle=20,
        cycle_timeout_s=2.0,
        tick_period_ms=5,
    )
    sim.start()
    assert sim.wait_ready(timeout=2.0), "simulator did not become ready"
    yield sim
    sim.stop()


# ----------------------------------------------------------------------
# 1. Boot lifecycle
# ----------------------------------------------------------------------

def test_is_ready_false_before_start():
    sim = CimierSimulator(port=_free_port(), boot_delay_s=10.0)
    try:
        assert sim.is_ready() is False
    finally:
        sim.stop()


def test_is_ready_true_after_boot():
    port = _free_port()
    sim = CimierSimulator(port=port, boot_delay_s=0.0, steps_per_cycle=20,
                          cycle_timeout_s=2.0, tick_period_ms=5)
    sim.start()
    try:
        assert sim.wait_ready(timeout=2.0)
        assert sim.is_ready() is True
    finally:
        sim.stop()


@pytest.mark.slow
def test_connection_refused_during_boot_delay():
    port = _free_port()
    sim = CimierSimulator(port=port, boot_delay_s=0.5, steps_per_cycle=20,
                          cycle_timeout_s=2.0, tick_period_ms=5)
    sim.start()
    try:
        # Pendant la fenetre boot : aucun serveur HTTP en ecoute -> refused.
        with pytest.raises((urllib.error.URLError, ConnectionRefusedError)):
            urllib.request.urlopen(sim.url + "/status", timeout=0.2)
        assert sim.wait_ready(timeout=1.5)
        # Apres boot : repond 200.
        status, _ = _http("GET", sim.url + "/status")
        assert status == 200
    finally:
        sim.stop()


def test_reset_boot_re_arms_window():
    """reset_boot() repasse par la fenetre de latence + reinit invert."""
    port = _free_port()
    sim = CimierSimulator(port=port, boot_delay_s=0.0, steps_per_cycle=20,
                          cycle_timeout_s=2.0, tick_period_ms=5,
                          initial_invert_direction=False)
    sim.start()
    try:
        assert sim.wait_ready(timeout=2.0)
        _http("POST", sim.url + "/config", body={"invert_direction": True})
        _, info = _http("GET", sim.url + "/info")
        assert info["invert_direction"] is True

        sim.reset_boot()
        assert sim.wait_ready(timeout=2.0)
        _, info = _http("GET", sim.url + "/info")
        assert info["invert_direction"] is False, "invert doit etre perdu au reset"
    finally:
        sim.stop()


# ----------------------------------------------------------------------
# 2. Endpoints de base
# ----------------------------------------------------------------------

def test_get_status_schema(simulator):
    status, payload = _http("GET", simulator.url + "/status")
    assert status == 200
    expected_keys = {
        "state", "open_switch", "closed_switch",
        "cycle_steps_done", "last_action_ts", "error_message",
    }
    assert expected_keys.issubset(payload.keys())
    # Position initiale = 0 -> closed
    assert payload["state"] == "closed"
    assert payload["closed_switch"] is True
    assert payload["open_switch"] is False


def test_post_open_starts_opening(simulator):
    status, payload = _http("POST", simulator.url + "/open")
    assert status == 200
    assert payload["state"] == "opening"


def test_post_close_idempotent_when_closed(simulator):
    status, payload = _http("POST", simulator.url + "/close")
    assert status == 200
    # Deja closed -> reste closed (idempotent par CimierController).
    assert payload["state"] == "closed"


def test_post_stop_during_cycle(simulator):
    _http("POST", simulator.url + "/open")
    # Stop immediat avant fin de cycle.
    status, payload = _http("POST", simulator.url + "/stop")
    assert status == 200
    # state apres stop : selon position des switches (peut etre unknown,
    # closed si on n'a pas eu le temps de faire un seul pas, etc).
    assert payload["state"] in {"unknown", "closed", "open"}


def test_get_info_schema(simulator):
    status, info = _http("GET", simulator.url + "/info")
    assert status == 200
    for key in (
        "firmware_version", "protocol_version", "steps_per_cycle",
        "cycle_timeout_s", "invert_direction",
        "wifi_rssi", "wifi_ip", "free_memory",
    ):
        assert key in info, "champ {} manquant".format(key)
    assert info["wifi_ip"] == "127.0.0.1"


def test_get_unknown_path_returns_404(simulator):
    with pytest.raises(urllib.error.HTTPError) as excinfo:
        urllib.request.urlopen(simulator.url + "/does-not-exist", timeout=2.0)
    assert excinfo.value.code == 404
    payload = json.loads(excinfo.value.read().decode("utf-8"))
    assert payload["error"] == "not_found"


def test_post_unknown_path_returns_404(simulator):
    req = urllib.request.Request(
        simulator.url + "/bogus", data=b"{}", method="POST"
    )
    req.add_header("Content-Type", "application/json")
    with pytest.raises(urllib.error.HTTPError) as excinfo:
        urllib.request.urlopen(req, timeout=2.0)
    assert excinfo.value.code == 404


# ----------------------------------------------------------------------
# 3. Cycle complet
# ----------------------------------------------------------------------

@pytest.mark.slow
def test_full_open_cycle(simulator):
    _http("POST", simulator.url + "/open")
    payload = _wait_state(simulator, "open", timeout=2.0)
    assert payload["open_switch"] is True
    assert payload["closed_switch"] is False
    assert payload["cycle_steps_done"] >= 20  # steps_per_cycle


@pytest.mark.slow
def test_full_close_cycle(simulator):
    # D'abord ouvrir
    _http("POST", simulator.url + "/open")
    _wait_state(simulator, "open", timeout=2.0)
    # Puis fermer
    _http("POST", simulator.url + "/close")
    payload = _wait_state(simulator, "closed", timeout=2.0)
    assert payload["closed_switch"] is True
    assert payload["open_switch"] is False


@pytest.mark.slow
def test_idempotent_open_when_already_open(simulator):
    _http("POST", simulator.url + "/open")
    _wait_state(simulator, "open", timeout=2.0)
    # Second /open : pas de cycle relance.
    status, payload = _http("POST", simulator.url + "/open")
    assert status == 200
    assert payload["state"] == "open"


def test_idempotent_close_when_already_closed(simulator):
    # Position initiale = closed
    status, payload = _http("POST", simulator.url + "/close")
    assert status == 200
    assert payload["state"] == "closed"


@pytest.mark.slow
def test_open_during_close_inverts(simulator):
    # Ouvrir d'abord pour avoir quelque chose a fermer
    _http("POST", simulator.url + "/open")
    _wait_state(simulator, "open", timeout=2.0)
    # Lancer fermeture puis ouvrir avant la fin
    _http("POST", simulator.url + "/close")
    _http("POST", simulator.url + "/open")
    # Le cycle s'inverse : on doit finir en open.
    payload = _wait_state(simulator, "open", timeout=2.0)
    assert payload["open_switch"] is True


# ----------------------------------------------------------------------
# 4. Configuration & invert_direction
# ----------------------------------------------------------------------

def test_post_config_invert_true(simulator):
    status, info = _http("POST", simulator.url + "/config",
                         body={"invert_direction": True})
    assert status == 200
    assert info["invert_direction"] is True


def test_post_config_invert_persists(simulator):
    _http("POST", simulator.url + "/config", body={"invert_direction": True})
    _, info = _http("GET", simulator.url + "/info")
    assert info["invert_direction"] is True


@pytest.mark.slow
def test_invert_direction_propagates_to_hardware(simulator):
    """Avec invert=True, la direction passee au moteur lors d'un /open est
    inversee (0 au lieu de 1)."""
    _http("POST", simulator.url + "/config", body={"invert_direction": True})
    _http("POST", simulator.url + "/open")
    # Attendre qu'au moins un set_direction soit logge.
    deadline = time.monotonic() + 1.0
    while time.monotonic() < deadline and not simulator.hardware.direction_log:
        time.sleep(0.01)
    assert simulator.hardware.direction_log, "aucune direction logguee"
    # Avec invert + open : direction reelle = 0 (inverse du nominal 1).
    assert simulator.hardware.direction_log[-1] == 0


def test_post_config_without_invert_key_ignored(simulator):
    _http("POST", simulator.url + "/config", body={"foo": "bar"})
    _, info = _http("GET", simulator.url + "/info")
    assert info["invert_direction"] is False


# ----------------------------------------------------------------------
# 5. Validation errors
# ----------------------------------------------------------------------

def test_post_invalid_json_body_returns_400(simulator):
    req = urllib.request.Request(
        simulator.url + "/config", data=b"not-json{{{", method="POST"
    )
    req.add_header("Content-Type", "application/json")
    with pytest.raises(urllib.error.HTTPError) as excinfo:
        urllib.request.urlopen(req, timeout=2.0)
    assert excinfo.value.code == 400


def test_post_config_non_dict_body_returns_400(simulator):
    req = urllib.request.Request(
        simulator.url + "/config", data=b"[1,2,3]", method="POST"
    )
    req.add_header("Content-Type", "application/json")
    with pytest.raises(urllib.error.HTTPError) as excinfo:
        urllib.request.urlopen(req, timeout=2.0)
    assert excinfo.value.code == 400


def test_post_open_with_empty_body_ok(simulator):
    """Le firmware accepte POST /open sans body. On reproduit ce comportement."""
    req = urllib.request.Request(
        simulator.url + "/open", data=b"", method="POST"
    )
    with urllib.request.urlopen(req, timeout=2.0) as resp:
        assert resp.status == 200


# ----------------------------------------------------------------------
# 6. Threading & arret propre
# ----------------------------------------------------------------------

def test_stop_releases_port():
    port = _free_port()
    sim = CimierSimulator(port=port, boot_delay_s=0.0, steps_per_cycle=20,
                          cycle_timeout_s=2.0, tick_period_ms=5)
    sim.start()
    assert sim.wait_ready(timeout=2.0)
    sim.stop()
    # Port doit etre re-bindable immediatement.
    probe = socket.socket()
    try:
        probe.bind(("127.0.0.1", port))
    finally:
        probe.close()


def test_no_thread_leak_after_stop():
    """Apres stop(), les threads internes du simulateur ne doivent plus tourner."""
    port = _free_port()
    sim = CimierSimulator(port=port, boot_delay_s=0.0, steps_per_cycle=20,
                          cycle_timeout_s=2.0, tick_period_ms=5)
    sim.start()
    sim.wait_ready(timeout=2.0)
    sim.stop()
    time.sleep(0.05)
    # Tous les threads internes de la simulation portent un nom 'cimier-sim-*'
    leaks = [t for t in threading.enumerate()
             if t.name.startswith("cimier-sim-") and t.is_alive()]
    assert leaks == [], "threads non termines: {}".format(leaks)


def test_two_simulators_in_parallel():
    port_a = _free_port()
    port_b = _free_port()
    sim_a = CimierSimulator(port=port_a, boot_delay_s=0.0, steps_per_cycle=20,
                            cycle_timeout_s=2.0, tick_period_ms=5)
    sim_b = CimierSimulator(port=port_b, boot_delay_s=0.0, steps_per_cycle=20,
                            cycle_timeout_s=2.0, tick_period_ms=5)
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


# ----------------------------------------------------------------------
# 7. Latence simulee
# ----------------------------------------------------------------------

@pytest.mark.slow
def test_boot_delay_is_observable():
    boot_delay = 0.4
    port = _free_port()
    sim = CimierSimulator(port=port, boot_delay_s=boot_delay, steps_per_cycle=20,
                          cycle_timeout_s=2.0, tick_period_ms=5)
    t0 = time.monotonic()
    sim.start()
    try:
        # Avant boot_delay : pas pret.
        assert not sim.is_ready()
        # Apres boot_delay (avec marge) : pret.
        sim.wait_ready(timeout=boot_delay + 1.0)
        elapsed = time.monotonic() - t0
        assert elapsed >= boot_delay * 0.8, "boot trop rapide ({:.3f}s)".format(elapsed)
        assert sim.is_ready()
    finally:
        sim.stop()


@pytest.mark.slow
def test_cycle_duration_proportional_to_steps():
    """20 pas a 5 ms/tick = ~100 ms minimum (avec jitter HTTP/threads)."""
    port = _free_port()
    sim = CimierSimulator(port=port, boot_delay_s=0.0, steps_per_cycle=20,
                          cycle_timeout_s=2.0, tick_period_ms=5)
    sim.start()
    try:
        assert sim.wait_ready(timeout=2.0)
        t0 = time.monotonic()
        _http("POST", sim.url + "/open")
        _wait_state(sim, "open", timeout=3.0)
        elapsed = time.monotonic() - t0
        # 20 * 5 ms = 100 ms minimum theorique. Tolerance large : 50 ms a 1.5 s.
        assert 0.05 <= elapsed <= 1.5, "duree cycle hors plage: {:.3f}s".format(elapsed)
    finally:
        sim.stop()


# ----------------------------------------------------------------------
# 8. Adapter virtuel (unit, sans HTTP)
# ----------------------------------------------------------------------

def test_virtual_adapter_position_clamped():
    hw = _VirtualHardwareAdapter(steps_per_cycle=5, initial_position=0)
    hw.set_direction(1)
    for _ in range(10):
        hw.pulse_step()
    assert hw.position == 5
    assert hw.read_open_switch() is True
    assert hw.read_closed_switch() is False


def test_virtual_adapter_close_direction():
    hw = _VirtualHardwareAdapter(steps_per_cycle=5, initial_position=5)
    hw.set_direction(0)
    for _ in range(10):
        hw.pulse_step()
    assert hw.position == 0
    assert hw.read_closed_switch() is True
    assert hw.read_open_switch() is False


def test_virtual_adapter_step_count_tracks_pulses():
    hw = _VirtualHardwareAdapter(steps_per_cycle=10)
    hw.set_direction(1)
    for _ in range(7):
        hw.pulse_step()
    assert hw.step_count == 7
