"""
Pilote moteur cimier via 2 relais Shelly (archi V3 tout-Shelly).

Contexte
--------
Le pilotage STEP/DIR du moteur cimier n'a jamais réussi à le faire tourner ;
le circuit de commande manuel (oscillateur + 2 interrupteurs : ON/OFF moteur
+ DPDT direction) le fait tourner de façon reproductible. Le pivot V3
automatise ce circuit avec des Shelly Gen 1 (contact sec) :
  - Shelly MOTOR (.85) : ON/OFF moteur (remplace l'interrupteur manuel).
  - Shelly DIR   (.86) : pilote un relais DPDT externe qui permute la ligne
                         DIR (sens du moteur).
Les fins de course haut/bas sont lues via un Shelly Uni+ (.84), cf.
``core/hardware/shelly_switch_reader.py``.

`cimier_service` (côté Pi) orchestre :
  1. set_direction(open_direction=True) → relais DIR positionné
  2. turn_on(timer_s=90) → moteur démarre, kill auto Shelly à 90 s en cas de
     WiFi-drop (filet de sécurité hardware, indépendant du Pi)
  3. polling des butées (Shelly Uni+) jusqu'à fin de course
  4. turn_off() → moteur stoppé

Le moteur tourne à vitesse fixe (potard de l'oscillateur) ; la précision
positionnelle vient des fins de course mécaniques, pas des pas. Suffisant
pour un cimier (mécanisme binaire open/closed).

API Shelly supportée
--------------------
- ``api="legacy"`` (terrain V3) : Shelly Gen 1
    URL : ``http://<host>/relay/<relay>?turn=<on|off>[&timer=<N>]``
- ``api="rpc"`` (défaut) : Shelly Gen 2 / Plus / Pro
    URL : ``http://<host>/rpc/Switch.Set?id=<relay>&on=<true|false>[&toggle_after=<N>]``

L'argument `urlopen` permet d'injecter un mock pour les tests.
"""

from __future__ import annotations

import logging
import urllib.error
import urllib.request

logger = logging.getLogger(__name__)


class MotorShellyError(Exception):
    """Erreur de communication avec le Shelly moteur."""


class MotorShelly:
    """Pilote 2 relais Shelly pour le moteur cimier.

    Conventions paramétriques (réglées côté config terrain, pas dans le code) :

      ``motor_on_relay_state`` :
        - False (défaut, **convention validée terrain 17-18/06**) : le moteur
          tourne quand le relais MOTOR est **ouvert** (oscillateur câblé NC).
          ``turn_on()`` met donc le relais à OFF (``turn=off`` / ``on=false``)
          pour démarrer, et ``turn_off()`` à ON pour arrêter.
        - True : convention « intuitive » NO (contact fermé = circuit
          alimenté). ``turn_on()`` met le relais à ON. Non utilisé en V3.

      ``open_dir_state`` :
        - True (défaut, convention validée terrain) :
          ``set_direction(open_direction=True)`` met le relais DIR à ON
          (``turn=on`` = sens montée / ouverture).
        - False : convention inversée (DPDT externe câblé dans l'autre sens).

    Filet de sécurité hardware (``timer_s`` sur ``turn_on``) :
        En API RPC (Gen 2/3), le paramètre Shelly ``toggle_after=N`` fait
        basculer le relais à son état opposé après N secondes. Quel que
        soit ``motor_on_relay_state``, l'effet reste **« moteur OFF après
        N secondes »** parce que ``toggle_after`` inverse l'état courant.

    Note opérationnelle Shelly Gen 1 — état au boot :
        Avec la convention validée (``motor_on_relay_state=False``), le
        ``default_state`` du Shelly MOTOR doit être réglé côté Shelly UI à
        **« ON »** (relais fermé) pour que le moteur reste à l'arrêt au boot
        du Shelly. À régler une fois lors de l'install terrain ; indépendant
        du code Python.

    Architecture **2 Shellys distincts** (Shelly Gen 1 × 2, 1 relais
    chacun) :
      - ``host_motor`` + ``relay_motor`` = Shelly MOTOR ;
      - ``host_dir``   + ``relay_dir``   = Shelly DIR.
    Comme les 2 Shellys ont des IPs différentes, ``relay_motor`` et
    ``relay_dir`` peuvent valoir le même index (0 par défaut, seul relais
    du Shelly 1).

    Aucune valeur terrain (IP, indices relais, conventions) en dur — tout
    via constructeur, rempli par `MotorShellyConfig` chargé depuis
    ``data/config.json``.
    """

    def __init__(
        self,
        host_motor: str,
        host_dir: str,
        relay_motor: int = 0,
        relay_dir: int = 0,
        open_dir_state: bool = True,
        motor_on_relay_state: bool = False,
        api: str = "rpc",
        timeout_s: float = 3.0,
        urlopen=None,
    ) -> None:
        if api not in ("rpc", "legacy"):
            raise ValueError("api must be 'rpc' (Gen 2) or 'legacy' (Gen 1), got " + repr(api))
        self._host_motor = host_motor
        self._host_dir = host_dir
        self._relay_motor = int(relay_motor)
        self._relay_dir = int(relay_dir)
        self._open_dir_state = bool(open_dir_state)
        self._motor_on_relay_state = bool(motor_on_relay_state)
        self._api = api
        self._timeout_s = float(timeout_s)
        self._urlopen = urlopen or urllib.request.urlopen

    # ------------------------------------------------------------------
    # API publique
    # ------------------------------------------------------------------

    def set_direction(self, open_direction: bool) -> None:
        """Positionne le relais DIR (Shelly host_dir) pour le sens demandé.

        Args:
            open_direction: True pour le sens ouverture cimier, False pour
                fermeture. La traduction en état physique du relais dépend
                de ``open_dir_state`` injecté à la construction.
        """
        relay_state = bool(open_direction) if self._open_dir_state else (not bool(open_direction))
        self._set_relay(self._host_dir, self._relay_dir, relay_state, timer_s=0.0)

    def turn_on(self, timer_s: float = 0.0) -> None:
        """Démarre le moteur.

        L'état physique du relais dépend de ``motor_on_relay_state`` :
        True → relais ON (NO standard), False → relais OFF (NC, cas Serge).

        Args:
            timer_s: si > 0, ``toggle_after`` Shelly fait revenir le relais
                à son état opposé après N secondes (= moteur OFF) — filet
                de sécurité indépendant du Pi en cas de WiFi-drop. 0 = pas
                de timer (le Pi est seul responsable du stop).
        """
        if timer_s < 0:
            raise ValueError("timer_s must be >= 0, got " + str(timer_s))
        self._set_relay(
            self._host_motor,
            self._relay_motor,
            self._motor_on_relay_state,
            timer_s=float(timer_s),
        )

    def turn_off(self) -> None:
        """Coupe le moteur (état physique du relais inversé de ``turn_on()``)."""
        self._set_relay(
            self._host_motor,
            self._relay_motor,
            not self._motor_on_relay_state,
            timer_s=0.0,
        )

    # ------------------------------------------------------------------
    # Properties (introspection / debug)
    # ------------------------------------------------------------------

    @property
    def host_motor(self) -> str:
        return self._host_motor

    @property
    def host_dir(self) -> str:
        return self._host_dir

    @property
    def api(self) -> str:
        return self._api

    @property
    def relay_motor(self) -> int:
        return self._relay_motor

    @property
    def relay_dir(self) -> int:
        return self._relay_dir

    @property
    def motor_on_relay_state(self) -> bool:
        return self._motor_on_relay_state

    # ------------------------------------------------------------------
    # Internals
    # ------------------------------------------------------------------

    def _build_url(self, host: str, relay_id: int, on: bool, timer_s: float) -> str:
        timer_int = int(timer_s) if timer_s > 0 else 0
        if self._api == "rpc":
            url = (
                "http://"
                + host
                + "/rpc/Switch.Set?id="
                + str(relay_id)
                + "&on="
                + ("true" if on else "false")
            )
            if timer_int > 0:
                url += "&toggle_after=" + str(timer_int)
            return url
        # legacy (Gen 1)
        url = "http://" + host + "/relay/" + str(relay_id) + "?turn=" + ("on" if on else "off")
        if timer_int > 0:
            url += "&timer=" + str(timer_int)
        return url

    def _set_relay(self, host: str, relay_id: int, on: bool, timer_s: float) -> None:
        url = self._build_url(host, relay_id, on, timer_s)
        try:
            with self._urlopen(url, timeout=self._timeout_s) as resp:
                status = getattr(resp, "status", 200)
                if status != 200:
                    raise MotorShellyError("Shelly HTTP " + str(status))
                resp.read()
        except urllib.error.URLError as exc:
            raise MotorShellyError("Shelly unreachable: " + str(exc.reason)) from exc
        except OSError as exc:
            raise MotorShellyError("Shelly socket error: " + str(exc)) from exc


class NoopMotorShelly:
    """Double inerte de MotorShelly : aucune requête réseau.

    Utilisé quand la config motor_shelly est incomplète (host_motor ou
    host_dir vide) — typiquement install terrain pas encore câblée, ou en
    tests qui veulent juste un placeholder. Toutes les méthodes sont des
    no-ops loggées pour la traçabilité.

    Les logs sont en WARNING car en production, ce double signifie que
    l'install n'est pas encore câblée (host_motor/host_dir vides dans la
    config) — état dégradé qui mérite un signal visible.
    """

    def set_direction(self, open_direction: bool) -> None:
        logger.warning("cimier_event=noop_motor call=set_direction open=%s", open_direction)

    def turn_on(self, timer_s: float = 0.0) -> None:
        logger.warning("cimier_event=noop_motor call=turn_on timer_s=%.1f", timer_s)

    def turn_off(self) -> None:
        logger.warning("cimier_event=noop_motor call=turn_off")
