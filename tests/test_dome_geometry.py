"""Tests du modèle géométrique coupole / monture allemande (core/tracking/dome_geometry.py)."""

import math

import pytest

from core.tracking.dome_geometry import (
    DomeGeometry,
    PierSide,
    dome_azimuth,
    expected_pier_side,
    fit_dome_geometry,
)

LATITUDE = 44.15


def _ecart(a: float, b: float) -> float:
    return (a - b + 180.0) % 360.0 - 180.0


class TestDomeAzimuth:
    def test_monture_centree_la_coupole_suit_l_objet(self):
        geom = DomeGeometry(dome_radius_m=1.2)
        for alt, az in [(30, 10), (45, 90), (60, 180), (80, 250), (85, 359)]:
            for side in PierSide:
                assert dome_azimuth(geom, alt, az, side, LATITUDE) == pytest.approx(az, abs=1e-6)

    def test_monture_decalee_au_nord_cas_calcule_a_la_main(self):
        # Rayon 1, monture 0,5 au nord, visée plein Est à l'horizon :
        # intersection (E=√0,75 ; N=0,5) → azimut atan2(0,866 ; 0,5) = 60°.
        geom = DomeGeometry(dome_radius_m=1.0, mount_north_m=0.5)
        assert dome_azimuth(geom, 0.0, 90.0, PierSide.WEST, LATITUDE) == pytest.approx(
            60.0, abs=1e-6
        )

    def test_decalage_de_tube_cote_ouest_pousse_la_coupole_vers_l_ouest(self):
        # Avant le méridien, le tube est à l'ouest du pied : pour un objet plein Sud,
        # l'ouverture doit être à l'ouest du Sud (azimut > 180°), et symétrique côté Est.
        geom = DomeGeometry(dome_radius_m=1.2, gem_offset_m=0.4)
        ouest = dome_azimuth(geom, 60.0, 180.0, PierSide.WEST, LATITUDE)
        est = dome_azimuth(geom, 60.0, 180.0, PierSide.EAST, LATITUDE)
        assert 180.0 < ouest < 270.0
        assert _ecart(ouest, 180.0) == pytest.approx(-_ecart(est, 180.0), abs=1e-6)

    def test_decalage_lateral_change_de_sens_avec_le_cote_du_pied(self):
        # Le décalage latéral est lié au tube : il se retourne avec la monture.
        plus = DomeGeometry(dome_radius_m=1.2, lateral_m=0.1)
        moins = DomeGeometry(dome_radius_m=1.2, lateral_m=-0.1)
        ouest = dome_azimuth(plus, 50.0, 120.0, PierSide.WEST, LATITUDE)
        assert ouest != pytest.approx(120.0, abs=0.5)
        assert ouest == pytest.approx(
            dome_azimuth(moins, 50.0, 120.0, PierSide.EAST, LATITUDE), abs=1e-6
        )

    def test_decalage_azimutal_du_codeur(self):
        geom = DomeGeometry(dome_radius_m=1.2, az_offset_deg=-2.5)
        assert dome_azimuth(geom, 45.0, 100.0, PierSide.WEST, LATITUDE) == pytest.approx(
            97.5, abs=1e-6
        )

    def test_monture_hors_de_la_coupole_refusee(self):
        geom = DomeGeometry(dome_radius_m=1.0, mount_up_m=1.5)
        with pytest.raises(ValueError):
            dome_azimuth(geom, 45.0, 100.0, PierSide.WEST, LATITUDE)


class TestExpectedPierSide:
    @pytest.mark.parametrize(
        "az, side",
        [
            (90.0, PierSide.WEST),
            (10.0, PierSide.WEST),
            (179.0, PierSide.WEST),
            (181.0, PierSide.EAST),
            (270.0, PierSide.EAST),
            (350.0, PierSide.EAST),
        ],
    )
    def test_cote_du_pied_selon_le_cote_du_meridien(self, az, side):
        assert expected_pier_side(az) is side


def _grille():
    return [(alt, az) for alt in (30, 45, 60, 70, 80) for az in range(0, 360, 15)]


class TestFit:
    def test_retrouve_une_geometrie_synthetique(self):
        vraie = DomeGeometry(
            dome_radius_m=1.2,
            mount_east_m=0.02,
            mount_north_m=0.08,
            mount_up_m=-0.25,
            gem_offset_m=0.42,
            lateral_m=-0.04,
            az_offset_deg=-2.0,
        )
        points = []
        for alt, az in _grille():
            if az % 180 == 0:
                continue  # au méridien, le côté du pied est ambigu
            side = expected_pier_side(az)
            points.append((alt, az, dome_azimuth(vraie, alt, az, side, LATITUDE)))

        fit = fit_dome_geometry(points, LATITUDE, dome_radius_m=1.2)

        g = fit.geometry
        assert g.mount_east_m == pytest.approx(vraie.mount_east_m, abs=1e-3)
        assert g.mount_north_m == pytest.approx(vraie.mount_north_m, abs=1e-3)
        assert g.mount_up_m == pytest.approx(vraie.mount_up_m, abs=1e-3)
        assert g.gem_offset_m == pytest.approx(vraie.gem_offset_m, abs=1e-3)
        assert g.lateral_m == pytest.approx(vraie.lateral_m, abs=1e-3)
        assert _ecart(g.az_offset_deg, vraie.az_offset_deg) == pytest.approx(0.0, abs=1e-2)
        assert max(abs(r) for r in fit.residuals_deg) < 1e-2

    def test_point_au_meridien_prend_le_cote_qui_colle(self):
        vraie = DomeGeometry(dome_radius_m=1.2, mount_up_m=-0.25, gem_offset_m=0.42)
        points = [
            (alt, az, dome_azimuth(vraie, alt, az, expected_pier_side(az), LATITUDE))
            for alt, az in _grille()
            if az % 180 != 0
        ]
        # Point au méridien mesuré tube côté Ouest (monture pas encore retournée)
        points.append((70.0, 180.0, dome_azimuth(vraie, 70.0, 180.0, PierSide.WEST, LATITUDE)))

        fit = fit_dome_geometry(points, LATITUDE, dome_radius_m=1.2)

        assert fit.sides[-1] is PierSide.WEST
        assert abs(fit.residuals_deg[-1]) < 1e-2


class TestAbaqueReelle:
    """Verrouille la faisabilité constatée le 17/10/2026 sur data/Loi_coupole.xlsx."""

    @pytest.fixture(scope="class")
    def fit(self):
        from core.tracking.abaque_manager import AbaqueManager

        abaque = AbaqueManager("data/Loi_coupole.xlsx")
        assert abaque.load_abaque()
        points = [
            (alt, az, dome)
            for alt, d in abaque.data_by_altitude.items()
            for az, dome in zip(d["az_astre"], d["az_coupole"])
        ]
        return points, fit_dome_geometry(points, LATITUDE, dome_radius_m=1.2)

    def test_concorde_avec_l_abaque_jusqu_a_60_degres(self, fit):
        points, resultat = fit
        bas = [r for (alt, _, _), r in zip(points, resultat.residuals_deg) if alt <= 60]
        rms = math.sqrt(sum(r * r for r in bas) / len(bas))
        assert rms < 3.5

    def test_concorde_globalement_malgre_les_mesures_douteuses(self, fit):
        _, resultat = fit
        r = resultat.residuals_deg
        assert math.sqrt(sum(x * x for x in r) / len(r)) < 7.5

    def test_retrouve_le_deport_du_tube_mesure(self, fit):
        # TRACKING_LOGIC.md : tube décalé de 40 cm dans une coupole de 120 cm de rayon.
        _, resultat = fit
        assert 0.30 < resultat.geometry.gem_offset_m < 0.55
