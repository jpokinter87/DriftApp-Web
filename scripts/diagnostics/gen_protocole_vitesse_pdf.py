#!/usr/bin/env python3
"""Génère docs/protocole_vitesse_v6.16_terrain.pdf depuis le protocole terrain."""

import os
import sys

sys.path.insert(0, "/home/jp/.claude/skills/pdf-report/scripts")
from pdf_report import Report  # noqa: E402

FONT_DIR = "/usr/share/fonts/truetype/dejavu/"
OUT = "/home/jp/PythonProject/DriftApp-Web/docs/protocole_vitesse_v6.16_terrain.pdf"


class Protocole(Report):
    """Report + bloc de commandes en chasse fixe (copier-coller SSH)."""

    def __init__(self, **kw):
        super().__init__(**kw)
        self.add_font("Mono", "", os.path.join(FONT_DIR, "DejaVuSansMono.ttf"))

    def code_block(self, lines):
        """Bloc gris, police mono, pour les commandes à recopier."""
        self.ln(1)
        self.set_font("Mono", "", 7.5)
        self.set_fill_color(242, 242, 245)
        self.set_draw_color(205, 205, 212)
        self.set_text_color(20, 20, 20)
        for line in lines:
            # Un cadre par ligne : les sauts de page restent propres.
            self.cell(0, 4.4, "  " + line, border="LR", new_x="LMARGIN", new_y="NEXT", fill=True)
        self.cell(0, 0.6, "", border="LRT", new_x="LMARGIN", new_y="NEXT", fill=True)
        self.set_text_color(0, 0, 0)
        self.set_font("DejaVu", "", 9)
        self.ln(2)

    def step(self, numero, titre):
        self.h2(f"Étape {numero} — {titre}")


pdf = Protocole(
    title="Vitesse de la coupole",
    subtitle="Explication et protocole terrain — v6.16.0",
    header_text="Protocole vitesse coupole — v6.16.0",
)

pdf.title_page(
    summary=(
        "La coupole tourne à ~43°/min alors que le boîtier de commande du constructeur "
        "atteint 90°/min avec le même moteur. La cause vient d'être identifiée : ce "
        "n'était pas une limite du driver, mais un coût fixe de 121 µs par pas dans "
        "l'ancien programme, qui rendait la vitesse du constructeur arithmétiquement "
        "inatteignable. Ce document explique le problème, décrit ce qui a été corrigé, "
        "et détaille le protocole à dérouler sur place."
    ),
    extra_lines=[
        "Observatoire Ubik — DriftApp Web",
        "Destinataire : Serge, sur site",
        "Durée : environ 1 h, dont ~20 min coupole en mouvement",
        "20 septembre 2026",
    ],
)

# ─────────────────────────────────────────────────────────────────────────────
pdf.add_page()
pdf.h1("1. Ce qui se passait, en deux mots")

pdf.body(
    "Depuis le début, la coupole tourne à environ 43°/min alors que le boîtier de "
    "commande du constructeur atteint 90°/min avec le même moteur. Tous les essais "
    "pour combler cet écart ont échoué, et on avait fini par conclure que le driver "
    "était en cause."
)
pdf.body("C'était faux. Voici l'image qui explique tout.")
pdf.body(
    "Pour faire tourner la coupole, le logiciel envoie des impulsions au moteur : une "
    "impulsion = un pas. Plus les impulsions sont rapprochées, plus la coupole va vite. "
    "On règle donc un délai entre deux impulsions, en microsecondes."
)
pdf.body(
    "Le problème : l'ancien programme mettait 121 microsecondes à préparer chaque "
    "impulsion, avant même de commencer à attendre le délai demandé. C'est comme un "
    "facteur à qui on dit « distribue une lettre toutes les 2 minutes » alors qu'il met "
    "déjà 2 minutes à marcher jusqu'à la boîte aux lettres : quoi qu'on lui demande, il "
    "ne fera jamais mieux qu'une lettre toutes les 4 minutes."
)
pdf.info_box(
    "Résultat concret : quand on demandait 120 µs, le moteur recevait en réalité "
    "247 µs. D'où les 45°/min mesurés, au lieu des 90 attendus. On mesurait le "
    "facteur, pas le moteur."
)
pdf.body(
    "Et pour atteindre les 90°/min du constructeur, il faudrait 124 µs entre deux "
    "impulsions. L'ancien programme en consommait 121 rien que pour lui. Il restait "
    "3 µs : c'était arithmétiquement impossible, aucun réglage n'y serait arrivé."
)

pdf.h2("Les mesures de décembre 2025, relues")

pdf.body(
    "Les dix mesures faites sur place le 12/12/2025 le montrent sans ambiguïté. "
    "Converties en microsecondes réellement écoulées entre deux pas, elles font "
    "apparaître un surcoût constant, quelle que soit la vitesse demandée :"
)

pdf.table(
    ["Délai demandé", "Vitesse mesurée", "Délai réel", "Surcoût"],
    [
        ["2000 µs", "5,3 °/min", "2087 µs", "+87 µs"],
        ["1100 µs", "9,0 °/min", "1242 µs", "+142 µs"],
        ["550 µs", "16,9 °/min", "658 µs", "+108 µs"],
        ["300 µs", "25,4 °/min", "439 µs", "+139 µs"],
        ["150 µs", "38,7 °/min", "288 µs", "+138 µs"],
        ["**120 µs**", "**45,0 °/min**", "**247 µs**", "**+127 µs**"],
        ["110 µs", "« strengstens verboten ! »", "—", "—"],
    ],
    col_widths=[35, 55, 40, 40],
)

pdf.body(
    "Le surcoût ne bouge pas : 121 µs en moyenne, sur une plage de délais de 17×. "
    "C'est la signature d'un coût fixe, pas d'une limite mécanique."
)
pdf.body(
    "Quant à la ligne « strengstens verboten », ce n'est pas le moteur qui décrochait : "
    "c'est le moment où le délai demandé passait sous le coût du programme. À partir de "
    "là, plus rien ne régulait les impulsions, elles partaient n'importe comment, et le "
    "moteur se mettait à vibrer. Un problème de régularité, pas de vitesse."
)
pdf.body(
    "Enfin, l'écart « 42 vs 48 °/min » qui intriguait n'a jamais existé : c'était la "
    "même vitesse, calculée avec deux règles de conversion différentes."
)
pdf.warning_box(
    "Conclusion : le moteur n'a jamais été poussé au-delà de 247 µs par pas, dans "
    "aucune des deux époques du programme. La limite du driver n'a jamais été "
    "mesurée — elle a été supposée."
)

# ─────────────────────────────────────────────────────────────────────────────
pdf.add_page()
pdf.h1("2. Ce qui a été corrigé")

pdf.table(
    ["Quoi", "En clair"],
    [
        [
            "La vitesse sort du code",
            "Elle se règle depuis la page Configuration > Avancé, sans SSH. "
            "Valeur par défaut : 260 µs, soit exactement la vitesse actuelle.",
        ],
        [
            "Le firmware du Pico",
            "La phase d'accélération calculait une formule compliquée à chaque pas : "
            "c'était le dernier endroit où le « facteur » existait encore. Les valeurs "
            "sont désormais préparées à l'avance.",
        ],
        [
            "Un instrument de mesure",
            "Un script compare, à chaque palier de vitesse, ce qu'on demande et ce que "
            "la coupole fait réellement (lu sur l'encodeur). C'est précisément ce qui "
            "n'avait jamais été fait.",
        ],
    ],
    col_widths=[45, 125],
)

pdf.success_box(
    "Tant que le Pico n'est pas flashé et que la vitesse reste à 260 µs, tout se "
    "comporte exactement comme avant. Cela a été vérifié : les commandes envoyées au "
    "Pico sont identiques à l'octet près."
)

pdf.h1("3. Ce qu'on ne sait pas encore")

pdf.body(
    "La vraie limite du moteur est inconnue. C'est tout l'objet de ce protocole."
)
pdf.body(
    "Un seul point physique peut encore bloquer : la tension d'alimentation du driver. "
    "À 124 µs par pas, le moteur tourne à environ 600 tr/min, et à cette vitesse le "
    "couple dépend directement de la tension. Le boîtier UPAN, qui atteint 96°/min, "
    "alimente son driver en 36 V. Si le nôtre est en 24 V, c'est là que ça butera — et "
    "ça se corrigera par l'alimentation, pas par le logiciel."
)
pdf.body("D'où l'étape 2 ci-dessous.")

# ─────────────────────────────────────────────────────────────────────────────
pdf.add_page()
pdf.h1("4. Protocole")

pdf.warning_box(
    "RÈGLES À RESPECTER\n"
    "1. Ne pas modifier la vitesse (delay_us) avant d'avoir flashé le Pico (étape 6). "
    "L'ancien firmware ne sait pas accélérer jusqu'à une vitesse élevée : le moteur "
    "décrocherait.\n"
    "2. Ne pas lancer le script de mesure avant le flash, pour la même raison.\n"
    "3. Pendant les mesures, rester près de la coupole et écouter : un décrochage "
    "s'entend (bruit de calage, comme lors de l'incident de septembre).\n"
    "4. Sur le Pico : une seule source d'alimentation USB à la fois.\n"
    "5. La mise à jour redémarre les services, donc la coupole bouge (calibration au "
    "démarrage). Choisir un moment tranquille."
)

pdf.h2("Bloc A — Relevés, sans rien lancer ni démonter")

pdf.step(1, "Relever le modèle exact du driver")
pdf.body(
    "La documentation du projet hésite entre deux modèles. Il faut trancher."
)
pdf.bold_bullet("À faire :", "lire l'étiquette collée sur le boîtier du driver moteur (celui qui reçoit les fils du moteur).")
pdf.bold_bullet("À rapporter :", "le modèle exact (DM556T ou DM860T, ou autre) et, si elle est lisible, la plage de tension indiquée.")

pdf.step(2, "Mesurer la tension d'alimentation du driver")
pdf.body("Multimètre en tension continue (DC), calibre 200 V si le réglage est manuel.")
pdf.bold_bullet("À faire :", "mesurer aux bornes d'alimentation puissance du driver, repérées VDC et GND (ou V+ / V−).")
pdf.bold_bullet("Attention :", "ne pas confondre avec les bornes PUL+ / DIR+, qui sont les signaux logiques et n'ont rien à voir.")
pdf.bold_bullet("Attendu :", "une valeur entre 24 et 48 V.")
pdf.bold_bullet("À rapporter :", "la valeur lue.")

pdf.step(3, "Noter les micro-interrupteurs (DIP)")
pdf.bold_bullet("À faire :", "photographier ou noter la position des petits interrupteurs sur le côté du driver (ON/OFF, généralement 8).")
pdf.bold_bullet("À rapporter :", "la photo, ou la suite ON/OFF.")
pdf.body(
    "Cela permet de confirmer le réglage de courant et le microstepping (on attend "
    "800 impulsions par tour moteur)."
)

pdf.info_box(
    "Les étapes 1 à 3 se font sans rien démonter ni rien lancer. Si la tension relevée "
    "est basse (24 V), prévenir avant d'aller plus loin : l'objectif de vitesse devra "
    "peut-être être revu à la baisse."
)

# ─────────────────────────────────────────────────────────────────────────────
pdf.add_page()
pdf.h2("Bloc B — Mise à jour, flash et mesures")

pdf.step(4, "Installer la mise à jour 6.16.0")
pdf.bold_bullet("À faire :", "sur le tableau de bord, cliquer sur « Mettre à jour » et laisser faire.")
pdf.bold_bullet("Attendu :", "la version affichée en bas de page passe à 6.16.0. La coupole effectue sa calibration habituelle au redémarrage.")
pdf.body(
    "Si une bannière de configuration apparaît avec la mention « migrated » : c'est "
    "normal, elle signale simplement qu'un nouveau réglage a été ajouté. Aucune valeur "
    "du site n'a été touchée."
)

pdf.step(5, "Vérifier que rien n'a changé")
pdf.bold_bullet("À faire :", "utiliser la coupole normalement — un GOTO, quelques JOG, éventuellement un début de suivi.")
pdf.bold_bullet("Attendu :", "strictement le même comportement qu'avant, même vitesse, même son.")
pdf.body(
    "C'est la vérification la plus importante du protocole : si quelque chose diffère "
    "ici, s'arrêter et prévenir."
)

pdf.step(6, "Sauvegarder puis flasher le Pico")
pdf.body("En SSH sur le Pi :")
pdf.code_block([
    "ssh slenk@<pi-du-site>",
    "cd ~/DriftApp",
    "",
    "# 1. SAUVEGARDE de l'ancien firmware — a ne pas sauter",
    "mkdir -p ~/firmware_backup",
    "mpremote cp :main.py            ~/firmware_backup/main.py",
    "mpremote cp :step_generator.py  ~/firmware_backup/step_generator.py",
    "mpremote cp :ramp.py            ~/firmware_backup/ramp.py",
    "ls -l ~/firmware_backup      # doit lister les 3 fichiers",
    "",
    "# 2. Flash du nouveau firmware",
    "cd ~/DriftApp/firmware",
    "mpremote cp main.py            :main.py",
    "mpremote cp step_generator.py  :step_generator.py",
    "mpremote cp ramp.py            :ramp.py",
])
pdf.bold_bullet("Attendu :", "aucune erreur. Le Pico redémarre tout seul.")
pdf.bold_bullet("Retour arrière :", "à tout moment, recopier les trois fichiers de ~/firmware_backup vers le Pico (mêmes commandes dans l'autre sens) et débrancher/rebrancher le Pico.")

pdf.step(7, "Re-vérifier que rien n'a changé")
pdf.bold_bullet("À faire :", "redémarrer les services (page Configuration > « Redémarrer les services »), puis refaire un GOTO et quelques JOG.")
pdf.bold_bullet("Attendu :", "là encore, comportement identique. Le flash est censé être neutre tant que la vitesse reste à 260 µs.")
pdf.body("Si ce n'est pas le cas, revenir à l'ancien firmware (étape 6) et prévenir.")

# ─────────────────────────────────────────────────────────────────────────────
pdf.add_page()
pdf.step(8, "Campagne de mesure")
pdf.body(
    "C'est l'étape où la coupole va tourner de plus en plus vite. Rester à proximité."
)
pdf.code_block([
    "cd ~/DriftApp",
    "",
    "# D'abord voir le plan, sans rien faire bouger",
    "python3 scripts/diagnostics/calibration_vitesse_encodeur.py --dry-run",
    "",
    "# Puis la mesure reelle (demande de taper « go » avant de demarrer)",
    "python3 scripts/diagnostics/calibration_vitesse_encodeur.py",
])
pdf.body(
    "Le script teste dix vitesses, de la plus lente à la plus rapide. À chaque palier "
    "il fait tourner la coupole de 10° et compare la vitesse obtenue à la vitesse "
    "demandée. Il affiche un tableau de ce type :"
)
pdf.code_block([
    "  délai       mesuré         visé   rendement",
    "  260 µs    42.8°/min    42.8°/min       100 %",
    "  235 µs    47.2°/min    47.3°/min       100 %",
    "  ...",
])
pdf.bold_bullet("Arrêt automatique :", "le script s'arrête seul au premier palier où la coupole ne suit plus, et annonce une valeur recommandée.")
pdf.bold_bullet("Arrêt manuel :", "Ctrl-C interrompt tout immédiatement si quelque chose semble anormal.")
pdf.bold_bullet("À rapporter :", "le tableau complet affiché en fin de script, et le fichier logs/calibration_vitesse_*.json.")

pdf.step(9, "Régler la vitesse définitive")
pdf.bold_bullet("À faire :", "page Configuration > Avancé > motor_driver > delay_us, saisir la valeur recommandée par le script (jamais une valeur plus basse), enregistrer, puis « Redémarrer les services ».")
pdf.bold_bullet("Attendu :", "la coupole est plus rapide, sans bruit anormal.")
pdf.body(
    "À valider sur une vraie session avant de considérer l'affaire close : un suivi "
    "complet, avec un passage au méridien si possible."
)

pdf.h1("5. Résumé de ce qu'il faut rapporter")

pdf.table(
    ["Étape", "Information attendue"],
    [
        ["1", "Modèle exact du driver"],
        ["2", "Tension d'alimentation mesurée"],
        ["3", "Position des DIP, ou photo"],
        ["5 et 7", "Confirmation que rien n'a changé (après mise à jour, puis après flash)"],
        ["8", "Tableau de mesures complet + fichier logs/calibration_vitesse_*.json"],
    ],
    col_widths=[25, 145],
)

pdf.info_box(
    "En cas de doute à n'importe quelle étape : s'arrêter et demander. Rien dans ce "
    "protocole n'est urgent, et l'ancien fonctionnement reste disponible à tout moment "
    "(retour arrière du firmware + delay_us remis à 260)."
)

pdf.output(OUT)
print("PDF écrit :", OUT)
