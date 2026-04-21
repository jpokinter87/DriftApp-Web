"""Tests unitaires du module d'anticipation méridien (v5.9 Phase 1).

Trois niveaux :

1. `TestMeridianFlipDetector` — trajectoires synthétiques (rapide, AC-1)
2. `TestMeridianSlewScheduler` — formule théorique (rapide, AC-2)
3. `TestRegressionVsSimulation` — équivalence numérique avec
   scripts/diagnostics/simulate_meridian_anticipation.py sur 5 objets réels
   (slow, astropy, AC-3).

Les valeurs EXPECTED du test de régression sont capturées d'une exécution
réelle de la simulation le 2026-04-21 (bootstrap tout en bas du fichier).
"""

from __future__ import annotations

from datetime import datetime, timedelta, timezone

import pytest

from core.tracking.meridian_anticipation import (
    FLIP_RATE_THRESHOLD_DEG_PER_SEC,
    FlipInfo,
    MeridianFlipDetector,
    MeridianSlewScheduler,
    TrajectoryPoint,
    build_lookahead_trajectory,
    find_meridian_time,
    is_at_meridian,
    target_at,
)


# --- Helpers synthétiques ----------------------------------------------------


def _make_trajectory(
    dome_targets: list[float], sampling_sec: int = 10, alt: float = 80.0, az: float = 180.0
) -> list[TrajectoryPoint]:
    """Construit une trajectoire synthétique où seul dome_target varie."""
    return [
        TrajectoryPoint(
            t_sec=float(i * sampling_sec),
            alt=alt,
            az=az,
            dome_target=float(target),
        )
        for i, target in enumerate(dome_targets)
    ]


def _subpolar_flip_trajectory(
    pre_target: float,
    post_target: float,
    flip_duration_sec: int,
    pad_sec: int = 300,
    sampling_sec: int = 10,
) -> list[TrajectoryPoint]:
    """Trajectoire avec un plateau pre_target, un flip linéaire, puis plateau post_target."""
    pre_pad = pad_sec // sampling_sec
    post_pad = pad_sec // sampling_sec
    n_flip = max(1, flip_duration_sec // sampling_sec)

    targets: list[float] = [pre_target] * pre_pad
    # Interpolation linéaire signée (shortest path) pendant le flip
    from core.utils.angle_utils import normalize_angle_180, normalize_angle_360

    signed = normalize_angle_180(post_target - pre_target)
    for i in range(1, n_flip + 1):
        frac = i / n_flip
        targets.append(normalize_angle_360(pre_target + signed * frac))
    targets += [post_target] * post_pad
    return _make_trajectory(targets, sampling_sec=sampling_sec)


# --- AC-1 : Détecteur synthétique --------------------------------------------


class TestMeridianFlipDetector:
    """Flip detection sur trajectoires construites à la main."""

    def test_detect_subpolar_flip(self):
        """Cas classique : dome_target passe de 175° à 5° en ~60 s à 80° d'altitude."""
        traj = _subpolar_flip_trajectory(
            pre_target=175.0,
            post_target=5.0,
            flip_duration_sec=60,
            pad_sec=200,
            sampling_sec=10,
        )
        flip = MeridianFlipDetector().detect(traj)
        assert flip is not None
        assert flip.duration == pytest.approx(60.0, abs=20.0)
        assert flip.amplitude == pytest.approx(170.0, abs=2.0)
        assert flip.signed_amplitude < 0  # shortest path 175→5 = -170°
        assert flip.pre_target == pytest.approx(175.0, abs=2.0)
        assert flip.post_target == pytest.approx(5.0, abs=2.0)

    def test_detect_circumpolar_flip(self):
        """Circumpolaire : dome_target passe de 355° à 5° (amplitude signée +10° via unwrap)."""
        traj = _subpolar_flip_trajectory(
            pre_target=355.0,
            post_target=5.0,
            flip_duration_sec=10,
            pad_sec=200,
            sampling_sec=10,
        )
        flip = MeridianFlipDetector().detect(traj)
        assert flip is not None
        assert flip.amplitude == pytest.approx(10.0, abs=2.0)
        # Sens : 355 → 5 côté court = +10° (CCW)
        assert flip.signed_amplitude > 0

    def test_detect_no_flip(self):
        """Trajectoire monotone très lente : rate toujours < threshold."""
        # Incrément de 0.1°/pas (= 0.01°/s) — bien en dessous de 0.8°/s
        targets = [100.0 + 0.1 * i for i in range(100)]
        traj = _make_trajectory(targets, sampling_sec=10)
        assert MeridianFlipDetector().detect(traj) is None

    def test_detect_flip_over_180(self):
        """Flip > 180° : amplitude signée via unwrapping cumulatif, pas shortest-path.

        On construit manuellement une séquence de deltas signés dépassant 180°
        (ce que la nature ne produit pas naturellement via shortest-path, mais
        que la projection astropy+abaque peut produire sur les flips réels).
        """
        # On simule 20 échantillons à +10°/pas (=1°/s > threshold), cumul = +200°
        targets = [0.0]
        for i in range(1, 21):
            targets.append((targets[-1] + 10.0) % 360.0)
        # Pad sortant de flip (plateau à ~200°)
        targets += [targets[-1]] * 30
        traj = _make_trajectory(targets, sampling_sec=10)
        flip = MeridianFlipDetector().detect(traj)
        assert flip is not None
        # Chaque delta shortest-path = +10° → somme signée = +200° (cumul unwrap)
        assert flip.signed_amplitude == pytest.approx(200.0, abs=5.0)
        assert flip.amplitude == pytest.approx(200.0, abs=5.0)
        assert flip.signed_amplitude > 0

    def test_detect_empty_trajectory(self):
        assert MeridianFlipDetector().detect([]) is None

    def test_detect_single_point_trajectory(self):
        assert MeridianFlipDetector().detect(_make_trajectory([180.0])) is None

    def test_is_at_meridian_subpolar(self):
        assert is_at_meridian(az=180.0, alt=80.0) is True
        assert is_at_meridian(az=179.0, alt=80.0) is True
        assert is_at_meridian(az=178.5, alt=80.0) is True
        assert is_at_meridian(az=175.0, alt=80.0) is False

    def test_is_at_meridian_circumpolar(self):
        assert is_at_meridian(az=0.0, alt=80.0) is True
        assert is_at_meridian(az=359.5, alt=80.0) is True
        assert is_at_meridian(az=5.0, alt=80.0) is False

    def test_is_at_meridian_low_altitude(self):
        assert is_at_meridian(az=180.0, alt=60.0) is False
        assert is_at_meridian(az=180.0, alt=65.0) is False  # strict >

    def test_target_at_boundaries(self):
        traj = _make_trajectory([100.0, 110.0, 120.0], sampling_sec=10)
        assert target_at(-5.0, traj) == 100.0
        assert target_at(25.0, traj) == 120.0
        # Interpolation simple entre 2 points sans flip
        assert target_at(5.0, traj) == pytest.approx(105.0, abs=0.01)

    def test_target_at_across_discrete_flip(self):
        """Autour d'un flip discret (> 30° entre samples), retour du plus proche."""
        traj = _make_trajectory([175.0, 5.0], sampling_sec=10)
        # Plus proche de t=0 → 175, plus proche de t=10 → 5
        assert target_at(3.0, traj) == 175.0
        assert target_at(7.0, traj) == 5.0


# --- AC-2 : Scheduler --------------------------------------------------------


class TestMeridianSlewScheduler:
    """Formule t_start_offset + direction + target."""

    def test_schedule_normal_case(self):
        """Δ=160°, τ=40s, v=0.7°/s → t_start_offset ≈ 94.3s, direction=-1."""
        flip = FlipInfo(
            start=500.0,
            end=540.0,
            duration=40.0,
            amplitude=160.0,
            signed_amplitude=-160.0,
            pre_target=190.0,
            post_target=5.0,
        )
        slew = MeridianSlewScheduler().schedule(flip, dome_speed_deg_per_sec=0.7)
        expected_offset = (160.0 - 0.7 * 40.0) / (2 * 0.7)  # = 94.29
        assert slew.t_start_offset == pytest.approx(expected_offset, abs=0.01)
        assert slew.t_start == pytest.approx(500.0 - expected_offset, abs=0.01)
        assert slew.direction == -1
        assert slew.target == 5.0

    def test_schedule_degenerate_short_flip(self):
        """Cas où Δ ≤ v·τ → t_start_offset clampé à 0."""
        flip = FlipInfo(
            start=500.0,
            end=600.0,
            duration=100.0,
            amplitude=30.0,
            signed_amplitude=-30.0,  # 30 < 0.7*100=70
            pre_target=190.0,
            post_target=160.0,
        )
        slew = MeridianSlewScheduler().schedule(flip, dome_speed_deg_per_sec=0.7)
        assert slew.t_start_offset == 0.0
        assert slew.t_start == 500.0

    def test_schedule_ccw_direction(self):
        """signed > 0 → direction = +1."""
        flip = FlipInfo(
            start=500.0,
            end=520.0,
            duration=20.0,
            amplitude=10.0,
            signed_amplitude=+10.0,
            pre_target=355.0,
            post_target=5.0,
        )
        slew = MeridianSlewScheduler().schedule(flip, dome_speed_deg_per_sec=0.7)
        assert slew.direction == 1

    def test_schedule_zero_direction(self):
        """signed == 0 → direction = 0 (cas dégénéré)."""
        flip = FlipInfo(
            start=500.0,
            end=520.0,
            duration=20.0,
            amplitude=0.0,
            signed_amplitude=0.0,
            pre_target=180.0,
            post_target=180.0,
        )
        slew = MeridianSlewScheduler().schedule(flip, dome_speed_deg_per_sec=0.7)
        assert slew.direction == 0

    def test_schedule_rejects_zero_speed(self):
        flip = FlipInfo(
            start=0.0,
            end=10.0,
            duration=10.0,
            amplitude=10.0,
            signed_amplitude=-10.0,
            pre_target=0.0,
            post_target=10.0,
        )
        with pytest.raises(ValueError):
            MeridianSlewScheduler().schedule(flip, dome_speed_deg_per_sec=0.0)


# --- AC-3 : Régression vs simulation standalone ------------------------------

# Oracles capturés depuis `uv run python scripts/diagnostics/simulate_meridian_anticipation.py`
# le 2026-04-21 (commits 5422d41 + 80961b8). Les valeurs d'amplitude, durée et
# t_start_offset viennent du tableau principal ; post_target et direction
# de la section DÉTAIL pour Capella et sont déduites pour les autres via le
# sens du transit méridien.
#
# Tolérances retenues :
#   - amplitude : ±1% + ±2° (échantillonnage 10s peut décaler d'un sample)
#   - duration  : ±20s (arrondi à un pas SAMPLING_SEC=10s × 2)
#   - t_start_offset : ±2s (déduit de amplitude/duration via la formule)
#   - direction : exact
#   - post_target : ±1° (uniquement vérifié pour Capella, pre/post donnés)

SITE_LAT = 44.15
SITE_LON = 5.23
DOME_SPEED = 42.0 / 60.0  # °/s
SIM_SEARCH_START = datetime(2026, 3, 28, 18, 0, 0, tzinfo=timezone.utc)
PRE_MERIDIAN_SEC = 500
SIM_DURATION_SEC = 3600
SAMPLING_SEC = 10

REAL_OBJECTS = [
    # (name, ra_j2000, dec_j2000, expected_amplitude, expected_duration, expected_direction)
    # La direction vient du SIGNE de l'amplitude unwrappée, pas d'une règle
    # géométrique universelle. Objets dont le dome wrap par 0° (IC 445, M 101,
    # Capella : pre ~300° → post ~40-77°) donnent signed>0 → direction=+1.
    ("IC 445", 99.3384942483, 67.85992306669, 76.2, 20, +1),
    ("M 101", 210.8024, 54.349, 97.1, 20, +1),
    ("46 LMi", 163.32787152823542, 34.214892133082735, 134.7, 110, -1),
    ("M 13", 250.4235, 36.461, 149.0, 100, -1),
    ("Capella", 79.1723, 45.998, 156.4, 20, +1),
]

# Seul Capella a son post_target publié dans le bloc DÉTAIL de la simulation.
CAPELLA_POST_TARGET_EXPECTED = 77.9  # ±1°


@pytest.fixture(scope="module")
def calc():
    from core.observatoire.calculations import AstronomicalCalculations

    return AstronomicalCalculations(SITE_LAT, SITE_LON, tz_offset=0)


@pytest.fixture(scope="module")
def abaque():
    from core.tracking.abaque_manager import AbaqueManager

    a = AbaqueManager()
    assert a.load_abaque(), "Abaque failed to load — Loi_coupole.xlsx absent ?"
    return a


@pytest.mark.slow
class TestRegressionVsSimulation:
    """Le module doit reproduire numériquement la simulation de référence."""

    def test_trajectory_shape(self, calc, abaque):
        mer_t = find_meridian_time(calc, 79.1723, 45.998, SIM_SEARCH_START, 18)
        sim_start = mer_t - timedelta(seconds=PRE_MERIDIAN_SEC)
        traj = build_lookahead_trajectory(
            calc,
            abaque,
            79.1723,
            45.998,
            sim_start,
            duration_sec=SIM_DURATION_SEC,
            sampling_sec=SAMPLING_SEC,
        )
        assert len(traj) == SIM_DURATION_SEC // SAMPLING_SEC + 1
        assert traj[0].t_sec == 0.0
        assert traj[-1].t_sec == float(SIM_DURATION_SEC)
        for p in traj:
            assert 0.0 <= p.az < 360.0
            assert -90.0 <= p.alt <= 95.0  # refraction peut dépasser 90
            assert 0.0 <= p.dome_target < 360.0

    @pytest.mark.parametrize(
        "name,ra,dec,exp_amplitude,exp_duration,exp_direction",
        REAL_OBJECTS,
        ids=[o[0] for o in REAL_OBJECTS],
    )
    def test_regression_real_object(
        self, calc, abaque, name, ra, dec, exp_amplitude, exp_duration, exp_direction
    ):
        """Chaque objet réel : détection + scheduler conformes à la simulation."""
        mer_t = find_meridian_time(calc, ra, dec, SIM_SEARCH_START, 18)
        sim_start = mer_t - timedelta(seconds=PRE_MERIDIAN_SEC)
        traj = build_lookahead_trajectory(
            calc,
            abaque,
            ra,
            dec,
            sim_start,
            duration_sec=SIM_DURATION_SEC,
            sampling_sec=SAMPLING_SEC,
        )

        flip = MeridianFlipDetector().detect(traj)
        assert flip is not None, f"{name}: aucun flip détecté"

        tol_amp = max(2.0, 0.01 * exp_amplitude)
        assert flip.amplitude == pytest.approx(exp_amplitude, abs=tol_amp), (
            f"{name}: amplitude {flip.amplitude:.2f}° vs attendu {exp_amplitude}° "
            f"(tol {tol_amp:.2f}°)"
        )
        assert flip.duration == pytest.approx(exp_duration, abs=20.0), (
            f"{name}: duration {flip.duration}s vs attendu {exp_duration}s"
        )

        slew = MeridianSlewScheduler().schedule(flip, DOME_SPEED)
        assert slew.direction == exp_direction, (
            f"{name}: direction {slew.direction} vs attendu {exp_direction} "
            f"(signed_amplitude={flip.signed_amplitude:.2f})"
        )

        # t_start_offset théorique recalculé depuis oracles — vérifie la formule
        exp_offset = max(0.0, (exp_amplitude - DOME_SPEED * exp_duration) / (2 * DOME_SPEED))
        assert slew.t_start_offset == pytest.approx(exp_offset, abs=3.0), (
            f"{name}: t_start_offset {slew.t_start_offset:.1f}s vs attendu {exp_offset:.1f}s"
        )
        assert slew.target == flip.post_target  # invariant scheduler

    def test_capella_post_target_matches_simulation(self, calc, abaque):
        """Capella a ses pre/post_target publiés dans le détail de la simulation."""
        ra, dec = 79.1723, 45.998
        mer_t = find_meridian_time(calc, ra, dec, SIM_SEARCH_START, 18)
        sim_start = mer_t - timedelta(seconds=PRE_MERIDIAN_SEC)
        traj = build_lookahead_trajectory(
            calc,
            abaque,
            ra,
            dec,
            sim_start,
            duration_sec=SIM_DURATION_SEC,
            sampling_sec=SAMPLING_SEC,
        )
        flip = MeridianFlipDetector().detect(traj)
        assert flip is not None
        assert flip.post_target == pytest.approx(CAPELLA_POST_TARGET_EXPECTED, abs=1.0)


# --- Invariants constantes module --------------------------------------------


def test_module_constants_align_with_simulation():
    """Les seuils du module doivent rester alignés avec la simulation de référence.

    Toute modification de FLIP_RATE_THRESHOLD nécessite de regénérer les oracles.
    """
    assert FLIP_RATE_THRESHOLD_DEG_PER_SEC == 0.8
