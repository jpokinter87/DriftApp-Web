"""
Abstraction du switch d'alimentation cimier.

Permet de couper / retablir l'alimentation du boitier electronique cimier
(driver DM560T + Pico W) entre les cycles pour economiser la batterie solaire.
Le DM560T au repos consomme du courant pour maintenir les aimants
stationnaires du moteur sous tension - couper son alim est plus radical et
plus efficace qu'agir sur ENA.

Implementations disponibles :
  - ShellyPowerSwitch  : commande un Shelly mini relais via REST.
                         Supporte les deux APIs : Gen 2 RPC (par defaut) et
                         Gen 1 legacy.
  - NoopPowerSwitch    : ne fait rien, pour dev / tests sans hardware.

Note Phase 1 — Architecture cascade 220V -> 12V (cadree 2026-04-30) :

    Le boitier cimier est alimente par 2 Shellys en serie :
    - **Shelly 220V** (commande directement par ce module) : pilote l'alim
      220V du chargeur 220->12V.
    - **Shelly 12V** (interne au boitier cimier) : distribue le 12V au driver
      DM560T et au Pico W (via boitier QC3.0 USB-C).

    Le Shelly 220V envoie un heartbeat au Shelly 12V toutes les 5-10 secondes.
    Le Shelly 12V s'auto-eteint s'il ne recoit rien pendant > 10 sec. Cela
    permet de couper le 12V alors meme que le Shelly 220V n'a plus de 220V
    en entree (puisqu'il s'est lui-meme deconnecte).

    Consequences pour l'orchestration cote `cimier_service.py` Phase 1 :

    - Apres `turn_on()` : compter ~5 s pour que le Shelly 12V s'allume +
      ~10-15 s pour le boot du Pico W (banner safe-boot 3 s + WiFi connect
      ~5-10 s) = total **~15-20 s avant que le Pico soit joignable** via
      HTTP. Polling `<pico>/status` avec retries / timeout 30 s recommande.

    - Apres `turn_off()` : le 12V coupe ~10 s plus tard (heartbeat manque).
      Ne pas relancer un cycle pendant ce delai. Le service doit garder
      l'etat "powered_off" coherent meme si la coupure est asynchrone.

    - Couper le Shelly coupe AUSSI le Pico W : `invert_direction` runtime
      est perdu au reboot. Le service Pi doit re-pousser la config via
      `<pico>/config` apres chaque rallumage si elle est non-defaut.
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
            raise ValueError(
                "api must be 'rpc' (Gen 2) or 'legacy' (Gen 1), got " + repr(api)
            )
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
