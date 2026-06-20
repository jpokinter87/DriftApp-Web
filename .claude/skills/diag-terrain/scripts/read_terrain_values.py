#!/usr/bin/env python3
"""Lit les valeurs terrain courantes depuis data/config.json (skill diag-terrain).

Évite de coder en dur IPs/ports/GPIO dans les protocoles générés
(feedback_no_hardcoded_ips) : le skill injecte ces valeurs lues à l'exécution.
Toute valeur vide ("") ou absente est signalée « à confirmer » pour que le
protocole transmis à Serge le demande explicitement.

Usage : python3 read_terrain_values.py [--config <chemin/config.json>]
Sortie : résumé texte sur stdout, exit 0.
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

PLACEHOLDER = "<non configuré — à confirmer avec Serge>"


def find_config(start: Path) -> Path | None:
    for d in [start, *start.parents]:
        cand = d / "data" / "config.json"
        if cand.exists():
            return cand
    return None


def show(label: str, value: object) -> None:
    # Seuls None et "" = non configuré. 0 / False sont des valeurs terrain
    # valides (switch_id=0, enabled=false, motor_on_relay_state=false…).
    if value is None or value == "":
        print(f"  {label}: {PLACEHOLDER}")
    else:
        print(f"  {label}: {value}")


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--config", default=None)
    args = ap.parse_args()

    cfg_path = Path(args.config) if args.config else find_config(Path.cwd())
    if not cfg_path or not cfg_path.exists():
        print("ERREUR : data/config.json introuvable. Lancer depuis la racine du dépôt,")
        print("ou passer --config <chemin>.")
        return 0  # ne pas bloquer le skill : il basculera sur des placeholders

    cfg = json.loads(cfg_path.read_text())
    print(f"=== VALEURS TERRAIN (source : {cfg_path}) ===")
    print(f"  simulation: {cfg.get('simulation')}")
    print()

    print("--- Moteur coupole ---")
    md = cfg.get("motor_driver", {})
    show("motor_driver.type", md.get("type"))
    show("motor_driver.serial", md.get("serial"))
    moteur = cfg.get("moteur", {})
    show("moteur.gpio_pins", moteur.get("gpio_pins"))
    show("moteur.microsteps", moteur.get("microsteps"))
    show("moteur.gear_ratio", moteur.get("gear_ratio"))
    print()

    print("--- Encodeur ---")
    enc = cfg.get("encodeur", {})
    for k, v in (enc.items() if isinstance(enc, dict) else []):
        show(f"encodeur.{k}", v)
    if not enc:
        print(f"  encodeur: {PLACEHOLDER}")
    print()

    print("--- Cimier ---")
    cim = cfg.get("cimier", {})
    show("cimier.enabled", cim.get("enabled"))
    show("cimier.host (Pico W)", cim.get("host"))
    show("cimier.port", cim.get("port"))
    ps = cim.get("power_switch", {})
    show("power_switch.type", ps.get("type"))
    show("power_switch.host (Shelly alim)", ps.get("host"))
    show("power_switch.switch_id", ps.get("switch_id"))
    ms = cim.get("motor_shelly", {})
    if isinstance(ms, dict) and ms:
        for k, v in ms.items():
            show(f"motor_shelly.{k}", v)
    auto = cim.get("automation", {})
    show("automation.mode", auto.get("mode") if isinstance(auto, dict) else auto)
    print()

    print("--- Site ---")
    site = cfg.get("site", {})
    show("site.nom", site.get("nom"))
    show("site.latitude", site.get("latitude"))
    show("site.longitude", site.get("longitude"))
    print()

    print("=== FIN ===")
    return 0


if __name__ == "__main__":
    sys.exit(main())
