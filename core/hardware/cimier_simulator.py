"""Simulateur HTTP fidele du firmware Pico W cimier.

Tourne sur la machine de dev (CPython, hors site terrain) pour permettre le
developpement et les tests des couches superieures (cimier_service, IPC,
endpoints Django, UI dashboard) sans avoir le hardware sous la main.

Reutilise tel quel le module pur ``firmware/cimier/cimier_controller.py``
(meme contrat d'interface que sur le Pico W). Le hardware est emule par un
``_VirtualHardwareAdapter`` interne : compteur de pas, switches deduits de la
position, direction memorisee.

Endpoints REST (port 8001 par defaut, JSON, localhost uniquement) :
  GET  /status   -> controller.to_status_dict()
  POST /open     -> controller.start_open()  + status
  POST /close    -> controller.start_close() + status
  POST /stop     -> controller.stop()        + status
  GET  /info     -> controller.to_info_dict() + champs simules (wifi/memoire)
  POST /config   -> {"invert_direction": bool}, retourne info

Latence boot 15-20 s simulee : pendant ``boot_delay_s``, aucun serveur HTTP
n'est en ecoute, le port n'est pas lie. Cote client, ``urlopen`` leve
``ConnectionRefusedError`` -- exactement ce que le polling Phase 1 verra
contre un Pico W qui n'a pas fini son boot WiFi.

CLI :
  uv run python -m core.hardware.cimier_simulator [--port 8001] [--boot-delay 0.0]
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

_FIRMWARE_DIR = Path(__file__).resolve().parents[2] / "firmware" / "cimier"
if str(_FIRMWARE_DIR) not in sys.path:
    sys.path.insert(0, str(_FIRMWARE_DIR))

import cimier_controller as _cc  # noqa: E402

DEFAULT_PORT = 8001
DEFAULT_BOOT_DELAY_S = 15.0
DEFAULT_STEPS_PER_CYCLE = 200
DEFAULT_CYCLE_TIMEOUT_S = 10.0
DEFAULT_TICK_PERIOD_MS = 20

SIMULATED_WIFI_RSSI = -55
SIMULATED_WIFI_IP = "127.0.0.1"
SIMULATED_FREE_MEMORY = 100_000


class _VirtualHardwareAdapter:
    """Hardware adapter purement memoire pour le simulateur.

    Maintient une position virtuelle ``[0, steps_per_cycle]`` et deduit l'etat
    des switches. Au boot, le simulateur est suppose ferme (position = 0)
    pour reproduire le comportement post-flash le plus courant.
    """

    def __init__(self, steps_per_cycle, initial_position=0):
        self._steps_per_cycle = steps_per_cycle
        self._position = max(0, min(initial_position, steps_per_cycle))
        self._direction = _cc._DIR_OPEN_NOMINAL
        self.step_count = 0
        self.direction_log = []

    def read_open_switch(self):
        return self._position >= self._steps_per_cycle

    def read_closed_switch(self):
        return self._position <= 0

    def set_direction(self, direction):
        self._direction = int(direction)
        self.direction_log.append(int(direction))

    def pulse_step(self):
        self.step_count += 1
        if self._direction == _cc._DIR_OPEN_NOMINAL:
            self._position = min(self._position + 1, self._steps_per_cycle)
        else:
            self._position = max(self._position - 1, 0)

    @property
    def position(self):
        return self._position

    @property
    def last_direction(self):
        return self._direction


class _SilentHandler(BaseHTTPRequestHandler):
    """Handler HTTP qui delegue le routing au simulateur attache."""

    server_version = "CimierSimulator/0.1"

    def log_message(self, format, *args):
        # Silence access log pour ne pas polluer pytest stderr.
        return

    def _read_body(self):
        length = int(self.headers.get("Content-Length") or 0)
        if length <= 0:
            return None
        raw = self.rfile.read(length)
        if not raw:
            return None
        try:
            return json.loads(raw.decode("utf-8"))
        except (ValueError, UnicodeDecodeError):
            return _BODY_INVALID

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
        sim = self.server.simulator
        body = self._read_body()
        if body is _BODY_INVALID:
            self._send_json(400, {"error": "bad_request"})
            return

        if self.path == "/open":
            sim._controller.start_open()
            self._send_json(200, sim._controller.to_status_dict())
            return
        if self.path == "/close":
            sim._controller.start_close()
            self._send_json(200, sim._controller.to_status_dict())
            return
        if self.path == "/stop":
            sim._controller.stop()
            self._send_json(200, sim._controller.to_status_dict())
            return
        if self.path == "/config":
            if isinstance(body, dict) and "invert_direction" in body:
                sim._controller.set_invert_direction(bool(body["invert_direction"]))
            elif body is not None and not isinstance(body, dict):
                self._send_json(400, {"error": "bad_request"})
                return
            self._send_json(200, sim._controller.to_info_dict())
            return
        self._send_json(404, {"error": "not_found", "method": "POST", "path": self.path})


# Sentinelle pour distinguer "body absent" de "body present mais invalide".
_BODY_INVALID = object()


class _SimulatorHTTPServer(HTTPServer):
    """HTTPServer qui transporte une reference vers le simulateur parent."""

    allow_reuse_address = True

    def __init__(self, server_address, handler, simulator):
        super().__init__(server_address, handler)
        self.simulator = simulator


class CimierSimulator:
    """Mini Pico W virtuel : controller + adapter + serveur HTTP + tick thread.

    Reproduction fidele :
      - Latence boot 15-20 s (parametrable). Pendant le boot, le port n'est
        pas lie => connection refused cote client.
      - ``invert_direction`` perdu au reset_boot (comme le Pico apres coupure
        Shelly).
      - Endpoints REST identiques au firmware (cf. firmware/cimier/main.py).
    """

    def __init__(
        self,
        port=DEFAULT_PORT,
        boot_delay_s=DEFAULT_BOOT_DELAY_S,
        steps_per_cycle=DEFAULT_STEPS_PER_CYCLE,
        cycle_timeout_s=DEFAULT_CYCLE_TIMEOUT_S,
        tick_period_ms=DEFAULT_TICK_PERIOD_MS,
        initial_invert_direction=False,
        initial_position=0,
        host="127.0.0.1",
    ):
        self._host = host
        self._port = port
        self._boot_delay_s = float(boot_delay_s)
        self._steps_per_cycle = int(steps_per_cycle)
        self._cycle_timeout_s = float(cycle_timeout_s)
        self._tick_period_s = max(0.001, tick_period_ms / 1000.0)
        self._boot_invert_default = bool(initial_invert_direction)
        self._initial_position = int(initial_position)

        self._hw = None
        self._controller = None
        self._server = None
        self._server_thread = None
        self._tick_thread = None
        self._boot_thread = None
        self._ready_event = threading.Event()
        self._stop_event = threading.Event()
        self._lock = threading.Lock()

    # ------------------------------------------------------------------
    # API publique
    # ------------------------------------------------------------------

    def start(self):
        """Lance le boot + thread tick + serveur HTTP. Bloquant uniquement
        pendant le ``boot_delay_s`` si on appelle ``wait_ready()``."""
        with self._lock:
            if self._server is not None or (
                self._boot_thread is not None and self._boot_thread.is_alive()
            ):
                raise RuntimeError("simulator already started")
            self._stop_event.clear()
            self._ready_event.clear()
            self._hw = _VirtualHardwareAdapter(
                self._steps_per_cycle, initial_position=self._initial_position
            )
            self._controller = _cc.CimierController(
                self._hw,
                time.monotonic,
                steps_per_cycle=self._steps_per_cycle,
                cycle_timeout_s=self._cycle_timeout_s,
                invert_direction=self._boot_invert_default,
            )
            self._boot_thread = threading.Thread(
                target=self._boot_then_serve, name="cimier-sim-boot", daemon=True
            )
            self._boot_thread.start()

    def stop(self):
        """Arret propre : ferme le serveur, stop le thread tick, libere le port."""
        self._stop_event.set()
        boot_thread = self._boot_thread
        server = self._server
        tick_thread = self._tick_thread
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
        if tick_thread is not None:
            tick_thread.join(timeout=2.0)

        self._server = None
        self._server_thread = None
        self._tick_thread = None
        self._boot_thread = None
        self._ready_event.clear()

    def is_ready(self):
        """True une fois le boot termine et le serveur HTTP en ecoute."""
        return self._ready_event.is_set()

    def wait_ready(self, timeout=None):
        """Bloque jusqu'a ce que le simulateur soit pret (ou timeout)."""
        return self._ready_event.wait(timeout=timeout)

    def reset_boot(self):
        """Simule une coupure Shelly + reboot Pico W.

        Ferme proprement le serveur, reinitialise ``invert_direction`` a sa
        valeur de boot par defaut (False sauf override constructeur), puis
        relance le cycle de boot complet (incluant la latence ``boot_delay_s``).
        """
        self.stop()
        self.start()

    @property
    def url(self):
        return "http://{}:{}".format(self._host, self._port)

    @property
    def port(self):
        return self._port

    @property
    def hardware(self):
        """Acces interne pour les tests (positions, step_count, direction_log)."""
        return self._hw

    @property
    def controller(self):
        """Acces interne pour les tests."""
        return self._controller

    # ------------------------------------------------------------------
    # Internals
    # ------------------------------------------------------------------

    def _boot_then_serve(self):
        """Attend ``boot_delay_s`` puis demarre serveur HTTP + tick thread."""
        # Wait par chunks pour respecter un stop() pendant le boot.
        deadline = time.monotonic() + self._boot_delay_s
        while not self._stop_event.is_set():
            remaining = deadline - time.monotonic()
            if remaining <= 0:
                break
            self._stop_event.wait(timeout=min(remaining, 0.1))
        if self._stop_event.is_set():
            return

        try:
            server = _SimulatorHTTPServer(
                (self._host, self._port), _SilentHandler, self
            )
        except OSError as exc:
            print(
                "[cimier_simulator] bind {}:{} echoue: {}".format(
                    self._host, self._port, exc
                ),
                file=sys.stderr,
            )
            return

        self._server = server
        self._server_thread = threading.Thread(
            target=server.serve_forever, name="cimier-sim-http", daemon=True
        )
        self._server_thread.start()

        self._tick_thread = threading.Thread(
            target=self._tick_loop, name="cimier-sim-tick", daemon=True
        )
        self._tick_thread.start()

        self._ready_event.set()

    def _tick_loop(self):
        while not self._stop_event.is_set():
            try:
                self._controller.tick()
            except Exception as exc:
                print(
                    "[cimier_simulator] tick exception: {}".format(exc),
                    file=sys.stderr,
                )
            self._stop_event.wait(timeout=self._tick_period_s)


# ----------------------------------------------------------------------
# CLI
# ----------------------------------------------------------------------

def _parse_args(argv):
    parser = argparse.ArgumentParser(
        description="Simulateur HTTP du firmware Pico W cimier (dev/tests).",
    )
    parser.add_argument("--port", type=int, default=DEFAULT_PORT)
    parser.add_argument(
        "--boot-delay",
        type=float,
        default=0.0,
        help="Latence boot simulee (s). Defaut 0.0 pour usage interactif rapide.",
    )
    parser.add_argument(
        "--steps-per-cycle",
        type=int,
        default=_cc.DEFAULT_STEPS_PER_CYCLE,
        help="Nombre de pas pour un cycle complet (defaut firmware reel).",
    )
    parser.add_argument(
        "--cycle-timeout",
        type=float,
        default=float(_cc.DEFAULT_CYCLE_TIMEOUT_S),
        help="Timeout cycle en secondes (defaut firmware reel).",
    )
    parser.add_argument("--host", default="127.0.0.1")
    parser.add_argument(
        "--initial",
        choices=("closed", "open"),
        default="closed",
        help="Position initiale simulee (defaut: closed).",
    )
    return parser.parse_args(argv)


def main(argv=None):
    args = _parse_args(argv)
    initial_position = args.steps_per_cycle if args.initial == "open" else 0
    sim = CimierSimulator(
        port=args.port,
        boot_delay_s=args.boot_delay,
        steps_per_cycle=args.steps_per_cycle,
        cycle_timeout_s=args.cycle_timeout,
        host=args.host,
        initial_position=initial_position,
    )
    print(
        "[cimier_simulator] booting on http://{}:{} (boot_delay={}s, steps={}, "
        "cycle_timeout={}s)".format(
            args.host, args.port, args.boot_delay, args.steps_per_cycle,
            args.cycle_timeout,
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
        # Verification port libere : SO_REUSEADDR pour eviter le faux negatif
        # TIME_WAIT (les connexions HTTP fermees laissent des sockets en attente
        # sans empecher un vrai usage).
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
