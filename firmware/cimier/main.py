"""
Firmware principal Pico W cimier — serveur capteurs WiFi REST.

Tourne sur Raspberry Pi Pico W (RP2040 + WiFi).

Depuis le pivot Shelly (v6.x), le Pico W est un pur serveur de capteurs :
il expose l'etat des 2 fins de course via HTTP. Le moteur cimier est
desormais pilote par des relais Shelly (commandes 220V) depuis le Pi
principal — le Pico W ne genere plus aucune impulsion STEP/DIR.

Architecture :
  - Mini serveur HTTP socket pur (aucune dependance externe a installer)
  - Boucle principale : accept HTTP non-bloquant + WDT + heartbeat
  - Mode safe-boot : delai 3 sec au demarrage avec banner. Permet Ctrl-C dans
    mpremote pour reprendre la main si le firmware bloque.
  - 2 fins de course NC sur GPIO 14/15 avec pull-up interne
  - Watchdog hardware RP2040 8000 ms = filet ultime si firmware fige

Endpoints REST (port 80, JSON) :
  GET  /status   -> {state, open_switch, closed_switch, error_message}
  GET  /info     -> {firmware_version, protocol_version, role, wifi_rssi, ...}

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


# ------------------------------------------------------------------
# Configuration GPIO (cf. README.md branchements)
# ------------------------------------------------------------------

PIN_OPEN_SWITCH = 14  # GP14 -> fin de course NC OUVERT
PIN_CLOSED_SWITCH = 15  # GP15 -> fin de course NC FERME

# Watchdog hardware ; on feed a chaque iteration de boucle.
# 8000 ms = max supporte par RP2040 (cf. docs.micropython.org/en/latest/library/machine.WDT.html).
# 200 ms initial etait toxique : collision avec le PM CYW43 (timer 200 ms) qui
# bloquait recv() pendant le reveil radio -> reset hardware -> RST cote client.
# Cf. MicroPython issue #17228 (RP2040 lockup if WDT timeout during lightsleep).
WDT_TIMEOUT_MS = 8000

HTTP_PORT = 80

# Fenetre safe-boot : permet a l'operateur d'interrompre via Ctrl-C
SAFE_BOOT_DELAY_S = 3


# ------------------------------------------------------------------
# Hardware adapter — implementation reelle GPIO
# ------------------------------------------------------------------

class PicoHardwareAdapter:
    """Bridge entre CimierController et le hardware Pico W reel."""

    def __init__(self, open_switch_pin, closed_switch_pin):
        self._sw_open = Pin(open_switch_pin, Pin.IN, Pin.PULL_UP)
        self._sw_closed = Pin(closed_switch_pin, Pin.IN, Pin.PULL_UP)

    def read_open_switch(self):
        # NC + pull-up : repos = 0, butee ou cable coupe = 1
        return self._sw_open.value() == 1

    def read_closed_switch(self):
        return self._sw_closed.value() == 1


# ------------------------------------------------------------------
# WiFi
# ------------------------------------------------------------------

def connect_wifi(ssid, password, timeout_s=30):
    wlan = network.WLAN(network.STA_IF)
    wlan.active(True)
    # Desactive le power management CYW43 (defaut 0xA11142 = sleep apres idle,
    # reveil ~200 ms qui bloque recv() et cause des RST cote client). 0xA11140
    # = PM_NONE, radio toujours active. Cf. issue pico-sdk #2153 + issue
    # MicroPython #9455 (Pico W network inaccessible after idle).
    wlan.config(pm=0xa11140)
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
    if method == "GET" and path == "/info":
        info = controller.to_info_dict()
        info["wifi_rssi"] = wlan.status("rssi") if wlan else None
        info["wifi_ip"] = wlan.ifconfig()[0] if wlan else None
        info["free_memory"] = gc.mem_free()
        return 200, info
    return 404, {"error": "not_found", "method": method, "path": path}


def serve_one_request(server_sock, controller, wlan):
    """Sert une requete HTTP avec accept court bloquant.

    server_sock doit avoir un settimeout(0.05) ou similaire.
    OSError sur accept = timeout normal (pas de client), pas un bug.

    Returns:
        bool: True si une connexion a ete acceptee, False sinon.
    """
    try:
        client, _addr = server_sock.accept()
    except OSError:
        return False  # timeout ou EAGAIN = pas de client en attente, normal
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
            print("[req] ->", status, method, path)
    except OSError as exc:
        print("HTTP error:", exc)
    finally:
        try:
            client.close()
        except OSError:
            pass
    return True


def run_server(controller, wlan, wdt, port):
    sock = socket.socket()
    sock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
    sock.bind(("0.0.0.0", port))
    sock.listen(5)
    # Timeout court : accept() bloque jusqu'a 50 ms puis OSError ETIMEDOUT.
    # Sur lwIP MicroPython Pico W, c'est l'approche fiable (select.poll() ne
    # notifie pas POLLIN sur sockets serveur). 50 ms < 200 ms WDT donc safe.
    sock.settimeout(0.05)
    print("HTTP server listening on port", port)

    last_heartbeat = time.ticks_ms()
    request_count = 0
    while True:
        # 1. Watchdog : tant que la boucle tourne, on est vivant
        wdt.feed()

        # 2. Servir 1 requete HTTP (accept court bloquant 50 ms max)
        if serve_one_request(sock, controller, wlan):
            request_count += 1

        # 3. Heartbeat toutes les 10 s : prouve que la boucle tourne
        if time.ticks_diff(time.ticks_ms(), last_heartbeat) >= 10000:
            print("[hb] state=" + controller.state +
                  " req_total=" + str(request_count) +
                  " mem=" + str(gc.mem_free()))
            last_heartbeat = time.ticks_ms()


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
    hw = PicoHardwareAdapter(PIN_OPEN_SWITCH, PIN_CLOSED_SWITCH)
    controller = CimierController(hw)
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
