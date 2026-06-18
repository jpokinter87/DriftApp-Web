"""
Coupe / rétablit l'alimentation 24V du module cimier via un Shelly (archi V3).

Le Shelly SHELLY-1-24V (.83) alimente le module cimier (contrôleur autonome
STEP + DM556T). ``cimier_service`` le coupe hors cycle (économie / sécurité)
et le rétablit en début de cycle, avec une attente d'appairage WiFi des
Shelly aval (MOTOR/DIR) avant d'énergiser le moteur.

API supportée :
  - ``api="legacy"`` (Gen 1) : ``http://<host>/relay/<id>?turn=<on|off>``
  - ``api="rpc"`` (Gen 2/Plus) : ``http://<host>/rpc/Switch.Set?id=<id>&on=<bool>``

Aucune valeur terrain (IP / index) en dur — tout via le constructeur, rempli
par ``PowerSwitchConfig`` depuis ``data/config.json``.

L'argument ``urlopen`` permet d'injecter un mock pour les tests.
"""

from __future__ import annotations

import urllib.error
import urllib.request


class PowerSwitchError(Exception):
    """Erreur de communication avec le switch."""


class NoopPowerSwitch:
    """Pas de switch physique. Methodes no-op + etat memoire.

    Pour dev / tests sans hardware, ou pour les setups sans relais Shelly.
    """

    def __init__(self) -> None:
        self._state = False

    def turn_on(self) -> None:
        self._state = True

    def turn_off(self) -> None:
        self._state = False

    def is_on(self) -> bool:
        return self._state


class ShellyPowerSwitch:
    """Pilote un Shelly mini relais via API REST.

    Supporte deux formats d'URL selon la generation du firmware Shelly :

    - **api="rpc"** (default) : Shelly Gen 2 / Plus / Pro
        URL : ``http://<host>/rpc/Switch.Set?id=<switch_id>&on=<true|false>``

    - **api="legacy"** : Shelly Gen 1
        URL : ``http://<host>/relay/<switch_id>?turn=<on|off>``

    L'argument `urlopen` permet d'injecter un mock pour les tests.
    """

    def __init__(
        self,
        host: str,
        switch_id: int = 0,
        api: str = "rpc",
        timeout_s: float = 3.0,
        urlopen=None,
    ) -> None:
        if api not in ("rpc", "legacy"):
            raise ValueError("api must be 'rpc' (Gen 2) or 'legacy' (Gen 1), got " + repr(api))
        self._host = host
        self._switch_id = switch_id
        self._api = api
        self._timeout_s = timeout_s
        self._urlopen = urlopen or urllib.request.urlopen

    def _build_url(self, on: bool) -> str:
        if self._api == "rpc":
            return (
                "http://"
                + self._host
                + "/rpc/Switch.Set?id="
                + str(self._switch_id)
                + "&on="
                + ("true" if on else "false")
            )
        return (
            "http://"
            + self._host
            + "/relay/"
            + str(self._switch_id)
            + "?turn="
            + ("on" if on else "off")
        )

    def _set(self, on: bool) -> None:
        url = self._build_url(on)
        try:
            with self._urlopen(url, timeout=self._timeout_s) as resp:
                status = getattr(resp, "status", 200)
                if status != 200:
                    raise PowerSwitchError("Shelly HTTP " + str(status))
                resp.read()
        except urllib.error.URLError as exc:
            raise PowerSwitchError("Shelly unreachable: " + str(exc.reason)) from exc
        except OSError as exc:
            raise PowerSwitchError("Shelly socket error: " + str(exc)) from exc

    def turn_on(self) -> None:
        self._set(True)

    def turn_off(self) -> None:
        self._set(False)

    @property
    def host(self) -> str:
        return self._host

    @property
    def api(self) -> str:
        return self._api
