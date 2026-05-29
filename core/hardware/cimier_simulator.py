"""Simulateur HTTP fidèle du firmware Pico W cimier (pivot Shelly v6.x).

Le Pico W est désormais un pur serveur de capteurs : ce simulateur expose
GET /status + GET /info, alimentés par un CimierMechanismSim (position →
fins de course). Aucune source de mouvement HTTP en Bloc 1 (l'animation
via Shelly simulé arrive au Bloc 2) : l'état est fixé par --initial.

Reproduit la latence boot (port non lié → ConnectionRefused côté client).

CLI : uv run python -m core.hardware.cimier_simulator [--port 8001]
      [--boot-delay 0.0] [--initial closed|open|mid]
"""

from __future__ import annotations

import argparse
import json
import socket
import sys
import threading
import time
from http.server import BaseHTTPRequestHandler, HTTPServer
from pathlib import Path

from core.hardware.cimier_mechanism_sim import CimierMechanismSim

_FIRMWARE_DIR = Path(__file__).resolve().parents[2] / "firmware" / "cimier"
if str(_FIRMWARE_DIR) not in sys.path:
    sys.path.insert(0, str(_FIRMWARE_DIR))

import cimier_controller as _cc  # noqa: E402

DEFAULT_PORT = 8001
DEFAULT_BOOT_DELAY_S = 15.0

SIMULATED_WIFI_RSSI = -55
SIMULATED_WIFI_IP = "127.0.0.1"
SIMULATED_FREE_MEMORY = 100_000


class _MechanismSwitchAdapter:
    """Adapter capteurs : lit les fins de course depuis le mécanisme."""

    def __init__(self, mechanism: CimierMechanismSim):
        self._m = mechanism

    def read_open_switch(self):
        return self._m.open_switch

    def read_closed_switch(self):
        return self._m.closed_switch


class _SilentHandler(BaseHTTPRequestHandler):
    server_version = "CimierSimulator/0.2"

    def log_message(self, format, *args):
        return

    def _send_json(self, status, payload):
        body = json.dumps(payload).encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(body)))
        self.send_header("Connection", "close")
        self.end_headers()
        self.wfile.write(body)

    def do_GET(self):  # noqa: N802
        sim = self.server.simulator
        if self.path == "/status":
            self._send_json(200, sim._controller.to_status_dict())
            return
        if self.path == "/info":
            info = sim._controller.to_info_dict()
            info["wifi_rssi"] = SIMULATED_WIFI_RSSI
            info["wifi_ip"] = SIMULATED_WIFI_IP
            info["free_memory"] = SIMULATED_FREE_MEMORY
            self._send_json(200, info)
            return
        self._send_json(404, {"error": "not_found", "method": "GET", "path": self.path})

    def do_POST(self):  # noqa: N802
        # Firmware capteur-only : aucun POST supporté.
        self._send_json(404, {"error": "not_found", "method": "POST", "path": self.path})


class _SimulatorHTTPServer(HTTPServer):
    allow_reuse_address = True

    def __init__(self, server_address, handler, simulator):
        super().__init__(server_address, handler)
        self.simulator = simulator


class CimierSimulator:
    """Mini Pico W virtuel capteur-only : mécanisme + contrôleur + serveur HTTP."""

    def __init__(
        self,
        port=DEFAULT_PORT,
        boot_delay_s=DEFAULT_BOOT_DELAY_S,
        initial_state="closed",
        full_travel_s=60.0,
        host="127.0.0.1",
    ):
        self._host = host
        self._port = port
        self._boot_delay_s = float(boot_delay_s)
        self._initial_state = initial_state
        self._full_travel_s = float(full_travel_s)

        self._mechanism = None
        self._controller = None
        self._server = None
        self._server_thread = None
        self._boot_thread = None
        self._ready_event = threading.Event()
        self._stop_event = threading.Event()
        self._lock = threading.Lock()

    def start(self):
        with self._lock:
            if self._server is not None or (
                self._boot_thread is not None and self._boot_thread.is_alive()
            ):
                raise RuntimeError("simulator already started")
            self._stop_event.clear()
            self._ready_event.clear()
            self._mechanism = CimierMechanismSim(
                initial_state=self._initial_state, full_travel_s=self._full_travel_s
            )
            self._controller = _cc.CimierController(_MechanismSwitchAdapter(self._mechanism))
            self._boot_thread = threading.Thread(
                target=self._boot_then_serve, name="cimier-sim-boot", daemon=True
            )
            self._boot_thread.start()

    def stop(self):
        self._stop_event.set()
        boot_thread = self._boot_thread
        server = self._server
        server_thread = self._server_thread
        if server is not None:
            try:
                server.shutdown()
            except Exception:
                pass
            try:
                server.server_close()
            except Exception:
                pass
        if boot_thread is not None:
            boot_thread.join(timeout=2.0)
        if server_thread is not None:
            server_thread.join(timeout=2.0)
        self._server = None
        self._server_thread = None
        self._boot_thread = None
        self._ready_event.clear()

    def is_ready(self):
        return self._ready_event.is_set()

    def wait_ready(self, timeout=None):
        return self._ready_event.wait(timeout=timeout)

    def reset_boot(self):
        """Simule une coupure 24V + reboot Pico (repasse par la latence boot)."""
        self.stop()
        self.start()

    @property
    def url(self):
        return "http://{}:{}".format(self._host, self._port)

    @property
    def port(self):
        return self._port

    @property
    def mechanism(self):
        """Accès interne (tests) : pilote la position/le moteur du mécanisme."""
        return self._mechanism

    @property
    def controller(self):
        return self._controller

    def _boot_then_serve(self):
        deadline = time.monotonic() + self._boot_delay_s
        while not self._stop_event.is_set():
            remaining = deadline - time.monotonic()
            if remaining <= 0:
                break
            self._stop_event.wait(timeout=min(remaining, 0.1))
        if self._stop_event.is_set():
            return
        try:
            server = _SimulatorHTTPServer((self._host, self._port), _SilentHandler, self)
        except OSError as exc:
            print(
                "[cimier_simulator] bind {}:{} echoue: {}".format(self._host, self._port, exc),
                file=sys.stderr,
            )
            return
        self._server = server
        self._server_thread = threading.Thread(
            target=server.serve_forever, name="cimier-sim-http", daemon=True
        )
        self._server_thread.start()
        self._ready_event.set()


def _parse_args(argv):
    parser = argparse.ArgumentParser(
        description="Simulateur HTTP du firmware Pico W cimier capteur-only (dev/tests).",
    )
    parser.add_argument("--port", type=int, default=DEFAULT_PORT)
    parser.add_argument("--boot-delay", type=float, default=0.0)
    parser.add_argument("--host", default="127.0.0.1")
    parser.add_argument("--initial", choices=("closed", "open", "mid"), default="closed")
    return parser.parse_args(argv)


def main(argv=None):
    args = _parse_args(argv)
    sim = CimierSimulator(
        port=args.port,
        boot_delay_s=args.boot_delay,
        host=args.host,
        initial_state=args.initial,
    )
    print(
        "[cimier_simulator] booting on http://{}:{} (boot_delay={}s, initial={})".format(
            args.host, args.port, args.boot_delay, args.initial
        ),
        file=sys.stderr,
    )
    sim.start()
    if not sim.wait_ready(timeout=args.boot_delay + 5.0):
        print("[cimier_simulator] echec demarrage", file=sys.stderr)
        sim.stop()
        return 1
    print(
        "[cimier_simulator] pret. curl http://{}:{}/status".format(args.host, args.port),
        file=sys.stderr,
    )
    try:
        while True:
            time.sleep(1.0)
    except KeyboardInterrupt:
        print("[cimier_simulator] arret demande (Ctrl-C)", file=sys.stderr)
    finally:
        sim.stop()
        try:
            probe = socket.socket()
            probe.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
            probe.settimeout(0.5)
            probe.bind((args.host, args.port))
            probe.close()
        except OSError:
            pass
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
