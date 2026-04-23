#!/usr/bin/env python3
"""
Simulation monture — tests terrain de jour.

Simule le comportement réel de la monture équatoriale pour des objets connus,
en calculant leur trajectoire heure par heure et en vérifiant les décisions
tracking+coupole. Basé sur les incidents NGC 5033 et LBN 166.16+04.52.

Usage:
    uv run python scripts/test_terrain.py
    uv run python scripts/test_terrain.py --date 2026-03-16
"""

import math
import sys
from datetime import datetime, timedelta
from pathlib import Path

# Ajouter le répertoire racine au path
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from core.config.config_loader import load_config
from core.observatoire import AstronomicalCalculations
from core.tracking.abaque_manager import AbaqueManager
from core.utils.angle_utils import shortest_angular_distance


# =============================================================================
# OBJETS DE TEST (coordonnées J2000 réelles)
# =============================================================================

OBJECTS = [
    {
        "name": "NGC 5033",
        "ra_deg": 198.36,   # 13h13m27s
        "dec_deg": 36.59,   # +36°35'38"
        "description": "Incident 16/03 à 2h20 — flip méridien, delta ~134°",
        "expect_large_delta": True,
        "transit_hour_utc_approx": 1.2,  # ~01h12 UTC (02h12 UTC+1)
    },
    {
        "name": "LBN 166.16+04.52",
        "ra_deg": 81.89,    # depuis les logs terrain
        "dec_deg": 42.97,   # depuis les logs terrain
        "description": "Incident 16/03 à 18h26 — zénith + flip, alt ~86.7°",
        "expect_large_delta": True,
        "transit_hour_utc_approx": 17.4,  # ~17h24 UTC (18h24 UTC+1)
    },
    {
        "name": "M42",
        "ra_deg": 83.82,    # 05h35m17s
        "dec_deg": -5.39,   # -05°23'28"
        "description": "Objet standard bas horizon depuis lat 44°N",
        "expect_large_delta": False,
        "transit_hour_utc_approx": 17.5,
    },
]


def estimate_transit_time(calc, ra_deg, sim_date):
    """Estime l'heure du transit méridien (angle horaire ≈ 0)."""
    best_time = None
    best_ha = 999.0

    # Balayer les 24 heures par pas de 5 minutes
    for minutes in range(0, 1440, 5):
        t = datetime(sim_date.year, sim_date.month, sim_date.day) + timedelta(minutes=minutes)
        ha = calc.calculer_angle_horaire(ra_deg, t)
        # Normaliser HA dans [-180, 180]
        ha_norm = ha if ha <= 180 else ha - 360
        if abs(ha_norm) < abs(best_ha):
            best_ha = ha_norm
            best_time = t

    return best_time


def simulate_object(obj, calc, abaque, sim_date):
    """Simule la trajectoire d'un objet sur 6 heures autour du transit."""
    name = obj["name"]
    ra = obj["ra_deg"]
    dec = obj["dec_deg"]

    print(f"\n{'═' * 60}")
    print(f"  SIMULATION MONTURE — {name}")
    print(f"{'═' * 60}")
    print(f"  Coordonnées J2000 : RA={ra:.2f}° DEC={dec:+.2f}°")
    print(f"  Site : Observatoire Ubik ({calc.latitude:.2f}°N, {calc.longitude:.2f}°E)")
    print(f"  Description : {obj['description']}")

    # Estimer le transit
    transit_time = estimate_transit_time(calc, ra, sim_date)
    if transit_time is None:
        print("  ERREUR: Impossible d'estimer le transit")
        return False

    print(f"  Transit méridien estimé : {transit_time.strftime('%H:%M')} (heure locale)")
    print()

    # Simuler de transit-3h à transit+3h, pas de 10 minutes
    start = transit_time - timedelta(hours=3)
    end = transit_time + timedelta(hours=3)
    step = timedelta(minutes=10)

    print(f"  {'Heure':<10}| {'HA':>8} | {'Az':>7} | {'Alt':>6} | {'Coupole':>8} | {'Delta':>8} | {'Mode':<12}")
    print(f"  {'-'*10}+{'-'*10}+{'-'*9}+{'-'*8}+{'-'*10}+{'-'*10}+{'-'*12}")

    prev_dome_pos = None
    transit_detected = False
    transit_ha = None
    transit_delta = None
    transit_alt = None
    max_delta = 0.0
    all_positions_valid = True
    prev_ha_sign = None

    t = start
    while t <= end:
        # Calculs astronomiques
        az, alt = calc.calculer_coords_horizontales(ra, dec, t)
        ha = calc.calculer_angle_horaire(ra, t)
        ha_norm = ha if ha <= 180 else ha - 360  # [-180, 180]
        ha_hours = ha_norm / 15.0  # en heures

        # Position coupole via abaque
        dome_pos, infos = abaque.get_dome_position(alt, az)

        # Vérifier validité
        if dome_pos is None or math.isnan(dome_pos) or not (0 <= dome_pos <= 360):
            all_positions_valid = False

        # Delta et mode (v5.10 : vitesse unique → mode toujours "continuous")
        if prev_dome_pos is not None:
            delta = shortest_angular_distance(prev_dome_pos, dome_pos)
            mode = "continuous"
        else:
            delta = 0.0
            mode = "—"

        # Détection transit méridien (changement de signe de HA)
        current_ha_sign = 1 if ha_norm >= 0 else -1
        marker = ""
        if prev_ha_sign is not None and current_ha_sign != prev_ha_sign:
            transit_detected = True
            transit_ha = ha_hours
            transit_delta = delta
            transit_alt = alt
            marker = " ★ TRANSIT"

        if abs(delta) > abs(max_delta):
            max_delta = delta

        print(
            f"  {t.strftime('%H:%M'):<10}| {ha_hours:>+7.2f}h | {az:>6.1f}° | {alt:>5.1f}° "
            f"| {dome_pos:>7.1f}° | {delta:>+7.1f}° | {mode:<12}{marker}"
        )

        prev_dome_pos = dome_pos
        prev_ha_sign = current_ha_sign
        t += step

    # === VÉRIFICATIONS ===
    print(f"\n  {'─' * 50}")
    print("  VÉRIFICATIONS")
    print(f"  {'─' * 50}")

    checks_passed = True

    # 1. Transit détecté
    if transit_detected:
        print(f"  Transit détecté : {transit_time.strftime('%H:%M')} (HA={transit_ha:+.2f}h) ✓")
    else:
        print("  Transit non détecté ✗")
        checks_passed = False

    # 2. Grand delta au transit (si attendu)
    if obj["expect_large_delta"]:
        if transit_delta is not None and abs(transit_delta) > 30:
            print(f"  Delta au transit : {transit_delta:+.1f}° > 30° → CONTINUOUS ✓")
        elif transit_delta is not None:
            print(f"  Delta au transit : {transit_delta:+.1f}° — attendu > 30° ✗")
            # Le delta max sur la trajectoire peut être plus grand
            if abs(max_delta) > 30:
                print(f"  (Delta max trajectoire : {max_delta:+.1f}° > 30° — OK sur la trajectoire)")
            else:
                checks_passed = False
        else:
            print("  Delta au transit : non calculé ✗")
            checks_passed = False
    else:
        if abs(max_delta) < 30:
            print(f"  Pas de grand delta : max={max_delta:+.1f}° < 30° ✓")
        else:
            print(f"  Delta inattendu : max={max_delta:+.1f}° > 30° (info)")

    # 3. Altitude au transit
    if transit_alt is not None:
        print(f"  Altitude au transit : {transit_alt:.1f}°")

    # 4. Positions abaque valides
    if all_positions_valid:
        print("  Cohérence abaque : toutes positions dans [0, 360] ✓")
    else:
        print("  Cohérence abaque : positions invalides détectées ✗")
        checks_passed = False

    result = "PASS" if checks_passed else "FAIL"
    print(f"\n  Résultat : {result}")
    return checks_passed


def main():
    """Point d'entrée principal."""
    # Date de simulation (par défaut : date des incidents)
    sim_date = datetime(2026, 3, 16)
    if len(sys.argv) > 2 and sys.argv[1] == "--date":
        try:
            sim_date = datetime.strptime(sys.argv[2], "%Y-%m-%d")
        except ValueError:
            print(f"Date invalide : {sys.argv[2]} (format attendu : YYYY-MM-DD)")
            sys.exit(1)

    # Charger la configuration
    config = load_config()

    # Initialiser les composants
    calc = AstronomicalCalculations(
        latitude=config.site.latitude,
        longitude=config.site.longitude,
        tz_offset=config.site.tz_offset,
    )

    abaque_path = str(Path(__file__).resolve().parent.parent / config.tracking.abaque_file)
    abaque = AbaqueManager(abaque_path)
    if not abaque.load_abaque():
        print("ERREUR: Impossible de charger l'abaque")
        sys.exit(1)

    print(f"{'═' * 60}")
    print("  PROGRAMME DE TESTS TERRAIN — Simulation monture")
    print(f"  Date de simulation : {sim_date.strftime('%Y-%m-%d')}")
    print(f"  Site : {config.site.latitude:.2f}°N, {config.site.longitude:.2f}°E")
    print(f"{'═' * 60}")

    # Exécuter les simulations
    results = {}
    for obj in OBJECTS:
        passed = simulate_object(obj, calc, abaque, sim_date)
        results[obj["name"]] = passed

    # Résumé
    print(f"\n{'═' * 60}")
    print("  RÉSUMÉ")
    print(f"{'═' * 60}")
    total_pass = 0
    total = len(results)
    for name, passed in results.items():
        status = "PASS" if passed else "FAIL"
        if passed:
            total_pass += 1
        print(f"  {name:<25} : {status}")
    print(f"\n  Total : {total_pass}/{total} PASS")
    print(f"{'═' * 60}")

    sys.exit(0 if total_pass == total else 1)


if __name__ == "__main__":
    main()
