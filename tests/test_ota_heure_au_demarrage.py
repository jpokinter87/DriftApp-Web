"""Démarrage des services à l'heure juste (6.28.6).

Le Pi n'a pas d'horloge sauvegardée : après une coupure de courant, il repart à
l'heure du dernier enregistrement et ne se recale par NTP qu'environ 30 s plus
tard (nuit du 26/10 : saut de +89,6 min le soir, de 08:34 à 11:57 le matin).
Nos services démarrent donc après ``time-sync.target``, que
``systemd-time-wait-sync`` ne laisse passer qu'une fois l'heure synchronisée,
ou au bout d'un délai borné pour qu'un Pi sans internet démarre quand même.
"""

from __future__ import annotations

import re
from pathlib import Path

PROJECT_ROOT = Path(__file__).parent.parent.resolve()
UPDATE_SCRIPT = PROJECT_ROOT / "scripts" / "update_driftapp.sh"
DROP_IN = PROJECT_ROOT / "setup" / "time-wait-sync-timeout.conf"
UNITS = sorted(PROJECT_ROOT.glob("*.service"))


def _valeurs(unit: Path, cle: str) -> list[str]:
    valeurs = []
    for ligne in unit.read_text().splitlines():
        if ligne.startswith(f"{cle}="):
            valeurs.extend(ligne.split("=", 1)[1].split())
    return valeurs


class TestServicesAttendentLHeure:
    def test_chaque_service_demarre_apres_time_sync(self):
        assert UNITS
        for unit in UNITS:
            assert "time-sync.target" in _valeurs(unit, "After"), unit.name

    def test_chaque_service_tire_time_sync(self):
        for unit in UNITS:
            assert "time-sync.target" in _valeurs(unit, "Wants"), unit.name


class TestAttenteBornee:
    def test_delai_maximal_de_l_attente(self):
        # Sans délai, un Pi sans internet ne démarrerait jamais la coupole.
        texte = DROP_IN.read_text()
        assert "[Service]" in texte
        delai = re.search(r"^TimeoutStartSec=(\d+)$", texte, re.MULTILINE)
        assert delai is not None
        assert 0 < int(delai.group(1)) <= 120


class TestInstallationParLaMaj:
    def _etape_4(self) -> str:
        contenu = UPDATE_SCRIPT.read_text()
        return contenu[contenu.find("ÉTAPE 4/5") : contenu.find("ÉTAPE 5/5")]

    def test_installe_le_delai_maximal(self):
        etape = self._etape_4()
        assert "setup/time-wait-sync-timeout.conf" in etape
        assert "systemd-time-wait-sync.service.d" in etape

    def test_active_l_attente_de_l_heure(self):
        assert "systemctl enable systemd-time-wait-sync.service" in self._etape_4()

    def test_delai_installe_avant_daemon_reload(self):
        etape = self._etape_4()
        assert etape.find("time-wait-sync-timeout.conf") < etape.find("daemon-reload")
