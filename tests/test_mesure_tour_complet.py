"""
Tests du script de mesure des échelles sur un tour complet (6.25.1).

Le script départage le facteur de pas et le facteur de l'encodeur à 800 km :
son calcul doit être juste avant d'être exécuté. Seules les fonctions pures
sont testées ; l'orchestration IPC relève de la validation terrain.
"""

import importlib.util
import sys
from pathlib import Path

import pytest

_DIAG = Path(__file__).resolve().parent.parent / "scripts" / "diagnostics"
_SCRIPT = _DIAG / "mesure_tour_complet.py"


def _charger_module():
    """Charge le script standalone comme un module importable."""
    sys.path.insert(0, str(_DIAG))  # le script importe son voisin, comme lancé à la main
    spec = importlib.util.spec_from_file_location("mesure_tour_complet", _SCRIPT)
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


tour = _charger_module()


def _simuler(sens, s, r, depart_phys=39.0, commande=385.0):
    """Ce que lirait le script pour des échelles s (pas) et r (encodeur) données.

    Coupole partie de `depart_phys` (encodeur juste à ce moment), microswitch
    physique à 45°, recalage de l'encodeur à 45° à chaque passage.
    """
    a1_phys = ((45.0 - depart_phys) * sens) % 360.0
    total_phys = commande * s
    a2_phys = total_phys - a1_phys - 360.0
    avant_1 = depart_phys + sens * a1_phys * r
    avant_2 = 45.0 + sens * 360.0 * r
    arrivee = 45.0 + sens * a2_phys * r
    return {
        "sens": sens,
        "depart": depart_phys % 360.0,
        "avant_recalages": [avant_1 % 360.0, avant_2 % 360.0],
        "arrivee": arrivee % 360.0,
        "commande": commande,
    }


class TestEchellesTour:
    def test_echelles_parfaites(self):
        e = tour.echelles_tour(**_simuler(+1, s=1.0, r=1.0))
        assert e["encodeur_par_degre"] == pytest.approx(1.0)
        assert e["degres_par_degre_pas"] == pytest.approx(1.0)

    def test_pas_trop_longs(self):
        """Cas soupçonné : chaque degré commandé fait 1,022° réels, encodeur juste."""
        e = tour.echelles_tour(**_simuler(+1, s=1.022, r=1.0))
        assert e["encodeur_par_degre"] == pytest.approx(1.0)
        assert e["degres_par_degre_pas"] == pytest.approx(1.022)

    def test_encodeur_trop_court(self):
        """Autre cas : pas justes, l'encodeur compte 2 % de moins que la réalité."""
        e = tour.echelles_tour(**_simuler(+1, s=1.0, r=0.978))
        assert e["encodeur_par_degre"] == pytest.approx(0.978)
        assert e["degres_par_degre_pas"] == pytest.approx(1.0)

    def test_sens_negatif(self):
        e = tour.echelles_tour(**_simuler(-1, s=1.01, r=0.99, depart_phys=51.0))
        assert e["encodeur_par_degre"] == pytest.approx(0.99)
        assert e["degres_par_degre_pas"] == pytest.approx(1.01)

    def test_encodeur_qui_compte_plus_d_un_tour(self):
        """L'encodeur peut compter plus de 360° : le dépliage ne doit pas le ramener à 8°."""
        e = tour.echelles_tour(**_simuler(+1, s=1.0, r=1.022))
        assert e["encodeur_par_degre"] == pytest.approx(1.022)

    def test_rapport_pas_encodeur_comme_dans_les_logs(self):
        """Le rapport pas → encodeur est ce que les GOTO du 22/10 mesuraient (≈ 1,022)."""
        e = tour.echelles_tour(**_simuler(+1, s=1.011, r=1.011))
        assert e["encodeur_par_degre_pas"] == pytest.approx(1.011 * 1.011)

    @pytest.mark.parametrize("n", [0, 1, 3])
    def test_il_faut_exactement_deux_recalages(self, n):
        mesure = _simuler(+1, s=1.0, r=1.0)
        mesure["avant_recalages"] = [44.0] * n
        with pytest.raises(ValueError):
            tour.echelles_tour(**mesure)


class TestFacteursProposes:
    def test_corrige_chaque_facteur_par_son_echelle(self):
        f = tour.facteurs_proposes(
            steps_correction_factor=1.08849,
            calibration_factor=0.010851,
            echelles={"degres_par_degre_pas": 1.022, "encodeur_par_degre": 0.99},
        )
        # Pas trop longs de 2,2 % → moins de pas par degré.
        assert f["steps_correction_factor"] == pytest.approx(1.08849 / 1.022)
        # Encodeur qui compte 1 % de moins → facteur plus grand.
        assert f["calibration_factor"] == pytest.approx(0.010851 / 0.99)
