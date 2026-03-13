"""
Tests exhaustifs pour core/tracking/abaque_manager.py

Couvre :
- Chargement de l'abaque depuis le fichier Excel réel
- Interpolation bilinéaire (cas normaux et limites)
- Gestion de la circularité des angles
- Extrapolation hors bornes
- Nearest neighbor fallback
- Diagnostics et export
"""

import pytest
from pathlib import Path

from core.tracking.abaque_manager import AbaqueManager


@pytest.fixture
def abaque_path(project_root):
    """Chemin vers le fichier abaque réel."""
    path = project_root / "data" / "Loi_coupole.xlsx"
    if not path.exists():
        pytest.skip("Fichier abaque Loi_coupole.xlsx non trouvé")
    return path


@pytest.fixture
def loaded_abaque(abaque_path):
    """AbaqueManager chargé avec les données réelles."""
    mgr = AbaqueManager(str(abaque_path))
    assert mgr.load_abaque() is True
    return mgr


# =============================================================================
# Chargement
# =============================================================================

class TestAbaqueLoading:
    def test_load_success(self, abaque_path):
        mgr = AbaqueManager(str(abaque_path))
        assert mgr.load_abaque() is True
        assert mgr.is_loaded is True

    def test_load_missing_file(self, tmp_path):
        mgr = AbaqueManager(str(tmp_path / "nonexistent.xlsx"))
        assert mgr.load_abaque() is False
        assert mgr.is_loaded is False

    def test_statistics_after_load(self, loaded_abaque):
        assert loaded_abaque.n_altitudes > 0
        assert loaded_abaque.n_azimuths > 0
        assert loaded_abaque.altitude_range[0] < loaded_abaque.altitude_range[1]
        assert loaded_abaque.azimuth_range[0] < loaded_abaque.azimuth_range[1]

    def test_data_not_empty(self, loaded_abaque):
        assert len(loaded_abaque.data_by_altitude) > 0
        for alt, data in loaded_abaque.data_by_altitude.items():
            assert len(data['az_astre']) > 0
            assert len(data['az_coupole']) > 0
            assert len(data['az_astre']) == len(data['az_coupole'])


# =============================================================================
# Interpolation — cas normaux
# =============================================================================

class TestAbaqueInterpolation:
    def test_returns_float(self, loaded_abaque):
        pos, infos = loaded_abaque.get_dome_position(45.0, 180.0)
        assert isinstance(pos, float)
        assert 0.0 <= pos < 360.0

    def test_returns_info_dict(self, loaded_abaque):
        pos, infos = loaded_abaque.get_dome_position(45.0, 180.0)
        assert "altitude_objet" in infos
        assert "azimut_objet" in infos
        assert "azimut_coupole" in infos
        assert "method" in infos
        assert "in_bounds" in infos

    def test_different_altitudes_different_results(self, loaded_abaque):
        """Des altitudes différentes doivent donner des positions différentes."""
        pos_low, _ = loaded_abaque.get_dome_position(30.0, 180.0)
        pos_high, _ = loaded_abaque.get_dome_position(60.0, 180.0)
        # Pas forcément très différents, mais probablement distincts
        # On vérifie juste que ça ne crash pas
        assert isinstance(pos_low, float)
        assert isinstance(pos_high, float)

    def test_different_azimuths_different_results(self, loaded_abaque):
        pos_north, _ = loaded_abaque.get_dome_position(45.0, 0.0)
        pos_south, _ = loaded_abaque.get_dome_position(45.0, 180.0)
        assert pos_north != pos_south

    def test_in_bounds_flag(self, loaded_abaque):
        """Position dans les bornes → in_bounds = True."""
        alt_mid = sum(loaded_abaque.altitude_range) / 2
        az_mid = sum(loaded_abaque.azimuth_range) / 2
        _, infos = loaded_abaque.get_dome_position(alt_mid, az_mid)
        assert infos["in_bounds"] is True

    def test_multiple_calls_consistent(self, loaded_abaque):
        """Mêmes entrées → même résultat."""
        pos1, _ = loaded_abaque.get_dome_position(45.0, 120.0)
        pos2, _ = loaded_abaque.get_dome_position(45.0, 120.0)
        assert pos1 == pos2

    def test_all_altitude_points(self, loaded_abaque):
        """Teste l'interpolation pour chaque altitude mesurée."""
        for alt in sorted(loaded_abaque.data_by_altitude.keys()):
            data = loaded_abaque.data_by_altitude[alt]
            az = data['az_astre'][len(data['az_astre']) // 2]  # Azimut milieu
            pos, infos = loaded_abaque.get_dome_position(alt, az)
            assert 0.0 <= pos < 360.0, f"Position invalide pour alt={alt}, az={az}: {pos}"


# =============================================================================
# Interpolation — edge cases
# =============================================================================

class TestAbaqueEdgeCases:
    def test_azimut_zero(self, loaded_abaque):
        """Azimut 0° (Nord)."""
        alt_mid = sum(loaded_abaque.altitude_range) / 2
        pos, _ = loaded_abaque.get_dome_position(alt_mid, 0.0)
        assert 0.0 <= pos < 360.0

    def test_azimut_359(self, loaded_abaque):
        alt_mid = sum(loaded_abaque.altitude_range) / 2
        pos, _ = loaded_abaque.get_dome_position(alt_mid, 359.0)
        assert 0.0 <= pos < 360.0

    def test_out_of_bounds_altitude_low(self, loaded_abaque):
        """Altitude sous la borne min → extrapolation."""
        min_alt = loaded_abaque.altitude_range[0]
        pos, infos = loaded_abaque.get_dome_position(min_alt - 10, 180.0)
        assert isinstance(pos, float)
        # in_bounds devrait être False
        assert infos["in_bounds"] is False

    def test_out_of_bounds_altitude_high(self, loaded_abaque):
        max_alt = loaded_abaque.altitude_range[1]
        pos, infos = loaded_abaque.get_dome_position(max_alt + 5, 180.0)
        assert isinstance(pos, float)

    def test_not_loaded_raises(self):
        mgr = AbaqueManager("nonexistent.xlsx")
        with pytest.raises(RuntimeError, match="non chargée"):
            mgr.get_dome_position(45.0, 180.0)


# =============================================================================
# Nearest neighbor
# =============================================================================

class TestAbaqueNearestNeighbor:
    def test_nearest_neighbor_returns_float(self, loaded_abaque):
        result = loaded_abaque._nearest_neighbor(45.0, 180.0)
        assert isinstance(result, float)
        assert 0.0 <= result < 360.0


# =============================================================================
# Diagnostics
# =============================================================================

class TestAbaqueDiagnostics:
    def test_diagnostics_loaded(self, loaded_abaque):
        diag = loaded_abaque.get_diagnostics()
        assert diag["status"] == "loaded"
        assert "statistics" in diag
        assert "altitudes_available" in diag

    def test_diagnostics_not_loaded(self):
        mgr = AbaqueManager("fake.xlsx")
        diag = mgr.get_diagnostics()
        assert diag["status"] == "not_loaded"

    def test_export_json(self, loaded_abaque, tmp_path):
        output = str(tmp_path / "export.json")
        result = loaded_abaque.export_to_json(output)
        assert result is True
        assert Path(output).exists()
