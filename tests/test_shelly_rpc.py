"""Tests du dialogue RPC Shelly partagé (Input.GetStatus)."""

from __future__ import annotations

import json
import urllib.error

import pytest

from core.hardware.shelly_rpc import ShellyRpcError, read_input_state


class FakeResponse:
    """Contexte minimal mimant ce que renvoie urlopen()."""

    def __init__(self, body: bytes, status: int = 200):
        self._body = body
        self.status = status

    def read(self):
        return self._body

    def __enter__(self):
        return self

    def __exit__(self, *exc):
        return False


def make_urlopen(body, status=200, captured=None):
    def _urlopen(url, timeout=None):
        if captured is not None:
            captured.append((url, timeout))
        return FakeResponse(body, status)

    return _urlopen


def test_returns_state_true_and_payload():
    state, payload = read_input_state("1.2.3.4", 0, urlopen=make_urlopen(b'{"id":0,"state":true}'))
    assert state is True
    assert payload == {"id": 0, "state": True}


def test_returns_state_false():
    state, _ = read_input_state("1.2.3.4", 0, urlopen=make_urlopen(b'{"id":0,"state":false}'))
    assert state is False


def test_builds_expected_url_and_passes_timeout():
    captured = []
    read_input_state(
        "1.2.3.4", 2, timeout_s=1.5, urlopen=make_urlopen(b'{"state":true}', captured=captured)
    )
    assert captured == [("http://1.2.3.4/rpc/Input.GetStatus?id=2", 1.5)]


def test_raises_on_network_error():
    def _urlopen(url, timeout=None):
        raise urllib.error.URLError("boom")

    with pytest.raises(ShellyRpcError):
        read_input_state("1.2.3.4", 0, urlopen=_urlopen)


def test_raises_on_http_error_status():
    with pytest.raises(ShellyRpcError):
        read_input_state("1.2.3.4", 0, urlopen=make_urlopen(b"{}", status=500))


def test_raises_on_invalid_json():
    with pytest.raises(ShellyRpcError):
        read_input_state("1.2.3.4", 0, urlopen=make_urlopen(b"pas du json"))


def test_raises_on_payload_without_state():
    with pytest.raises(ShellyRpcError):
        read_input_state("1.2.3.4", 0, urlopen=make_urlopen(json.dumps({"id": 0}).encode()))
