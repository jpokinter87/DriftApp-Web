#!/usr/bin/env python3
"""Pilotage manuel du cimier V3 — séquencement nu des commandes Shelly.

Encode LA VÉRITÉ du synoptique : docs/synoptique electronique cimier V3.pdf.
Aucune abstraction héritée (pas de cooldown / drop / IPC / parser config).
Lançable en python3 pur sur le Pi : `python3 scripts/diagnostics/cimier_manual.py read`.

Source (synoptique V3, page « Commandes ») :
  SHELLY-1-24  (.83)  ON  http://192.168.1.83/relay/0?turn=on   alim module cimier
  SHELLY-1-MOT (.85)  moteur TOURNE  turn=off  / ARRÊT turn=on   (LOGIQUE INVERSÉE)
  SHELLY-1-UPDN(.86)  UP turn=on / DN turn=off                   sens via DPDT
  SHELLY-HAUT  (.84)  http://192.168.1.84/rpc/Input.GetStatus?id=1  True=Ouvert / False=fermé
  SHELLY-BAS   (.84)  http://192.168.1.84/rpc/Input.GetStatus?id=0  True=Ouvert / False=fermé
  (butée « fermée » = contact fermé = butée ATTEINTE)
"""

from __future__ import annotations

import argparse
import json
import sys
import time
import urllib.request

HOSTS = {
    "power": "192.168.1.83",  # SHELLY-1-24V  — alim module cimier
    "uni": "192.168.1.84",    # SHELLY Uni+   — lecture butées HAUT/BAS
    "motor": "192.168.1.85",  # SHELLY-1-MOT  — moteur (logique inversée)
    "dir": "192.168.1.86",    # SHELLY-1-UPDN — sens via DPDT
}

HAUT_ID = 1  # SHELLY-HAUT : Input.GetStatus?id=1
BAS_ID = 0   # SHELLY-BAS  : Input.GetStatus?id=0

# Conventions du synoptique — surchargeables par flags CLI au banc.
CONV = {
    "mot_run": "off",          # relais MOT turn=off → moteur TOURNE
    "dir_up": "on",            # relais UPDN turn=on → sens MONTÉE
    "switch_closed": "false",  # input state=false → butée fermée (atteinte)
    "settle_s": 2.0,
    "poll_s": 0.1,
    "timeout_s": 3.0,
}


def relay_url(host: str, turn: str) -> str:
    return f"http://{host}/relay/0?turn={turn}"


def input_url(host: str, input_id: int) -> str:
    return f"http://{host}/rpc/Input.GetStatus?id={input_id}"


def motor_turn(action: str, conv: dict) -> str:
    """action ∈ {run, stop} → valeur turn= (run par défaut = off, inversé)."""
    run = conv["mot_run"]
    stop = "on" if run == "off" else "off"
    return run if action == "run" else stop


def dir_turn(action: str, conv: dict) -> str:
    """action ∈ {up, down} → valeur turn= (up par défaut = on)."""
    up = conv["dir_up"]
    down = "off" if up == "on" else "on"
    return up if action == "up" else down


def butee_atteinte(state: bool, conv: dict) -> bool:
    """True si la butée est atteinte (contact fermé). Par défaut : state=False → atteinte."""
    closed_value = conv["switch_closed"] == "true"
    return state == closed_value
