"""
Firmware principal Pico W cimier — pilotage WiFi REST.

Tourne sur Raspberry Pi Pico W (RP2040 + WiFi).

Architecture :
  - Mini serveur HTTP socket pur (aucune dependance externe a installer)
  - Boucle principale : tick controller (~50 Hz) + accept HTTP non-bloquant + WDT
  - Mode safe-boot : delai 3 sec au demarrage avec banner. Permet Ctrl-C dans
    mpremote pour reprendre la main si le firmware bloque.
  - 2 fins de course NC sur GPIO 14/15 avec pull-up interne
  - Watchdog hardware RP2040 200 ms = filet ultime si firmware fige

Endpoints REST (port 80, JSON) :
  GET  /status   -> {state, open_switch, closed_switch, ...}
  POST /open     -> demarre cycle ouverture
  POST /close    -> demarre cycle fermeture
  POST /stop     -> stop immediat
  GET  /info     -> {firmware_version, wifi_rssi, free_memory, ...}
  POST /config   -> {invert_direction: bool}

Pre-requis Pico W :
  - MicroPython 1.20+
  - Aucune lib externe (pas de microdot, pas de mip install)
  - Fichier secrets.py local avec WIFI_SSID + WIFI_PASSWORD
"""

import gc
import json
import socket
import sys
import time
import network

from machine import Pin, WDT

from cimier_controller import CimierController
from step_generator import SoftwareStepGenerator


# ------------------------------------------------------------------
# Configuration GPIO (cf. README.md branchements)
# ------------------------------------------------------------------

PIN_STEP = 2          # GP2 -> PUL+ DM560T
PIN_DIR = 3           # GP3 -> DIR+ DM560T
PIN_OPEN_SWITCH = 14  # GP14 -> fin de course NC OUVERT
PIN_CLOSED_SWITCH = 15  # GP15 -> fin de course NC FERME

# Cadence tick : 3200 steps / 60 s = ~53 Hz -> ~19 ms entre pas
STEP_PERIOD_MS = 19

# Watchdog hardware ; on feed a chaque iteration de boucle
WDT_TIMEOUT_MS = 200

HTTP_PORT = 80

# Fenetre safe-boot : permet a l'operateur d'interrompre via Ctrl-C
SAFE_BOOT_DELAY_S = 3


# ------------------------------------------------------------------
# Time provider compatible MicroPython
# ------------------------------------------------------------------

def now_seconds():
    """Secondes depuis le boot (float). Wrappe ticks_ms (overflow ~49 jours).

    Suffit pour timeouts cycle (60 s) et marker last_action_ts.
    """
    return time.ticks_ms() / 1000.0


# ------------------------------------------------------------------
# Hardware adapter — implementation reelle GPIO
# ------------------------------------------------------------------

class PicoHardwareAdapter:
    """Bridge entre CimierController et le hardware Pico W reel."""

    def __init__(self, step_gen, open_switch_pin, closed_switch_pin):
        self._sg = step_gen
        self._sw_open = Pin(open_switch_pin, Pin.IN, Pin.PULL_UP)
        self._sw_closed = Pin(closed_switch_pin, Pin.IN, Pin.PULL_UP)

    def read_open_switch(self):
        # NC + pull-up : repos = 0, butee ou cable coupe = 1
        return self._sw_open.value() == 1

    def read_closed_switch(self):
        return self._sw_closed.value() == 1

    def set_direction(self, direction):
        self._sg.set_direction(direction)

    def pulse_step(self):
        self._sg.pulse_step()


# ------------------------------------------------------------------
# WiFi
# ------------------------------------------------------------------

def connect_wifi(ssid, password, timeout_s=30):
    wlan = network.WLAN(network.STA_IF)
    wlan.active(True)
    if wlan.isconnected():
        return wlan
    wlan.connect(ssid, password)
    deadline_ms = time.ticks_add(time.ticks_ms(), timeout_s * 1000)
    while not wlan.isconnected():
        if time.ticks_diff(deadline_ms, time.ticks_ms()) <= 0:
            raise RuntimeError("WiFi connection timeout")
        time.sleep_ms(200)
    return wlan


# ------------------------------------------------------------------
# Mini serveur HTTP socket pur
# ------------------------------------------------------------------

def parse_http_request(data):
    """Parser HTTP minimaliste. Retourne (method, path, body_dict_or_None)."""
    try:
        text = data.decode("utf-8")
    except UnicodeError:
        return None, None, None
    head, _, body_str = text.partition("\r\n\r\n")
    lines = head.split("\r\n")
    if not lines:
        return None, None, None
    parts = lines[0].split(" ")
    if len(parts) < 2:
        return None, None, None
    method = parts[0]
    path = parts[1]
    body = None
    if body_str.strip():
        try:
            body = json.loads(body_str)
        except (ValueError, TypeError):
            body = None
    return method, path, body


def build_response(status_code, body_dict):
    body = json.dumps(body_dict).encode("utf-8")
    status_text = "OK" if status_code == 200 else "Error"
    headers = (
        "HTTP/1.1 " + str(status_code) + " " + status_text + "\r\n"
        "Content-Type: application/json\r\n"
        "Content-Length: " + str(len(body)) + "\r\n"
        "Connection: close\r\n\r\n"
    ).encode("utf-8")
    return headers + body


def route_request(controller, wlan, method, path, body):
    """Routage des endpoints. Retourne (status_code, response_dict)."""
    if method == "GET" and path == "/status":
        return 200, controller.to_status_dict()
    if method == "POST" and path == "/open":
        controller.start_open()
        return 200, controller.to_status_dict()
    if method == "POST" and path == "/close":
        controller.start_close()
        return 200, controller.to_status_dict()
    if method == "POST" and path == "/stop":
        controller.stop()
        return 200, controller.to_status_dict()
    if method == "GET" and path == "/info":
        info = controller.to_info_dict()
        info["wifi_rssi"] = wlan.status("rssi") if wlan else None
        info["wifi_ip"] = wlan.ifconfig()[0] if wlan else None
        info["free_memory"] = gc.mem_free()
        return 200, info
    if method == "POST" and path == "/config":
        if isinstance(body, dict) and "invert_direction" in body:
            controller.set_invert_direction(body["invert_direction"])
        return 200, controller.to_info_dict()
    return 404, {"error": "not_found", "method": method, "path": path}


def serve_one_request(server_sock, controller, wlan):
    """Tente d'accepter une connexion. Non-bloquant : ne fait rien si pas de client."""
    try:
        client, _addr = server_sock.accept()
    except OSError:
        return  # pas de client en attente, continue la boucle
    try:
        client.settimeout(2)
        data = client.recv(2048)
        if data:
            method, path, body = parse_http_request(data)
            if method:
                status, payload = route_request(controller, wlan, method, path, body)
            else:
                status, payload = 400, {"error": "bad_request"}
            client.send(build_response(status, payload))
    except OSError as exc:
        print("HTTP error:", exc)
    finally:
        try:
            client.close()
        except OSError:
            pass


def run_server(controller, wlan, wdt, port):
    sock = socket.socket()
    sock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
    sock.bind(("0.0.0.0", port))
    sock.listen(5)
    sock.settimeout(0)  # accept non-bloquant
    print("HTTP server listening on port", port)

    last_step = time.ticks_ms()
    while True:
        # 1. Tick controller a la cadence STEP_PERIOD_MS
        if time.ticks_diff(time.ticks_ms(), last_step) >= STEP_PERIOD_MS:
            controller.tick()
            last_step = time.ticks_ms()

        # 2. Watchdog : tant que la boucle tourne, on est vivant
        wdt.feed()

        # 3. Servir 1 requete HTTP si dispo
        serve_one_request(sock, controller, wlan)

        # 4. Yield un poil pour eviter de griller le CPU
        time.sleep_ms(2)


# ------------------------------------------------------------------
# Safe boot — banner + delai d'interruption
# ------------------------------------------------------------------

def safe_boot_window():
    """Banner + delai SAFE_BOOT_DELAY_S sec.

    Pendant cette fenetre, l'operateur peut interrompre via Ctrl-C dans mpremote
    pour acceder au REPL et debugger sans que la boucle principale se lance.
    """
    print("=" * 60)
    print("DriftApp Cimier Firmware")
    print("=" * 60)
    print("Boot dans", SAFE_BOOT_DELAY_S, "secondes...")
    print("(Ctrl-C dans mpremote pour interrompre et acceder au REPL)")
    for remaining in range(SAFE_BOOT_DELAY_S, 0, -1):
        print(" ", remaining, "s")
        time.sleep(1)
    print("Boot demarre.")
    print()


# ------------------------------------------------------------------
# Main
# ------------------------------------------------------------------

def main():
    safe_boot_window()

    # 1. Imports retardes : on distingue "module absent" de "noms absents"
    #    pour donner un message d'erreur clair (c'etait pas le cas avant).
    try:
        import secrets as _secrets
    except ImportError:
        print("ERREUR: fichier secrets.py introuvable sur le Pico W.")
        print("Cree-le avec WIFI_SSID + WIFI_PASSWORD puis : mpremote cp secrets.py :")
        return
    try:
        WIFI_SSID = _secrets.WIFI_SSID
        WIFI_PASSWORD = _secrets.WIFI_PASSWORD
    except AttributeError as exc:
        print("ERREUR: secrets.py present mais variable manquante:", exc)
        print("Le fichier doit contenir EXACTEMENT :")
        print('  WIFI_SSID = "TonReseauWiFi"')
        print('  WIFI_PASSWORD = "MotDePasse"')
        return

    # 2. Hardware (le WDT est arme plus tard, apres WiFi : la connexion peut
    #    prendre plusieurs secondes et un WDT 200 ms reset le Pico avant la fin)
    step_gen = SoftwareStepGenerator(PIN_STEP, PIN_DIR)
    hw = PicoHardwareAdapter(step_gen, PIN_OPEN_SWITCH, PIN_CLOSED_SWITCH)
    controller = CimierController(hw, now_seconds)
    print("Hardware initialise. Etat:", controller.state)

    # 3. WiFi (avant WDT : connexion peut prendre 2-15 s)
    print("Connexion WiFi a", WIFI_SSID, "...")
    try:
        wlan = connect_wifi(WIFI_SSID, WIFI_PASSWORD)
    except RuntimeError as exc:
        print("ERREUR WiFi:", exc)
        print("Verifie SSID/mot de passe + reseau en 2.4 GHz (le Pico W ne fait pas le 5 GHz).")
        return

    ip = wlan.ifconfig()[0]
    print()
    print(">>> WiFi connected: " + ip + " <<<")
    print(">>> Test rapide : curl http://" + ip + "/status <<<")
    print()

    # 4. WDT arme juste avant la boucle principale (run_server feed a chaque tick)
    wdt = WDT(timeout=WDT_TIMEOUT_MS)

    # 5. Boucle principale
    run_server(controller, wlan, wdt, HTTP_PORT)


# Demarrage automatique avec garde-fou top-level
try:
    main()
except KeyboardInterrupt:
    print()
    print("Boot interrompu (Ctrl-C). Acces REPL disponible.")
except Exception as exc:
    print("ERREUR FATALE:", exc)
    sys.print_exception(exc)
    print("Acces REPL disponible apres reset.")
