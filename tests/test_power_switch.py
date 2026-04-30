"""Tests du module core.hardware.power_switch."""

from __future__ import annotations

import urllib.error
from unittest.mock import MagicMock

import pytest

from core.hardware.power_switch import (
    NoopPowerSwitch,
    PowerSwitchError,
    ShellyPowerSwitch,
)


# ----------------------------------------------------------------------
# Helpers
# ----------------------------------------------------------------------

def make_mock_urlopen(status_code: int = 200, body: bytes = b'{"was_on":false}'):
    """Construit un mock urlopen qui retourne une reponse context manager."""
    response = MagicMock()
    response.status = status_code
    response.read = MagicMock(return_value=body)
    response.__enter__ = MagicMock(return_value=response)
    response.__exit__ = MagicMock(return_value=False)
    return MagicMock(return_value=response)


# ----------------------------------------------------------------------
# NoopPowerSwitch
# ----------------------------------------------------------------------

class TestNoopPowerSwitch:
    def test_initial_state_off(self):
        sw = NoopPowerSwitch()
        assert sw.is_on() is False

    def test_turn_on_sets_state_true(self):
        sw = NoopPowerSwitch()
        sw.turn_on()
        assert sw.is_on() is True

    def test_turn_off_sets_state_false(self):
        sw = NoopPowerSwitch()
        sw.turn_on()
        sw.turn_off()
        assert sw.is_on() is False

    def test_turn_on_is_idempotent(self):
        sw = NoopPowerSwitch()
        sw.turn_on()
        sw.turn_on()
        assert sw.is_on() is True


# ----------------------------------------------------------------------
# ShellyPowerSwitch — URL building (RPC Gen 2)
# ----------------------------------------------------------------------

class TestShellyRpc:
    def test_turn_on_url_format(self):
        mock = make_mock_urlopen()
        sw = ShellyPowerSwitch("192.168.1.51", urlopen=mock)
        sw.turn_on()
        called_url = mock.call_args[0][0]
        assert called_url == "http://192.168.1.51/rpc/Switch.Set?id=0&on=true"

    def test_turn_off_url_format(self):
        mock = make_mock_urlopen()
        sw = ShellyPowerSwitch("192.168.1.51", urlopen=mock)
        sw.turn_off()
        called_url = mock.call_args[0][0]
        assert called_url == "http://192.168.1.51/rpc/Switch.Set?id=0&on=false"

    def test_custom_switch_id(self):
        mock = make_mock_urlopen()
        sw = ShellyPowerSwitch("192.168.1.51", switch_id=2, urlopen=mock)
        sw.turn_on()
        assert "id=2" in mock.call_args[0][0]


# ----------------------------------------------------------------------
# ShellyPowerSwitch — URL building (legacy Gen 1)
# ----------------------------------------------------------------------

class TestShellyLegacy:
    def test_turn_on_url_format(self):
        mock = make_mock_urlopen()
        sw = ShellyPowerSwitch("192.168.1.51", api="legacy", urlopen=mock)
        sw.turn_on()
        called_url = mock.call_args[0][0]
        assert called_url == "http://192.168.1.51/relay/0?turn=on"

    def test_turn_off_url_format(self):
        mock = make_mock_urlopen()
        sw = ShellyPowerSwitch("192.168.1.51", api="legacy", urlopen=mock)
        sw.turn_off()
        called_url = mock.call_args[0][0]
        assert called_url == "http://192.168.1.51/relay/0?turn=off"

    def test_invalid_api_raises_value_error(self):
        with pytest.raises(ValueError, match="api must be"):
            ShellyPowerSwitch("192.168.1.51", api="bogus")


# ----------------------------------------------------------------------
# ShellyPowerSwitch — Erreurs reseau
# ----------------------------------------------------------------------

class TestShellyErrors:
    def test_http_500_raises_power_switch_error(self):
        mock = make_mock_urlopen(status_code=500)
        sw = ShellyPowerSwitch("192.168.1.51", urlopen=mock)
        with pytest.raises(PowerSwitchError, match="HTTP 500"):
            sw.turn_on()

    def test_url_error_raises_power_switch_error(self):
        mock = MagicMock(side_effect=urllib.error.URLError("Connection refused"))
        sw = ShellyPowerSwitch("192.168.1.51", urlopen=mock)
        with pytest.raises(PowerSwitchError, match="unreachable"):
            sw.turn_on()

    def test_socket_error_raises_power_switch_error(self):
        mock = MagicMock(side_effect=OSError("timeout"))
        sw = ShellyPowerSwitch("192.168.1.51", urlopen=mock)
        with pytest.raises(PowerSwitchError, match="socket"):
            sw.turn_on()


# ----------------------------------------------------------------------
# ShellyPowerSwitch — Timeout
# ----------------------------------------------------------------------

def test_timeout_passed_to_urlopen():
    mock = make_mock_urlopen()
    sw = ShellyPowerSwitch("192.168.1.51", timeout_s=5.0, urlopen=mock)
    sw.turn_on()
    kwargs = mock.call_args[1]
    assert kwargs.get("timeout") == 5.0


def test_default_timeout():
    mock = make_mock_urlopen()
    sw = ShellyPowerSwitch("192.168.1.51", urlopen=mock)
    sw.turn_on()
    kwargs = mock.call_args[1]
    assert kwargs.get("timeout") == 3.0


# ----------------------------------------------------------------------
# Properties
# ----------------------------------------------------------------------

def test_host_property():
    sw = ShellyPowerSwitch("192.168.1.51", urlopen=make_mock_urlopen())
    assert sw.host == "192.168.1.51"


def test_api_property_default_rpc():
    sw = ShellyPowerSwitch("192.168.1.51", urlopen=make_mock_urlopen())
    assert sw.api == "rpc"


def test_api_property_legacy():
    sw = ShellyPowerSwitch("192.168.1.51", api="legacy", urlopen=make_mock_urlopen())
    assert sw.api == "legacy"
