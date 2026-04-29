"""
Firmware principal Pico W cimier — pilotage WiFi REST.

Tourne sur un Raspberry Pi Pico W (RP2040 + WiFi).

Architecture :
  - WiFi (mode STA) connecte au reseau local, IP fixe via DHCP statique
  - Mini-serveur HTTP via Microdot (asyncio)
  - CimierController (logique metier, module partage testable)
  - SoftwareStepGenerator (50 Hz suffit pour cycle 60 s)
  - 2 fins de course NC sur GPIO 14/15 avec pull-up interne
  - Watchdog hardware RP2040 200 ms = filet ultime

Endpoints REST (port 80) :
  GET  /status   -> {state, open_switch, closed_switch, ...}
  POST /open     -> demarre cycle ouverture
  POST /close    -> demarre cycle fermeture
  POST /stop     -> stop immediat
  GET  /info     -> {firmware_version, wifi_rssi, free_memory, ...}
  POST /config   -> {invert_direction: bool}

Pre-requis :
  - MicroPython 1.20+ avec asyncio
  - Microdot installe : `mip install microdot`
  - Fichier secrets.py local (WiFi credentials, non versionne)
"""

import gc
import network
import time
import uasyncio as asyncio
from machine import Pin, WDT

from microdot.microdot import Microdot, Response
from cimier_controller import CimierController
from step_generator import SoftwareStepGenerator

try:
    from secrets import WIFI_SSID, WIFI_PASSWORD
except ImportError:
    raise RuntimeError("secrets.py manquant : creer avec WIFI_SSID + WIFI_PASSWORD")


# ------------------------------------------------------------------
# Configuration GPIO (cf. README.md branchements)
# ------------------------------------------------------------------

PIN_STEP = 2          # GP2 -> PUL+ DM560T
PIN_DIR = 3           # GP3 -> DIR+ DM560T
PIN_OPEN_SWITCH = 14  # GP14 -> fin de course NC OUVERT
PIN_CLOSED_SWITCH = 15  # GP15 -> fin de course NC FERME

# Pulse rate cible : 3200 steps / 60 s = ~53 Hz -> sleep 18750 us entre pas
STEP_PERIOD_US = 18750

# Watchdog hardware : timeout 200 ms ; on feed a chaque tick (~20 ms)
WDT_TIMEOUT_MS = 200

HTTP_PORT = 80


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
        # NC + pull-up : repos = 0 (contact ferme tire a GND), butee = 1
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

def connect_wifi():
    wlan = network.WLAN(network.STA_IF)
    wlan.active(True)
    if not wlan.isconnected():
        wlan.connect(WIFI_SSID, WIFI_PASSWORD)
        for _ in range(60):  # 30 s timeout
            if wlan.isconnected():
                break
            time.sleep_ms(500)
    if not wlan.isconnected():
        raise RuntimeError("WiFi connection failed")
    return wlan


# ------------------------------------------------------------------
# Initialisation globale
# ------------------------------------------------------------------

_step_gen = SoftwareStepGenerator(PIN_STEP, PIN_DIR)
_hw = PicoHardwareAdapter(_step_gen, PIN_OPEN_SWITCH, PIN_CLOSED_SWITCH)
_controller = CimierController(_hw, time.time)
_wdt = WDT(timeout=WDT_TIMEOUT_MS)
_wlan = None


# ------------------------------------------------------------------
# Endpoints REST (Microdot)
# ------------------------------------------------------------------

app = Microdot()
Response.default_content_type = "application/json"


@app.get("/status")
def status(request):
    return _controller.to_status_dict()


@app.post("/open")
def open_cmd(request):
    _controller.start_open()
    return _controller.to_status_dict()


@app.post("/close")
def close_cmd(request):
    _controller.start_close()
    return _controller.to_status_dict()


@app.post("/stop")
def stop_cmd(request):
    _controller.stop()
    return _controller.to_status_dict()


@app.get("/info")
def info(request):
    info_dict = _controller.to_info_dict()
    info_dict["wifi_rssi"] = _wlan.status("rssi") if _wlan else None
    info_dict["wifi_ip"] = _wlan.ifconfig()[0] if _wlan else None
    info_dict["free_memory"] = gc.mem_free()
    return info_dict


@app.post("/config")
def config(request):
    body = request.json or {}
    if "invert_direction" in body:
        _controller.set_invert_direction(body["invert_direction"])
    return _controller.to_info_dict()


# ------------------------------------------------------------------
# Boucle de cycle (tick haute frequence)
# ------------------------------------------------------------------

async def cycle_runner():
    """Tache asyncio en parallele du serveur HTTP.

    Appelle controller.tick() a la cadence STEP_PERIOD_US et nourrit le WDT.
    """
    while True:
        _controller.tick()
        _wdt.feed()
        await asyncio.sleep_ms(STEP_PERIOD_US // 1000)


# ------------------------------------------------------------------
# Main
# ------------------------------------------------------------------

async def main():
    global _wlan
    _wlan = connect_wifi()
    print("WiFi connected:", _wlan.ifconfig()[0])
    asyncio.create_task(cycle_runner())
    await app.start_server(host="0.0.0.0", port=HTTP_PORT)


# Demarrage automatique au boot du Pico W
asyncio.run(main())
