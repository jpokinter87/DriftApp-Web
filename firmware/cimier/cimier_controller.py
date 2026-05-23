"""Logique capteurs cimier — module pur (pivot Shelly v6.x).

Depuis le pivot Shelly, le moteur cimier n'est plus piloté par le Pico W :
le Pico W est un pur serveur de capteurs (fins de course). Ce module ne
contient plus que la dérivation d'état depuis les 2 fins de course + la
sérialisation REST.

Tourne en MicroPython (firmware/cimier/main.py) et en CPython (tests,
simulateur). Hardware abstrait via duck typing sur ``hardware_adapter`` :
  - read_open_switch() -> bool    (True si butée ouverte atteinte)
  - read_closed_switch() -> bool   (True si butée fermée atteinte)
"""

# États (string pour sérialisation REST)
STATE_CLOSED = "closed"
STATE_OPEN = "open"
STATE_ERROR = "error"
STATE_UNKNOWN = "unknown"

# Versions firmware (0.2.0 = pivot Shelly capteur-only ; protocole 2 = sans /open /close)
FIRMWARE_VERSION = "0.2.0"
FIRMWARE_PROTOCOL_VERSION = 2


class CimierController:
    """Dérive l'état du cimier depuis les 2 fins de course (lecture seule)."""

    def __init__(self, hardware_adapter):
        self._hw = hardware_adapter
        self._state = STATE_UNKNOWN
        self._last_error_message = ""
        self._refresh_state_from_switches()

    def _refresh_state_from_switches(self):
        open_triggered = bool(self._hw.read_open_switch())
        closed_triggered = bool(self._hw.read_closed_switch())
        if open_triggered and closed_triggered:
            self._state = STATE_ERROR
            self._last_error_message = "both_switches_triggered"
        elif open_triggered:
            self._state = STATE_OPEN
            self._last_error_message = ""
        elif closed_triggered:
            self._state = STATE_CLOSED
            self._last_error_message = ""
        else:
            self._state = STATE_UNKNOWN
            self._last_error_message = ""

    @property
    def state(self):
        self._refresh_state_from_switches()
        return self._state

    def to_status_dict(self):
        self._refresh_state_from_switches()
        return {
            "state": self._state,
            "open_switch": bool(self._hw.read_open_switch()),
            "closed_switch": bool(self._hw.read_closed_switch()),
            "error_message": self._last_error_message,
        }

    def to_info_dict(self):
        return {
            "firmware_version": FIRMWARE_VERSION,
            "protocol_version": FIRMWARE_PROTOCOL_VERSION,
            "role": "sensor",
        }
