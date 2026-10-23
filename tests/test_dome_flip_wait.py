"""Règle d'attente du retournement de la monture avant la bascule de la coupole (6.24)."""

from datetime import datetime, timedelta, timezone

import pytest

from core.hardware.asiair_client import EtatMonture
from core.tracking.dome_flip_wait import (
    AttenteRetournement,
    instant_meridien,
    monture_en_avance,
    monture_en_retard,
)

AVANT = 170.0  # azimut objet, moitié Est : pas encore au méridien
APRES = 190.0  # moitié Ouest : passé au méridien selon DriftApp


class TestMontureEnRetard:
    def test_monture_cote_avant_objet_passe(self):
        assert monture_en_retard(EtatMonture("pier_west", 0.01), APRES)

    def test_objet_pas_encore_au_meridien(self):
        assert not monture_en_retard(EtatMonture("pier_west", 0.01), AVANT)

    def test_monture_deja_retournee(self):
        assert not monture_en_retard(EtatMonture("pier_east", -0.01), APRES)

    def test_meridien_asiair_pas_encore_atteint_ne_compte_pas(self):
        # DriftApp voit le transit avant l'ASIAIR : la coupole doit quand même attendre.
        assert monture_en_retard(EtatMonture("pier_west", +0.005), APRES)

    def test_culmination_nord(self):
        # Objet au-dessus du pôle : azimut 350° = passé au méridien.
        assert monture_en_retard(EtatMonture("pier_west", -0.01), 350.0)
        assert not monture_en_retard(EtatMonture("pier_west", 0.01), 10.0)

    @pytest.mark.parametrize("delta_h", [6.0, -6.0, 11.5, -10.5])
    def test_loin_du_passage_superieur(self, delta_h):
        assert not monture_en_retard(EtatMonture("pier_west", delta_h), APRES)

    def test_cote_inconnu_ou_asiair_muet(self):
        assert not monture_en_retard(EtatMonture(None, 0.01), APRES)
        assert not monture_en_retard(None, APRES)


class TestAttenteRetournement:
    RETARD = EtatMonture("pier_west", -0.01)
    RETOURNEE = EtatMonture("pier_east", -0.02)

    def test_pas_d_attente_en_temps_normal(self):
        a = AttenteRetournement(max_wait_s=1800)
        d = a.evaluer(EtatMonture("pier_west", 0.1), AVANT, 0.0)
        assert (d.attendre, d.evenement) == (False, None)
        assert a.en_cours(0.0) is None

    def test_debut_puis_fin_au_retournement(self):
        a = AttenteRetournement(max_wait_s=1800)
        d = a.evaluer(self.RETARD, APRES, 100.0)
        assert (d.attendre, d.evenement) == (True, "start")
        assert a.evaluer(self.RETARD, APRES, 130.0).attendre
        assert a.en_cours(160.0) == pytest.approx(60.0)
        d = a.evaluer(self.RETOURNEE, APRES, 400.0)
        assert (d.attendre, d.evenement, d.attente_s) == (False, "pierside", 300.0)
        assert a.en_cours(400.0) is None

    def test_asiair_devenu_muet_leve_l_attente(self):
        a = AttenteRetournement(max_wait_s=1800)
        a.evaluer(self.RETARD, APRES, 0.0)
        d = a.evaluer(None, APRES, 60.0)
        assert (d.attendre, d.evenement) == (False, "asiair_silent")

    def test_delai_maximal_puis_pas_de_relance(self):
        a = AttenteRetournement(max_wait_s=1800)
        a.evaluer(self.RETARD, APRES, 0.0)
        assert a.evaluer(self.RETARD, APRES, 1799.0).attendre
        d = a.evaluer(self.RETARD, APRES, 1800.0)
        assert (d.attendre, d.evenement, d.attente_s) == (False, "timeout", 1800.0)
        # Même cause : pas de nouvelle attente, même après un silence de l'ASIAIR.
        assert a.evaluer(self.RETARD, APRES, 1830.0) == (False, None, 0.0)
        assert a.evaluer(None, APRES, 1860.0) == (False, None, 0.0)
        assert a.evaluer(self.RETARD, APRES, 1890.0) == (False, None, 0.0)

    def test_nouvelle_attente_apres_retour_a_la_normale(self):
        a = AttenteRetournement(max_wait_s=60)
        a.evaluer(self.RETARD, APRES, 0.0)
        a.evaluer(self.RETARD, APRES, 60.0)  # timeout
        a.evaluer(self.RETOURNEE, APRES, 90.0)  # monture vue retournée
        assert a.evaluer(self.RETARD, APRES, 120.0).evenement == "start"


class TestMontureEnAvance:
    """6.26 : monture retournée alors que l'objet n'a pas passé le méridien."""

    def test_monture_retournee_objet_pas_encore_passe(self):
        assert monture_en_avance(EtatMonture("pier_east", 0.02), AVANT)

    def test_culmination_nord_cas_du_23_10(self):
        assert monture_en_avance(EtatMonture("pier_east", 0.02), 0.24)

    def test_objet_deja_passe(self):
        assert not monture_en_avance(EtatMonture("pier_east", -0.02), APRES)

    def test_monture_cote_avant(self):
        assert not monture_en_avance(EtatMonture("pier_west", 0.02), AVANT)

    @pytest.mark.parametrize("delta_h", [6.0, -6.0, 11.5])
    def test_loin_du_passage_superieur(self, delta_h):
        assert not monture_en_avance(EtatMonture("pier_east", delta_h), AVANT)

    def test_cote_inconnu_ou_asiair_muet(self):
        assert not monture_en_avance(EtatMonture(None, 0.02), AVANT)
        assert not monture_en_avance(None, AVANT)


T0 = datetime(2026, 10, 23, 19, 28, 17, tzinfo=timezone.utc)


def _azimut_lineaire(az0, deg_par_min):
    """Azimut qui varie linéairement depuis T0, ramené dans [0, 360[."""
    return lambda t: (az0 + deg_par_min * (t - T0).total_seconds() / 60.0) % 360.0


class TestInstantMeridien:
    def test_passage_au_nord_azimut_decroissant(self):
        # Cas du 23/10 : 0,24° à 21:28:17, −0,39°/min → 0° vers +37 s.
        t = instant_meridien(_azimut_lineaire(0.24, -0.39), T0, 900.0)
        assert abs((t - T0).total_seconds() - 36.9) <= 5.0

    def test_passage_au_sud_azimut_croissant(self):
        t = instant_meridien(_azimut_lineaire(170.0, 2.0), T0, 900.0)
        assert abs((t - T0).total_seconds() - 300.0) <= 5.0
        assert t > T0 + timedelta(seconds=295)

    def test_hors_fenetre(self):
        assert instant_meridien(_azimut_lineaire(170.0, 0.5), T0, 900.0) is None

    def test_juste_au_bord_de_la_fenetre(self):
        # Passage à 14 min 50 s, fenêtre de 15 min : trouvé.
        t = instant_meridien(_azimut_lineaire(180.0 - 0.5 * 14.8333, 0.5), T0, 900.0)
        assert t is not None
