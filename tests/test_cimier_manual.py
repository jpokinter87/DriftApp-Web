"""Tests de la logique pure de scripts/diagnostics/cimier_manual.py.

Le script encode la vérité du synoptique V3 (docs/synoptique electronique cimier V3.pdf).
Conventions par défaut : moteur tourne quand relais MOT turn=off (logique inversée),
sens UP = relais UPDN turn=on, butée atteinte quand input state=False.
"""

from __future__ import annotations

import importlib.util
import json
from pathlib import Path

import pytest

# Le script vit dans scripts/diagnostics/ (pas un package) → import par chemin.
_SPEC = importlib.util.spec_from_file_location(
    "cimier_manual",
    Path(__file__).resolve().parent.parent / "scripts" / "diagnostics" / "cimier_manual.py",
)
cimier_manual = importlib.util.module_from_spec(_SPEC)
_SPEC.loader.exec_module(cimier_manual)


def default_conv():
    return dict(cimier_manual.CONV)


def test_relay_url():
    assert cimier_manual.relay_url("192.168.1.85", "off") == "http://192.168.1.85/relay/0?turn=off"


def test_input_url():
    assert (
        cimier_manual.input_url("192.168.1.84", 1)
        == "http://192.168.1.84/rpc/Input.GetStatus?id=1"
    )


def test_motor_turn_inverted():
    conv = default_conv()
    # Synoptique : moteur TOURNE quand relais turn=off, ARRÊT quand turn=on.
    assert cimier_manual.motor_turn("run", conv) == "off"
    assert cimier_manual.motor_turn("stop", conv) == "on"


def test_dir_turn():
    conv = default_conv()
    assert cimier_manual.dir_turn("up", conv) == "on"
    assert cimier_manual.dir_turn("down", conv) == "off"


def test_butee_atteinte_default():
    conv = default_conv()
    # state=False → contact fermé → butée atteinte ; state=True → ouverte → non atteinte.
    assert cimier_manual.butee_atteinte(False, conv) is True
    assert cimier_manual.butee_atteinte(True, conv) is False


def test_read_switch_parses_state(monkeypatch):
    # _call renvoie le corps brut du Shelly Uni+ ; read_switch en extrait le booléen state.
    monkeypatch.setattr(cimier_manual, "_call", lambda url, timeout: '{"id":1,"state":true}')
    assert cimier_manual.read_switch(cimier_manual.HOSTS["uni"], 1, 3.0) is True

    monkeypatch.setattr(cimier_manual, "_call", lambda url, timeout: '{"id":0,"state":false}')
    assert cimier_manual.read_switch(cimier_manual.HOSTS["uni"], 0, 3.0) is False


def test_read_switch_returns_none_on_http_failure(monkeypatch):
    monkeypatch.setattr(cimier_manual, "_call", lambda url, timeout: None)
    assert cimier_manual.read_switch(cimier_manual.HOSTS["uni"], 1, 3.0) is None


def test_cycle_stops_on_butee(monkeypatch):
    # La butée HAUT lue est d'abord "ouverte" (True), puis "atteinte" (False) au 2e poll.
    # On capture les URLs envoyées pour vérifier l'arrêt moteur + coupure alim.
    calls = []
    switch_states = iter([True, True, False])  # pré-check ouverte, poll1 ouverte, poll2 atteinte

    def fake_call(url, timeout):
        calls.append(url)
        if "Input.GetStatus" in url:
            state = next(switch_states)
            return json.dumps({"state": state})
        return "OK"

    monkeypatch.setattr(cimier_manual, "_call", fake_call)
    monkeypatch.setattr(cimier_manual.time, "sleep", lambda s: None)

    cimier_manual.cycle("up", default_conv(), timeout=3.0, settle=0.0, poll=0.0)

    # Moteur démarré (turn=off) puis arrêté (turn=on) ; alim coupée en fin.
    assert cimier_manual.relay_url(cimier_manual.HOSTS["motor"], "off") in calls  # run
    assert cimier_manual.relay_url(cimier_manual.HOSTS["motor"], "on") in calls   # stop
    assert calls[-1] == cimier_manual.relay_url(cimier_manual.HOSTS["power"], "off")


def test_cycle_skips_when_already_at_butee(monkeypatch):
    # Pré-check : butée déjà atteinte (False) → pas de démarrage moteur, alim coupée direct.
    calls = []

    def fake_call(url, timeout):
        calls.append(url)
        if "Input.GetStatus" in url:
            return json.dumps({"state": False})  # déjà fermée = atteinte
        return "OK"

    monkeypatch.setattr(cimier_manual, "_call", fake_call)
    monkeypatch.setattr(cimier_manual.time, "sleep", lambda s: None)

    cimier_manual.cycle("up", default_conv(), timeout=3.0, settle=0.0, poll=0.0)

    # Le moteur n'a jamais démarré (run = turn=off jamais envoyé).
    assert cimier_manual.relay_url(cimier_manual.HOSTS["motor"], "off") not in calls
    assert calls[-1] == cimier_manual.relay_url(cimier_manual.HOSTS["power"], "off")
