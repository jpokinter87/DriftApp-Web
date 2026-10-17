"""Tests du script d'acquisition de l'inclinomètre WitMotion (scripts/diagnostics/inclinometre_monture.py)."""

import importlib.util
import struct
import sys
from pathlib import Path

import pytest

_SCRIPT = (
    Path(__file__).resolve().parents[1] / "scripts" / "diagnostics" / "inclinometre_monture.py"
)


@pytest.fixture(scope="module")
def incl():
    """Charge le script standalone comme un module importable."""
    spec = importlib.util.spec_from_file_location("inclinometre_monture", _SCRIPT)
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


def _trame(ax=0, ay=0, az=0, wx=0, wy=0, wz=0, roll=0, pitch=0, yaw=0):
    """Trame WitMotion 0x55 0x61 + 9 entiers 16 bits signés little-endian (valeurs brutes)."""
    return bytes([0x55, 0x61]) + struct.pack("<9h", ax, ay, az, wx, wy, wz, roll, pitch, yaw)


class TestDecodage:
    def test_trame_decodee_aux_bonnes_echelles(self, incl):
        # az = 2048 → 1 g ; wx = 1638 → 99,98 °/s ; roll = 16384 → 90° ; pitch = -8192 → -45°
        (m,), reste = incl.extraire_trames(_trame(az=2048, wx=1638, roll=16384, pitch=-8192))
        assert reste == b""
        assert m.az_g == pytest.approx(1.0)
        assert m.wx_dps == pytest.approx(1638 / 32768 * 2000)
        assert m.roll_deg == pytest.approx(90.0)
        assert m.pitch_deg == pytest.approx(-45.0)

    def test_plusieurs_trames_dans_une_notification(self, incl):
        mesures, reste = incl.extraire_trames(_trame(roll=100) + _trame(roll=200))
        assert [round(m.roll_deg / 180 * 32768) for m in mesures] == [100, 200]
        assert reste == b""

    def test_trame_coupee_gardee_pour_la_notification_suivante(self, incl):
        trame = _trame(roll=300)
        mesures, reste = incl.extraire_trames(trame[:7])
        assert mesures == [] and reste == trame[:7]
        mesures, reste = incl.extraire_trames(reste + trame[7:])
        assert len(mesures) == 1 and reste == b""

    def test_octets_parasites_et_reponses_de_registre_ignores(self, incl):
        reponse_registre = bytes([0x55, 0x71]) + bytes(18)
        mesures, reste = incl.extraire_trames(b"\x00\x12" + reponse_registre + _trame(yaw=50))
        assert len(mesures) == 1
        assert reste == b""


class TestDetecteurMouvement:
    def test_debut_et_fin_d_un_mouvement(self, incl):
        det = incl.DetecteurMouvement(seuil_dps=1.0, calme_s=2.0)
        assert det.mise_a_jour(0.0, 0.1, roll=10.0, pitch=5.0) is None
        assert det.mise_a_jour(1.0, 3.0, roll=10.0, pitch=5.0) == "debut"
        assert det.mise_a_jour(30.0, 4.0, roll=-150.0, pitch=20.0) is None
        assert (
            det.mise_a_jour(31.0, 0.1, roll=-170.0, pitch=25.0) is None
        )  # calme depuis moins de 2 s
        assert det.mise_a_jour(33.5, 0.1, roll=-170.0, pitch=25.0) == "fin"
        assert det.duree_s == pytest.approx(30.0)
        assert det.delta_roll == pytest.approx(180.0)
        assert det.delta_pitch == pytest.approx(20.0)

    def test_delta_de_roulis_pris_au_plus_court(self, incl):
        det = incl.DetecteurMouvement(seuil_dps=1.0, calme_s=0.5)
        det.mise_a_jour(0.0, 5.0, roll=170.0, pitch=0.0)
        det.mise_a_jour(1.0, 0.0, roll=-170.0, pitch=0.0)
        assert det.mise_a_jour(2.0, 0.0, roll=-170.0, pitch=0.0) == "fin"
        assert det.delta_roll == pytest.approx(20.0)

    def test_suivi_sideral_lent_n_est_pas_un_mouvement(self, incl):
        det = incl.DetecteurMouvement(seuil_dps=1.0, calme_s=2.0)
        for t in range(60):
            assert det.mise_a_jour(float(t), 0.004, roll=float(t) * 0.004, pitch=0.0) is None
