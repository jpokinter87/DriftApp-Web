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
from typing import Tuple

REQUEST_ID = 501


class AsiairError(Exception):
    """Lecture impossible (réseau, délai, réponse d'erreur ou incomplète)."""


def lire_coordonnees(host: str, port: int, timeout_s: float) -> Tuple[float, float]:
    """Interroge l'ASIAIR et renvoie ``(ra_deg, dec_deg)`` telles que l'ASIAIR
    les donne, c'est-à-dire en **JNow** (vérifié par Serge, 20/10/2026). La
    conversion en J2000 appartient à l'appelant.

    Raises:
        AsiairError: message lisible par l'opérateur.
    """
    result = _requete(host, port, timeout_s, "scope_get_info")
    try:
        ra_h, dec_deg = float(result["RA"]), float(result["Dec"])
    except (KeyError, TypeError, ValueError):
        raise AsiairError("réponse sans coordonnées (monture connectée ?)") from None
    if not -90.0 <= dec_deg <= 90.0:
        raise AsiairError(f"déclinaison hors bornes ({dec_deg})")
    return (ra_h * 15.0) % 360.0, dec_deg


def _requete(host: str, port: int, timeout_s: float, method: str) -> dict:
    """Envoie `method` et renvoie le ``result`` de la réponse portant notre id."""
    echeance = time.monotonic() + timeout_s
    try:
        with socket.create_connection((host, port), timeout=timeout_s) as s:
            s.sendall((json.dumps({"id": REQUEST_ID, "method": method}) + "\r\n").encode())
            tampon = b""
            while True:
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
                    if msg is None or msg.get("id") != REQUEST_ID:
                        continue
                    if "error" in msg:
                        raise AsiairError(f"erreur ASIAIR : {msg['error']}")
                    if not isinstance(msg.get("result"), dict):
                        raise AsiairError("réponse sans coordonnées (monture connectée ?)")
                    return msg["result"]
    except AsiairError:
        raise
    except OSError as exc:  # inclut délai dépassé et connexion refusée/fermée
        raise AsiairError(f"ASIAIR injoignable ({host}:{port}) : {_motif(exc)}") from None


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
