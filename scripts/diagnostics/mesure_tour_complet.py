#!/usr/bin/env python3
"""
╔══════════════════════════════════════════════════════════════════════════════╗
║        MESURE DES ÉCHELLES SUR UN TOUR COMPLET — MICROSWITCH 45°              ║
║                                                                              ║
║  Les grands déplacements vont 2 à 4 % trop loin (logs du 16 au 22/10).       ║
║  Les logs comparent toujours les pas à l'encodeur : ils donnent le rapport   ║
║  des deux échelles (≈ 1,022), jamais laquelle est fausse — le facteur de     ║
║  pas (`steps_correction_factor`) ou celui de l'encodeur                      ║
║  (`CALIBRATION_FACTOR` d'ems22d_calibrated.py).                               ║
║                                                                              ║
║  La seule référence physique est le microswitch 45°. Entre deux passages     ║
║  dans le même sens, la coupole a fait exactement 360°. Pour chaque sens et   ║
║  chaque vitesse, le script :                                                 ║
║    1. place la coupole 6° avant le microswitch (GOTO) ;                      ║
║    2. commande un JOG de 385° : elle franchit le microswitch deux fois ;     ║
║    3. lit l'encodeur juste avant chaque recalage à 45°.                      ║
║  Échelle encodeur = ce qu'il a compté entre les deux passages / 360.         ║
║  Échelle des pas  = degrés réels parcourus / 385 commandés.                  ║
║                                                                              ║
║  SÉCURITÉ                                                                    ║
║  — Ne modifie NI config.json NI le démon encodeur.                           ║
║  — 4 tours complets (~30 min), la coupole finit au parking 45°.              ║
║  — Ctrl-C envoie un STOP.                                                    ║
║                                                                              ║
║  USAGE                                                                       ║
║    python3 scripts/diagnostics/mesure_tour_complet.py --dry-run              ║
║    python3 scripts/diagnostics/mesure_tour_complet.py                        ║
╚══════════════════════════════════════════════════════════════════════════════╝
"""

import argparse
import ast
import json
import signal
import sys
import time
from datetime import datetime
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parent.parent.parent
sys.path.insert(0, str(PROJECT_ROOT))

from calibration_vitesse_encodeur import (  # noqa: E402
    ENCODER_FILE,
    FRAICHEUR_MAX_S,
    _ecart_angulaire,
    envoyer_commande,
    envoyer_stop,
    geometrie,
    lire_json,
    lire_statut_moteur,
    preflight,
    print_error,
    print_info,
    print_ok,
    print_warning,
)

from core.utils.log_paths import logs_subdir  # noqa: E402

ANGLE_SWITCH_DEG = 45.0
RECUL_DEPART_DEG = 6.0  # départ 6° avant le microswitch, dans le sens du tour
# 385° : franchit le microswitch à ~6° puis à ~366°, même si les pas sont
# faux de 4 % dans un sens ou dans l'autre (369,6° au pire).
TOUR_COMMANDE_DEG = 385.0
ECHANTILLONNAGE_S = 0.01  # l'encodeur publie à 50 Hz : aucun recalage manqué
SEUIL_ECART = 0.005  # au-delà de 0,5 %, une échelle est jugée fausse


# =============================================================================
# CALCUL (fonctions pures)
# =============================================================================


def _distance(a: float, b: float, sens: int) -> float:
    """Distance parcourue de a à b en tournant dans le sens donné, dans [0, 360)."""
    return ((b - a) * sens) % 360.0


def echelles_tour(sens, depart, avant_recalages, arrivee, commande) -> dict:
    """
    Échelles de l'encodeur et des pas, d'après un tour franchissant deux fois le microswitch.

    Args:
        sens: +1 (azimut croissant) ou -1.
        depart: angle encodeur au départ (encodeur recalé peu avant, sur un arc court).
        avant_recalages: angles encodeur lus juste avant chacun des deux recalages.
        arrivee: angle encodeur à l'arrêt (recalé au second passage).
        commande: degrés commandés au moteur (positif).

    Returns:
        dict: encodeur_par_degre (degrés encodeur par degré réel),
        degres_par_degre_pas (degrés réels par degré commandé),
        encodeur_par_degre_pas (leur produit, ce que mesurent les GOTO),
        parcours_reel (degrés réels parcourus).
    """
    if len(avant_recalages) != 2:
        raise ValueError(f"2 passages sur le microswitch attendus, {len(avant_recalages)} vus")

    # Entre les deux passages : 360° réels. L'encodeur, recalé à 45° au premier,
    # a compté 360° plus ou moins quelques degrés (déplié autour de 360).
    compte = 360.0 + _ecart_angulaire(0.0, (avant_recalages[1] - ANGLE_SWITCH_DEG) * sens)
    r = compte / 360.0

    # Les deux bouts courts (départ → 1er passage, 2e passage → arrêt) sont
    # mesurés à l'encodeur, ramenés en degrés réels par son échelle.
    debut = _distance(depart, avant_recalages[0], sens) / r
    fin = _distance(ANGLE_SWITCH_DEG, arrivee, sens) / r
    parcours = debut + 360.0 + fin
    s = parcours / commande

    return {
        "encodeur_par_degre": r,
        "degres_par_degre_pas": s,
        "encodeur_par_degre_pas": r * s,
        "parcours_reel": parcours,
    }


def facteurs_proposes(steps_correction_factor, calibration_factor, echelles) -> dict:
    """Facteurs qui rendraient chaque échelle exacte."""
    return {
        "steps_correction_factor": steps_correction_factor / echelles["degres_par_degre_pas"],
        "calibration_factor": calibration_factor / echelles["encodeur_par_degre"],
    }


def calibration_factor_encodeur() -> float:
    """Valeur de CALIBRATION_FACTOR lue dans ems22d_calibrated.py (sans l'importer : lgpio)."""
    source = (PROJECT_ROOT / "ems22d_calibrated.py").read_text()
    for noeud in ast.parse(source).body:
        if isinstance(noeud, ast.Assign) and any(
            isinstance(c, ast.Name) and c.id == "CALIBRATION_FACTOR" for c in noeud.targets
        ):
            return float(eval(compile(ast.Expression(noeud.value), "<facteur>", "eval")))
    raise ValueError("CALIBRATION_FACTOR introuvable dans ems22d_calibrated.py")


# =============================================================================
# ORCHESTRATION IPC
# =============================================================================


def lire_encodeur_complet():
    """(angle, last_calibration_at) de l'encodeur, ou (None, None) si périmé."""
    data = lire_json(ENCODER_FILE)
    if not data or data.get("ts") is None or time.time() - data["ts"] > FRAICHEUR_MAX_S:
        return None, None
    return data.get("angle"), data.get("last_calibration_at")


def attendre_fin_mouvement(timeout_s: float) -> bool:
    """Attend que le Motor Service reparte au repos après une commande."""
    t0 = time.time()
    demarre = False
    while time.time() - t0 < timeout_s:
        statut = lire_statut_moteur()
        if statut not in ("idle", "error"):
            demarre = True
        elif demarre or time.time() - t0 > 3.0:
            return statut == "idle"
        time.sleep(0.1)
    envoyer_stop()
    return False


def goto(angle: float) -> bool:
    if not envoyer_commande({"command": "goto", "angle": angle % 360.0}):
        return False
    return attendre_fin_mouvement(300.0)


def mesurer_tour(sens: int, delay_us: float, spd: float) -> dict:
    """Un tour complet dans le sens donné, à la vitesse donnée."""
    if not goto(ANGLE_SWITCH_DEG - sens * RECUL_DEPART_DEG):
        return {"erreur": "GOTO de départ échoué"}
    time.sleep(1.0)

    depart, derniere_calib = lire_encodeur_complet()
    if depart is None:
        return {"erreur": "encodeur indisponible au départ"}

    commande = TOUR_COMMANDE_DEG
    if not envoyer_commande({"command": "jog", "delta": sens * commande, "speed": delay_us * 1e-6}):
        return {"erreur": "commande refusée"}

    timeout_s = commande * spd * delay_us * 1e-6 + 90.0
    avant_recalages = []
    precedent = depart
    t0 = time.time()
    demarre = False
    while time.time() - t0 < timeout_s:
        angle, calib = lire_encodeur_complet()
        if angle is not None:
            if calib != derniere_calib:
                avant_recalages.append(precedent)
                print_info(f"Microswitch franchi — encodeur lisait {precedent:.2f}° juste avant")
                derniere_calib = calib
            precedent = angle

        statut = lire_statut_moteur()
        if statut == "moving":
            demarre = True
        elif demarre and statut in ("idle", "error"):
            break
        time.sleep(ECHANTILLONNAGE_S)
    else:
        envoyer_stop()
        return {"erreur": f"timeout après {timeout_s:.0f}s"}

    time.sleep(1.0)
    arrivee, _ = lire_encodeur_complet()
    if arrivee is None:
        return {"erreur": "encodeur indisponible à l'arrivée"}

    mesure = {
        "sens": sens,
        "delay_us": delay_us,
        "depart": depart,
        "avant_recalages": avant_recalages,
        "arrivee": arrivee,
        "commande": commande,
    }
    try:
        mesure.update(echelles_tour(sens, depart, avant_recalages, arrivee, commande))
    except ValueError as e:
        mesure["erreur"] = str(e)
    return mesure


# =============================================================================
# PROGRAMME PRINCIPAL
# =============================================================================


def plan_de_mesure(delais_us) -> list:
    """(sens, délai) de chaque tour : les deux sens pour chaque vitesse."""
    return [(sens, us) for us in delais_us for sens in (+1, -1)]


def delais_par_defaut() -> list:
    """260 µs (petits mouvements) et la vitesse rapide de la config, si différente."""
    from core.config.config import FAST_MOTOR_DELAY, SINGLE_SPEED_MOTOR_DELAY

    lent = round(SINGLE_SPEED_MOTOR_DELAY * 1e6)
    rapide = round(FAST_MOTOR_DELAY * 1e6)
    return [lent] if rapide == lent else [lent, rapide]


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Mesure les échelles des pas et de l'encodeur sur un tour complet."
    )
    parser.add_argument(
        "--delais",
        type=int,
        nargs="+",
        metavar="US",
        help="Délais en µs/pas à mesurer (défaut : 260 et fast_delay_us de la config)",
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Affiche le plan de mesure sans faire bouger la coupole",
    )
    args = parser.parse_args()

    signal.signal(signal.SIGINT, lambda *_: (envoyer_stop(), sys.exit(130)))

    from core.config.config_loader import load_config

    facteur_pas = load_config().motor.steps_correction_factor
    facteur_encodeur = calibration_factor_encodeur()
    spd, _ = geometrie()

    print("\n" + "=" * 78)
    print("  MESURE DES ÉCHELLES SUR UN TOUR COMPLET")
    print("=" * 78)
    print_info(f"steps_correction_factor = {facteur_pas}  ({spd:.1f} pas/degré)")
    print_info(f"CALIBRATION_FACTOR encodeur = {facteur_encodeur:.6f}")

    plan = plan_de_mesure(args.delais or delais_par_defaut())
    print("\n── Plan de mesure ──")
    total = 0.0
    for sens, us in plan:
        duree = TOUR_COMMANDE_DEG * spd * us * 1e-6
        total += duree + 60.0
        print(
            f"  tour {'+' if sens > 0 else '−'}{TOUR_COMMANDE_DEG:.0f}° à {us} µs  (~{duree / 60:.0f} min)"
        )
    print_info(f"Durée totale estimée : ~{total / 60:.0f} min")

    if args.dry_run:
        print("\n(dry-run : aucune commande envoyée)\n")
        return 0

    if not preflight():
        print_error("\nPréflight en échec — mesure annulée.\n")
        return 1
    if lire_json(ENCODER_FILE).get("last_calibration_at") is None:
        print_error("Encodeur jamais recalé : lancer « Calibrer maintenant » d'abord.\n")
        return 1

    print_warning("\n⚠️  LA COUPOLE VA FAIRE PLUSIEURS TOURS COMPLETS. Personne dans son rayon.")
    if input("  Taper 'go' pour démarrer : ").strip().lower() != "go":
        print_info("Annulé.\n")
        return 0

    resultats = []
    for sens, us in plan:
        print(f"\n── Tour {'+' if sens > 0 else '−'} à {us} µs ──")
        mesure = mesurer_tour(sens, us, spd)
        resultats.append(mesure)
        if "erreur" in mesure:
            print_error(f"Mesure impossible : {mesure['erreur']}")
            break
        _afficher(mesure)

    print_info("\nRetour au parking 45°…")
    goto(ANGLE_SWITCH_DEG)

    _rapport(resultats, facteur_pas, facteur_encodeur)
    return 0


def _afficher(m: dict):
    print(
        f"  encodeur : {m['encodeur_par_degre'] * 360:.2f}° comptés pour 360° réels"
        f"  ({(m['encodeur_par_degre'] - 1) * 100:+.2f} %)"
    )
    print(
        f"  pas      : {m['parcours_reel']:.2f}° réels pour {m['commande']:.0f}° commandés"
        f"  ({(m['degres_par_degre_pas'] - 1) * 100:+.2f} %)"
    )


def _verdict(r: float, s: float) -> str:
    pas_faux = abs(s - 1) > SEUIL_ECART
    encodeur_faux = abs(r - 1) > SEUIL_ECART
    if pas_faux and encodeur_faux:
        return "les deux échelles sont fausses"
    if pas_faux:
        return "le facteur de pas est faux, l'encodeur est juste"
    if encodeur_faux:
        return "l'encodeur est faux, le facteur de pas est juste"
    return "les deux échelles sont justes à 0,5 % près"


def _rapport(resultats, facteur_pas, facteur_encodeur):
    print("\n" + "=" * 78)
    print("  RÉSULTAT")
    print("=" * 78)

    valides = [m for m in resultats if "erreur" not in m]
    if not valides:
        print_error("Aucune mesure exploitable.\n")
    else:
        print(f"\n  {'tour':>12} {'encodeur':>10} {'pas':>10}")
        for m in valides:
            tour = f"{'+' if m['sens'] > 0 else '−'} {m['delay_us']} µs"
            print(
                f"  {tour:>12} {(m['encodeur_par_degre'] - 1) * 100:>+9.2f}%"
                f" {(m['degres_par_degre_pas'] - 1) * 100:>+9.2f}%"
            )
        r = sum(m["encodeur_par_degre"] for m in valides) / len(valides)
        s = sum(m["degres_par_degre_pas"] for m in valides) / len(valides)
        moyennes = {"encodeur_par_degre": r, "degres_par_degre_pas": s}
        proposes = facteurs_proposes(facteur_pas, facteur_encodeur, moyennes)
        print_ok(f"Verdict : {_verdict(r, s)}")
        print_info(
            f"steps_correction_factor : {facteur_pas} → {proposes['steps_correction_factor']:.5f}"
        )
        print_info(
            f"CALIBRATION_FACTOR      : {facteur_encodeur:.6f} → {proposes['calibration_factor']:.6f}"
        )
        print_info("Rien n'est modifié : envoyer le rapport ci-dessous à JP.")

    horodatage = datetime.now().strftime("%Y%m%d_%H%M%S")
    rapport = logs_subdir("diagnostics") / f"mesure_tour_complet_{horodatage}.json"
    try:
        rapport.write_text(
            json.dumps(
                {
                    "date": datetime.now().isoformat(),
                    "steps_correction_factor": facteur_pas,
                    "calibration_factor": facteur_encodeur,
                    "tours": resultats,
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
