"""Génère docs/description_technique_coupole.pdf (description technique de la coupole)."""

import sys

sys.path.insert(0, "/home/jp/.claude/skills/pdf-report/scripts")
from pdf_report import Report  # noqa: E402

OUT = "/home/jp/PythonProject/DriftApp-Web/docs/description_technique_coupole.pdf"

pdf = Report(
    title="Coupole de l'Observatoire Ubik",
    subtitle="Description technique — 24/10/2026",
    header_text="Observatoire Ubik — Description technique de la coupole",
)
pdf.title_page(
    summary=(
        "Synthèse des données disponibles sur la coupole : site, mécanique, entraînement en "
        "azimut, mesure de position, loi de coupole, cimier, informatique de contrôle. "
        "Sources : dépôt DriftApp Web, data/config.json, abaque Loi_coupole.xlsx, notes et "
        "mesures de terrain. Les points incertains ou contradictoires sont signalés."
    ),
    extra_lines=[
        "Observatoire Ubik — 44,15° N, 5,23° E, 800 m",
        "Exploitation sur site : Serge",
        "Logiciel : DriftApp Web 6.26.2",
    ],
)

pdf.add_page()
pdf.warning_box(
    "Le data/config.json de la machine de développement est le gabarit du dépôt, pas celui du Pi. "
    "Les valeurs réelles du terrain, quand elles sont connues par les logs ou les retours de Serge, "
    "sont indiquées à part."
)

# 1. Site
pdf.h1("1. Site")
pdf.table(
    ["Élément", "Valeur"],
    [
        ["Nom", "Observatoire Ubik"],
        ["Coordonnées", "44,15° N, 5,23° E, altitude 800 m"],
        ["Fuseau", "Europe/Paris (changement d'heure géré par zoneinfo)"],
        ["Exploitation", "Serge, sur place. Développement à distance (800 km), sans accès au Pi."],
    ],
    col_widths=[40, 130],
)

# 2. Mécanique
pdf.h1("2. Structure mécanique")
pdf.bold_bullet(
    "Coupole :",
    "tournante en azimut, rayon retenu 1,20 m (une ancienne doc donne 200 cm de diamètre, contradictoire).",
)
pdf.bold_bullet("Couronne :", "2 303 mm de diamètre.")
pdf.bold_bullet("Cimier :", "trappe motorisée séparément ; ouverture utile d'environ 40° de large.")
pdf.bold_bullet("Parking :", "azimut 45°, qui est aussi la position du microswitch de recalage.")
pdf.bold_bullet(
    "Monture :",
    "équatoriale allemande pilotée par une ASIAIR (ZWO), 192.168.1.70, port 4400. Modèle de "
    "monture non documenté. Retournement à méridien + « Flip Timing after Meridian », à la fin "
    "de la pose en cours (poses typiques de 600 s).",
)

# 3. Entraînement
pdf.h1("3. Entraînement en azimut")
pdf.h2("3.1 Chaîne de puissance")
pdf.body(
    "Pi 5 → USB CDC 115 200 bauds → Pi Pico RP2040 (PIO, résolution 8 ns) → GP2/GP3 → "
    "driver DM860T (36 V) → moteur NEMA 200 pas/tour. Le DM556T du boîtier constructeur UPAN "
    "est branché en parallèle sur le même moteur."
)
pdf.table(
    ["Élément", "Caractéristiques"],
    [
        ["Moteur", "Pas-à-pas NEMA, 200 pas/tour, courant 2,5 A"],
        ["Driver DriftApp", "DM860T sous 36 V, micropas 4 (800 pas/tour moteur)"],
        ["Driver constructeur", "DM556T de l'UPAN (STM32F412 + RP2040-Zero, en C), 96°/min"],
        ["Brochage Pico", "GP2 → PUL+, GP3 → DIR+, GND → PUL−/DIR− ; port /dev/ttyACM0"],
        [
            "Ancien mode GPIO",
            "BCM 17 = DIR, 18 = STEP ; encore dans le code, non utilisé (type rp2040)",
        ],
    ],
    col_widths=[40, 130],
)
pdf.warning_box(
    "Deux drivers sur le même moteur : vérifier l'étiquette avant de câbler PUL+/DIR+. "
    "C'est le DM860T qui est piloté par DriftApp."
)

pdf.h2("3.2 Réduction et résolution")
pdf.table(
    ["Grandeur", "Valeur"],
    [
        ["Réduction nominale", "2230:1 (≈ 50 × 44,6, établie par essais)"],
        ["Facteur de correction des pas", "1,08849, soit une réduction effective ≈ 2 427:1"],
        ["Pas par tour de coupole", "1 941 866"],
        ["Résolution d'un pas", "≈ 0,000185° (≈ 0,67″)"],
    ],
    col_widths=[60, 110],
)

pdf.h2("3.3 Vitesses")
pdf.table(
    ["Usage", "Délai", "Vitesse", "Tour complet"],
    [
        ["Suivi et petits mouvements (< 3°)", "260 µs/pas", "≈ 43°/min", "≈ 8,4 min"],
        [
            "Grands mouvements (≥ 3°), fast_delay_us = 120 sur le Pi",
            "120 µs/pas",
            "≈ 90°/min",
            "≈ 4 min",
        ],
        ["Limite mesurée le 27/09", "tenue à 104 µs, décroche à 100 µs", "", ""],
        ["Boîtier constructeur (référence)", "", "90°/min", ""],
    ],
    col_widths=[70, 40, 30, 30],
)
pdf.bold_bullet(
    "Rampe :",
    "accélération constante sur ≈ 2 s (ramp_time_s), pour tous les mouvements. STOP doux en "
    "vitesse rapide, immédiat à 260 µs et au-delà. Version 6.19.1, validée sur le terrain.",
)
pdf.warning_box(
    "Défaut ouvert : les grands déplacements rapides dépassent toujours la cible de 2 à 3,4 %, "
    "dans le sens du mouvement. Rapport degrés-pas / degrés-encodeur ≈ 1,022. On ne sait pas "
    "encore lequel des deux facteurs est faux : mesure sur tour complet livrée en 6.25.1, rapport "
    "de Serge attendu."
)

# 4. Mesure de position
pdf.h1("4. Mesure de position")
pdf.h2("4.1 Encodeur absolu EMS22A")
pdf.table(
    ["Grandeur", "Valeur"],
    [
        ["Type", "Magnétique, 10 bits (1 024 points/tour), SPI bus 0 device 0, 1 MHz"],
        ["Lecture", "50 Hz par le démon ems22d_calibrated.py → /dev/shm/ems22_position.json"],
        ["Montage", "Roue de 50 mm roulant sur la couronne de 2 303 mm"],
        ["Facteur calibré", "0,010851 : un tour de roue = 3,91° de coupole"],
        ["Résolution", "≈ 94 400 points par tour de coupole, soit ≈ 0,0038° par point"],
    ],
    col_widths=[40, 130],
)
pdf.warning_box(
    "Incohérence dans les données : le rapport géométrique 50/2303 donnerait un facteur de 0,0217. "
    "Le facteur calibré en vaut à peu près la moitié. Soit une cote mécanique est fausse, soit il "
    "existe un renvoi non documenté. À rapprocher du défaut de 2,2 % (§ 3.3)."
)
pdf.h2("4.2 Microswitch de recalage")
pdf.bullet("SS-5GL placé à 45°, GPIO 27 avec pull-up, lu par le démon de l'encodeur.")
pdf.bullet("Au front descendant, le comptage est recalé à 45°.")
pdf.bullet("Secours : « Forcer à 45° » dans l'UI, la coupole étant placée à vue (caméra).")
pdf.bullet(
    "Calibration au démarrage de motor_service : balayage −7° puis +14°, dépassement de 0,5° après le switch."
)
pdf.bullet(
    "Switch abîmé remplacé en octobre. Depuis la 6.23.4, le démon survit sans GPIO et choisit le "
    "contrôleur GPIO par son label (noyau 6.12.109)."
)

# 5. Abaque
pdf.h1("5. Loi de coupole (abaque)")
pdf.bullet(
    "Fichier data/Loi_coupole.xlsx, feuille « cartographie » : 276 points mesurés sur le terrain (azimut de l'astre → azimut de la coupole)."
)
pdf.bullet(
    "11 hauteurs : 30, 45, 53, 60, 65, 70, 72,5, 75, 77,5, 80 et 85° ; maille de 15° en azimut."
)
pdf.bullet(
    "L'abaque intègre implicitement le décentrement du tube. Un modèle géométrique calé dessus "
    "donnait un déport ≈ 44 cm et un décalage vertical ≈ −27 cm (retiré en 6.21.11, récupérable dans git)."
)
pdf.h3("Particularités")
pdf.bullet(
    "Au-dessus de 53°, le saut 345° → 0° correspond à un vrai retournement de monture au passage supérieur nord : ne pas l'interpoler en boucle."
)
pdf.bullet("Artefact d'environ 17° vers 40° de hauteur au passage inférieur.")
pdf.bullet(
    "Maille trop grossière près du zénith : az 60–105° et az 255–285°, entre 65 et 80° de hauteur."
)

# 6. Cimier
pdf.h1("6. Cimier (architecture V3 tout-Shelly)")
pdf.table(
    ["Shelly", "IP", "Rôle"],
    [
        ["1 Gen 1 « 24V »", ".83", "Alimentation du module, coupée hors cycle"],
        ["Plus Uni", ".84", "Fins de course : id 1 = HAUT, id 0 = BAS (NC, invert=true)"],
        [
            "1 Gen 1 « MOT »",
            ".85",
            "Marche/arrêt moteur ; le moteur tourne quand le relais est sur off",
        ],
        ["1 Gen 1 « UPDN »", ".86", "Sens via DPDT externe (UP = on)"],
        ["« 12V »", ".82", "Alimentation permanente (batterie), non pilotée par DriftApp"],
    ],
    col_widths=[40, 15, 115],
)
pdf.bold_bullet(
    "Motorisation :",
    "contrôleur autonome (générateur STEP à potentiomètre) → DM556T. Les microswitches coupent le contrôleur directement, au niveau matériel. Pico W supprimé.",
)
pdf.bold_bullet(
    "Cycle :",
    "24V ON → sens → MOT ON → interrogation des fins de course → MOT OFF → 24V OFF. Délai maximal 90 s, 10 s d'attente entre deux cycles.",
)
pdf.h3("Automatisation (modes manual, semi, full)")
pdf.bullet("Ouverture quand le Soleil est à −12°.")
pdf.bullet("Fermeture visée quand le Soleil remonte à −6°, avec 10 min d'avance.")
pdf.bullet("Parking à 45° avant la fermeture ; nouvelle tentative de fermeture toutes les 5 min.")
pdf.warning_box("Automatisation prête dans le code mais jamais validée sur le terrain.")
pdf.h3("Capteur de pluie")
pdf.bullet("Actuel : MH-RD (sortie D0) sur un Shelly Plus Uni dédié (.87, id 0).")
pdf.bullet(
    "Résistance chauffante sur un Shelly .78 : keepalive 4 min, arrêt automatique du Shelly à 300 s."
)
pdf.bullet(
    "Une lecture mouillée suffit pour passer en « pluie » ; N lectures sèches pour en sortir."
)
pdf.bullet(
    "Pas de réouverture après une fermeture pour pluie. Shelly muet : refus d'ouvrir, jamais de fermeture."
)
pdf.info_box(
    "En cours : le MH-RD est peu fiable et s'oxyde. Remplacement par un Kemo M152K (capacitif, "
    "chauffage intégré), commandé le 24/10."
)

# 7. Informatique
pdf.h1("7. Informatique de contrôle")
pdf.body(
    "Raspberry Pi 5, noyau 6.12.109 rpt-rpi-2712, écran tactile en mode kiosque à l'observatoire."
)
pdf.table(
    ["Service systemd", "Rôle"],
    [
        ["ems22d", "Encodeur et microswitch"],
        ["motor_service", "Boucle à 20 Hz, watchdog 30 s"],
        ["cimier_service", "Cimier"],
        ["driftapp_web", "Django, port 8000"],
        ["asiair_monitor", "Journal permanent de la monture"],
    ],
    col_widths=[50, 120],
)
pdf.bold_bullet(
    "Communication :",
    "fichiers JSON dans /dev/shm verrouillés par fcntl (motor_command, motor_status, ems22_position, cimier_*).",
)
pdf.h3("Suivi")
pdf.bullet("Correction toutes les 30 s si l'écart dépasse 0,3°.")
pdf.bullet(
    "Sous 3° : boucle fermée sur l'encodeur, tolérance 0,5°. Au-dessus : rotation directe puis correction finale."
)
pdf.bullet("Abandon d'un mouvement si l'erreur dépasse 20°.")
pdf.h3("Méridien")
pdf.bullet("Déplacement anticipé de la coupole avant le transit (stratégie E).")
pdf.bullet(
    "Bascule calée sur le côté du pied lu sur l'ASIAIR : attente de 30 min au plus si la monture est en retard, suivi immédiat si elle est en avance (6.26.0, ce cas n'a pas encore été vu sur le terrain)."
)
pdf.h3("Mise à jour")
pdf.bold_bullet(
    "OTA :", "depuis l'UI, sur comparaison de la version de pyproject.toml (actuelle : 6.26.2)."
)

# 8. Lacunes
pdf.h1("8. Données manquantes ou contradictoires")
pdf.bullet("Modèle de la monture et du tube.")
pdf.bullet("Dimensions réelles de la coupole (hauteur, diamètre intérieur exact).")
pdf.bullet("Facteur 2 inexpliqué sur le facteur de l'encodeur (§ 4.1).")
pdf.bullet("Origine du rapport 1,022 entre pas et encodeur (§ 3.3).")

pdf.output(OUT)
print(OUT)
