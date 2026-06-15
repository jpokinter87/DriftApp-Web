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


def _call(url: str, timeout: float):
    """GET transparent : imprime l'URL envoyée puis la réponse. None si échec réseau."""
    print(f"  -> GET {url}")
    try:
        with urllib.request.urlopen(url, timeout=timeout) as resp:
            body = resp.read().decode("utf-8", "replace").strip()
        print(f"  <- {body}")
        return body
    except Exception as exc:  # noqa: BLE001 — diagnostic : on veut voir toute erreur réseau
        print(f"  !! {exc}")
        return None


def read_switch(host: str, input_id: int, timeout: float):
    """Lit Input.GetStatus → booléen state, ou None si la lecture échoue."""
    body = _call(input_url(host, input_id), timeout)
    if body is None:
        return None
    try:
        return bool(json.loads(body)["state"])
    except (ValueError, KeyError, TypeError) as exc:
        print(f"  !! réponse illisible : {exc}")
        return None


def cycle(direction: str, conv: dict, timeout: float, settle: float, poll: float) -> None:
    """Séquence d'ouverture (direction='up') ou de fermeture ('down') — cinématique synoptique V3."""
    switch_id = HAUT_ID if direction == "up" else BAS_ID
    nom = "HAUT" if direction == "up" else "BAS"

    print("1. SHELLY-1-24/ON : alimentation du module cimier")
    _call(relay_url(HOSTS["power"], "on"), timeout)

    print(f"2. Attente {settle}s (appairage Wifi des Shelly)")
    time.sleep(settle)

    print("3. Moteur au repos (relais MOT à l'arrêt)")
    _call(relay_url(HOSTS["motor"], motor_turn("stop", conv)), timeout)

    print(f"4. Sens {direction.upper()}")
    _call(relay_url(HOSTS["dir"], dir_turn(direction, conv)), timeout)

    print(f"5. Pré-check butée {nom}")
    state = read_switch(HOSTS["uni"], switch_id, timeout)
    if state is not None and butee_atteinte(state, conv):
        print(f"   butée {nom} déjà atteinte → rien à faire")
        print("9. SHELLY-1-24/OFF : coupure alimentation")
        _call(relay_url(HOSTS["power"], "off"), timeout)
        return

    print("6. SHELLY-1-MOT : démarrage du moteur")
    _call(relay_url(HOSTS["motor"], motor_turn("run", conv)), timeout)

    print(f"7. Surveillance butée {nom} toutes les {poll}s")
    while True:
        state = read_switch(HOSTS["uni"], switch_id, timeout)
        if state is not None and butee_atteinte(state, conv):
            print(f"   butée {nom} atteinte")
            break
        time.sleep(poll)

    print("8. SHELLY-1-MOT : arrêt du moteur")
    _call(relay_url(HOSTS["motor"], motor_turn("stop", conv)), timeout)

    print("9. SHELLY-1-24/OFF : coupure alimentation")
    _call(relay_url(HOSTS["power"], "off"), timeout)
