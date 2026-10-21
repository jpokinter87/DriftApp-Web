"""Règle d'attente du retournement de la monture avant la bascule de la coupole (6.24)."""

import pytest

from core.hardware.asiair_client import EtatMonture
from core.tracking.dome_flip_wait import AttenteRetournement, monture_en_retard

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
