#!/usr/bin/env python3
"""Génère docs/protocole_mesures_abaque_terrain.pdf (remesure ciblée de l'abaque coupole).

Les valeurs « abaque » et « modèle » de chaque position sont calculées à la génération
(AbaqueManager + calage de core/tracking/dome_geometry.py).

Usage :
    uv run --with fpdf2 python scripts/diagnostics/gen_protocole_abaque_pdf.py
"""

import logging
import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(PROJECT_ROOT))
sys.path.insert(0, "/home/jp/.claude/skills/pdf-report/scripts")

from pdf_report import Report  # noqa: E402

from core.config.config import SITE_LATITUDE  # noqa: E402
from core.tracking.abaque_manager import AbaqueManager  # noqa: E402
from core.tracking.dome_geometry import (  # noqa: E402
    PierSide,
    dome_azimuth,
    expected_pier_side,
    fit_dome_geometry,
)

OUT = PROJECT_ROOT / "docs" / "protocole_mesures_abaque_terrain.pdf"
RAYON_COUPOLE_M = 1.20
HAUTEURS_HAUTES = [65.0, 70.0, 72.5, 75.0, 77.5, 80.0]

ZONE_A = [(alt, az) for az in (60.0, 75.0, 90.0, 105.0) for alt in HAUTEURS_HAUTES]
ZONE_B = [(alt, az) for az in (255.0, 270.0, 285.0) for alt in HAUTEURS_HAUTES]
PRIORITE_2 = [
    (65.0, 45.0),
    (72.5, 120.0),
    (75.0, 225.0),
    (80.0, 225.0),
    (65.0, 300.0),
    (60.0, 315.0),
    (65.0, 315.0),
]
PRIORITE_3 = [(60.0, 0.0), (30.0, 180.0)]

COLONNES = [
    "N°",
    "Alt",
    "Az",
    "Abaque",
    "Modèle",
    "Alt lue",
    "Az lu",
    "Contrep.",
    "Az coupole",
    "Heure",
]
LARGEURS = [9, 12, 12, 15, 15, 20, 20, 21, 25, 21]


def _contrepoids(az: float) -> str:
    # Tube côté Ouest du pied (objet à l'Est) ⇔ contrepoids à l'Est.
    return "E" if expected_pier_side(az).value == "west" else "O"


def main() -> None:
    logging.disable(logging.INFO)
    abaque = AbaqueManager(str(PROJECT_ROOT / "data" / "Loi_coupole.xlsx"))
    if not abaque.load_abaque():
        raise SystemExit("Abaque illisible")
    points = [
        (alt, az, dome)
        for alt, d in abaque.data_by_altitude.items()
        for az, dome in zip(d["az_astre"], d["az_coupole"])
    ]
    geom = fit_dome_geometry(points, SITE_LATITUDE, dome_radius_m=RAYON_COUPOLE_M).geometry
    mesures = {(alt, az): dome for alt, az, dome in points}

    numero = 0

    def lignes(positions):
        nonlocal numero
        rows = []
        for alt, az in positions:
            numero += 1
            dome_abaque = mesures.get((alt, az))
            abaque_txt = f"{dome_abaque:.0f}°" if dome_abaque is not None else "—"
            if az % 180 == 0:
                # Au méridien : valeur du modèle pour chaque côté (contrepoids E / O)
                e = dome_azimuth(geom, alt, az, PierSide.WEST, SITE_LATITUDE)
                o = dome_azimuth(geom, alt, az, PierSide.EAST, SITE_LATITUDE)
                modele_txt, attendu = f"E {e:.0f}° / O {o:.0f}°", "(?)"
            else:
                modele_txt = (
                    f"{dome_azimuth(geom, alt, az, expected_pier_side(az), SITE_LATITUDE):.0f}°"
                )
                attendu = f"({_contrepoids(az)})"
            rows.append(
                [
                    str(numero),
                    f"{alt:g}°",
                    f"{az:g}°",
                    abaque_txt,
                    modele_txt,
                    "",
                    "",
                    attendu,
                    "",
                    "",
                ]
            )
        return rows

    pdf = Report(
        title="Remesure ciblée de l'abaque coupole",
        subtitle="Protocole terrain — DriftApp 6.21.8 — octobre 2026",
        header_text="DriftApp — protocole abaque",
    )
    pdf.title_page(
        summary=(
            "Le 16/10 sur MWP 1, la coupole s'apprêtait à basculer au passage au méridien, "
            "alors que l'ASIAIR n'a retourné la monture qu'environ 11 minutes plus tard, "
            "à la fin de la pose de 600 s en cours. L'abaque ne peut pas suivre ce cas : elle "
            "ne connaît la coupole que tube du « bon » côté. Un modèle géométrique de la "
            "monture, calé sur l'abaque, le peut. Il concorde avec elle à 2-3° près presque "
            "partout, sauf dans deux zones proches du zénith où l'abaque se contredit "
            "d'un point à l'autre. Ces mesures diront qui a raison. "
            f"{len(ZONE_A) + len(ZONE_B) + len(PRIORITE_2) + len(PRIORITE_3)} positions, "
            "environ 3 minutes chacune ; elles peuvent se faire sur plusieurs soirées."
        ),
        extra_lines=[
            "Observatoire Ubik",
            "À retourner à JP : la grille remplie (une photo suffit)",
        ],
    )

    pdf.add_page()
    pdf.h1("1. La donnée qui compte : le côté des contrepoids")
    pdf.body(
        "L'abaque actuelle ne dit pas de quel côté du pied se trouvait le tube lors de chaque mesure. "
        "C'est précisément ce qui manque pour comprendre le retournement. Pour chaque mesure, "
        "notez donc où sont les contrepoids : à l'Est (E) ou à l'Ouest (O)."
    )
    pdf.bullet("Objet à l'Est du méridien (azimut 0° à 180°) : contrepoids normalement à l'Est.")
    pdf.bullet(
        "Objet à l'Ouest du méridien (azimut 180° à 360°) : contrepoids normalement à l'Ouest."
    )
    pdf.info_box(
        "La colonne « Contrep. » (contrepoids) indique entre parenthèses le côté attendu. "
        "Notez ce que vous voyez réellement : si c'est l'autre côté, c'est une information précieuse."
    )

    pdf.h1("2. Préparation")
    pdf.bold_bullet(
        "Suivi DriftApp arrêté :",
        "ne pas cliquer « Démarrer le suivi ». La coupole se "
        "déplace à la main avec les boutons ±1° / ±10° du Contrôle manuel.",
    )
    pdf.bold_bullet(
        "Coupole calibrée :",
        "badge vert ✓ dans l'en-tête. Sinon, « Calibrer maintenant » avant de commencer.",
    )
    pdf.bold_bullet(
        "Monture :", "pilotée par l'ASIAIR comme d'habitude ; le suivi sidéral peut rester actif."
    )
    pdf.bold_bullet("Cimier ouvert", "pour voir l'ouverture depuis le tube ou la caméra.")

    pdf.h1("3. Mesure d'un point")
    pdf.body("1. Amener le tube près de la position (Alt / Az) indiquée dans la grille.")
    pdf.success_box(
        "Inutile d'être exact : à ±2° de la cible, c'est parfait. Le calcul accepte n'importe "
        "quelle position, il suffit de noter les valeurs réellement affichées par l'ASIAIR."
    )
    pdf.body(
        "2. Centrer l'ouverture du cimier sur le tube avec les boutons ±1° / ±10°, avec le même critère "
        "que pour les mesures d'origine de l'abaque."
    )
    pdf.body(
        "3. Noter : l'Alt et l'Az lus dans l'ASIAIR au moment du centrage, le côté des contrepoids, "
        "l'azimut de la coupole affiché par DriftApp (cartouche ENC sous la boussole) et l'heure."
    )
    pdf.info_box(
        "Les colonnes « Abaque » et « Modèle » donnent les deux réponses possibles, pour trouver "
        "l'ouverture plus vite. Dans les zones à vérifier, elles peuvent différer de plusieurs dizaines "
        "de degrés : fiez-vous à ce que vous voyez, pas aux chiffres. Si le bon centrage ne tombe sur "
        "aucune des deux, notez-le simplement."
    )

    pdf.h1("4. Ordre conseillé")
    pdf.bullet("Priorité 1 d'abord (zones A puis B) : c'est là que l'abaque se contredit.")
    pdf.bullet("Dans une zone, garder le même azimut et monter en hauteur : moins de déplacements.")
    pdf.bullet("Les priorités 2 et 3 peuvent attendre une autre soirée.")

    pdf.add_page()
    pdf.h1("5. Grille à remplir")
    pdf.h2("Priorité 1 — Zone A : Est / Nord-Est, haut dans le ciel")
    pdf.table(COLONNES, lignes(ZONE_A), col_widths=LARGEURS)
    pdf.add_page()
    pdf.h2("Priorité 1 — Zone B : Ouest / Nord-Ouest, haut dans le ciel")
    pdf.table(COLONNES, lignes(ZONE_B), col_widths=LARGEURS)
    pdf.h2("Priorité 2 — Points isolés à revérifier")
    pdf.table(COLONNES, lignes(PRIORITE_2), col_widths=LARGEURS)
    pdf.add_page()
    pdf.h2("Priorité 3 — Points pile au méridien")
    pdf.body(
        "Au méridien, la monture peut être d'un côté comme de l'autre. Mesurer tel qu'elle se "
        "présente ; le côté des contrepoids est ici la donnée essentielle. La colonne "
        "« Modèle » donne la valeur attendue pour chaque côté (contrepoids E / O)."
    )
    pdf.table(COLONNES, lignes(PRIORITE_3), col_widths=[9, 12, 12, 15, 30, 18, 18, 17, 22, 17])

    pdf.h1("6. Bonus : avant le retournement")
    pdf.body(
        "Tube pas encore retourné après le méridien : c'est exactement la situation du 16/10. Lors d'une prochaine session où l'objet passe au "
        "méridien haut dans le ciel, entre le passage au méridien et le retournement par l'ASIAIR :"
    )
    pdf.bullet("arrêter le suivi DriftApp juste avant le passage (comme le 16/10) ;")
    pdf.bullet("toutes les 2 à 3 minutes, recentrer l'ouverture à la main et noter une ligne ;")
    pdf.bullet("noter aussi l'heure à laquelle l'ASIAIR retourne la monture.")
    pdf.warning_box(
        "Ces quelques lignes valent plus que tout le reste : elles vérifient directement la position "
        "que le modèle propose pendant l'attente du retournement. Les contrepoids sont alors encore à l'Est."
    )
    rows = [[str(i), "", "", "", "", "", ""] for i in range(1, 7)]
    pdf.table(
        ["N°", "Objet", "Alt lue", "Az lu", "Contre-poids", "Az coupole", "Heure"],
        rows,
        col_widths=[10, 40, 20, 20, 25, 30, 25],
    )
    pdf.body("Heure du retournement de la monture par l'ASIAIR : ............")

    pdf.h1("7. Retour")
    pdf.body(
        "Envoyer la grille remplie (photo ou recopie), avec la date de chaque soirée. "
        "JP recalcule le modèle avec ces mesures et décide des corrections de l'abaque."
    )

    pdf.output(str(OUT))
    print(f"PDF écrit : {OUT}")


if __name__ == "__main__":
    main()
