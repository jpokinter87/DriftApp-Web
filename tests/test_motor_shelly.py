"""Tests du module core.hardware.motor_shelly.

Pivot architectural cimier (v6.x) : remplacement du pilotage STEP/DIR via le
Pico W par 2 Shellys 1 Gen 3 distincts (1 relais chacun, contact sec) pour
le moteur cimier. Cf. ``core/hardware/motor_shelly.py`` pour le contexte
complet.

Conventions de test :
  - host MOTOR  : "192.168.1.85"
  - host DIR    : "192.168.1.86"
  - Discrimination motor vs dir = HOST (les 2 Shellys ont chacun un relais
    d'index 0 par défaut → l'index ne discrimine plus).

Pattern miroir de tests/test_power_switch.py : mocks urlopen, format URL,
gestion d'erreurs, support RPC (Gen 2/3) et legacy (Gen 1).
"""

from __future__ import annotations

import urllib.error
from unittest.mock import MagicMock

import pytest

from core.hardware.motor_shelly import (
    MotorShelly,
    MotorShellyError,
)


# ----------------------------------------------------------------------
# Helpers
# ----------------------------------------------------------------------

HOST_MOTOR = "192.168.1.85"
HOST_DIR = "192.168.1.86"


def make_mock_urlopen(status_code: int = 200, body: bytes = b'{"was_on":false}'):
    """Construit un mock urlopen qui retourne une réponse context manager."""
    response = MagicMock()
    response.status = status_code
    response.read = MagicMock(return_value=body)
    response.__enter__ = MagicMock(return_value=response)
    response.__exit__ = MagicMock(return_value=False)
    return MagicMock(return_value=response)


def _called_url(mock):
    return mock.call_args[0][0]


def _called_urls(mock):
    return [call.args[0] for call in mock.call_args_list]


# ----------------------------------------------------------------------
# Construction + validation
# ----------------------------------------------------------------------


class TestMotorShellyConstruction:
    def test_default_api_is_rpc(self):
        sh = MotorShelly(HOST_MOTOR, HOST_DIR, urlopen=make_mock_urlopen())
        assert sh.api == "rpc"

    def test_host_motor_property(self):
        sh = MotorShelly(HOST_MOTOR, HOST_DIR, urlopen=make_mock_urlopen())
        assert sh.host_motor == HOST_MOTOR

    def test_host_dir_property(self):
        sh = MotorShelly(HOST_MOTOR, HOST_DIR, urlopen=make_mock_urlopen())
        assert sh.host_dir == HOST_DIR

    def test_relay_indices_default_zero_each(self):
        """Shelly 1 Gen 3 : 1 seul relais d'index 0. Les 2 hôtes étant distincts,
        rien n'empêche les 2 relais d'avoir le même index."""
        sh = MotorShelly(HOST_MOTOR, HOST_DIR, urlopen=make_mock_urlopen())
        assert sh.relay_motor == 0
        assert sh.relay_dir == 0

    def test_relay_indices_custom(self):
        """Override possible pour Shellys multi-relais (Plus 2PM, etc.)."""
        sh = MotorShelly(
            HOST_MOTOR,
            HOST_DIR,
            relay_motor=2,
            relay_dir=3,
            urlopen=make_mock_urlopen(),
        )
        assert sh.relay_motor == 2
        assert sh.relay_dir == 3

    def test_invalid_api_raises_value_error(self):
        with pytest.raises(ValueError, match="api must be"):
            MotorShelly(HOST_MOTOR, HOST_DIR, api="bogus")


# ----------------------------------------------------------------------
# turn_on / turn_off — RPC (Gen 2/3), convention normale
# ----------------------------------------------------------------------


class TestMotorShellyOnOffRpc:
    def test_turn_on_url_format_uses_motor_host(self):
        mock = make_mock_urlopen()
        sh = MotorShelly(HOST_MOTOR, HOST_DIR, urlopen=mock)
        sh.turn_on()
        url = _called_url(mock)
        assert url == "http://" + HOST_MOTOR + "/rpc/Switch.Set?id=0&on=false"

    def test_turn_off_url_format_uses_motor_host(self):
        mock = make_mock_urlopen()
        sh = MotorShelly(HOST_MOTOR, HOST_DIR, urlopen=mock)
        sh.turn_off()
        url = _called_url(mock)
        assert url == "http://" + HOST_MOTOR + "/rpc/Switch.Set?id=0&on=true"

    def test_turn_on_uses_motor_relay_index(self):
        mock = make_mock_urlopen()
        sh = MotorShelly(HOST_MOTOR, HOST_DIR, relay_motor=2, urlopen=mock)
        sh.turn_on()
        url = _called_url(mock)
        assert HOST_MOTOR in url
        assert "id=2" in url

    def test_turn_on_with_safety_timer(self):
        """Filet de sécurité WiFi-drop : Shelly auto-off après N secondes."""
        mock = make_mock_urlopen()
        sh = MotorShelly(HOST_MOTOR, HOST_DIR, urlopen=mock)
        sh.turn_on(timer_s=90.0)
        url = _called_url(mock)
        assert HOST_MOTOR in url
        assert "toggle_after=90" in url
        assert "on=false" in url

    def test_turn_on_zero_timer_omits_param(self):
        mock = make_mock_urlopen()
        sh = MotorShelly(HOST_MOTOR, HOST_DIR, urlopen=mock)
        sh.turn_on(timer_s=0.0)
        assert "toggle_after" not in _called_url(mock)


# ----------------------------------------------------------------------
# turn_on / turn_off — legacy (Gen 1)
# ----------------------------------------------------------------------


class TestMotorShellyOnOffLegacy:
    def test_turn_on_url_format(self):
        mock = make_mock_urlopen()
        sh = MotorShelly(HOST_MOTOR, HOST_DIR, api="legacy", urlopen=mock)
        sh.turn_on()
        assert _called_url(mock) == "http://" + HOST_MOTOR + "/relay/0?turn=off"

    def test_turn_off_url_format(self):
        mock = make_mock_urlopen()
        sh = MotorShelly(HOST_MOTOR, HOST_DIR, api="legacy", urlopen=mock)
        sh.turn_off()
        assert _called_url(mock) == "http://" + HOST_MOTOR + "/relay/0?turn=on"

    def test_turn_on_with_safety_timer_legacy(self):
        mock = make_mock_urlopen()
        sh = MotorShelly(HOST_MOTOR, HOST_DIR, api="legacy", urlopen=mock)
        sh.turn_on(timer_s=90.0)
        url = _called_url(mock)
        assert "timer=90" in url
        assert "turn=off" in url


# ----------------------------------------------------------------------
# set_direction — convention open_dir_state, target = host_dir
# ----------------------------------------------------------------------


class TestMotorShellySetDirection:
    def test_set_direction_open_default_relay_on_uses_dir_host(self):
        """open_dir_state=True (défaut) : open_direction=True → DIR Shelly ON."""
        mock = make_mock_urlopen()
        sh = MotorShelly(HOST_MOTOR, HOST_DIR, urlopen=mock)
        sh.set_direction(open_direction=True)
        url = _called_url(mock)
        assert HOST_DIR in url  # bien le Shelly DIR, pas le MOTOR
        assert HOST_MOTOR not in url
        assert "id=0" in url  # relay_dir défaut = 0 (Shelly 1 Gen 3)
        assert "on=true" in url

    def test_set_direction_close_default_relay_off_uses_dir_host(self):
        mock = make_mock_urlopen()
        sh = MotorShelly(HOST_MOTOR, HOST_DIR, urlopen=mock)
        sh.set_direction(open_direction=False)
        url = _called_url(mock)
        assert HOST_DIR in url
        assert "on=false" in url

    def test_set_direction_inverted_open_state(self):
        """open_dir_state=False : convention inversée (cas Serge : ouvert = UP)."""
        mock = make_mock_urlopen()
        sh = MotorShelly(HOST_MOTOR, HOST_DIR, open_dir_state=False, urlopen=mock)
        sh.set_direction(open_direction=True)
        url = _called_url(mock)
        assert HOST_DIR in url
        assert "on=false" in url

    def test_set_direction_uses_dir_relay_index(self):
        mock = make_mock_urlopen()
        sh = MotorShelly(HOST_MOTOR, HOST_DIR, relay_dir=3, urlopen=mock)
        sh.set_direction(open_direction=True)
        url = _called_url(mock)
        assert HOST_DIR in url
        assert "id=3" in url

    def test_set_direction_does_not_touch_motor_host(self):
        """set_direction ne doit jamais cibler le Shelly MOTOR."""
        mock = make_mock_urlopen()
        sh = MotorShelly(HOST_MOTOR, HOST_DIR, urlopen=mock)
        sh.set_direction(open_direction=True)
        url = _called_url(mock)
        assert HOST_MOTOR not in url


# ----------------------------------------------------------------------
# Convention moteur validée terrain (défaut) : motor_on_relay_state=False
# ----------------------------------------------------------------------
# Le moteur tourne quand le circuit MOTOR est OUVERT (oscillateur câblé NC).
# turn_on() met donc le relais à OFF (turn=off) pour démarrer, et turn_off()
# le met à ON (turn=on) pour arrêter. Validé du premier coup terrain 17-18/06.


class TestMotorShellyInvertedMotorLogic:
    def test_turn_on_with_inverted_state_sets_relay_off(self):
        mock = make_mock_urlopen()
        sh = MotorShelly(
            HOST_MOTOR,
            HOST_DIR,
            motor_on_relay_state=False,
            urlopen=mock,
        )
        sh.turn_on()
        url = _called_url(mock)
        assert HOST_MOTOR in url  # bien le Shelly MOTOR
        assert "on=false" in url  # contact ouvert = moteur démarre

    def test_turn_off_with_inverted_state_sets_relay_on(self):
        mock = make_mock_urlopen()
        sh = MotorShelly(
            HOST_MOTOR,
            HOST_DIR,
            motor_on_relay_state=False,
            urlopen=mock,
        )
        sh.turn_off()
        url = _called_url(mock)
        assert HOST_MOTOR in url
        assert "on=true" in url  # contact fermé = moteur stoppé

    def test_turn_on_inverted_with_safety_timer(self):
        """toggle_after Shelly fait basculer à l'état opposé après N s → moteur
        passe de ON (relais OFF) à OFF (relais ON) automatiquement."""
        mock = make_mock_urlopen()
        sh = MotorShelly(
            HOST_MOTOR,
            HOST_DIR,
            motor_on_relay_state=False,
            urlopen=mock,
        )
        sh.turn_on(timer_s=90.0)
        url = _called_url(mock)
        assert "on=false" in url
        assert "toggle_after=90" in url

    def test_motor_on_relay_state_default_is_false(self):
        sh = MotorShelly(HOST_MOTOR, HOST_DIR, urlopen=make_mock_urlopen())
        assert sh.motor_on_relay_state is False

    def test_motor_on_relay_state_property_reflects_constructor(self):
        sh = MotorShelly(
            HOST_MOTOR,
            HOST_DIR,
            motor_on_relay_state=False,
            urlopen=make_mock_urlopen(),
        )
        assert sh.motor_on_relay_state is False

    def test_inverted_motor_does_not_affect_dir_relay(self):
        """motor_on_relay_state n'impacte que turn_on/turn_off, pas set_direction."""
        mock = make_mock_urlopen()
        sh = MotorShelly(
            HOST_MOTOR,
            HOST_DIR,
            motor_on_relay_state=False,
            urlopen=mock,
        )
        sh.set_direction(open_direction=True)
        url = _called_url(mock)
        assert HOST_DIR in url  # bien le Shelly DIR
        assert "on=true" in url  # DIR suit open_dir_state défaut


class TestMotorShellyRelayOnConvention:
    """Branche non-défaut : motor_on_relay_state=True (relais ON = moteur ON).
    Couverture conservée bien que la convention validée terrain soit False."""

    def test_turn_on_relay_on_rpc(self):
        mock = make_mock_urlopen()
        sh = MotorShelly(HOST_MOTOR, HOST_DIR, motor_on_relay_state=True, urlopen=mock)
        sh.turn_on()
        assert "on=true" in _called_url(mock)

    def test_turn_on_relay_on_legacy(self):
        mock = make_mock_urlopen()
        sh = MotorShelly(
            HOST_MOTOR, HOST_DIR, api="legacy", motor_on_relay_state=True, urlopen=mock
        )
        sh.turn_on()
        assert _called_url(mock) == "http://" + HOST_MOTOR + "/relay/0?turn=on"


# ----------------------------------------------------------------------
# Séquences typiques (utilisées par cimier_service)
# ----------------------------------------------------------------------


class TestMotorShellySequences:
    def test_open_cycle_set_direction_then_turn_on(self):
        """Ouverture : set_direction(True) → turn_on(timer_s=90).
        URL 1 sur DIR Shelly, URL 2 sur MOTOR Shelly avec timer."""
        mock = make_mock_urlopen()
        sh = MotorShelly(HOST_MOTOR, HOST_DIR, urlopen=mock)
        sh.set_direction(open_direction=True)
        sh.turn_on(timer_s=90.0)
        urls = _called_urls(mock)
        assert len(urls) == 2
        assert HOST_DIR in urls[0]
        assert "on=true" in urls[0]
        assert HOST_MOTOR in urls[1]
        assert "on=false" in urls[1]
        assert "toggle_after=90" in urls[1]

    def test_close_cycle_set_direction_then_turn_on(self):
        mock = make_mock_urlopen()
        sh = MotorShelly(HOST_MOTOR, HOST_DIR, urlopen=mock)
        sh.set_direction(open_direction=False)
        sh.turn_on(timer_s=90.0)
        urls = _called_urls(mock)
        assert HOST_DIR in urls[0]
        assert "on=false" in urls[0]
        assert HOST_MOTOR in urls[1]
        assert "on=false" in urls[1]

    def test_serge_terrain_open_cycle_inverted_conventions(self):
        """Cas terrain Serge : open_dir_state=False (ouvert=UP) +
        motor_on_relay_state=False (oscillateur NC). Ouverture :
        DIR Shelly → on=false (UP), MOTOR Shelly → on=false (démarre)."""
        mock = make_mock_urlopen()
        sh = MotorShelly(
            HOST_MOTOR,
            HOST_DIR,
            open_dir_state=False,
            motor_on_relay_state=False,
            urlopen=mock,
        )
        sh.set_direction(open_direction=True)
        sh.turn_on(timer_s=90.0)
        urls = _called_urls(mock)
        assert HOST_DIR in urls[0]
        assert "on=false" in urls[0]  # DIR ouvert = UP
        assert HOST_MOTOR in urls[1]
        assert "on=false" in urls[1]  # MOTOR ouvert = moteur démarre


# ----------------------------------------------------------------------
# Erreurs réseau / HTTP
# ----------------------------------------------------------------------


class TestMotorShellyErrors:
    def test_http_500_raises_motor_shelly_error(self):
        mock = make_mock_urlopen(status_code=500)
        sh = MotorShelly(HOST_MOTOR, HOST_DIR, urlopen=mock)
        with pytest.raises(MotorShellyError, match="HTTP 500"):
            sh.turn_on()

    def test_url_error_raises_motor_shelly_error(self):
        mock = MagicMock(side_effect=urllib.error.URLError("Connection refused"))
        sh = MotorShelly(HOST_MOTOR, HOST_DIR, urlopen=mock)
        with pytest.raises(MotorShellyError, match="unreachable"):
            sh.turn_on()

    def test_socket_error_raises_motor_shelly_error(self):
        mock = MagicMock(side_effect=OSError("timeout"))
        sh = MotorShelly(HOST_MOTOR, HOST_DIR, urlopen=mock)
        with pytest.raises(MotorShellyError, match="socket"):
            sh.turn_on()

    def test_error_on_set_direction_propagates(self):
        mock = MagicMock(side_effect=urllib.error.URLError("Connection refused"))
        sh = MotorShelly(HOST_MOTOR, HOST_DIR, urlopen=mock)
        with pytest.raises(MotorShellyError):
            sh.set_direction(open_direction=True)

    def test_negative_timer_raises_value_error(self):
        sh = MotorShelly(HOST_MOTOR, HOST_DIR, urlopen=make_mock_urlopen())
        with pytest.raises(ValueError, match="timer_s"):
            sh.turn_on(timer_s=-1.0)


# ----------------------------------------------------------------------
# Timeout urlopen
# ----------------------------------------------------------------------


def test_timeout_passed_to_urlopen():
    mock = make_mock_urlopen()
    sh = MotorShelly(HOST_MOTOR, HOST_DIR, timeout_s=5.0, urlopen=mock)
    sh.turn_on()
    assert mock.call_args[1].get("timeout") == 5.0


def test_default_timeout():
    mock = make_mock_urlopen()
    sh = MotorShelly(HOST_MOTOR, HOST_DIR, urlopen=mock)
    sh.turn_on()
    assert mock.call_args[1].get("timeout") == 3.0
