"""
Détection et anticipation du flip méridien pour la coupole (stratégie E).

Module pur (pas de dépendance runtime au tracking ni au moteur) qui :

1. Projette la trajectoire coupole (astropy + abaque) sur une fenêtre donnée
2. Détecte un flip méridien par analyse du gradient du dome_target
3. Calcule le moment optimal de slew anticipatif, avec direction imposée

Référence théorique (validée par simulation sur 5 objets réels) :

    t_start_offset = max(0, (Δ − v·τ_flip) / (2·v))

où Δ = amplitude signée du flip (via unwrapping cumulatif), v = vitesse coupole
en °/s, τ_flip = durée du flip. Le slew est lancé à flip.start - t_start_offset.

Ce module ne modifie PAS le tracking runtime. Il est consommé par le
`tracking_meridian_anticipation_mixin` (Phase 2) qui l'orchestre.

Voir aussi : scripts/diagnostics/simulate_meridian_anticipation.py (référence
de vérité pour les tests de régression).
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timedelta
from typing import TYPE_CHECKING, Optional

from core.utils.angle_utils import normalize_angle_180, normalize_angle_360

if TYPE_CHECKING:
    from core.observatoire.calculations import AstronomicalCalculations
    from core.tracking.abaque_manager import AbaqueManager


# --- Constantes du détecteur --------------------------------------------------

FLIP_RATE_THRESHOLD_DEG_PER_SEC = 0.8
"""Taux dome_target au-delà duquel on considère être dans un flip."""

FLIP_POST_MARGIN_SEC = 20
"""Marge après flip_end pour échantillonner post_target stable."""

FLIP_PRE_MARGIN_SEC = 10
"""Marge avant flip_start pour échantillonner pre_target stable."""

FLIP_DISCRETE_THRESHOLD_DEG = 30.0
"""Seuil au-delà duquel deux échantillons consécutifs indiquent un flip discret."""

MERIDIAN_ALT_MIN_DEG = 65.0
"""Altitude minimale pour qu'une position soit considérée proche du méridien."""

MERIDIAN_AZ_TOL_DEG = 2.0
"""Tolérance azimutale pour qualifier une position « au méridien »."""


# --- Structures de données ----------------------------------------------------


@dataclass(frozen=True)
class TrajectoryPoint:
    """Un point de la trajectoire projetée de la coupole."""

    t_sec: float
    alt: float
    az: float
    dome_target: float


@dataclass(frozen=True)
class FlipInfo:
    """Caractéristiques d'un flip méridien détecté.

    `amplitude` = abs(signed_amplitude) ; conservés séparément pour lever
    l'ambiguïté des flips > 180° (où le shortest-path mathématique masque
    le vrai sens de rotation que la coupole doit suivre).
    """

    start: float
    end: float
    duration: float
    amplitude: float
    signed_amplitude: float
    pre_target: float
    post_target: float


@dataclass(frozen=True)
class SlewSchedule:
    """Ordre de slew anticipatif calculé pour un flip donné."""

    t_start: float
    t_start_offset: float
    target: float
    direction: int  # +1 = CCW (azimut croissant), -1 = CW, 0 = indéterminé
    flip: FlipInfo


# --- Helpers --------------------------------------------------------------------


def target_at(t_sec: float, trajectory: list[TrajectoryPoint]) -> float:
    """Position cible dome à un t arbitraire, sans interpoler à travers un flip.

    Quand deux échantillons consécutifs présentent un saut > FLIP_DISCRETE_THRESHOLD_DEG,
    on retourne la valeur de l'échantillon temporellement le plus proche plutôt
    que de lisser à travers la discontinuité.
    """
    if not trajectory:
        raise ValueError("trajectory is empty")
    if t_sec <= trajectory[0].t_sec:
        return trajectory[0].dome_target
    if t_sec >= trajectory[-1].t_sec:
        return trajectory[-1].dome_target

    for i in range(len(trajectory) - 1):
        t0, t1 = trajectory[i].t_sec, trajectory[i + 1].t_sec
        if t0 <= t_sec <= t1:
            v0, v1 = trajectory[i].dome_target, trajectory[i + 1].dome_target
            signed_delta = normalize_angle_180(v1 - v0)
            if abs(signed_delta) > FLIP_DISCRETE_THRESHOLD_DEG:
                return v0 if (t_sec - t0) < (t1 - t_sec) else v1
            frac = (t_sec - t0) / (t1 - t0) if t1 > t0 else 0.0
            return normalize_angle_360(v0 + signed_delta * frac)
    return trajectory[-1].dome_target


def is_at_meridian(az: float, alt: float) -> bool:
    """Vrai si la position est proche du méridien (az ≈ 180° subpolaire OU az ≈ 0° circumpolaire).

    Un objet dont la déclinaison excède la latitude du site transite au méridien
    côté Nord (az ≈ 0°) plutôt que Sud (az ≈ 180°). Les deux cas doivent être
    détectés pour que l'anticipation fonctionne sur les circumpolaires.
    """
    if alt <= MERIDIAN_ALT_MIN_DEG:
        return False
    dist_south = abs(normalize_angle_180(az - 180.0))
    dist_north = abs(normalize_angle_180(az))
    return min(dist_south, dist_north) < MERIDIAN_AZ_TOL_DEG


# --- Détecteur de flip --------------------------------------------------------


class MeridianFlipDetector:
    """Détecte un flip méridien dans une trajectoire projetée.

    Scanne les deltas consécutifs du dome_target ; entre en mode flip quand le
    taux dépasse FLIP_RATE_THRESHOLD_DEG_PER_SEC, sort quand il retombe.
    L'amplitude est calculée par intégration des deltas SIGNÉS (unwrapping),
    ce qui capte correctement :
    - les flips subpolaires (passage az=180°, signed<0 vers l'Ouest)
    - les circumpolaires (passage az=0°, signed souvent <0 aussi mais petite amplitude)
    - les flips > 180° (shortest-path normalisé donnerait la mauvaise direction)
    """

    def __init__(
        self,
        rate_threshold_deg_per_sec: float = FLIP_RATE_THRESHOLD_DEG_PER_SEC,
        pre_margin_sec: float = FLIP_PRE_MARGIN_SEC,
        post_margin_sec: float = FLIP_POST_MARGIN_SEC,
    ):
        self.rate_threshold = rate_threshold_deg_per_sec
        self.pre_margin = pre_margin_sec
        self.post_margin = post_margin_sec

    def detect(self, trajectory: list[TrajectoryPoint]) -> Optional[FlipInfo]:
        """Retourne un FlipInfo si un flip est détecté dans la fenêtre, sinon None."""
        if len(trajectory) < 2:
            return None

        in_flip = False
        flip_start_idx: Optional[int] = None
        flip_end_idx: Optional[int] = None

        for i in range(1, len(trajectory)):
            dt = trajectory[i].t_sec - trajectory[i - 1].t_sec
            if dt <= 0:
                continue
            d_target = abs(
                normalize_angle_180(trajectory[i].dome_target - trajectory[i - 1].dome_target)
            )
            rate = d_target / dt
            if rate > self.rate_threshold and not in_flip:
                in_flip = True
                flip_start_idx = i - 1
            elif rate <= self.rate_threshold and in_flip:
                in_flip = False
                flip_end_idx = i
                break

        if flip_start_idx is None or flip_end_idx is None:
            return None

        flip_start_t = trajectory[flip_start_idx].t_sec
        flip_end_t = trajectory[flip_end_idx].t_sec
        pre_target = target_at(max(0.0, flip_start_t - self.pre_margin), trajectory)
        post_target = target_at(flip_end_t + self.post_margin, trajectory)

        signed_amplitude = 0.0
        for i in range(flip_start_idx, flip_end_idx):
            signed_amplitude += normalize_angle_180(
                trajectory[i + 1].dome_target - trajectory[i].dome_target
            )

        return FlipInfo(
            start=flip_start_t,
            end=flip_end_t,
            duration=flip_end_t - flip_start_t,
            amplitude=abs(signed_amplitude),
            signed_amplitude=signed_amplitude,
            pre_target=pre_target,
            post_target=post_target,
        )


# --- Scheduler du slew anticipatif --------------------------------------------


class MeridianSlewScheduler:
    """Calcule le moment, la cible et la direction du slew anticipatif optimal.

    Formule théorique (lag_max minimal vs flip réactif) :
        t_start_offset = max(0, (Δ − v·τ_flip) / (2·v))
    Le slew est lancé à flip.start - t_start_offset, vise post_target, avec
    la direction imposée par le signe de signed_amplitude — essentielle pour
    les flips > 180° (sinon la coupole part dans le mauvais sens via shortest-path).
    """

    def schedule(self, flip: FlipInfo, dome_speed_deg_per_sec: float) -> SlewSchedule:
        if dome_speed_deg_per_sec <= 0:
            raise ValueError(f"dome_speed_deg_per_sec must be > 0, got {dome_speed_deg_per_sec}")
        t_start_offset = max(
            0.0,
            (flip.amplitude - dome_speed_deg_per_sec * flip.duration)
            / (2 * dome_speed_deg_per_sec),
        )
        t_start = flip.start - t_start_offset
        if flip.signed_amplitude > 0:
            direction = 1
        elif flip.signed_amplitude < 0:
            direction = -1
        else:
            direction = 0
        return SlewSchedule(
            t_start=t_start,
            t_start_offset=t_start_offset,
            target=flip.post_target,
            direction=direction,
            flip=flip,
        )


# --- Projection de trajectoire ------------------------------------------------


def build_lookahead_trajectory(
    calc: "AstronomicalCalculations",
    abaque: "AbaqueManager",
    ra_j2000: float,
    dec_j2000: float,
    sim_start: datetime,
    duration_sec: int = 3600,
    sampling_sec: int = 10,
) -> list[TrajectoryPoint]:
    """Construit la projection de la trajectoire dome sur une fenêtre temporelle.

    Retourne une liste de N = duration_sec // sampling_sec + 1 points, chacun
    avec (t_sec relatif au sim_start, alt, az, dome_target). L'abaque doit
    avoir été chargée au préalable (abaque.load_abaque()).
    """
    trajectory: list[TrajectoryPoint] = []
    n_steps = duration_sec // sampling_sec + 1
    for i in range(n_steps):
        t = sim_start + timedelta(seconds=i * sampling_sec)
        az, alt = calc.calculer_coords_horizontales(ra_j2000, dec_j2000, t)
        dome_target, _ = abaque.get_dome_position(alt, az)
        trajectory.append(
            TrajectoryPoint(
                t_sec=float(i * sampling_sec),
                alt=alt,
                az=az,
                dome_target=float(dome_target),
            )
        )
    return trajectory


def find_meridian_time(
    calc: "AstronomicalCalculations",
    ra_j2000: float,
    dec_j2000: float,
    search_start: datetime,
    window_hours: int = 18,
) -> datetime:
    """Trouve l'instant UTC de culmination (max altitude) dans une fenêtre donnée.

    Gère aussi bien les objets subpolaires (culmination à az=180°) que
    circumpolaires (culmination à az=0°). Affinage à 10 s près autour du max.
    """
    best_t, best_alt = search_start, -90.0
    total_minutes = window_hours * 60
    for i in range(total_minutes):
        t = search_start + timedelta(minutes=i)
        _, alt = calc.calculer_coords_horizontales(ra_j2000, dec_j2000, t)
        if alt > best_alt:
            best_alt = alt
            best_t = t
    for i in range(-60, 60):
        t = best_t + timedelta(seconds=i * 10)
        _, alt = calc.calculer_coords_horizontales(ra_j2000, dec_j2000, t)
        if alt > best_alt:
            best_alt = alt
            best_t = t
    return best_t
