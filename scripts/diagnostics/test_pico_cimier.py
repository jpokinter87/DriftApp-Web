#!/usr/bin/env python3
"""
Outil interactif de test du firmware Pico W cimier.

Permet de tester manuellement les endpoints REST du Pico W avant que
Phase 1 (cimier_service Django) soit livrée. Utile pour la validation
de bringup terrain : direction moteur, fins de course, cycle ouverture/
fermeture.

Usage:
    uv run python scripts/diagnostics/test_pico_cimier.py 192.168.1.42
    uv run python scripts/diagnostics/test_pico_cimier.py --host 192.168.1.42

Astuce hardware si pas de switches branches :
    Tirer GP14 et GP15 a GND avec 2 cavaliers (simule "switches NC au repos").
    Sans cavaliers, les pull-up internes mettent les 2 entrees a 1 -> le
    controller croit que les deux butees sont declenchees -> moteur bloque.

Pendant un cycle, debrancher temporairement un cavalier simule l'arrivee en
butee (open ou closed selon le cavalier debranche) -> arret propre du moteur.
"""

import argparse
import json
import sys
import urllib.error
import urllib.request

DEFAULT_TIMEOUT_S = 5


def make_request(host, method, path, body=None):
    """Effectue une requete HTTP vers le Pico W et retourne le dict JSON.

    Args:
        host: IP ou nom DNS du Pico W (ex. "192.168.1.42")
        method: "GET" ou "POST"
        path: chemin de l'endpoint (ex. "/status", "/open")
        body: dict serialise en JSON pour les POST avec body

    Returns:
        dict: reponse JSON parsee, ou None en cas d'erreur (deja affichee).
    """
    url = f"http://{host}{path}"
    data = None
    headers = {"Accept": "application/json"}
    if body is not None:
        data = json.dumps(body).encode("utf-8")
        headers["Content-Type"] = "application/json"

    req = urllib.request.Request(url, data=data, method=method, headers=headers)
    try:
        with urllib.request.urlopen(req, timeout=DEFAULT_TIMEOUT_S) as resp:
            payload = resp.read().decode("utf-8")
        return json.loads(payload)
    except urllib.error.HTTPError as e:
        print(f"  HTTP {e.code} sur {method} {path}: {e.reason}")
    except urllib.error.URLError as e:
        print(f"  Erreur reseau sur {method} {path}: {e.reason}")
    except json.JSONDecodeError as e:
        print(f"  Reponse non-JSON sur {method} {path}: {e}")
    except TimeoutError:
        print(f"  Timeout {DEFAULT_TIMEOUT_S}s sur {method} {path}")
    return None


def print_response(label, data):
    """Affiche un dict JSON formate avec un label."""
    if data is None:
        print(f"  [{label}] echec — pas de reponse")
        return
    print(f"  [{label}]")
    for key in sorted(data.keys()):
        print(f"    {key}: {data[key]}")


def cmd_status(host):
    print_response("status", make_request(host, "GET", "/status"))


def cmd_open(host):
    print("  -> Demande d'ouverture (le moteur demarre)")
    print_response("open", make_request(host, "POST", "/open"))


def cmd_close(host):
    print("  -> Demande de fermeture (le moteur demarre dans l'autre sens)")
    print_response("close", make_request(host, "POST", "/close"))


def cmd_stop(host):
    print("  -> Stop d'urgence")
    print_response("stop", make_request(host, "POST", "/stop"))


def cmd_info(host):
    print_response("info", make_request(host, "GET", "/info"))


def cmd_toggle_invert(host):
    info = make_request(host, "GET", "/info")
    if info is None:
        return
    current = info.get("invert_direction", False)
    new_value = not current
    print(f"  -> Bascule invert_direction : {current} -> {new_value}")
    print_response(
        "config",
        make_request(host, "POST", "/config", {"invert_direction": new_value}),
    )


COMMANDS = [
    ("status", "Lire l'etat actuel du cimier", cmd_status),
    ("open", "Demarrer cycle ouverture", cmd_open),
    ("close", "Demarrer cycle fermeture", cmd_close),
    ("stop", "Stop d'urgence", cmd_stop),
    ("info", "Metadonnees firmware (version, WiFi, memoire)", cmd_info),
    ("invert", "Inverser le sens moteur (toggle)", cmd_toggle_invert),
]


def print_menu():
    print()
    print("Commandes :")
    for i, (name, desc, _) in enumerate(COMMANDS, start=1):
        print(f"  {i}. {name:<8} — {desc}")
    print("  q. quitter")


def interactive_loop(host):
    print(f"Cible : http://{host}")
    print("Astuce : sans switches branches, mettre 2 cavaliers GP14<->GND et GP15<->GND.")

    while True:
        print_menu()
        try:
            choice = input("\n> ").strip().lower()
        except (EOFError, KeyboardInterrupt):
            print()
            return

        if choice in ("q", "quit", "exit"):
            return

        # Accepter un numero (1, 2, ...) ou un nom (status, open, ...)
        cmd_func = None
        if choice.isdigit():
            idx = int(choice)
            if 1 <= idx <= len(COMMANDS):
                cmd_func = COMMANDS[idx - 1][2]
        else:
            for name, _, func in COMMANDS:
                if choice == name:
                    cmd_func = func
                    break

        if cmd_func is None:
            print("  ?? Commande inconnue. Tape un numero ou un nom de commande.")
            continue

        cmd_func(host)


def main():
    parser = argparse.ArgumentParser(
        description="Outil de test interactif du firmware Pico W cimier.",
    )
    parser.add_argument(
        "host",
        nargs="?",
        help="IP ou DNS du Pico W (ex. 192.168.1.42). Demande interactive si absent.",
    )
    parser.add_argument(
        "--host",
        dest="host_opt",
        help="Idem en option longue.",
    )
    args = parser.parse_args()

    host = args.host or args.host_opt
    if not host:
        try:
            host = input("IP du Pico W : ").strip()
        except (EOFError, KeyboardInterrupt):
            print()
            return 1
    if not host:
        print("Aucune IP fournie, abandon.")
        return 1

    interactive_loop(host)
    return 0


if __name__ == "__main__":
    sys.exit(main())
