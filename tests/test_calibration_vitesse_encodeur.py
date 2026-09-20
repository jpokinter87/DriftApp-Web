"""
Tests du script de calibration vitesse à l'encodeur (v6.16).

Le script fait bouger la coupole sur site : sa logique de décision — « ce
palier est-il tenu ou la coupole décroche-t-elle ? » — doit être juste avant
d'être exécutée à 800 km. Seules les fonctions pures sont testées ici ;
l'orchestration IPC relève de la validation terrain.
"""

import importlib.util
import sys
from pathlib import Path

import pytest

_SCRIPT = (
    Path(__file__).resolve().parent.parent
    / "scripts"
    / "diagnostics"
    / "calibration_vitesse_encodeur.py"
)


def _charger_module():
    """Charge le script standalone comme un module importable."""
    spec = importlib.util.spec_from_file_location("calib_vitesse_encodeur", _SCRIPT)
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


calib = _charger_module()


def _mesure(delay_us, vitesse_mesuree, angle=10.0, parcouru=None):
    """Fabrique une mesure de palier."""
    return {
        "delay_us": delay_us,
        "angle_commande": angle,
        "angle_parcouru": angle if parcouru is None else parcouru,
        "vitesse_mesuree": vitesse_mesuree,
        "vitesse_theorique": 0.0,
        "rendement": 1.0,
        "echantillons": 200,
    }


class TestEcartAngulaire:
    """L'azimut boucle à 360° : l'écart doit rester le plus court."""

    def test_ecart_simple(self):
        assert calib._ecart_angulaire(10.0, 20.0) == pytest.approx(10.0)

    def test_ecart_negatif(self):
        assert calib._ecart_angulaire(20.0, 10.0) == pytest.approx(-10.0)

    def test_passage_par_zero(self):
        """359° → 1° vaut +2°, pas -358°."""
        assert calib._ecart_angulaire(359.0, 1.0) == pytest.approx(2.0)

    def test_passage_par_zero_inverse(self):
        assert calib._ecart_angulaire(1.0, 359.0) == pytest.approx(-2.0)


class TestVitesseCroisiere:
    """Les rampes doivent être exclues de la mesure."""

    def test_ignore_les_rampes(self):
        """Départ et arrivée lents, croisière rapide : seule la croisière compte."""
        echantillons = []
        t, angle = 0.0, 0.0
        for i in range(40):
            # 10 pas lents, 20 rapides (1°/s), 10 lents
            vitesse = 1.0 if 10 <= i < 30 else 0.1
            echantillons.append((t, angle))
            t += 0.05
            angle += vitesse * 0.05

        # La tranche centrale couvre exactement la croisière : 1°/s = 60°/min
        assert calib._vitesse_croisiere(echantillons) == pytest.approx(60.0, rel=0.05)

    def test_trop_peu_d_echantillons(self):
        assert calib._vitesse_croisiere([(0.0, 0.0), (0.05, 0.1)]) is None

    def test_duree_nulle(self):
        """Des horodatages identiques ne doivent pas diviser par zéro."""
        assert calib._vitesse_croisiere([(1.0, 0.0)] * 40) is None


class TestDiagnostiquer:
    """Détection du décrochage."""

    def test_premier_palier_toujours_tenu(self):
        """Sans référence, on ne peut rien conclure — le palier passe."""
        assert calib._diagnostiquer(_mesure(260, 42.8), None) is None

    def test_palier_tenu(self):
        """Délai -10 % → vitesse +11 % : la coupole suit."""
        precedent = _mesure(260, 42.8)
        assert calib._diagnostiquer(_mesure(235, 47.3), precedent) is None

    def test_pas_perdus_detectes(self):
        """La coupole n'a pas parcouru l'angle demandé : pas perdus."""
        raison = calib._diagnostiquer(
            _mesure(140, 79.0, angle=10.0, parcouru=6.0), _mesure(155, 71.8)
        )
        assert raison is not None
        assert "pas perdus" in raison

    def test_saturation_detectee(self):
        """Le délai baisse mais la vitesse ne suit plus : saturation."""
        precedent = _mesure(260, 42.8)
        raison = calib._diagnostiquer(_mesure(130, 44.0), precedent)
        assert raison is not None
        assert "saturation" in raison

    def test_reproduit_la_saturation_de_decembre_2025(self):
        """L'instrument qui aurait évité la conclusion erronée de 2025.

        Mesures réelles du site (Vitesses.xlsx, 12/12/2025), où la boucle
        Python ajoutait 121 µs à chaque pas : demander 300 puis 150 µs
        n'a produit que +52 % de vitesse au lieu des +100 % attendus.
        Faute de cette comparaison, le plafond logiciel a été pris pour
        une limite du driver pendant neuf mois.
        """
        precedent = _mesure(300, 25.35)
        raison = calib._diagnostiquer(_mesure(150, 38.67), precedent)

        assert raison is not None
        assert "saturation" in raison

    def test_ne_signale_pas_la_saturation_aux_delais_longs(self):
        """Aux délais longs, le même surcoût reste invisible — c'est normal."""
        precedent = _mesure(1100, 8.96)
        assert calib._diagnostiquer(_mesure(550, 16.9), precedent) is None


class TestVitesseTheorique:
    """Conversion délai → vitesse, sur la géométrie réelle de la coupole."""

    SPD = 5394.1  # pas/degré : 200 × 4 × 2230 × 1.08849 / 360

    def test_valeur_historique(self):
        """260 µs — la vitesse unique de la v5.10."""
        assert calib.vitesse_theorique(260, self.SPD) == pytest.approx(42.8, rel=0.01)

    def test_cible_boitier_constructeur(self):
        """124 µs — les 90°/min du boîtier constructeur."""
        assert calib.vitesse_theorique(124, self.SPD) == pytest.approx(89.7, rel=0.01)

    def test_paliers_strictement_decroissants(self):
        """Le plan de mesure doit aller du plus lent au plus rapide."""
        paliers = calib.PALIERS_US
        assert paliers == sorted(paliers, reverse=True)
        assert paliers[0] == 260  # on repart toujours de la valeur en service
