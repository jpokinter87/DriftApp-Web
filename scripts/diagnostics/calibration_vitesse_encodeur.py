#!/usr/bin/env python3
"""
╔══════════════════════════════════════════════════════════════════════════════╗
║           CALIBRATION VITESSE MAXIMALE — MESURE À L'ENCODEUR                  ║
║                                                                              ║
║  Descend la vitesse par paliers et mesure, à CHAQUE palier, la vitesse       ║
║  RÉELLE de la coupole lue sur l'encodeur EMS22A. Le décrochage moteur se     ║
║  voit alors directement : la coupole cesse de suivre la vitesse demandée.    ║
║                                                                              ║
║  POURQUOI CE SCRIPT EXISTE                                                   ║
║  Les deux campagnes précédentes (12/2025 GPIO, 03/2026 RP2040) ont mesuré    ║
║  un plafond LOGICIEL en croyant mesurer une limite du driver :               ║
║    — 12/2025 : la boucle Python coûtait 121 µs/pas. Demander 120 µs livrait  ║
║      247 µs réels. Conclusion « 45°/min = limite stable » : c'était le       ║
║      plafond du Raspberry Pi, pas celui du moteur.                           ║
║    — 03/2026 : repli sur 260 µs à cause du coût par pas de MicroPython,      ║
║      puis étiqueté « limite DM860T » alors que le PIO autonome venait de     ║
║      supprimer cette contrainte.                                             ║
║  Aucune de ces campagnes n'a jamais comparé la vitesse demandée à la         ║
║  vitesse obtenue. C'est exactement ce que fait ce script.                    ║
║                                                                              ║
║  SÉCURITÉ                                                                    ║
║  — Ne modifie NI config.json NI aucun service : la vitesse est passée dans   ║
║    la commande IPC (champ `speed`), palier par palier.                       ║
║  — Alterne le sens à chaque palier : la coupole reste près de son point de   ║
║    départ.                                                                   ║
║  — S'arrête au premier décrochage, et Ctrl-C envoie un STOP.                 ║
║                                                                              ║
║  USAGE                                                                       ║
║    python3 scripts/diagnostics/calibration_vitesse_encodeur.py --dry-run     ║
║    python3 scripts/diagnostics/calibration_vitesse_encodeur.py               ║
║    python3 scripts/diagnostics/calibration_vitesse_encodeur.py --angle 15    ║
╚══════════════════════════════════════════════════════════════════════════════╝
"""

import argparse
import json
import math
import signal
import sys
import time
from datetime import datetime
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parent.parent.parent
sys.path.insert(0, str(PROJECT_ROOT))

COMMAND_FILE = Path("/dev/shm/motor_command.json")
STATUS_FILE = Path("/dev/shm/motor_status.json")
ENCODER_FILE = Path("/dev/shm/ems22_position.json")

# Paliers de délai en µs/pas. ~10 % d'écart : assez fin pour situer le
# décrochage, assez large pour ne pas y passer la nuit.
#   260 = valeur historique     124 ≈ 90°/min (boîtier constructeur)
#   116 ≈ 96°/min (UPAN mesuré) — dernier palier, au-delà rien ne le justifie
PALIERS_US = [260, 235, 210, 190, 170, 155, 140, 130, 124, 116]

ANGLE_PAR_PALIER_DEG = 10.0
ECHANTILLONNAGE_S = 0.05  # l'encodeur publie à 50 Hz
FRAICHEUR_MAX_S = 1.0
PAUSE_ENTRE_PALIERS_S = 2.0

# Un palier est considéré décroché si la coupole n'a pas parcouru l'angle
# demandé (perte de pas) ou si la vitesse n'a pas progressé comme attendu.
TOLERANCE_ANGLE = 0.90  # 90 % de l'angle commandé
TOLERANCE_GAIN = 0.70  # 70 % du gain de vitesse attendu


def print_ok(msg):
    print(f"  ✅ {msg}")


def print_error(msg):
    print(f"  ❌ {msg}")


def print_warning(msg):
    print(f"  ⚠️  {msg}")


def print_info(msg):
    print(f"  ℹ️  {msg}")


# =============================================================================
# LECTURE IPC
# =============================================================================


def lire_json(path: Path):
    """Lit un fichier IPC JSON, None si absent ou illisible."""
    try:
        return json.loads(path.read_text())
    except (FileNotFoundError, json.JSONDecodeError, OSError):
        return None


def lire_encodeur():
    """Retourne (angle, ts) de l'encodeur, ou (None, None) si périmé."""
    data = lire_json(ENCODER_FILE)
    if not data:
        return None, None
    ts = data.get("ts")
    if ts is None or time.time() - ts > FRAICHEUR_MAX_S:
        return None, None
    return data.get("angle"), ts


def lire_statut_moteur() -> str:
    data = lire_json(STATUS_FILE)
    return (data or {}).get("status", "unknown")


def envoyer_commande(command: dict) -> bool:
    """Écrit une commande dans le slot IPC du Motor Service."""
    command["id"] = f"vitesse_{int(time.time() * 1000)}"
    try:
        COMMAND_FILE.write_text(json.dumps(command))
        return True
    except OSError as e:
        print_error(f"Erreur envoi commande: {e}")
        return False


def envoyer_stop():
    envoyer_commande({"command": "stop"})


# =============================================================================
# GÉOMÉTRIE
# =============================================================================


def geometrie() -> tuple:
    """(pas par degré de coupole, pas par tour moteur), d'après la config du site."""
    from core.config.config_loader import load_config

    m = load_config().motor
    pas_par_tour_moteur = m.steps_per_revolution * m.microsteps
    spd = pas_par_tour_moteur * m.gear_ratio * m.steps_correction_factor / 360.0
    return spd, pas_par_tour_moteur


def vitesse_theorique(delay_us: float, spd: float) -> float:
    """Vitesse en °/min attendue pour un délai donné, si aucun pas n'est perdu."""
    return 60.0 / (delay_us * 1e-6 * spd)


# =============================================================================
# MESURE D'UN PALIER
# =============================================================================


def mesurer_palier(delay_us: float, angle_deg: float, spd: float) -> dict:
    """
    Exécute un JOG à la vitesse demandée et mesure la vitesse réelle.

    La vitesse de croisière est estimée sur la partie centrale du parcours,
    pour exclure les rampes d'accélération et de décélération.

    Returns:
        dict: mesure du palier (voir clés ci-dessous), 'erreur' si échec.
    """
    depart, _ = lire_encodeur()
    if depart is None:
        return {"erreur": "encodeur indisponible avant le mouvement"}

    if not envoyer_commande({"command": "jog", "delta": angle_deg, "speed": delay_us * 1e-6}):
        return {"erreur": "commande refusée"}

    # Durée attendue + marge : la rampe ajoute ~1 s, le reste est du confort.
    attendu_s = abs(angle_deg) * spd * delay_us * 1e-6
    timeout_s = attendu_s + 20.0

    echantillons = []
    t0 = time.time()
    demarre = False

    while time.time() - t0 < timeout_s:
        angle, ts = lire_encodeur()
        if angle is not None:
            echantillons.append((ts, angle))

        statut = lire_statut_moteur()
        if statut == "moving":
            demarre = True
        elif demarre and statut in ("idle", "error"):
            break

        time.sleep(ECHANTILLONNAGE_S)
    else:
        envoyer_stop()
        return {"erreur": f"timeout après {timeout_s:.0f}s"}

    if len(echantillons) < 10:
        return {"erreur": "trop peu d'échantillons encodeur"}

    arrivee = echantillons[-1][1]
    parcouru = abs(_ecart_angulaire(depart, arrivee))

    croisiere = _vitesse_croisiere(echantillons)
    if croisiere is None:
        return {"erreur": "impossible d'isoler la croisière"}

    theorique = vitesse_theorique(delay_us, spd)
    return {
        "delay_us": delay_us,
        "angle_commande": abs(angle_deg),
        "angle_parcouru": parcouru,
        "vitesse_mesuree": croisiere,
        "vitesse_theorique": theorique,
        "rendement": croisiere / theorique if theorique else 0.0,
        "echantillons": len(echantillons),
    }


def _ecart_angulaire(a: float, b: float) -> float:
    """Écart signé le plus court entre deux azimuts (degrés)."""
    d = (b - a + 180.0) % 360.0 - 180.0
    return d


def _vitesse_croisiere(echantillons) -> float:
    """
    Vitesse en °/min sur la partie centrale du parcours.

    On écarte les 25 % de début et de fin : ce sont les rampes, dont la
    vitesse moyenne n'a rien à voir avec la vitesse de croisière visée.
    """
    n = len(echantillons)
    debut, fin = n // 4, (3 * n) // 4
    if fin - debut < 3:
        return None

    t_debut, a_debut = echantillons[debut]
    t_fin, a_fin = echantillons[fin]
    duree = t_fin - t_debut
    if duree <= 0:
        return None

    return abs(_ecart_angulaire(a_debut, a_fin)) / duree * 60.0


# =============================================================================
# PRÉFLIGHT
# =============================================================================


def preflight() -> bool:
    """Vérifie que la mesure peut se dérouler sans surprise."""
    print("\n── Vérifications préalables ──")
    ok = True

    statut = lire_statut_moteur()
    if statut == "unknown":
        print_error("Motor Service muet — vérifier qu'il tourne")
        ok = False
    elif statut != "idle":
        print_error(f"Motor Service occupé (status={statut}) — attendre l'inactivité")
        ok = False
    else:
        print_ok("Motor Service inactif")

    status = lire_json(STATUS_FILE) or {}
    if status.get("tracking_object"):
        print_error(f"Suivi en cours ({status['tracking_object']}) — l'arrêter d'abord")
        ok = False
    else:
        print_ok("Aucun suivi en cours")

    angle, _ = lire_encodeur()
    if angle is None:
        print_error("Encodeur EMS22A indisponible ou périmé — mesure impossible")
        ok = False
    else:
        print_ok(f"Encodeur à {angle:.2f}°")

    return ok


# =============================================================================
# PROGRAMME PRINCIPAL
# =============================================================================


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Mesure la vitesse réelle de la coupole palier par palier."
    )
    parser.add_argument(
        "--angle",
        type=float,
        default=ANGLE_PAR_PALIER_DEG,
        help=f"Angle parcouru à chaque palier (défaut {ANGLE_PAR_PALIER_DEG}°)",
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Affiche le plan de mesure sans faire bouger la coupole",
    )
    args = parser.parse_args()

    signal.signal(signal.SIGINT, lambda *_: (envoyer_stop(), sys.exit(130)))

    spd, pas_tour_moteur = geometrie()
    print("\n" + "=" * 78)
    print("  CALIBRATION VITESSE MAXIMALE — MESURE À L'ENCODEUR")
    print("=" * 78)
    print_info(f"Géométrie : {spd:.1f} pas/degré de coupole")
    print_info(f"Angle par palier : {args.angle:.1f}°  (sens alterné)")

    print("\n── Plan de mesure ──")
    print(f"  {'délai':>7} {'vitesse visée':>15} {'moteur':>11}")
    for us in PALIERS_US:
        v = vitesse_theorique(us, spd)
        rpm = v / 60.0 * spd / pas_tour_moteur * 60.0
        print(f"  {us:>5} µs {v:>12.1f}°/min {rpm:>8.0f} tr/min")

    if args.dry_run:
        print("\n(dry-run : aucune commande envoyée)\n")
        return 0

    if not preflight():
        print_error("\nPréflight en échec — mesure annulée.\n")
        return 1

    print_warning("\n⚠️  LA COUPOLE VA BOUGER. Personne dans son rayon de rotation.")
    if input("  Taper 'go' pour démarrer : ").strip().lower() != "go":
        print_info("Annulé.\n")
        return 0

    resultats = []
    precedent = None
    decroche_a = None

    for index, delay_us in enumerate(PALIERS_US):
        sens = 1.0 if index % 2 == 0 else -1.0
        print(f"\n── Palier {delay_us} µs ──")

        mesure = mesurer_palier(delay_us, sens * args.angle, spd)
        if "erreur" in mesure:
            print_error(f"Mesure impossible : {mesure['erreur']}")
            break

        resultats.append(mesure)
        _afficher_mesure(mesure)

        raison = _diagnostiquer(mesure, precedent)
        if raison:
            print_error(f"DÉCROCHAGE : {raison}")
            decroche_a = delay_us
            break

        print_ok("Palier tenu")
        precedent = mesure
        time.sleep(PAUSE_ENTRE_PALIERS_S)

    _rapport(resultats, decroche_a, spd)
    return 0


def _afficher_mesure(m: dict):
    print(
        f"  parcouru {m['angle_parcouru']:.2f}° / {m['angle_commande']:.2f}° commandés"
        f"  ({m['echantillons']} échantillons)"
    )
    print(
        f"  vitesse  {m['vitesse_mesuree']:.1f}°/min mesurés"
        f" / {m['vitesse_theorique']:.1f}°/min visés"
        f"  → rendement {m['rendement'] * 100:.0f} %"
    )


def _diagnostiquer(mesure: dict, precedent: dict):
    """Retourne la raison du décrochage, ou None si le palier est tenu."""
    if mesure["angle_parcouru"] < TOLERANCE_ANGLE * mesure["angle_commande"]:
        return (
            f"la coupole n'a parcouru que {mesure['angle_parcouru']:.2f}° "
            f"sur {mesure['angle_commande']:.2f}° — pas perdus"
        )

    if precedent is None:
        return None

    gain_attendu = precedent["delay_us"] / mesure["delay_us"]
    gain_reel = (
        mesure["vitesse_mesuree"] / precedent["vitesse_mesuree"]
        if precedent["vitesse_mesuree"]
        else 0.0
    )
    if gain_reel < 1.0 + TOLERANCE_GAIN * (gain_attendu - 1.0):
        return (
            f"la vitesse n'a gagné que {(gain_reel - 1) * 100:.0f} % "
            f"au lieu de {(gain_attendu - 1) * 100:.0f} % — saturation"
        )

    return None


def _rapport(resultats, decroche_a, spd):
    print("\n" + "=" * 78)
    print("  RÉSULTAT")
    print("=" * 78)

    if not resultats:
        print_error("Aucune mesure exploitable.\n")
        return

    print(f"\n  {'délai':>7} {'mesuré':>12} {'visé':>12} {'rendement':>10}")
    for m in resultats:
        print(
            f"  {m['delay_us']:>5} µs {m['vitesse_mesuree']:>9.1f}°/min"
            f" {m['vitesse_theorique']:>9.1f}°/min {m['rendement'] * 100:>8.0f} %"
        )

    tenus = [m for m in resultats if m["rendement"] >= TOLERANCE_ANGLE]
    if not tenus:
        print_error("\nAucun palier tenu — vérifier l'installation avant d'insister.\n")
        return

    meilleur = min(tenus, key=lambda m: m["delay_us"])
    marge = math.ceil(meilleur["delay_us"] * 1.15)

    print(
        f"\n  Palier le plus rapide tenu : {meilleur['delay_us']} µs "
        f"({meilleur['vitesse_mesuree']:.1f}°/min mesurés)"
    )
    if decroche_a:
        print(f"  Décrochage constaté à     : {decroche_a} µs")
        print_info(f"Valeur recommandée (marge 15 %) : motor_driver.delay_us = {marge}")
    else:
        print_info("Aucun décrochage jusqu'au dernier palier — la limite n'est pas atteinte.")

    horodatage = datetime.now().strftime("%Y%m%d_%H%M%S")
    rapport = PROJECT_ROOT / "logs" / f"calibration_vitesse_{horodatage}.json"
    try:
        rapport.write_text(
            json.dumps(
                {
                    "date": datetime.now().isoformat(),
                    "pas_par_degre": spd,
                    "paliers": resultats,
                    "decroche_a_us": decroche_a,
                    "recommandation_us": marge if decroche_a else None,
                },
                indent=2,
            )
        )
        print_info(f"Rapport détaillé : {rapport}")
    except OSError as e:
        print_warning(f"Rapport non écrit : {e}")

    print()


if __name__ == "__main__":
    sys.exit(main())
