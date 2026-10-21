"""Surveillance du côté du pied de la monture contre un faux ASIAIR TCP (6.24)."""

import json
import socket
import threading
import time

from core.hardware.asiair_watcher import AsiairPierWatcher


class FauxAsiair:
    """Serveur TCP qui accepte des connexions successives ; `muet` le fait se taire."""

    def __init__(self, pier="pier_west", ra=17.62, lst=17.61):
        self.pier, self.ra, self.lst = pier, ra, lst
        self.muet = False
        self._serveur = socket.socket()
        self._serveur.bind(("127.0.0.1", 0))
        self._serveur.listen(5)
        self.port = self._serveur.getsockname()[1]
        threading.Thread(target=self._accepter, daemon=True).start()

    def _accepter(self):
        while True:
            try:
                conn, _ = self._serveur.accept()
            except OSError:
                return
            threading.Thread(target=self._servir, args=(conn,), daemon=True).start()

    def _servir(self, conn):
        with conn:
            for ligne in conn.makefile():
                if self.muet:
                    continue
                req = json.loads(ligne)
                if req["method"] == "scope_get_info":
                    result = {"RA": self.ra, "Dec": 68.75, "sidereal_time": self.lst}
                else:
                    result = self.pier
                conn.sendall((json.dumps({"id": req["id"], "result": result}) + "\r\n").encode())

    def fermer(self):
        self._serveur.close()


def _attendre(condition, delai=3.0):
    fin = time.monotonic() + delai
    while time.monotonic() < fin:
        if condition():
            return True
        time.sleep(0.02)
    return False


def test_etat_frais_puis_changement_de_cote():
    faux = FauxAsiair()
    w = AsiairPierWatcher("127.0.0.1", faux.port, 0.5, periode_s=0.05).start()
    try:
        assert _attendre(lambda: w.etat_frais() is not None)
        assert w.etat_frais().pier == "pier_west"
        faux.pier = "pier_east"
        assert _attendre(lambda: w.etat_frais().pier == "pier_east")
    finally:
        w.stop()
        faux.fermer()


def test_etat_perime_quand_l_asiair_se_tait():
    faux = FauxAsiair()
    w = AsiairPierWatcher("127.0.0.1", faux.port, 0.1, periode_s=0.05).start()
    try:
        assert _attendre(lambda: w.etat_frais(max_age_s=0.3) is not None)
        faux.muet = True
        assert _attendre(lambda: w.etat_frais(max_age_s=0.3) is None)
    finally:
        w.stop()
        faux.fermer()


def test_asiair_injoignable_sans_exception(caplog):
    s = socket.socket()
    s.bind(("127.0.0.1", 0))
    port = s.getsockname()[1]
    s.close()
    w = AsiairPierWatcher("127.0.0.1", port, 0.1, periode_s=0.02).start()
    time.sleep(0.2)
    assert w.etat_frais() is None
    assert w._thread.is_alive()
    w.stop()
    assert not w._thread.is_alive()
    assert sum("asiair_pier_unreachable" in r.message for r in caplog.records) == 1
