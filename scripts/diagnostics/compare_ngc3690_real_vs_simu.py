"""
Comparaison réel vs simulé pour la session NGC 3690 (26-27/04/2026).

Reproduit l'analyse pédagogique faite pour les autres objets en superposant :
  - les corrections réellement observées dans le log motor_service
    (`logs/motor_service_20260426_213832_NGC_3690.log`)
  - les trajectoires prédites par le simulateur pour les 4 stratégies
    (A actuel / B horizon fixe / C adaptatif / E timing optimal)

NGC 3690 est circumpolaire (Dec +58.56°, lat 44.15°) → transit méridien NORD
(az ≈ 0°). Le saut coupole observé : 311.9° → 39.1° à 22:50:29 (delta +87°).

Usage :
    uv run python scripts/diagnostics/compare_ngc3690_real_vs_simu.py
"""

from __future__ import annotations

import sys
from datetime import datetime, timedelta
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(PROJECT_ROOT))

from core.observatoire.calculations import AstronomicalCalculations
from core.tracking.abaque_manager import AbaqueManager
from core.utils.angle_utils import normalize_angle_180

from scripts.diagnostics.simulate_meridian_anticipation import (
    DOME_SPEED_DEG_PER_MIN,
    SITE_LAT,
    SITE_LON,
    detect_flip,
    optimal_slew_schedule,
    simulate,
)

# --- Cible étudiée -----------------------------------------------------------

NGC3690_RA = 172.13
NGC3690_DEC = 58.56

# Le motor_service log timestamps sont en heure LOCALE (Pi configuré en CEST,
# tracking_corrections_mixin appelle datetime.now()). Le calc est instancié
# avec tz_offset=2 (auto-DST ZoneInfo) et soustrait l'offset en interne pour
# obtenir l'UTC. On reproduit ce setup pour aligner sim et log.
SITE_TZ_OFFSET = 2  # CEST en avril
SESSION_START_LOCAL = datetime(2026, 4, 26, 21, 38, 32)  # naive, locale CEST
SESSION_DURATION_SEC = 4 * 3600

LOG_FILE = PROJECT_ROOT / "logs" / "motor_service_20260426_213832_NGC_3690.log"


# --- Lecture log réel --------------------------------------------------------

def parse_real_corrections(log_path: Path):
    """Renvoie une liste de (t_sec_relatif_session, az, alt, dome, delta_deg)."""
    samples = []
    if not log_path.exists():
        return samples

    with log_path.open() as fh:
        for line in fh:
            if "correction | delta=" not in line:
                continue
            parts = line.split()
            if len(parts) < 13:
                continue
            ts_str = parts[0] + " " + parts[1].rstrip(",")
            try:
                ts = datetime.strptime(
                    ts_str.split(",")[0],
                    "%Y-%m-%d %H:%M:%S",
                )
            except ValueError:
                continue
            try:
                delta = float(parts[9].split("=")[1])
                az = float(parts[10].split("=")[1])
                alt = float(parts[11].split("=")[1])
                dome = float(parts[12].split("=")[1])
            except (IndexError, ValueError):
                continue
            t_sec = (ts - SESSION_START_LOCAL).total_seconds()
            samples.append((t_sec, az, alt, dome, delta))

    # dédoublonne (le log écrit 2 lignes par correction)
    dedup = []
    last = None
    for s in samples:
        if last is None or s[0] != last[0]:
            dedup.append(s)
        last = s
    return dedup


# --- Comparaison -------------------------------------------------------------

def main() -> None:
    calc = AstronomicalCalculations(SITE_LAT, SITE_LON, tz_offset=SITE_TZ_OFFSET)
    abaque = AbaqueManager()
    abaque.load_abaque()

    # 1) Trajectoire céleste alignée sur le start session (datetime local naive)
    sim_start = SESSION_START_LOCAL
    n_steps = SESSION_DURATION_SEC // 10 + 1
    traj = []
    for i in range(n_steps):
        t = sim_start + timedelta(seconds=i * 10)
        az, alt = calc.calculer_coords_horizontales(NGC3690_RA, NGC3690_DEC, t)
        dome_target, _ = abaque.get_dome_position(alt, az)
        traj.append({
            "t_sec": i * 10,
            "alt": alt,
            "az": az,
            "dome_target": float(dome_target),
        })

    # 2) Détection flip + schedule
    flip = detect_flip(traj)
    print("=" * 110)
    print("COMPARAISON RÉEL vs SIMULÉ — NGC 3690 (26-27/04/2026)")
    print("=" * 110)
    print(f"Site : lat={SITE_LAT}° lon={SITE_LON}° | vitesse coupole : {DOME_SPEED_DEG_PER_MIN:.0f}°/min")
    print(f"Cible : RA={NGC3690_RA}° Dec={NGC3690_DEC}° (circumpolaire, transit nord)")
    print(f"Session : start {SESSION_START_LOCAL.strftime('%Y-%m-%d %H:%M:%S')} local "
          f"(tz={SITE_TZ_OFFSET:+d}h) | durée sim {SESSION_DURATION_SEC // 60} min")
    print("-" * 110)

    if flip is None:
        print("⚠️  Aucun flip détecté dans la fenêtre simulée.")
    else:
        flip_t_abs = SESSION_START_LOCAL + timedelta(seconds=flip["start"])
        flip_end_abs = SESSION_START_LOCAL + timedelta(seconds=flip["end"])
        print(f"Flip détecté : T+{flip['start']}s → T+{flip['end']}s "
              f"(durée {flip['duration']:.0f}s, Δ={flip['amplitude']:.1f}°, "
              f"signed={flip['signed_amplitude']:+.1f}°)")
        print(f"              local absolu : {flip_t_abs.strftime('%H:%M:%S')} → {flip_end_abs.strftime('%H:%M:%S')}")
        print(f"              pre_target={flip['pre_target']:.1f}° → post_target={flip['post_target']:.1f}°")

        slew_t, slew_target, direction = optimal_slew_schedule(flip)
        slew_t_abs = SESSION_START_LOCAL + timedelta(seconds=slew_t)
        print(f"Schedule E   : t_start=T+{slew_t:.0f}s ({slew_t_abs.strftime('%H:%M:%S')}) "
              f"target={slew_target:.1f}° direction={direction:+d}")

    # 3) Simulations
    print()
    print(f"{'Stratégie':<24}{'lag_max':>10}{'lag_avg':>10}{'moves':>8}{'distance':>10}")
    print("-" * 62)
    results = {}
    for name, key in [("A actuel (réactif)", "reactive"),
                      ("B horizon fixe 180s", "fixed"),
                      ("C horizon adaptatif", "adaptive"),
                      ("E timing optimal", "optimal")]:
        r = simulate(traj, key)
        results[key] = r
        print(f"{name:<24}{r['max_lag']:>9.2f}°{r['avg_lag']:>9.2f}°"
              f"{r['dome'].move_count:>8d}{r['dome'].total_distance:>9.1f}°")

    # 4) Lecture log réel + extraction transit
    print()
    print("-" * 110)
    print("OBSERVATION RÉELLE (log motor_service)")
    print("-" * 110)
    real = parse_real_corrections(LOG_FILE)
    print(f"Corrections enregistrées : {len(real)}")
    if real:
        first, last = real[0], real[-1]
        print(f"Première : T+{first[0]:>5.0f}s | az={first[1]:.1f}° alt={first[2]:.1f}° "
              f"dome={first[3]:.1f}° delta={first[4]:+.2f}°")
        print(f"Dernière : T+{last[0]:>5.0f}s | az={last[1]:.1f}° alt={last[2]:.1f}° "
              f"dome={last[3]:.1f}° delta={last[4]:+.2f}°")

        # Transit réel : la plus grosse correction
        big = max(real, key=lambda r: abs(r[4]))
        big_abs = SESSION_START_LOCAL + timedelta(seconds=big[0])
        print(f"Plus gros saut : T+{big[0]:>5.0f}s ({big_abs.strftime('%H:%M:%S')} local) | "
              f"delta={big[4]:+.2f}° az={big[1]:.1f}° alt={big[2]:.1f}° dome→{big[3]:.1f}°")

        # Position dome juste avant la grosse correction
        idx = real.index(big)
        if idx > 0:
            prev = real[idx - 1]
            print(f"  → avant : T+{prev[0]:>5.0f}s dome={prev[3]:.1f}° "
                  f"(saut coupole {prev[3]:.1f}° → {big[3]:.1f}°)")

        # Lag réel calculé : compare dome observé à dome_target théorique
        lag_real_max = 0.0
        lag_real_at_transit = 0.0
        for t_sec, az, alt, dome, delta in real:
            i_traj = min(int(t_sec // 10), len(traj) - 1)
            target = traj[i_traj]["dome_target"]
            lag = abs(normalize_angle_180(target - dome))
            if lag > lag_real_max:
                lag_real_max = lag
            if flip and abs(t_sec - flip["start"]) < 60:
                lag_real_at_transit = max(lag_real_at_transit, lag)
        print(f"Lag max observé (post-correction) : {lag_real_max:.2f}°")

    # 5) Synthèse
    print()
    print("-" * 110)
    print("SYNTHÈSE")
    print("-" * 110)
    a = results["reactive"]["max_lag"]
    e = results["optimal"]["max_lag"]
    if flip is None:
        print("Stratégie E inapplicable (pas de flip détecté dans la fenêtre).")
    else:
        gain_e = a - e
        pct = 100 * gain_e / a if a > 0 else 0
        print(f"Stratégie A (= ce qui a tourné réellement)  → lag max simulé : {a:.1f}°")
        print(f"Stratégie E (anticipation pré-calculée)     → lag max simulé : {e:.1f}°")
        print(f"Gain théorique E vs A : -{gain_e:.1f}° ({pct:+.0f}%)")
        slew_t, _, _ = optimal_slew_schedule(flip)
        if flip["start"] > 3600:
            print(f"\nDans la session réelle, la fenêtre du détecteur (3600s) était dépassée "
                  f"de {flip['start'] - 3600}s : le flip était à T+{flip['start']}s, hors fenêtre.")
            print(f"→ legitimement loggé `meridian_anticipation_no_flip`. "
                  f"Tracking réactif a pris le relais.")
        else:
            print(f"\nLe flip était dans la fenêtre 3600s du détecteur (T+{flip['start']}s) "
                  f"→ l'anticipation aurait dû déclencher en runtime.")


if __name__ == "__main__":
    main()
