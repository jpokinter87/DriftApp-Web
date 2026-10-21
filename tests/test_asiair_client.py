"""Lecture de l'AD/Déc pointée par l'ASIAIR (bouton « ASIAIR » du dashboard).

Les tests dialoguent avec un vrai serveur TCP local qui imite l'ASIAIR :
une ligne JSON par message, terminée par CRLF.
"""

import json
import socket
import threading

import pytest

from core.hardware.asiair_client import (
    AsiairError,
    EtatMonture,
    lire_coordonnees,
    lire_etat_monture,
)


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


# --- lire_etat_monture (bascule coupole sur le côté du pied, 6.24) ---


def _faux_asiair_monture(info, pier, evenement_avant=False):
    """Répond à chaque requête de la connexion : `info` pour scope_get_info,
    `pier` pour scope_get_pierside (le résultat est une chaîne, comme l'ASIAIR)."""

    def servir_requete(requete):
        lignes = [json.dumps({"Event": "ScopeTrack", "state": "on"})] if evenement_avant else []
        if requete["method"] == "scope_get_info":
            lignes.append(_resultat(requete, info))
        elif requete["method"] == "scope_get_pierside":
            lignes.append(_resultat(requete, pier))
        return lignes

    serveur = socket.socket()
    serveur.bind(("127.0.0.1", 0))
    serveur.listen(1)

    def servir():
        conn, _ = serveur.accept()
        with conn:
            for ligne in conn.makefile():
                for rep in servir_requete(json.loads(ligne)):
                    conn.sendall((rep + "\r\n").encode())
        serveur.close()

    threading.Thread(target=servir, daemon=True).start()
    return serveur.getsockname()[1]


def test_etat_monture_avant_meridien():
    # Valeurs relevées par la sonde le 21/10 à 17:14:52.
    port = _faux_asiair_monture(
        {"RA": 17.614039, "Dec": 68.749687, "sidereal_time": 17.611908}, "pier_west"
    )
    etat = lire_etat_monture("127.0.0.1", port, 2.0)
    assert etat.pier == "pier_west"
    assert etat.delta_h == pytest.approx(0.002131)


def test_etat_monture_apres_meridien_et_evenements_intercales():
    port = _faux_asiair_monture(
        {"RA": 17.6236, "Dec": 68.75, "sidereal_time": 17.6539}, "pier_east", evenement_avant=True
    )
    etat = lire_etat_monture("127.0.0.1", port, 2.0)
    assert etat == EtatMonture("pier_east", pytest.approx(-0.0303))


@pytest.mark.parametrize(
    "ra_h, lst_h, attendu",
    [(23.9, 0.1, -0.2), (0.1, 23.9, 0.2), (6.0, 18.0, -12.0), (12.0, 1.0, 11.0)],
)
def test_etat_monture_delta_h_ramene_dans_12h(ra_h, lst_h, attendu):
    port = _faux_asiair_monture({"RA": ra_h, "Dec": 10.0, "sidereal_time": lst_h}, "pier_east")
    assert lire_etat_monture("127.0.0.1", port, 2.0).delta_h == pytest.approx(attendu)


def test_etat_monture_cote_inconnu():
    port = _faux_asiair_monture({"RA": 1.0, "Dec": 10.0, "sidereal_time": 1.5}, "pier_unknown")
    assert lire_etat_monture("127.0.0.1", port, 2.0).pier is None


def test_etat_monture_sans_temps_sideral():
    port = _faux_asiair_monture({"RA": 1.0, "Dec": 10.0}, "pier_east")
    with pytest.raises(AsiairError, match="temps sidéral"):
        lire_etat_monture("127.0.0.1", port, 2.0)


def test_etat_monture_injoignable():
    port = _faux_asiair(lambda r: None)
    with pytest.raises(AsiairError, match="injoignable"):
        lire_etat_monture("127.0.0.1", port, 0.3)
