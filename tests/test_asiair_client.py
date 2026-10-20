"""Lecture de l'AD/Déc pointée par l'ASIAIR (bouton « ASIAIR » du dashboard).

Les tests dialoguent avec un vrai serveur TCP local qui imite l'ASIAIR :
une ligne JSON par message, terminée par CRLF.
"""

import json
import socket
import threading

import pytest

from core.hardware.asiair_client import AsiairError, lire_coordonnees


def _faux_asiair(reponses):
    """Démarre un serveur qui lit une requête puis envoie `reponses(requete)`.

    `reponses` reçoit la requête décodée et renvoie la liste des lignes brutes
    à envoyer (ou None pour ne rien répondre). Retourne le port.
    """
    serveur = socket.socket()
    serveur.bind(("127.0.0.1", 0))
    serveur.listen(1)

    def servir():
        conn, _ = serveur.accept()
        with conn:
            requete = json.loads(conn.makefile().readline())
            lignes = reponses(requete)
            if lignes is None:
                conn.recv(1)  # attend que le client abandonne
                return
            for ligne in lignes:
                conn.sendall((ligne + "\r\n").encode())
        serveur.close()

    threading.Thread(target=servir, daemon=True).start()
    return serveur.getsockname()[1]


def _resultat(requete, result):
    return json.dumps({"jsonrpc": "2.0", "id": requete["id"], "result": result})


def test_coordonnees_converties_en_degres():
    port = _faux_asiair(
        lambda r: [_resultat(r, {"RA": 0.712305, "Dec": 41.269, "sidereal_time": 3.5})]
    )
    ra_deg, dec_deg = lire_coordonnees("127.0.0.1", port, 2.0)
    assert ra_deg == pytest.approx(10.684575)
    assert dec_deg == pytest.approx(41.269)


def test_requete_scope_get_info():
    recu = {}

    def reponses(requete):
        recu.update(requete)
        return [_resultat(requete, {"RA": 1.0, "Dec": 2.0})]

    lire_coordonnees("127.0.0.1", _faux_asiair(reponses), 2.0)
    assert recu["method"] == "scope_get_info"


def test_evenements_non_sollicites_ignores():
    def reponses(requete):
        return [
            json.dumps({"Event": "PiStatus", "temp": 41.2}),
            "pas du json",
            json.dumps({"jsonrpc": "2.0", "id": requete["id"] + 1, "result": {"RA": 9, "Dec": 9}}),
            _resultat(requete, {"RA": 12.0, "Dec": -30.5}),
        ]

    assert lire_coordonnees("127.0.0.1", _faux_asiair(reponses), 2.0) == (180.0, -30.5)


def test_ra_ramenee_dans_0_360():
    port = _faux_asiair(lambda r: [_resultat(r, {"RA": 24.0, "Dec": 0.0})])
    assert lire_coordonnees("127.0.0.1", port, 2.0) == (0.0, 0.0)


def test_reponse_erreur_jsonrpc():
    def reponses(requete):
        return [json.dumps({"id": requete["id"], "error": {"code": 1, "message": "no mount"}})]

    with pytest.raises(AsiairError, match="no mount"):
        lire_coordonnees("127.0.0.1", _faux_asiair(reponses), 2.0)


def test_reponse_sans_coordonnees():
    port = _faux_asiair(lambda r: [_resultat(r, {"sidereal_time": 3.5})])
    with pytest.raises(AsiairError, match="sans coordonnées"):
        lire_coordonnees("127.0.0.1", port, 2.0)


def test_declinaison_hors_bornes():
    port = _faux_asiair(lambda r: [_resultat(r, {"RA": 1.0, "Dec": 95.0})])
    with pytest.raises(AsiairError, match="hors bornes"):
        lire_coordonnees("127.0.0.1", port, 2.0)


def test_pas_de_reponse_dans_le_delai():
    port = _faux_asiair(lambda r: None)
    with pytest.raises(AsiairError, match="injoignable .*délai dépassé"):
        lire_coordonnees("127.0.0.1", port, 0.3)


def test_connexion_fermee_sans_reponse():
    port = _faux_asiair(lambda r: [])
    with pytest.raises(AsiairError, match="injoignable"):
        lire_coordonnees("127.0.0.1", port, 2.0)


def test_connexion_refusee():
    s = socket.socket()
    s.bind(("127.0.0.1", 0))
    port = s.getsockname()[1]
    s.close()  # port libre, personne n'écoute
    with pytest.raises(AsiairError, match="injoignable"):
        lire_coordonnees("127.0.0.1", port, 1.0)
