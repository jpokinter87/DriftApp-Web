"""Lecture des fins de course cimier via un Shelly Uni+ (archi V3).

Archi V3 : les 2 microswitches (Haut/Bas) sont câblés sur
les 2 entrées du Shelly Uni+, lues via l'API RPC Gen 2
``GET /rpc/Input.GetStatus?id=<n>`` → ``{"id": n, "state": <bool>}``.

Sémantique terrain (microswitches NC, validée au banc — restée configurable) :
  - ``state=True``  = contact fermé  = repos = PAS en butée (NC fermé au repos).
  - ``state=False`` = contact ouvert = butée atteinte (le NC s'ouvre quand actionné).
Avec ``invert=True`` (défaut) : butée atteinte = input False.

Mapping d'entrées (configurable) :
  - ``open_input_id``   : entrée du microswitch HAUT (défaut id=1).
  - ``closed_input_id`` : entrée du microswitch BAS  (défaut id=0).

Aucune valeur terrain en dur — host / ids / inversion via le constructeur,
remplis par ``SwitchReaderConfig`` depuis ``data/config.json``.

L'argument ``urlopen`` permet d'injecter un mock pour les tests.
"""

from __future__ import annotations

import json
import urllib.error
import urllib.request
from dataclasses import dataclass


class SwitchReaderError(Exception):
    """Erreur de communication avec le Shelly Uni+."""


@dataclass(frozen=True)
class SwitchState:
    """État des fins de course dérivé des 2 entrées du Shelly Uni+."""

    open_switch: bool
    closed_switch: bool
    both_switches: bool
    raw: dict


class ShellySwitchReader:
    """Lit les 2 microswitches cimier via un Shelly Uni+ (RPC Gen 2)."""

    def __init__(
        self,
        host: str,
        api: str = "rpc",
        open_input_id: int = 1,
        closed_input_id: int = 0,
        invert: bool = True,
        timeout_s: float = 3.0,
        urlopen=None,
    ) -> None:
        if api != "rpc":
            raise ValueError(
                "ShellySwitchReader ne supporte que api='rpc' (Shelly Uni+ Gen 2), reçu "
                + repr(api)
            )
        self._host = host
        self._open_input_id = int(open_input_id)
        self._closed_input_id = int(closed_input_id)
        self._invert = bool(invert)
        self._timeout_s = float(timeout_s)
        self._urlopen = urlopen or urllib.request.urlopen

    def _read_input(self, input_id: int):
        url = "http://" + self._host + "/rpc/Input.GetStatus?id=" + str(input_id)
        try:
            with self._urlopen(url, timeout=self._timeout_s) as resp:
                status = getattr(resp, "status", 200)
                raw = resp.read()
        except urllib.error.URLError as exc:
            raise SwitchReaderError("Shelly Uni+ unreachable: " + str(exc.reason)) from exc
        except OSError as exc:
            raise SwitchReaderError("Shelly Uni+ socket error: " + str(exc)) from exc
        if status != 200:
            raise SwitchReaderError("Shelly Uni+ HTTP " + str(status))
        try:
            payload = json.loads(raw.decode("utf-8"))
        except (ValueError, UnicodeDecodeError) as exc:
            raise SwitchReaderError("Shelly Uni+ JSON invalide: " + str(exc)) from exc
        if not isinstance(payload, dict) or "state" not in payload:
            raise SwitchReaderError("Shelly Uni+ payload sans 'state': " + repr(payload))
        return bool(payload["state"]), payload

    def read(self) -> SwitchState:
        haut_state, haut_raw = self._read_input(self._open_input_id)
        bas_state, bas_raw = self._read_input(self._closed_input_id)
        if self._invert:
            open_switch = not haut_state
            closed_switch = not bas_state
        else:
            open_switch = haut_state
            closed_switch = bas_state
        return SwitchState(
            open_switch=open_switch,
            closed_switch=closed_switch,
            both_switches=open_switch and closed_switch,
            raw={"haut": haut_raw, "bas": bas_raw},
        )

    @property
    def host(self) -> str:
        return self._host


class NoopSwitchReader:
    """Reader inerte (dev/tests) : renvoie un ``SwitchState`` fixe configurable.

    Les attributs ``open_switch`` / ``closed_switch`` sont mutables pour qu'un
    test ou le dev puisse simuler une transition de butée.
    """

    def __init__(self, open_switch: bool = False, closed_switch: bool = False) -> None:
        self.open_switch = bool(open_switch)
        self.closed_switch = bool(closed_switch)

    def read(self) -> SwitchState:
        return SwitchState(
            open_switch=self.open_switch,
            closed_switch=self.closed_switch,
            both_switches=self.open_switch and self.closed_switch,
            raw={},
        )
