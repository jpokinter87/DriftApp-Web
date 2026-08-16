"""Dialogue RPC Gen 2 partagé avec les Shelly (``Input.GetStatus``).

Un seul endroit où vivent la construction d'URL, le timeout, le typage des
erreurs et la validation du payload. Consommé par :

  - ``ShellySwitchReader`` — butées HAUT/BAS du cimier (Shelly Uni+ .84) ;
  - ``ShellyRainWeatherProvider`` — capteur de pluie (Shelly Plus Uni .87).

L'argument ``urlopen`` permet d'injecter un double dans les tests.
Aucune valeur terrain ici : host, id et timeout viennent de l'appelant.
"""

from __future__ import annotations

import json
import urllib.error
import urllib.request
from typing import Any, Dict, Optional, Tuple


class ShellyRpcError(Exception):
    """Échec de lecture d'une entrée Shelly (réseau, HTTP, payload)."""


def read_input_state(
    host: str,
    input_id: int,
    timeout_s: float = 3.0,
    urlopen: Optional[Any] = None,
) -> Tuple[bool, Dict[str, Any]]:
    """Lit ``GET http://<host>/rpc/Input.GetStatus?id=<n>``.

    Returns:
        ``(state, payload)`` — ``state`` est le booléen brut rapporté par le
        Shelly, sans interprétation métier (l'inversion éventuelle appartient
        à l'appelant, qui seul connaît son câblage).

    Raises:
        ShellyRpcError: hôte injoignable, HTTP ≠ 200, JSON invalide, payload
            sans clé ``state``, ou ``state`` non booléen (entrée *stateless*).
    """
    opener = urlopen or urllib.request.urlopen
    url = "http://" + host + "/rpc/Input.GetStatus?id=" + str(int(input_id))
    try:
        with opener(url, timeout=float(timeout_s)) as resp:
            status = getattr(resp, "status", 200)
            raw = resp.read()
    except urllib.error.URLError as exc:
        raise ShellyRpcError("Shelly unreachable: " + str(exc.reason)) from exc
    except OSError as exc:
        raise ShellyRpcError("Shelly socket error: " + str(exc)) from exc
    if status != 200:
        raise ShellyRpcError("Shelly HTTP " + str(status))
    try:
        payload = json.loads(raw.decode("utf-8"))
    except (ValueError, UnicodeDecodeError) as exc:
        raise ShellyRpcError("Shelly JSON invalide: " + str(exc)) from exc
    if not isinstance(payload, dict) or "state" not in payload:
        raise ShellyRpcError("Shelly payload sans 'state': " + repr(payload))
    state = payload["state"]
    if not isinstance(state, bool):
        # `state` vaut null quand l'entrée est *stateless* : type `button`
        # (ou `analog`/`count`), ou entrée désactivée. `bool(None)` valait
        # False, c'est-à-dire « pas de pluie » côté capteur et « butée
        # atteinte » côté microswitches — le sens dangereux dans les deux cas,
        # et sans aucune trace. Une entrée mal typée est un défaut de
        # configuration, pas une mesure : on la traite comme une lecture
        # impossible (fail-safe des appelants).
        raise ShellyRpcError(
            "Shelly 'state' non booléen (" + repr(state) + ") — entrée en type "
            "button/analog ou désactivée ? Vérifier Input.GetConfig?id=" + str(int(input_id))
        )
    return state, payload
