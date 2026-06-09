"""Tests du simulateur Shelly unifié cimier (dev) — relais + Uni+ + mécanisme."""

from __future__ import annotations

import json
import time
import urllib.request

import pytest

from core.hardware.cimier_simulator import CimierSimulator


@pytest.fixture
def sim():
    s = CimierSimulator(port=0, boot_delay_s=0.0, initial_state="closed", full_travel_s=0.5)
    s.start()
    assert s.wait_ready(timeout=2.0)
    yield s
    s.stop()


def _get_json(url):
    with urllib.request.urlopen(url, timeout=2.0) as resp:
        return json.loads(resp.read().decode("utf-8"))


def test_uni_inputs_reflect_initial_closed(sim):
    # closed → BAS en butée (contact fermé → state False), HAUT pas en butée (state True)
    bas = _get_json(sim.url + "/rpc/Input.GetStatus?id=0")
    haut = _get_json(sim.url + "/rpc/Input.GetStatus?id=1")
    assert bas["state"] is False
    assert haut["state"] is True


def test_relay_endpoints_return_200(sim):
    for relay in (0, 1, 2):
        payload = _get_json(sim.url + "/relay/{}?turn=on".format(relay))
        assert "ison" in payload


def test_open_cycle_animates_to_top(sim):
    # 24V on, UPDN up (ouverture), MOT on → la position doit atteindre le haut
    _get_json(sim.url + "/relay/0?turn=on")  # 24V
    _get_json(sim.url + "/relay/2?turn=on")  # UPDN = ouverture
    _get_json(sim.url + "/relay/1?turn=on")  # MOT on

    deadline = time.monotonic() + 3.0
    haut_state = True
    while time.monotonic() < deadline:
        haut_state = _get_json(sim.url + "/rpc/Input.GetStatus?id=1")["state"]
        if haut_state is False:  # butée haute atteinte (contact fermé)
            break
        time.sleep(0.05)
    assert haut_state is False


def test_power_off_freezes_motion(sim):
    _get_json(sim.url + "/relay/0?turn=off")  # 24V OFF
    _get_json(sim.url + "/relay/2?turn=on")
    _get_json(sim.url + "/relay/1?turn=on")  # MOT on mais pas de 24V

    # Sans 24V, la position ne doit pas bouger quel que soit le temps écoulé.
    time.sleep(0.1)
    haut = _get_json(sim.url + "/rpc/Input.GetStatus?id=1")["state"]
    assert haut is True  # pas bougé : toujours pas en butée haute


def test_shelly_switch_reader_reads_via_real_http(sim):
    # Le vrai ShellySwitchReader doit lire les butées du simulateur en HTTP réel.
    from core.hardware.shelly_switch_reader import ShellySwitchReader

    host = sim.url.replace("http://", "")  # "127.0.0.1:<port>"
    reader = ShellySwitchReader(host=host, open_input_id=1, closed_input_id=0, invert=True)
    state = reader.read()
    # initial_state="closed" → BAS en butée (id=0, state=False) → invert → closed_switch=True
    # HAUT libre (id=1, state=True) → invert → open_switch=False
    assert state.closed_switch is True
    assert state.open_switch is False
    assert state.both_switches is False
