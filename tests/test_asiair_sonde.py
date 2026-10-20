"""Tests de la surveillance de la monture via l'ASIAIR (scripts/diagnostics/asiair_sonde.py).

L'essai de bout en bout dialogue avec un vrai serveur TCP local qui imite le port
monture de l'ASIAIR : une ligne JSON par message, terminée par CRLF.
"""

import importlib.util
import json
import socket
import sys
import threading
from pathlib import Path

import pytest

_SCRIPT = Path(__file__).resolve().parents[1] / "scripts" / "diagnostics" / "asiair_sonde.py"


@pytest.fixture(scope="module")
def sonde():
    """Charge le script standalone comme un module importable."""
    spec = importlib.util.spec_from_file_location("asiair_sonde", _SCRIPT)
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


def _info(ra_h, lst_h):
    return {"id": 601, "result": {"RA": ra_h, "Dec": 34.2, "sidereal_time": lst_h}}


class TestDeltaMeridien:
    def test_avant_et_apres_le_passage(self, sonde):
        assert sonde.delta_meridien_h(21.5, 21.0) == pytest.approx(0.5)
        assert sonde.delta_meridien_h(21.0, 21.5) == pytest.approx(-0.5)

    def test_passage_par_0h(self, sonde):
        assert sonde.delta_meridien_h(0.2, 23.9) == pytest.approx(0.3)
        assert sonde.delta_meridien_h(23.9, 0.2) == pytest.approx(-0.3)


class TestEtat:
    def test_passage_au_meridien_signale_une_fois(self, sonde):
        etat = sonde.Etat()
        assert etat.traiter(_info(21.01, 21.0)) == []
        (ligne,) = etat.traiter(_info(21.0, 21.01))
        assert "PASSAGE AU MÉRIDIEN" in ligne
        assert etat.traiter(_info(21.0, 21.02)) == []

    def test_goto_vers_une_cible_deja_passee_n_est_pas_un_passage(self, sonde):
        etat = sonde.Etat()
        etat.traiter(_info(2.0, 21.0))  # cible 5 h avant le méridien
        assert etat.traiter(_info(18.0, 21.0)) == []  # GOTO : 3 h après

    def test_changement_de_cote_du_pied(self, sonde):
        etat = sonde.Etat()
        assert etat.traiter({"id": 602, "result": "pier_east"}) == ["côté du pied : pier_east"]
        assert etat.traiter({"id": 602, "result": "pier_east"}) == []
        (ligne,) = etat.traiter({"id": 602, "result": "pier_west"})
        assert "CÔTÉ DU PIED CHANGÉ : pier_east -> pier_west" in ligne

    def test_changement_de_suivi(self, sonde):
        etat = sonde.Etat()
        assert etat.traiter({"id": 603, "result": True}) == ["suivi de la monture : True"]
        assert etat.traiter({"id": 603, "result": True}) == []
        assert etat.traiter({"id": 603, "result": False}) == ["suivi de la monture : False"]

    def test_erreur_affichee_une_seule_fois_par_requete(self, sonde):
        etat = sonde.Etat()
        erreur = {"id": 602, "error": {"code": 1, "message": "not capable"}}
        assert len(etat.traiter(erreur)) == 1
        assert etat.traiter(erreur) == []

    def test_evenements_monture_affiches_les_autres_seulement_journalises(self, sonde):
        etat = sonde.Etat()
        (ligne,) = etat.traiter({"Event": "ScopeGoto", "state": "start"})
        assert "ScopeGoto" in ligne
        assert etat.traiter({"Event": "Exposure", "state": "working"}) == []


def _faux_asiair():
    """Serveur qui répond aux trois lectures et pousse un événement non sollicité ;
    le côté du pied passe à l'ouest au deuxième cycle de lectures. Retourne le port."""
    serveur = socket.socket()
    serveur.bind(("127.0.0.1", 0))
    serveur.listen(1)

    def servir():
        conn, _ = serveur.accept()
        with conn, conn.makefile() as lecteur:
            conn.sendall(b'{"Event":"ScopeTrack","state":"on"}\r\n')
            n_pied = 0
            for ligne in lecteur:
                requete = json.loads(ligne)
                if requete["method"] == "scope_get_info":
                    reponse = _info(21.0, 20.99)
                elif requete["method"] == "scope_get_pierside":
                    n_pied += 1
                    reponse = {"id": 602, "result": "pier_east" if n_pied == 1 else "pier_west"}
                else:
                    reponse = {"id": 603, "result": True}
                conn.sendall((json.dumps(reponse) + "\r\n").encode())
        serveur.close()

    threading.Thread(target=servir, daemon=True).start()
    return serveur.getsockname()[1]


def test_nuit_miniature_contre_un_faux_asiair(sonde, tmp_path):
    chemin = tmp_path / "asiair.jsonl"
    lignes = []
    sonde.surveiller("127.0.0.1", _faux_asiair(), 0.2, chemin, duree_s=0.6, afficher=lignes.append)

    console = "\n".join(lignes)
    assert "connecté à l'ASIAIR" in console
    assert "événement ScopeTrack" in console
    assert "CÔTÉ DU PIED CHANGÉ : pier_east -> pier_west" in console

    enregistrements = [json.loads(x) for x in chemin.read_text(encoding="utf-8").splitlines()]
    recus = [e["msg"] for e in enregistrements if "msg" in e]
    assert {"Event": "ScopeTrack", "state": "on"} in recus
    assert {m.get("id") for m in recus} >= {601, 602, 603}
    assert all("t" in e and "heure" in e for e in enregistrements)


def test_asiair_injoignable_journalise_sans_planter(sonde, tmp_path):
    libre = socket.socket()
    libre.bind(("127.0.0.1", 0))
    port = libre.getsockname()[1]
    libre.close()
    chemin = tmp_path / "asiair.jsonl"
    lignes = []
    sonde.surveiller("127.0.0.1", port, 1.0, chemin, duree_s=0.3, afficher=lignes.append)

    assert any("injoignable" in ligne for ligne in lignes)
    (premier,) = [json.loads(x) for x in chemin.read_text(encoding="utf-8").splitlines()]
    assert premier["sonde"] == "erreur"
