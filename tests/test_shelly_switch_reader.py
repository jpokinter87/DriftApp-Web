"""Tests ShellySwitchReader — lecture des butées cimier via Shelly Uni+ (RPC)."""

from __future__ import annotations

import json
import urllib.error

import pytest

from core.hardware.shelly_switch_reader import (
    NoopSwitchReader,
    ShellySwitchReader,
    SwitchReaderError,
    SwitchState,
)


class _FakeResp:
    """Réponse urlopen factice (context manager)."""

    def __init__(self, payload, status=200):
        self.status = status
        self._body = json.dumps(payload).encode("utf-8") if isinstance(payload, dict) else payload

    def __enter__(self):
        return self

    def __exit__(self, *a):
        return False

    def read(self):
        return self._body


def _urlopen_map(mapping):
    """Renvoie un urlopen factice routant l'URL → _FakeResp selon `id=` présent."""

    def _fake(url, timeout=None):
        for key, resp in mapping.items():
            if "id=" + str(key) in url:
                if isinstance(resp, Exception):
                    raise resp
                return resp
        raise AssertionError("URL inattendue: " + url)

    return _fake


def test_invert_default_butee_atteinte_quand_input_false():
    # HAUT (id=1) state=False → butée haute atteinte → open_switch=True
    # BAS  (id=0) state=True  → pas en butée basse  → closed_switch=False
    reader = ShellySwitchReader(
        host="1.2.3.4",
        urlopen=_urlopen_map(
            {1: _FakeResp({"id": 1, "state": False}), 0: _FakeResp({"id": 0, "state": True})}
        ),
    )
    state = reader.read()
    assert isinstance(state, SwitchState)
    assert state.open_switch is True
    assert state.closed_switch is False
    assert state.both_switches is False


def test_both_switches_quand_les_deux_en_butee():
    reader = ShellySwitchReader(
        host="1.2.3.4",
        urlopen=_urlopen_map(
            {1: _FakeResp({"id": 1, "state": False}), 0: _FakeResp({"id": 0, "state": False})}
        ),
    )
    state = reader.read()
    assert state.open_switch is True
    assert state.closed_switch is True
    assert state.both_switches is True


def test_invert_false_passe_input_brut():
    reader = ShellySwitchReader(
        host="1.2.3.4",
        invert=False,
        urlopen=_urlopen_map(
            {1: _FakeResp({"id": 1, "state": True}), 0: _FakeResp({"id": 0, "state": False})}
        ),
    )
    state = reader.read()
    assert state.open_switch is True
    assert state.closed_switch is False


def test_mapping_ids_configurable():
    # open_input_id=3, closed_input_id=7
    reader = ShellySwitchReader(
        host="1.2.3.4",
        open_input_id=3,
        closed_input_id=7,
        urlopen=_urlopen_map(
            {3: _FakeResp({"id": 3, "state": False}), 7: _FakeResp({"id": 7, "state": True})}
        ),
    )
    state = reader.read()
    assert state.open_switch is True
    assert state.closed_switch is False


def test_url_rpc_construite():
    seen = []

    def _capture(url, timeout=None):
        seen.append(url)
        return _FakeResp({"id": 0, "state": True})

    ShellySwitchReader(host="9.9.9.9", urlopen=_capture).read()
    assert all(u.startswith("http://9.9.9.9/rpc/Input.GetStatus?id=") for u in seen)
    # défauts open_input_id=1 (HAUT) et closed_input_id=0 (BAS) → les 2 URLs construites
    assert any(u.endswith("?id=1") for u in seen)
    assert any(u.endswith("?id=0") for u in seen)


def test_urlerror_leve_switchreadererror():
    reader = ShellySwitchReader(
        host="1.2.3.4",
        urlopen=_urlopen_map({1: urllib.error.URLError("down"), 0: _FakeResp({"state": True})}),
    )
    with pytest.raises(SwitchReaderError):
        reader.read()


def test_http_non_200_leve_switchreadererror():
    reader = ShellySwitchReader(
        host="1.2.3.4",
        urlopen=_urlopen_map(
            {1: _FakeResp({"state": False}, status=500), 0: _FakeResp({"state": True})}
        ),
    )
    with pytest.raises(SwitchReaderError):
        reader.read()


def test_payload_sans_state_leve_switchreadererror():
    reader = ShellySwitchReader(
        host="1.2.3.4",
        urlopen=_urlopen_map({1: _FakeResp({"id": 1}), 0: _FakeResp({"state": True})}),
    )
    with pytest.raises(SwitchReaderError):
        reader.read()


def test_json_invalide_leve_switchreadererror():
    reader = ShellySwitchReader(
        host="1.2.3.4",
        urlopen=_urlopen_map({1: _FakeResp(b"pas du json"), 0: _FakeResp({"state": True})}),
    )
    with pytest.raises(SwitchReaderError):
        reader.read()


def test_api_non_rpc_rejetee():
    with pytest.raises(ValueError):
        ShellySwitchReader(host="1.2.3.4", api="legacy")


def test_noop_reader_renvoie_etat_configurable():
    r = NoopSwitchReader(open_switch=True, closed_switch=False)
    state = r.read()
    assert state.open_switch is True
    assert state.closed_switch is False
    assert state.both_switches is False
    r.closed_switch = True
    assert r.read().both_switches is True
