"""Simulateur Shelly unifié cimier (archi V3, dev/tests).

Émule, sur un seul port HTTP, les Shellys du boîtier cimier adossés à un
``CimierMechanismSim`` animé en temps réel :

  - Shelly Uni+ (RPC Gen 2) : ``GET /rpc/Input.GetStatus?id=<n>`` →
    ``{"id": n, "state": <bool>}``. id=0 → microswitch BAS, id=1 → HAUT.
    Convention V3 : ``state=True`` = contact ouvert = PAS en butée ;
    ``state=False`` = contact fermé = butée atteinte.
  - 3 relais legacy (Gen 1) : ``GET /relay/<n>?turn=on|off`` →
    ``{"ison": <bool>}``. n=0 → 24V (alim), n=1 → MOT (moteur), n=2 → UPDN
    (sens : ON = ouverture).

Un thread animateur fait progresser la position tant que 24V ET MOT sont ON
(course complète en ``full_travel_s``). Conventions naturelles (relais ON =
actif) — les conventions terrain potentiellement inversées sont validées au
banc, pas en dev.

CLI : uv run python -m core.hardware.cimier_simulator [--port 8001]
      [--initial closed|open|mid] [--full-travel 60]
"""

from __future__ import annotations

import argparse
import json
import sys
import threading
import time
from http.server import BaseHTTPRequestHandler, HTTPServer
from urllib.parse import parse_qs, urlparse

from core.hardware.cimier_mechanism_sim import CimierMechanismSim

DEFAULT_PORT = 8001

RELAY_24V = 0
RELAY_MOT = 1
RELAY_UPDN = 2

INPUT_BAS = 0
INPUT_HAUT = 1


class _SilentHandler(BaseHTTPRequestHandler):
    server_version = "CimierSimulator/1.0"

    def log_message(self, fmt, *args):
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
        parsed = urlparse(self.path)
        qs = parse_qs(parsed.query)

        if parsed.path == "/rpc/Input.GetStatus":
            try:
                input_id = int(qs.get("id", ["-1"])[0])
            except (TypeError, ValueError):
                input_id = -1
            state = sim.input_state(input_id)
            if state is None:
                self._send_json(404, {"error": "unknown_input", "id": input_id})
                return
            self._send_json(200, {"id": input_id, "state": state})
            return

        if parsed.path.startswith("/relay/"):
            try:
                relay_id = int(parsed.path.rsplit("/", 1)[1])
            except (TypeError, ValueError):
                self._send_json(404, {"error": "bad_relay"})
                return
            turn = qs.get("turn", [""])[0]
            ison = sim.set_relay(relay_id, turn)
            if ison is None:
                self._send_json(404, {"error": "unknown_relay", "id": relay_id})
                return
            self._send_json(200, {"ison": ison})
            return

        self._send_json(404, {"error": "not_found", "path": self.path})

    def do_POST(self):  # noqa: N802
        self._send_json(404, {"error": "not_found", "method": "POST", "path": self.path})


class _SimulatorHTTPServer(HTTPServer):
    allow_reuse_address = True

    def __init__(self, server_address, handler, simulator):
        super().__init__(server_address, handler)
        self.simulator = simulator


class CimierSimulator:
    """Émulateur Shelly unifié : relais (24V/MOT/UPDN) + Uni+, mécanisme animé."""

    def __init__(
        self,
        port=DEFAULT_PORT,
        boot_delay_s=0.0,
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
        self._server = None
        self._server_thread = None
        self._boot_thread = None
        self._animator_thread = None
        self._ready_event = threading.Event()
        self._stop_event = threading.Event()
        self._lock = threading.Lock()

        self._power_on = False  # relais 24V
        self._last_advance_ts = None

    # --- lifecycle -----------------------------------------------------
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
            self._power_on = False
            self._boot_thread = threading.Thread(
                target=self._boot_then_serve, name="cimier-sim-boot", daemon=True
            )
            self._boot_thread.start()

    def stop(self):
        self._stop_event.set()
        for attr in ("_server",):
            server = getattr(self, attr)
            if server is not None:
                try:
                    server.shutdown()
                except Exception:
                    pass
                try:
                    server.server_close()
                except Exception:
                    pass
        for attr in ("_boot_thread", "_server_thread", "_animator_thread"):
            th = getattr(self, attr)
            if th is not None:
                th.join(timeout=2.0)
        self._server = None
        self._server_thread = None
        self._boot_thread = None
        self._animator_thread = None
        self._ready_event.clear()

    def is_ready(self):
        return self._ready_event.is_set()

    def wait_ready(self, timeout=None):
        return self._ready_event.wait(timeout=timeout)

    @property
    def url(self):
        return "http://{}:{}".format(self._host, self._actual_port())

    @property
    def port(self):
        return self._actual_port()

    @property
    def mechanism(self):
        return self._mechanism

    def _actual_port(self):
        if self._server is not None:
            return self._server.server_address[1]
        return self._port

    # --- API métier (appelée par le handler, thread-safe) --------------
    def input_state(self, input_id):
        """État brut d'une entrée Uni+ (None si id inconnu).

        Convention V3 : butée atteinte → contact fermé → state=False.
        """
        with self._lock:
            self._advance_locked()
            if input_id == INPUT_HAUT:
                return not self._mechanism.open_switch
            if input_id == INPUT_BAS:
                return not self._mechanism.closed_switch
            return None

    def set_relay(self, relay_id, turn):
        """Pilote un relais simulé. Retourne l'état (ison) ou None si inconnu."""
        on = turn == "on"
        with self._lock:
            self._advance_locked()
            if relay_id == RELAY_24V:
                self._power_on = on
                return on
            if relay_id == RELAY_MOT:
                self._mechanism.set_motor(on)
                return on
            if relay_id == RELAY_UPDN:
                self._mechanism.set_direction(open_direction=on)
                return on
            return None

    # --- animation -----------------------------------------------------
    def _advance_locked(self):
        """Avance le mécanisme du temps écoulé (à appeler sous self._lock)."""
        now = time.monotonic()
        if self._last_advance_ts is None:
            self._last_advance_ts = now
            return
        elapsed = now - self._last_advance_ts
        self._last_advance_ts = now
        if self._power_on and self._mechanism.motor_on:
            self._mechanism.advance(elapsed)

    def _animate_loop(self):
        while not self._stop_event.is_set():
            with self._lock:
                self._advance_locked()
            self._stop_event.wait(timeout=0.05)

    def _boot_then_serve(self):
        if self._boot_delay_s > 0:
            self._stop_event.wait(timeout=self._boot_delay_s)
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
        # stop() a pu être appelé pendant le bind : ne pas exposer un serveur
        # que personne ne fermera (sinon serve_forever tournerait à l'infini).
        if self._stop_event.is_set():
            server.server_close()
            return
        self._server = server
        self._last_advance_ts = time.monotonic()
        self._server_thread = threading.Thread(
            target=server.serve_forever, name="cimier-sim-http", daemon=True
        )
        self._server_thread.start()
        self._animator_thread = threading.Thread(
            target=self._animate_loop, name="cimier-sim-anim", daemon=True
        )
        self._animator_thread.start()
        self._ready_event.set()


def _parse_args(argv):
    parser = argparse.ArgumentParser(
        description="Simulateur Shelly unifié cimier (dev/tests) : relais + Uni+.",
    )
    parser.add_argument("--port", type=int, default=DEFAULT_PORT)
    parser.add_argument("--host", default="127.0.0.1")
    parser.add_argument("--initial", choices=("closed", "open", "mid"), default="closed")
    parser.add_argument("--full-travel", type=float, default=60.0)
    # Conservé pour compatibilité avec start_dev.sh (start_dev passe 0.0)
    parser.add_argument("--boot-delay", type=float, default=0.0)
    return parser.parse_args(argv)


def main(argv=None):
    args = _parse_args(argv)
    sim = CimierSimulator(
        port=args.port,
        host=args.host,
        initial_state=args.initial,
        full_travel_s=args.full_travel,
        boot_delay_s=args.boot_delay,
    )
    print(
        "[cimier_simulator] booting on http://{}:{} (initial={}, full_travel={}s)".format(
            args.host, args.port, args.initial, args.full_travel
        ),
        file=sys.stderr,
    )
    sim.start()
    if not sim.wait_ready(timeout=5.0):
        print("[cimier_simulator] echec demarrage", file=sys.stderr)
        sim.stop()
        return 1
    print(
        "[cimier_simulator] pret. curl http://{}:{}/rpc/Input.GetStatus?id=1".format(
            args.host, args.port
        ),
        file=sys.stderr,
    )
    try:
        while True:
            time.sleep(1.0)
    except KeyboardInterrupt:
        print("[cimier_simulator] arret demande (Ctrl-C)", file=sys.stderr)
    finally:
        sim.stop()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
