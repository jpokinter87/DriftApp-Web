"""Lecture de l'AD/Déc pointée par l'ASIAIR de la monture.

Protocole relevé par Serge (20/10/2026, ``test_suivi5.py``) : JSON-RPC sur une
connexion TCP (port 4400), un message JSON par ligne terminée par CRLF. On
envoie ``scope_get_info`` ; la réponse porte ``result.RA`` (heures) et
``result.Dec`` (degrés). L'ASIAIR émet aussi des événements non sollicités sur
la même connexion : on ne retient que la réponse portant notre ``id``.

Aucune valeur terrain ici : host, port et délai viennent de l'appelant
(section ``asiair`` de ``data/config.json``).
"""

from __future__ import annotations

import json
import socket
import time
from typing import List, NamedTuple, Optional, Tuple

REQUEST_ID = 501
COTES_PIED = ("pier_east", "pier_west")


class AsiairError(Exception):
    """Lecture impossible (réseau, délai, réponse d'erreur ou incomplète)."""


class EtatMonture(NamedTuple):
    """Côté du pied (``"pier_east"``, ``"pier_west"`` ou ``None`` si inconnu) et
    écart au méridien selon l'ASIAIR, en heures : > 0 avant le passage, < 0 après.
    v6.30 : temps sidéral de la monture (heures) et heure de la lecture (epoch), pour
    le comparer à celui du site."""

    pier: Optional[str]
    delta_h: float
    lst_h: Optional[float] = None
    lu_a: Optional[float] = None


def lire_coordonnees(host: str, port: int, timeout_s: float) -> Tuple[float, float]:
    """Interroge l'ASIAIR et renvoie ``(ra_deg, dec_deg)`` telles que l'ASIAIR
    les donne, c'est-à-dire en **JNow** (vérifié par Serge, 20/10/2026). La
    conversion en J2000 appartient à l'appelant.

    Raises:
        AsiairError: message lisible par l'opérateur.
    """
    (result,) = _requetes(host, port, timeout_s, ["scope_get_info"])
    try:
        ra_h, dec_deg = float(result["RA"]), float(result["Dec"])
    except (KeyError, TypeError, ValueError):
        raise AsiairError("réponse sans coordonnées (monture connectée ?)") from None
    if not -90.0 <= dec_deg <= 90.0:
        raise AsiairError(f"déclinaison hors bornes ({dec_deg})")
    return (ra_h * 15.0) % 360.0, dec_deg


def lire_etat_monture(host: str, port: int, timeout_s: float) -> EtatMonture:
    """Côté du pied et écart au méridien de la monture, sur une seule connexion.

    ``delta_h = range12(RA − sidereal_time)`` de ``scope_get_info`` : le calcul
    du firmware ASIAIR pour décider du retournement (``meridian_flip.cpp``).

    Raises:
        AsiairError: message lisible par l'opérateur.
    """
    info, pier = _requetes(host, port, timeout_s, ["scope_get_info", "scope_get_pierside"])
    try:
        ra_h, lst_h = float(info["RA"]), float(info["sidereal_time"])
    except (KeyError, TypeError, ValueError):
        raise AsiairError("réponse sans temps sidéral (monture connectée ?)") from None
    delta_h = (ra_h - lst_h + 12.0) % 24.0 - 12.0
    return EtatMonture(pier if pier in COTES_PIED else None, delta_h, lst_h, time.time())


def _requetes(host: str, port: int, timeout_s: float, methods: List[str]) -> list:
    """Envoie les `methods` (ids REQUEST_ID, REQUEST_ID+1…) sur une connexion et
    renvoie leurs ``result`` dans le même ordre."""
    ids = [REQUEST_ID + i for i in range(len(methods))]
    resultats: dict = {}
    echeance = time.monotonic() + timeout_s
    try:
        with socket.create_connection((host, port), timeout=timeout_s) as s:
            for i, method in zip(ids, methods):
                s.sendall((json.dumps({"id": i, "method": method}) + "\r\n").encode())
            tampon = b""
            while len(resultats) < len(ids):
                reste = echeance - time.monotonic()
                if reste <= 0:
                    raise TimeoutError
                s.settimeout(reste)
                morceau = s.recv(8192)
                if not morceau:
                    raise ConnectionError("connexion fermée sans réponse")
                tampon += morceau
                *lignes, tampon = tampon.split(b"\n")
                for ligne in lignes:
                    msg = _decoder(ligne)
                    if msg is None or msg.get("id") not in ids:
                        continue
                    if "error" in msg:
                        raise AsiairError(f"erreur ASIAIR : {msg['error']}")
                    resultats[msg["id"]] = msg.get("result")
    except AsiairError:
        raise
    except OSError as exc:  # inclut délai dépassé et connexion refusée/fermée
        raise AsiairError(f"ASIAIR injoignable ({host}:{port}) : {_motif(exc)}") from None
    return [resultats[i] for i in ids]


def _motif(exc: OSError) -> str:
    if isinstance(exc, TimeoutError):  # socket.timeout en est un alias (3.10+)
        return "délai dépassé"
    if isinstance(exc, ConnectionRefusedError):
        return "connexion refusée"
    return str(exc)


def _decoder(ligne: bytes):
    try:
        msg = json.loads(ligne.decode(errors="replace"))
    except json.JSONDecodeError:
        return None
    return msg if isinstance(msg, dict) else None
