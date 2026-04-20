"""
Simulation comparative : tracking réactif (actuel) vs anticipatif au passage méridien.

Balayage multi-altitudes pour évaluer la robustesse de l'idée Serge (20/04/2026) :
au lieu de rattraper le méridien par corrections successives, anticiper la position
dome cible N secondes plus tard et y aller en un seul GOTO.

Objets synthétisés (RA 0°, Dec ajusté pour un alt_max cible au méridien) sur le
site de l'Observatoire Ubik (lat 44.15°, lon 5.23°). Un objet réel (46 LMi) sert
de cas de référence.

Vitesse moteur : 42°/min (max mesuré terrain 22-23/03, 96°/min UPAN non
atteignable — firmware fermé).

Usage :
    uv run python scripts/diagnostics/simulate_meridian_anticipation.py
"""

from __future__ import annotations

import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(PROJECT_ROOT))

from core.observatoire.calculations import AstronomicalCalculations
from core.tracking.abaque_manager import AbaqueManager
from core.utils.angle_utils import normalize_angle_180, normalize_angle_360


# --- Paramètres globaux -------------------------------------------------------

SITE_LAT = 44.15
SITE_LON = 5.23
SIM_SEARCH_START = datetime(2026, 3, 28, 18, 0, 0, tzinfo=timezone.utc)  # début recherche méridien
SEARCH_WINDOW_HOURS = 18
SIM_DURATION_SEC = 3600   # 1 h autour du méridien
PRE_MERIDIAN_SEC = 500    # sim commence 500s avant le transit détecté
SAMPLING_SEC = 10

DOME_SPEED_DEG_PER_MIN = 42.0
DOME_SPEED_DEG_PER_SEC = DOME_SPEED_DEG_PER_MIN / 60.0

NORMAL_INTERVAL_SEC = 60
CORRECTION_THRESHOLD_DEG = 0.5

# Anticipation
MERIDIAN_AZ_TOL_DEG = 2.0
MERIDIAN_ALT_MIN_DEG = 65.0
ANTICIPATION_HORIZON_SEC = 180  # stratégie B (horizon fixe)

# Stratégie C : horizon adaptatif par point-fixe
#   On cherche H tel que |target(T+H) - pos_now| / vitesse = H
#   → on vise la position où la cible sera AU MOMENT où on y arrive.
ADAPTIVE_MAX_H_SEC = 300  # on cherche H dans [min, max]
ADAPTIVE_MIN_H_SEC = 10
ADAPTIVE_STEP_SEC = 2     # pas de scan (2s = compromis précision/perf)
ADAPTIVE_TOL_SEC = 3.0    # tolérance |required_H - H|

# Stratégie D : chain mode (GOTO adaptatifs enchaînés pendant méridien)
CHAIN_EXIT_HORIZON_SEC = 20   # sortie de chain mode quand H adaptatif < seuil
CHAIN_EXIT_DELTA_DEG = 3.0    # ou quand la cible future est très proche (< seuil)

# Stratégie E : timing optimal basé sur la prédiction du flip
#   Détection : taux du target > FLIP_RATE_THRESHOLD sur une période continue
#   |t_start|_opt = max(0, (Δ_flip - v·τ_flip) / (2·v))  — équilibre lag pré/post flip
FLIP_RATE_THRESHOLD_DEG_PER_SEC = 0.8  # abaissé pour capturer flips lents (alt 75-80°)
FLIP_POST_MARGIN_SEC = 20     # sample target(flip_end + margin) pour valeur stable


# --- Scénarios : objets à tester ---------------------------------------------
# (nom, RA_J2000°, Dec_J2000°, description)
# Pour atteindre un alt_max donné au méridien depuis lat 44.15° : dec = lat - (90 - alt_max)
# ou dec = lat + (90 - alt_max) selon le côté (on prend le nord pour rester > 60°).

OBJECTS = [
    ("alt=70° (dec+24.15°)", 120.0, 24.15),
    ("alt=75° (dec+29.15°)", 130.0, 29.15),
    ("alt=80° (dec+34.15°)", 140.0, 34.15),
    ("alt=83° (dec+37.15°)", 150.0, 37.15),
    ("alt=86° (dec+40.15°)", 160.0, 40.15),
    ("alt=88° (dec+42.15°)", 170.0, 42.15),
    ("46 LMi (réel)        ", 163.32787152823542, 34.214892133082785),
]


# --- Recherche méridien -------------------------------------------------------

def find_meridian_time(calc: AstronomicalCalculations, ra: float, dec: float,
                       start: datetime, window_hours: int) -> datetime:
    """Trouve l'UTC où |az - 180°| est minimal avec alt > 0°."""
    best_t, best_d = start, 1e9
    total_minutes = window_hours * 60
    for i in range(total_minutes):
        t = start + timedelta(minutes=i)
        az, alt = calc.calculer_coords_horizontales(ra, dec, t)
        if alt <= 0:
            continue
        d = abs(normalize_angle_180(az - 180.0))
        if d < best_d:
            best_d = d
            best_t = t
    # Affinage à 10s près autour du minimum
    for i in range(-60, 60):
        t = best_t + timedelta(seconds=i * 10)
        az, alt = calc.calculer_coords_horizontales(ra, dec, t)
        if alt <= 0:
            continue
        d = abs(normalize_angle_180(az - 180.0))
        if d < best_d:
            best_d = d
            best_t = t
    return best_t


def build_trajectory(calc, abaque, ra, dec, sim_start):
    traj = []
    n_steps = SIM_DURATION_SEC // SAMPLING_SEC + 1
    for i in range(n_steps):
        t = sim_start + timedelta(seconds=i * SAMPLING_SEC)
        az, alt = calc.calculer_coords_horizontales(ra, dec, t)
        dome_target, _ = abaque.get_dome_position(alt, az)
        traj.append({
            "t_sec": i * SAMPLING_SEC,
            "alt": alt,
            "az": az,
            "dome_target": float(dome_target),
        })
    return traj


def find_meridian_index(traj):
    best_i, best_d = 0, 1e9
    for i, p in enumerate(traj):
        d = abs(normalize_angle_180(p["az"] - 180.0))
        if d < best_d:
            best_d = d
            best_i = i
    return best_i


# --- Simulation moteur --------------------------------------------------------

class DomeSim:
    def __init__(self, initial_pos: float):
        self.pos = initial_pos
        self.busy_until = 0
        self.total_distance = 0.0
        self.move_count = 0
        self.total_move_time = 0.0
        self.current_signed_delta = 0.0  # pour position_during_move avec direction imposée

    def request_move(self, t_now: float, target: float, force_direction: int = 0) -> bool:
        """force_direction : 0 = shortest path, +1 = CCW (increase), -1 = CW (decrease)."""
        if t_now < self.busy_until:
            return False
        if force_direction == 0:
            delta = normalize_angle_180(target - self.pos)
        elif force_direction > 0:
            delta = (target - self.pos) % 360
        else:
            delta = -((self.pos - target) % 360)
        if abs(delta) < CORRECTION_THRESHOLD_DEG:
            return False
        duration = abs(delta) / DOME_SPEED_DEG_PER_SEC
        self.busy_until = t_now + duration
        self.pos = normalize_angle_360(target)
        self.total_distance += abs(delta)
        self.move_count += 1
        self.total_move_time += duration
        self.current_signed_delta = delta
        return True


FLIP_THRESHOLD_DEG = 30.0  # au-delà, on considère que c'est un flip discret (pas d'interp)


def target_at(t_sec: float, traj) -> float:
    """Position cible dome à un t arbitraire, sans interpoler à travers un flip."""
    if t_sec <= traj[0]["t_sec"]:
        return traj[0]["dome_target"]
    if t_sec >= traj[-1]["t_sec"]:
        return traj[-1]["dome_target"]
    for i in range(len(traj) - 1):
        if traj[i]["t_sec"] <= t_sec <= traj[i + 1]["t_sec"]:
            t0, t1 = traj[i]["t_sec"], traj[i + 1]["t_sec"]
            v0, v1 = traj[i]["dome_target"], traj[i + 1]["dome_target"]
            delta = abs(normalize_angle_180(v1 - v0))
            if delta > FLIP_THRESHOLD_DEG:
                # Flip méridien : retour de la valeur la plus proche dans le temps
                return v0 if (t_sec - t0) < (t1 - t_sec) else v1
            frac = (t_sec - t0) / (t1 - t0)
            signed_delta = normalize_angle_180(v1 - v0)
            return normalize_angle_360(v0 + signed_delta * frac)
    return traj[-1]["dome_target"]


def detect_flip(traj) -> dict | None:
    """Détecte le flip méridien dans la trajectoire.

    Calcule l'amplitude signée via intégration des deltas consécutifs (unwrapping)
    pour capturer la VRAIE direction du flip, pas le plus court chemin mathématique.
    """
    in_flip = False
    flip_start_idx, flip_end_idx = None, None
    for i in range(1, len(traj)):
        dt = traj[i]["t_sec"] - traj[i - 1]["t_sec"]
        d_target = abs(normalize_angle_180(
            traj[i]["dome_target"] - traj[i - 1]["dome_target"]))
        rate = d_target / dt
        if rate > FLIP_RATE_THRESHOLD_DEG_PER_SEC and not in_flip:
            in_flip = True
            flip_start_idx = i - 1
        elif rate <= FLIP_RATE_THRESHOLD_DEG_PER_SEC and in_flip:
            in_flip = False
            flip_end_idx = i
            break

    if flip_start_idx is None or flip_end_idx is None:
        return None

    flip_start_t = traj[flip_start_idx]["t_sec"]
    flip_end_t = traj[flip_end_idx]["t_sec"]
    pre_target = target_at(max(0, flip_start_t - 10), traj)
    post_target = target_at(flip_end_t + FLIP_POST_MARGIN_SEC, traj)

    # Amplitude signée par unwrapping : somme des deltas signés consécutifs
    signed_amplitude = 0.0
    for i in range(flip_start_idx, flip_end_idx):
        signed_amplitude += normalize_angle_180(
            traj[i + 1]["dome_target"] - traj[i]["dome_target"])

    return {
        "start": flip_start_t,
        "end": flip_end_t,
        "duration": flip_end_t - flip_start_t,
        "amplitude": abs(signed_amplitude),
        "signed_amplitude": signed_amplitude,
        "pre_target": pre_target,
        "post_target": post_target,
    }


def optimal_slew_schedule(flip: dict) -> tuple:
    """Calcule (t_start, target, direction) du slew optimal.

    direction : +1 = CCW (azimut croissant), -1 = CW (décroissant).
    On utilise l'amplitude SIGNÉE du flip (via unwrapping) pour le sens réel.
    """
    v = DOME_SPEED_DEG_PER_SEC
    delta = flip["amplitude"]
    tau_flip = flip["duration"]
    t_start_offset = max(0.0, (delta - v * tau_flip) / (2 * v))
    slew_start_t = flip["start"] - t_start_offset
    direction = 1 if flip["signed_amplitude"] > 0 else -1
    return slew_start_t, flip["post_target"], direction


def adaptive_horizon(t_trigger: float, pos_now: float, traj, debug: bool = False) -> tuple:
    """Scan descendant : plus grand H tel que |target(T+H) - pos_now|/speed ≈ H.

    Sélectionne la solution POST-flip en scannant du plus grand vers le plus petit H.
    Si aucun H ne satisfait la tolérance, retourne celui qui minimise l'erreur.
    """
    best_H, best_err, best_target = None, 1e9, pos_now
    for H_int in range(ADAPTIVE_MAX_H_SEC, ADAPTIVE_MIN_H_SEC, -ADAPTIVE_STEP_SEC):
        H = float(H_int)
        future_target = target_at(t_trigger + H, traj)
        delta = abs(normalize_angle_180(future_target - pos_now))
        required_H = delta / DOME_SPEED_DEG_PER_SEC
        err = abs(required_H - H)
        # Scan descendant : premier H avec |err| < tol = plus grand valide
        if err < ADAPTIVE_TOL_SEC:
            if debug:
                print(f"  [adaptive] T={t_trigger} pos={pos_now:.1f} → H={H:.0f}s "
                      f"target={future_target:.1f}° (req_H={required_H:.1f}, err={err:.1f})")
            return H, future_target
        if err < best_err:
            best_err, best_H, best_target = err, H, future_target
    if debug:
        print(f"  [adaptive] T={t_trigger} pos={pos_now:.1f} → fallback H={best_H:.0f}s "
              f"target={best_target:.1f}° (best_err={best_err:.1f})")
    return (best_H or ADAPTIVE_MIN_H_SEC), best_target


def position_during_move(t_now, pre_pos, target, move_start, busy_until, signed_delta=None):
    if t_now >= busy_until:
        return normalize_angle_360(target)
    if signed_delta is None:
        signed_delta = normalize_angle_180(target - pre_pos)
    frac = (t_now - move_start) / (busy_until - move_start)
    return normalize_angle_360(pre_pos + signed_delta * frac)


def simulate(traj, strategy: str, debug: bool = False):
    """strategy ∈ {'reactive', 'fixed', 'adaptive', 'chained', 'optimal'}."""
    dome = DomeSim(initial_pos=traj[0]["dome_target"])
    meridian_triggered = False
    chain_active = False
    last_correction_t = 0
    move_start = 0.0
    pre_move_pos = dome.pos
    current_target = dome.pos
    lags = []
    trigger_info = None
    chain_moves = []  # liste (t, horizon, target) pour debug

    # Stratégie E : pré-calcul du schedule optimal
    optimal_schedule = None
    signed_delta_E = None  # pour position_during_move
    if strategy == "optimal":
        flip = detect_flip(traj)
        if flip:
            slew_start_t, slew_target, direction = optimal_slew_schedule(flip)
            optimal_schedule = {
                "t_start": slew_start_t,
                "target": slew_target,
                "direction": direction,
                "flip": flip,
            }

    for p in traj:
        t = p["t_sec"]

        if t < dome.busy_until:
            actual = position_during_move(t, pre_move_pos, current_target,
                                          move_start, dome.busy_until,
                                          signed_delta=dome.current_signed_delta)
        else:
            actual = dome.pos

        lag = abs(normalize_angle_180(p["dome_target"] - actual))
        lags.append(lag)

        at_meridian = (abs(normalize_angle_180(p["az"] - 180.0)) < MERIDIAN_AZ_TOL_DEG
                       and p["alt"] > MERIDIAN_ALT_MIN_DEG)

        # --- Stratégie E : timing optimal pré-calculé ---
        if strategy == "optimal" and optimal_schedule and not meridian_triggered:
            if t >= optimal_schedule["t_start"] and t >= dome.busy_until:
                pre_move_pos = dome.pos
                current_target = optimal_schedule["target"]
                move_start = t
                if dome.request_move(t, optimal_schedule["target"],
                                     force_direction=optimal_schedule["direction"]):
                    meridian_triggered = True
                    last_correction_t = t
                    trigger_info = {
                        "t": t,
                        "target": optimal_schedule["target"],
                        "direction": optimal_schedule["direction"],
                        "from": pre_move_pos,
                        "flip": optimal_schedule["flip"],
                    }
                continue

        # --- Stratégies anticipatives (fixed / adaptive / chained) ---
        if strategy in ("fixed", "adaptive", "chained"):
            # Entrée dans la zone méridien
            if not meridian_triggered and at_meridian:
                if strategy == "fixed":
                    horizon = ANTICIPATION_HORIZON_SEC
                    future_target = target_at(t + horizon, traj)
                else:
                    horizon, future_target = adaptive_horizon(t, dome.pos, traj, debug=debug)

                pre_move_pos = dome.pos
                current_target = future_target
                move_start = t
                if dome.request_move(t, future_target):
                    meridian_triggered = True
                    chain_active = (strategy == "chained")
                    last_correction_t = t
                    trigger_info = {"t": t, "horizon": horizon, "target": future_target,
                                    "from": pre_move_pos}
                    chain_moves.append((t, horizon, future_target))
                continue

            # Chain mode : enchaîner les GOTO adaptatifs dès que le dome est libre
            if chain_active and t >= dome.busy_until:
                horizon, future_target = adaptive_horizon(t, dome.pos, traj, debug=debug)
                delta = abs(normalize_angle_180(future_target - dome.pos))
                # Sortie de chain mode si la cible future est stable (petit horizon & petit delta)
                if horizon < CHAIN_EXIT_HORIZON_SEC and delta < CHAIN_EXIT_DELTA_DEG:
                    chain_active = False
                    last_correction_t = t
                elif delta >= CORRECTION_THRESHOLD_DEG:
                    pre_move_pos = dome.pos
                    current_target = future_target
                    move_start = t
                    dome.request_move(t, future_target)
                    last_correction_t = t
                    chain_moves.append((t, horizon, future_target))
                    continue

        # Tracking normal (en dehors du méridien OU après sortie du chain)
        if t - last_correction_t >= NORMAL_INTERVAL_SEC and t >= dome.busy_until:
            delta = abs(normalize_angle_180(p["dome_target"] - dome.pos))
            if delta >= CORRECTION_THRESHOLD_DEG:
                pre_move_pos = dome.pos
                current_target = p["dome_target"]
                move_start = t
                dome.request_move(t, p["dome_target"])
            last_correction_t = t

    return {
        "dome": dome,
        "max_lag": max(lags),
        "avg_lag": sum(lags) / len(lags),
        "trigger": trigger_info,
        "chain_moves": chain_moves,
    }


# --- Rapport ------------------------------------------------------------------

def main():
    calc = AstronomicalCalculations(SITE_LAT, SITE_LON, tz_offset=0)
    abaque = AbaqueManager()
    abaque.load_abaque()

    print("=" * 130)
    print(f"SIMULATION MULTI-ALTITUDES — A (actuel) / B (fixe {ANTICIPATION_HORIZON_SEC}s) / C (adaptatif) / E (timing optimal pré-calculé)")
    print(f"Site : lat={SITE_LAT}° lon={SITE_LON}° | vitesse coupole : {DOME_SPEED_DEG_PER_MIN:.0f}°/min")
    print("=" * 130)

    header = (f"{'Scénario':<22} {'alt_max':>7} | "
              f"{'A_lagM':>7} | "
              f"{'B_lagM':>7} | "
              f"{'C_lagM':>7} | "
              f"{'E_lagM':>7} {'E_th':>6} {'E_tSt':>6} {'Δ_flip':>7} {'τ_flip':>6}")
    print(header)
    print("-" * len(header))

    results = []
    for name, ra, dec in OBJECTS:
        mer_t = find_meridian_time(calc, ra, dec, SIM_SEARCH_START, SEARCH_WINDOW_HOURS)
        sim_start = mer_t - timedelta(seconds=PRE_MERIDIAN_SEC)
        traj = build_trajectory(calc, abaque, ra, dec, sim_start)
        idx = find_meridian_index(traj)
        alt_max = traj[idx]["alt"]

        r_a = simulate(traj, "reactive")
        r_b = simulate(traj, "fixed")
        r_c = simulate(traj, "adaptive")
        r_e = simulate(traj, "optimal")
        results.append((name, alt_max, r_a, r_b, r_c, r_e, ra, dec))

        # Métriques théoriques E
        flip = detect_flip(traj)
        if flip:
            v = DOME_SPEED_DEG_PER_SEC
            e_theoretical = max(0.0, (flip["amplitude"] - v * flip["duration"]) / 2.0)
            t_start_off = max(0.0, (flip["amplitude"] - v * flip["duration"]) / (2 * v))
            flip_amp = flip["amplitude"]
            flip_dur = flip["duration"]
        else:
            e_theoretical, t_start_off, flip_amp, flip_dur = 0.0, 0.0, 0.0, 0.0

        print(
            f"{name:<22} {alt_max:>6.1f}° | "
            f"{r_a['max_lag']:>6.2f}° | "
            f"{r_b['max_lag']:>6.2f}° | "
            f"{r_c['max_lag']:>6.2f}° | "
            f"{r_e['max_lag']:>6.2f}° {e_theoretical:>5.1f}° {t_start_off:>5.0f}s "
            f"{flip_amp:>6.1f}° {flip_dur:>5.0f}s"
        )

    print()
    print("Légende : lagM = lag max mesuré | E_th = lag max théorique (modèle linéaire)")
    print("          E_tSt = offset optimal avant flip_start | Δ_flip = amplitude | τ_flip = durée")
    print()

    # Gains vs A
    print("-" * 130)
    print("GAIN LAG MAX vs stratégie actuelle (A)")
    print("-" * 130)
    print(f"{'Scénario':<22} {'alt_max':>7}  {'A_lagM':>8}  {'B vs A':>10}  {'C vs A':>10}  {'E vs A':>10}  {'E vs C':>10}")
    for name, alt_max, r_a, r_b, r_c, r_e, _, _ in results:
        dba = r_b["max_lag"] - r_a["max_lag"]
        dca = r_c["max_lag"] - r_a["max_lag"]
        dea = r_e["max_lag"] - r_a["max_lag"]
        dec_ = r_e["max_lag"] - r_c["max_lag"]
        print(f"{name:<22} {alt_max:>6.1f}°  {r_a['max_lag']:>7.2f}°  "
              f"{dba:>+9.2f}°  {dca:>+9.2f}°  {dea:>+9.2f}°  {dec_:>+9.2f}°")

    # Détail schedule pour le pire cas
    print()
    worst = max(results, key=lambda r: r[1])
    print("-" * 130)
    print(f"DÉTAIL — {worst[0]} (alt_max={worst[1]:.1f}°) : schedule E")
    print("-" * 130)
    _, _, _, _, _, r_e, ra, dec = worst
    mer_t = find_meridian_time(calc, ra, dec, SIM_SEARCH_START, SEARCH_WINDOW_HOURS)
    if r_e["trigger"]:
        tr = r_e["trigger"]
        flip = tr["flip"]
        print(f"Méridien UTC : {mer_t.strftime('%H:%M:%S')}")
        print(f"Flip détecté : T+{flip['start']:.0f}s → T+{flip['end']:.0f}s "
              f"(durée {flip['duration']:.0f}s, Δ={flip['amplitude']:.1f}°)")
        print(f"              pre_target={flip['pre_target']:.1f}° → post_target={flip['post_target']:.1f}°")
        print(f"Slew E lancé à T+{tr['t']}s (offset pré-flip {flip['start'] - tr['t']:.0f}s)")
        print(f"              from={tr['from']:.1f}° → to={tr['target']:.1f}° "
              f"(delta={abs(normalize_angle_180(tr['target'] - tr['from'])):.1f}°)")


if __name__ == "__main__":
    main()
