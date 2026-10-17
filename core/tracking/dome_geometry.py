"""
Modèle géométrique coupole / monture allemande (GEM).

Calcule l'azimut d'ouverture de la coupole pour qu'un tube porté par une monture
allemande vise un objet (altitude, azimut), en tenant compte du côté du pied :
l'axe optique part d'un point décalé du centre de la coupole, et l'ouverture doit
être là où cette droite traverse la sphère de la coupole (intersection droite-sphère).

Contrairement à l'abaque `Loi_coupole.xlsx`, mesurée avec la monture du « bon » côté
pour chaque position, le modèle donne la position pour les deux côtés du pied à tout
angle horaire — par exemple tube encore côté Ouest après le méridien, tant que la
monture n'a pas été retournée.

Principe repris de N.I.N.A. (`NINA.Equipment/Equipment/MyDome/DomeSynchronization.cs`,
https://github.com/isbeorn/nina, licence MPL-2.0). Ce fichier est distribué sous la
même licence (Mozilla Public License 2.0, https://mozilla.org/MPL/2.0/).

Repère : x = Est, y = Nord, z = Zénith, origine au centre de la sphère de la coupole.
Seul le rapport des longueurs au rayon compte pour l'azimut.
"""

from __future__ import annotations

import math
from dataclasses import dataclass
from enum import Enum

import numpy as np
from scipy.optimize import least_squares


class PierSide(Enum):
    """Côté du pied où se trouve le tube (convention ASCOM).

    WEST : tube à l'ouest du pied, vise l'Est — objet avant le méridien.
    EAST : tube à l'est du pied, vise l'Ouest — objet après le méridien (monture retournée).
    """

    WEST = "west"
    EAST = "east"


@dataclass(frozen=True)
class DomeGeometry:
    """Géométrie coupole + monture, longueurs en mètres.

    mount_*_m : position du croisement des axes AD/Déc par rapport au centre de la coupole.
    gem_offset_m : distance du croisement des axes à l'axe optique, le long de l'axe de Déc.
    lateral_m : décalage de l'axe optique perpendiculaire à l'axe de Déc et à la visée
        (tube pas centré sur la queue d'aronde) ; se retourne avec la monture.
    az_offset_deg : décalage entre l'azimut géométrique et l'azimut du codeur coupole.
    """

    dome_radius_m: float
    mount_east_m: float = 0.0
    mount_north_m: float = 0.0
    mount_up_m: float = 0.0
    gem_offset_m: float = 0.0
    lateral_m: float = 0.0
    az_offset_deg: float = 0.0


@dataclass(frozen=True)
class GeometryFit:
    """Résultat d'un calage : géométrie, résidus (mesure − modèle, °) et côté retenu par point."""

    geometry: DomeGeometry
    residuals_deg: list[float]
    sides: list[PierSide]


def expected_pier_side(az_deg: float) -> PierSide:
    """Côté du pied d'une monture retournée exactement au méridien.

    Objet à l'Est du méridien (azimut entre 0° et 180°) → tube côté Ouest.
    """
    return PierSide.WEST if math.sin(math.radians(az_deg)) > 0 else PierSide.EAST


def _side_sign(side: PierSide) -> float:
    return 1.0 if side is PierSide.WEST else -1.0


def _dome_azimuths(params, radius, alt_deg, az_deg, side_sign, latitude_deg):
    """Azimuts coupole vectorisés.

    params = (est, nord, haut, déport, latéral, décalage_az). Retourne (azimuts°, monture_dans_la_coupole).
    """
    east, north, up, gem, lateral, az_offset = params
    alt = np.radians(alt_deg)
    az = np.radians(az_deg)
    lat = math.radians(latitude_deg)

    # Direction de visée et axe polaire (vers le pôle céleste Nord)
    d = np.stack([np.cos(alt) * np.sin(az), np.cos(alt) * np.cos(az), np.sin(alt)], axis=-1)
    polar = np.array([0.0, math.cos(lat), math.sin(lat)])

    # Axe de déclinaison ⟂ axe polaire et visée ; côté Ouest = déport vers d × polaire
    dec_axis = np.cross(d, polar)
    dec_axis /= np.linalg.norm(dec_axis, axis=-1, keepdims=True)
    side = np.asarray(side_sign)[..., None] * dec_axis
    origin = np.array([east, north, up]) + gem * side + lateral * np.cross(d, side)

    # Intersection droite-sphère : |origin + t·d| = R, racine positive
    b = np.sum(origin * d, axis=-1)
    c = np.sum(origin * origin, axis=-1) - radius * radius
    inside = c < 0
    t = -b + np.sqrt(np.maximum(b * b - c, 0.0))
    hit = origin + t[..., None] * d
    azimuth = (np.degrees(np.arctan2(hit[..., 0], hit[..., 1])) + az_offset) % 360.0
    return azimuth, inside


def dome_azimuth(
    geometry: DomeGeometry,
    alt_deg: float,
    az_deg: float,
    pier_side: PierSide,
    latitude_deg: float,
) -> float:
    """Azimut de la coupole (°, 0-360) pour viser (alt, az) avec le tube du côté `pier_side`."""
    params = (
        geometry.mount_east_m,
        geometry.mount_north_m,
        geometry.mount_up_m,
        geometry.gem_offset_m,
        geometry.lateral_m,
        geometry.az_offset_deg,
    )
    azimuth, inside = _dome_azimuths(
        params, geometry.dome_radius_m, alt_deg, az_deg, _side_sign(pier_side), latitude_deg
    )
    if not inside:
        raise ValueError("Le tube est hors de la sphère de la coupole : géométrie incohérente")
    return float(azimuth)


def _wrap(delta):
    return (delta + 180.0) % 360.0 - 180.0


def fit_dome_geometry(
    points: list[tuple[float, float, float]],
    latitude_deg: float,
    dome_radius_m: float,
    n_starts: int = 20,
) -> GeometryFit:
    """Cale la géométrie sur des mesures (altitude°, azimut objet°, azimut coupole°).

    Le côté du pied de chaque point est celui d'une monture retournée au méridien ;
    pour un point exactement au méridien (ambigu), on retient le côté qui colle le mieux.
    Moindres carrés robustes (soft L1, échelle 1°) : quelques mesures aberrantes
    ne tirent pas le calage. Départs multiples déterministes (graine fixe).
    """
    data = np.asarray(points, dtype=float)
    alt, az, measured = data[:, 0], data[:, 1], data[:, 2]
    signs = np.array([_side_sign(expected_pier_side(a)) for a in az])
    at_meridian = np.abs(np.sin(np.radians(az))) < 1e-6
    radius = dome_radius_m

    def residuals_and_sides(x):
        az_a, _ = _dome_azimuths(x, radius, alt, az, signs, latitude_deg)
        az_b, _ = _dome_azimuths(x, radius, alt, az, -signs, latitude_deg)
        r_a = _wrap(measured - az_a)
        r_b = _wrap(measured - az_b)
        flip = at_meridian & (np.abs(r_b) < np.abs(r_a))
        return np.where(flip, r_b, r_a), np.where(flip, -signs, signs)

    # Décalage azimutal initial : moyenne circulaire de (mesure − objet)
    delta = np.radians(measured - az)
    az0 = math.degrees(math.atan2(np.mean(np.sin(delta)), np.mean(np.cos(delta))))

    lim = 0.6 * radius
    lower = [-lim, -lim, -lim, 0.0, -lim, -720.0]
    upper = [lim, lim, lim, 0.8 * radius, lim, 720.0]
    rng = np.random.default_rng(0)
    best = None
    for i in range(n_starts):
        start = (
            np.zeros(6)
            if i == 0
            else np.r_[
                rng.uniform(-0.4, 0.4, 3) * radius,
                rng.uniform(0.0, 0.6) * radius,
                rng.uniform(-0.2, 0.2) * radius,
                0.0,
            ]
        )
        start[5] = az0
        result = least_squares(
            lambda x: residuals_and_sides(x)[0],
            start,
            bounds=(lower, upper),
            loss="soft_l1",
            f_scale=1.0,
        )
        if best is None or result.cost < best.cost:
            best = result

    residuals, chosen = residuals_and_sides(best.x)
    east, north, up, gem, lateral, az_offset = best.x
    geometry = DomeGeometry(
        dome_radius_m=radius,
        mount_east_m=float(east),
        mount_north_m=float(north),
        mount_up_m=float(up),
        gem_offset_m=float(gem),
        lateral_m=float(lateral),
        az_offset_deg=float(_wrap(az_offset)),
    )
    sides = [PierSide.WEST if s > 0 else PierSide.EAST for s in chosen]
    return GeometryFit(geometry=geometry, residuals_deg=[float(r) for r in residuals], sides=sides)
