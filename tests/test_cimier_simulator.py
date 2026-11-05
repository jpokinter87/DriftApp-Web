"""Tests du simulateur Shelly unifié cimier (dev) — relais + Uni+ + mécanisme."""

from __future__ import annotations

import json
import time
import urllib.error
import urllib.request

import pytest

from core.hardware.cimier_simulator import INPUT_RAIN, CimierSimulator


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
    for relay in (0, 1, 2, 3):
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


# --- entrée pluie simulée (2026-08) ------------------------------------


def test_rain_input_is_dry_by_default(sim):
    payload = _get_json(sim.url + "/rpc/Input.GetStatus?id={}".format(INPUT_RAIN))
    assert payload["state"] is False


def test_dev_rain_on_makes_it_wet(sim):
    _get_json(sim.url + "/dev/rain?on=1")
    payload = _get_json(sim.url + "/rpc/Input.GetStatus?id={}".format(INPUT_RAIN))
    assert payload["state"] is True


def test_dev_rain_off_makes_it_dry_again(sim):
    _get_json(sim.url + "/dev/rain?on=1")
    _get_json(sim.url + "/dev/rain?on=0")
    payload = _get_json(sim.url + "/rpc/Input.GetStatus?id={}".format(INPUT_RAIN))
    assert payload["state"] is False


def test_dev_rain_returns_current_state(sim):
    assert _get_json(sim.url + "/dev/rain?on=1") == {"raining": True}


def test_rain_input_does_not_disturb_the_limit_switches(sim):
    before = _get_json(sim.url + "/rpc/Input.GetStatus?id=0")["state"]
    _get_json(sim.url + "/dev/rain?on=1")
    assert _get_json(sim.url + "/rpc/Input.GetStatus?id=0")["state"] == before


def test_heater_relay_toggles_independently_of_motion(sim):
    """Relais 3 (résistance chauffante) : ON/OFF simple, sans lien avec le mécanisme."""
    payload_on = _get_json(sim.url + "/relay/3?turn=on")
    assert payload_on["ison"] is True
    payload_off = _get_json(sim.url + "/relay/3?turn=off")
    assert payload_off["ison"] is False


# --- 6.31.0 : sonde sans commutation, voltmètres simulés ---


def test_relay_status_without_turn_does_not_switch(sim):
    assert _get_json(sim.url + "/relay/0?turn=on") == {"ison": True}
    assert _get_json(sim.url + "/relay/0") == {"ison": True}
    _get_json(sim.url + "/relay/0?turn=off")
    assert _get_json(sim.url + "/relay/0") == {"ison": False}


def test_voltmeters_have_default_values(sim):
    from core.hardware.cimier_simulator import VOLTMETER_BATTERY, VOLTMETER_CHARGER

    battery = _get_json(sim.url + f"/rpc/Voltmeter.GetStatus?id={VOLTMETER_BATTERY}")
    charger = _get_json(sim.url + f"/rpc/Voltmeter.GetStatus?id={VOLTMETER_CHARGER}")
    assert battery == {"id": VOLTMETER_BATTERY, "voltage": 12.55}
    assert charger == {"id": VOLTMETER_CHARGER, "voltage": 13.6}


def test_dev_voltage_changes_a_value(sim):
    assert _get_json(sim.url + "/dev/voltage?id=100&v=11.8") == {"id": 100, "voltage": 11.8}
    assert _get_json(sim.url + "/rpc/Voltmeter.GetStatus?id=100")["voltage"] == 11.8


def test_unknown_voltmeter_is_404(sim):
    with pytest.raises(urllib.error.HTTPError):
        _get_json(sim.url + "/rpc/Voltmeter.GetStatus?id=7")


def test_read_voltage_via_real_http(sim):
    from core.hardware.shelly_rpc import read_voltage

    host = sim.url.removeprefix("http://")
    assert read_voltage(host, 101, timeout_s=2.0) == 13.6
