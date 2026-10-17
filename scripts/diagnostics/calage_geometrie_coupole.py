"""
Calage du modèle géométrique coupole / monture sur l'abaque `data/Loi_coupole.xlsx`.

Étape 1 du chantier « retournement de la monture » (17/10/2026) : l'ASIAIR retourne
la monture après la fin de la pose en cours (jusqu'à ~11 min après le méridien),
alors que l'abaque fait basculer la coupole au méridien. Le modèle géométrique
(core/tracking/dome_geometry.py) donne la position pour les deux côtés du pied ;
ce script cale ses paramètres sur les 275 mesures de l'abaque et signale les
mesures qui ne s'accordent pas avec la géométrie.

N'agit sur rien : lecture de l'abaque et affichage uniquement.

Usage :
    uv run python scripts/diagnostics/calage_geometrie_coupole.py
    uv run python scripts/diagnostics/calage_geometrie_coupole.py --rayon 1.2 --seuil 5
"""

from __future__ import annotations

import argparse
import logging
import math
import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(PROJECT_ROOT))

from core.config.config import SITE_LATITUDE  # noqa: E402
from core.tracking.abaque_manager import AbaqueManager  # noqa: E402
from core.tracking.dome_geometry import expected_pier_side, fit_dome_geometry  # noqa: E402

# Rayon de la coupole : config d'origine v4.3 (`rayon_coupole_cm: 120`) et TRACKING_LOGIC.md
RAYON_COUPOLE_M = 1.20


def _rms(values: list[float]) -> float:
    return math.sqrt(sum(v * v for v in values) / len(values)) if values else float("nan")


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[1])
    parser.add_argument("--abaque", default=str(PROJECT_ROOT / "data" / "Loi_coupole.xlsx"))
    parser.add_argument(
        "--rayon", type=float, default=RAYON_COUPOLE_M, help="rayon de la coupole (m)"
    )
    parser.add_argument("--seuil", type=float, default=5.0, help="écart signalé comme douteux (°)")
    args = parser.parse_args()

    logging.disable(logging.INFO)
    abaque = AbaqueManager(args.abaque)
    if not abaque.load_abaque():
        print(f"Abaque illisible : {args.abaque}")
        return 1
    points = [
        (alt, az, dome)
        for alt, d in sorted(abaque.data_by_altitude.items())
        for az, dome in zip(d["az_astre"], d["az_coupole"])
    ]

    fit = fit_dome_geometry(points, SITE_LATITUDE, dome_radius_m=args.rayon)
    g = fit.geometry

    print(
        f"Calage sur {len(points)} points — latitude {SITE_LATITUDE}°, rayon coupole {g.dome_radius_m:.2f} m\n"
    )
    print("Géométrie (croisement des axes par rapport au centre de la coupole) :")
    print(f"  vers l'Est        {g.mount_east_m * 100:+6.1f} cm")
    print(f"  vers le Nord      {g.mount_north_m * 100:+6.1f} cm")
    print(f"  vers le haut      {g.mount_up_m * 100:+6.1f} cm")
    print(f"  déport du tube    {g.gem_offset_m * 100:6.1f} cm   (mesure d'origine : 40 cm)")
    print(f"  décalage latéral  {g.lateral_m * 100:+6.1f} cm")
    print(f"  décalage codeur   {g.az_offset_deg:+6.2f}°\n")

    residus = fit.residuals_deg
    print(
        f"Écart modèle / abaque : rms {_rms(residus):.2f}°, "
        f"médiane {sorted(abs(r) for r in residus)[len(residus) // 2]:.2f}°\n"
    )
    print("Par altitude :   rms     max")
    for alt in sorted({p[0] for p in points}):
        r = [res for p, res in zip(points, residus) if p[0] == alt]
        print(f"  {alt:5.1f}°      {_rms(r):5.2f}°  {max(abs(x) for x in r):5.2f}°")

    douteux = [(p, r, s) for p, r, s in zip(points, residus, fit.sides) if abs(r) > args.seuil]
    print(f"\nMesures à plus de {args.seuil:.0f}° du modèle ({len(douteux)}) :")
    print("  alt     az objet  az coupole  modèle   écart  côté du pied")
    for (alt, az, dome), r, side in sorted(douteux, key=lambda x: -abs(x[1])):
        marque = "" if side is expected_pier_side(az) else " (au méridien)"
        print(
            f"  {alt:5.1f}  {az:7.1f}   {dome:8.1f}   {(dome - r) % 360:7.1f}  {r:+6.1f}  {side.value}{marque}"
        )
    return 0


if __name__ == "__main__":
    sys.exit(main())
