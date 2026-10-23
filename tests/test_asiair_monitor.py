"""Tests de la surveillance permanente de la monture via l'ASIAIR (services/asiair_monitor.py).

L'essai de bout en bout dialogue avec un vrai serveur TCP local qui imite le port
monture de l'ASIAIR : une ligne JSON par message, terminée par CRLF.
"""

import json
import socket
import threading
from datetime import datetime, timedelta

import pytest

from core.config.config_loader import AsiairConfig
from services import asiair_monitor as monitor


def _info(ra_h, lst_h):
    return {"id": 601, "result": {"RA": ra_h, "Dec": 34.2, "sidereal_time": lst_h}}


def _lire(chemin):
    return [json.loads(x) for x in chemin.read_text(encoding="utf-8").splitlines()]


class TestDeltaMeridien:
    def test_avant_et_apres_le_passage(self):
        assert monitor.delta_meridien_h(21.5, 21.0) == pytest.approx(0.5)
        assert monitor.delta_meridien_h(21.0, 21.5) == pytest.approx(-0.5)

    def test_passage_par_0h(self):
        assert monitor.delta_meridien_h(0.2, 23.9) == pytest.approx(0.3)
        assert monitor.delta_meridien_h(23.9, 0.2) == pytest.approx(-0.3)


class TestEtat:
    def test_passage_au_meridien_signale_une_fois(self):
        etat = monitor.Etat()
        assert etat.traiter(_info(21.01, 21.0)) == []
        (ligne,) = etat.traiter(_info(21.0, 21.01))
        assert "PASSAGE AU MÉRIDIEN" in ligne
        assert etat.traiter(_info(21.0, 21.02)) == []

    def test_goto_vers_une_cible_deja_passee_n_est_pas_un_passage(self):
        etat = monitor.Etat()
        etat.traiter(_info(2.0, 21.0))  # cible 5 h avant le méridien
        assert etat.traiter(_info(18.0, 21.0)) == []  # GOTO : 3 h après

    def test_changement_de_cote_du_pied(self):
        etat = monitor.Etat()
        assert etat.traiter({"id": 602, "result": "pier_east"}) == ["côté du pied : pier_east"]
        assert etat.traiter({"id": 602, "result": "pier_east"}) == []
        (ligne,) = etat.traiter({"id": 602, "result": "pier_west"})
        assert "CÔTÉ DU PIED CHANGÉ : pier_east -> pier_west" in ligne

    def test_changement_de_suivi(self):
        etat = monitor.Etat()
        assert etat.traiter({"id": 603, "result": True}) == ["suivi de la monture : True"]
        assert etat.traiter({"id": 603, "result": True}) == []
        assert etat.traiter({"id": 603, "result": False}) == ["suivi de la monture : False"]

    def test_erreur_affichee_une_seule_fois_par_requete(self):
        etat = monitor.Etat()
        erreur = {"id": 602, "error": {"code": 1, "message": "not capable"}}
        assert len(etat.traiter(erreur)) == 1
        assert etat.traiter(erreur) == []

    def test_evenements_monture_affiches_les_autres_seulement_journalises(self):
        etat = monitor.Etat()
        (ligne,) = etat.traiter({"Event": "ScopeGoto", "state": "start"})
        assert "ScopeGoto" in ligne
        assert etat.traiter({"Event": "Exposure", "state": "working"}) == []

    def test_message_indi_affiche(self):
        etat = monitor.Etat()
        msg = {
            "Event": "INDIServer",
            "Timestamp": "2154.8",
            "Msg": "2026-10-21T15:14:57: [INFO] Target pier side set to EAST ",
        }
        assert etat.traiter(msg) == [
            "INDI 2026-10-21T15:14:57: [INFO] Target pier side set to EAST"
        ]


class TestJournalNuit:
    def test_bascule_de_fichier_a_midi(self, tmp_path):
        heure = [datetime(2026, 10, 22, 11, 59, 59)]
        journal = monitor.JournalNuit(tmp_path, horloge=lambda: heure[0])
        journal.noter({"sonde": "a"})
        heure[0] = datetime(2026, 10, 22, 12, 0, 1)
        journal.noter({"sonde": "b"})

        (avant,) = _lire(tmp_path / "2026-10-21.jsonl")
        (apres,) = _lire(tmp_path / "2026-10-22.jsonl")
        assert avant["sonde"] == "a" and avant["heure"] == "11:59:59"
        assert apres["sonde"] == "b" and "t" in apres

    def test_purge_au_dela_de_14_nuits(self, tmp_path):
        maintenant = datetime(2026, 10, 23, 22, 0)
        vieux = tmp_path / f"{(maintenant - timedelta(days=15)):%Y-%m-%d}.jsonl"
        recent = tmp_path / f"{(maintenant - timedelta(days=13)):%Y-%m-%d}.jsonl"
        vieux.write_text("{}\n")
        recent.write_text("{}\n")

        monitor.JournalNuit(tmp_path, horloge=lambda: maintenant).noter({"sonde": "x"})

        assert not vieux.exists()
        assert recent.exists()


def _faux_asiair():
    """Serveur qui répond aux trois lectures et pousse deux événements non sollicités ;
    le côté du pied passe à l'ouest au deuxième cycle de lectures. Retourne le port."""
    serveur = socket.socket()
    serveur.bind(("127.0.0.1", 0))
    serveur.listen(1)

    def servir():
        conn, _ = serveur.accept()
        with conn, conn.makefile() as lecteur:
            conn.sendall(b'{"Event":"ScopeTrack","state":"on"}\r\n')
            conn.sendall(
                b'{"Event":"INDIServer","Msg":"x: [INFO] Start Tracking (Sidereal). "}\r\n'
            )
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


def _port_libre():
    libre = socket.socket()
    libre.bind(("127.0.0.1", 0))
    port = libre.getsockname()[1]
    libre.close()
    return port


def test_nuit_miniature_contre_un_faux_asiair(tmp_path):
    journal = monitor.JournalNuit(tmp_path)
    lignes = []
    monitor.surveiller(
        "127.0.0.1", _faux_asiair(), 0.2, journal, duree_s=0.6, afficher=lignes.append
    )

    console = "\n".join(lignes)
    assert "connecté à l'ASIAIR" in console
    assert "événement ScopeTrack" in console
    assert "INDI x: [INFO] Start Tracking (Sidereal)." in console
    assert "CÔTÉ DU PIED CHANGÉ : pier_east -> pier_west" in console

    (fichier,) = tmp_path.glob("*.jsonl")
    assert fichier.stem == monitor.night_key(datetime.now())
    enregistrements = _lire(fichier)
    recus = [e["msg"] for e in enregistrements if "msg" in e]
    assert {"Event": "ScopeTrack", "state": "on"} in recus
    assert {m.get("id") for m in recus} >= {601, 602, 603}
    assert all("t" in e and "heure" in e for e in enregistrements)


def test_coupure_journalisee_une_seule_fois(tmp_path, monkeypatch):
    monkeypatch.setattr(monitor, "RECONNEXION_S", 0.05)
    journal = monitor.JournalNuit(tmp_path)
    lignes = []
    monitor.surveiller(
        "127.0.0.1", _port_libre(), 1.0, journal, duree_s=0.4, afficher=lignes.append
    )

    assert len([x for x in lignes if "injoignable" in x]) == 1
    (fichier,) = tmp_path.glob("*.jsonl")
    (premier,) = _lire(fichier)
    assert premier["sonde"] == "erreur"


def test_retour_apres_coupure_signale(tmp_path, monkeypatch):
    monkeypatch.setattr(monitor, "RECONNEXION_S", 0.05)
    port = _port_libre()
    serveur_pret = []

    def ouvrir_plus_tard():
        serveur = socket.socket()
        serveur.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        serveur.bind(("127.0.0.1", port))
        serveur.listen(1)
        serveur_pret.append(serveur)
        conn, _ = serveur.accept()
        with conn, conn.makefile() as lecteur:
            for _ in lecteur:
                pass

    timer = threading.Timer(0.2, ouvrir_plus_tard)
    timer.daemon = True
    timer.start()
    journal = monitor.JournalNuit(tmp_path)
    lignes = []
    monitor.surveiller("127.0.0.1", port, 1.0, journal, duree_s=0.6, afficher=lignes.append)
    for serveur in serveur_pret:
        serveur.close()

    assert any("ASIAIR de retour" in x for x in lignes)
    (fichier,) = tmp_path.glob("*.jsonl")
    sondes = [e["sonde"] for e in _lire(fichier) if "sonde" in e]
    assert sondes == ["erreur", "reconnecté"]


class TestCible:
    def test_desactivee(self):
        assert monitor.cible(AsiairConfig(host="10.0.0.5", monitor_enabled=False)) is None

    def test_sans_host(self):
        assert monitor.cible(AsiairConfig(host="")) is None

    def test_active(self):
        assert monitor.cible(AsiairConfig(host="10.0.0.5", port=4401)) == ("10.0.0.5", 4401)
