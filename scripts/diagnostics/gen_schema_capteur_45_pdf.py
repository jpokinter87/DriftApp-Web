#!/usr/bin/env python3
"""Génère docs/schema_capteur_45_E3Z-D61.pdf : montage du capteur optique de recalage 45°.

Remplace le microswitch SS-5GL (GPIO27, front 1→0 = 45°) par un capteur E3Z-S10N3 (NPN).
Aucun changement de code : sortie NPN = niveau bas quand la cible est vue.
Sans diode (16/11) : sortie à collecteur ouvert mesurée, noir ↔ bleu 0 V au repos et
0,5 V en détection ; une 1N5819 ajouterait ≈ 0,3 V, à la limite du seuil bas du Pi.
10 kΩ sur la broche 17 (3,3 V), la broche 1 restant à l'encodeur (14/11).
"""

import sys

sys.path.insert(0, "/home/jp/.claude/skills/pdf-report/scripts")
from pdf_report import Report  # noqa: E402

OUT = "/home/jp/PythonProject/DriftApp/docs/schema_capteur_45_E3Z-D61.pdf"

MARRON = (140, 75, 25)
BLEU = (30, 90, 210)
NOIR = (20, 20, 20)
ROUGE = (200, 30, 30)
VERT = (20, 140, 60)
GRIS = (110, 110, 110)


class Schema(Report):
    def body(self, text):
        # multi_cell laisse x en bout de ligne après une puce : repartir de la marge.
        self.set_x(self.l_margin)
        super().body(text)

    def step(self, n, text):
        self.set_font("DejaVu", "B", 9)
        self.set_text_color(30, 30, 30)
        self.set_x(self.l_margin + 6)
        self.cell(7, 5, f"{n}.")
        self.set_font("DejaVu", "", 9)
        self.multi_cell(self.w - self.l_margin - self.r_margin - 13, 5, text)
        self.ln(0.8)

    def wire(self, points, color, width=0.9):
        self.set_draw_color(*color)
        self.set_line_width(width)
        for (x1, y1), (x2, y2) in zip(points, points[1:]):
            self.line(x1, y1, x2, y2)
        self.set_line_width(0.2)
        self.set_draw_color(0, 0, 0)

    def dot(self, x, y, color):
        self.set_fill_color(*color)
        self.ellipse(x - 1.3, y - 1.3, 2.6, 2.6, "F")

    def label(self, x, y, text, size=8, style="", color=(0, 0, 0), align="L", w=60):
        self.set_font("DejaVu", style, size)
        self.set_text_color(*color)
        if align == "R":
            x -= w
        elif align == "C":
            x -= w / 2
        self.set_xy(x, y - size * 0.18)
        self.cell(w, size * 0.36, text, align=align)
        self.set_text_color(0, 0, 0)

    def box(self, x, y, w, h, fill=(245, 245, 248)):
        self.set_fill_color(*fill)
        self.set_draw_color(60, 60, 60)
        self.set_line_width(0.5)
        self.rect(x, y, w, h, "DF")
        self.set_line_width(0.2)

    def terminal(self, x, y):
        self.set_fill_color(255, 255, 255)
        self.set_draw_color(0, 0, 0)
        self.ellipse(x - 1.4, y - 1.4, 2.8, 2.8, "DF")

    def resistor_v(self, x, y1, y2, color):
        """Résistance verticale (rectangle) entre y1 et y2."""
        self.set_draw_color(*color)
        self.set_line_width(0.6)
        self.set_fill_color(255, 255, 255)
        self.rect(x - 2.2, y1, 4.4, y2 - y1, "DF")
        self.set_line_width(0.2)


pdf = Schema(
    title="Capteur optique de recalage 45°",
    subtitle="E3Z-S10N3 à la place du microswitch",
)

# ── Page 1 : schéma (paysage) ─────────────────────────────────────────
pdf.add_page(orientation="L")
pdf.set_font("DejaVu", "B", 14)
pdf.set_xy(15, 14)
pdf.cell(0, 8, "Schéma de câblage — capteur optique 45° (E3Z-S10N3, sortie NPN, sans diode)")
pdf.set_font("DejaVu", "", 9)
pdf.set_xy(15, 22)
pdf.cell(
    0,
    5,
    "Remplace le microswitch : même entrée du Pi (broche 13), aucune modification du logiciel.",
)

# Alimentation 12 V
pdf.box(25, 40, 50, 32)
pdf.label(50, 47, "Alimentation", 9, "B", align="C")
pdf.label(50, 52, "12 V continu", 9, "B", align="C")
pdf.label(50, 57, "(bloc secteur dédié,", 7, color=GRIS, align="C")
pdf.label(50, 61, "100 mA suffisent)", 7, color=GRIS, align="C")
pdf.terminal(25, 66)
pdf.label(28, 66, "0 V", 8, "B", color=BLEU)
pdf.terminal(75, 66)
pdf.label(72, 66, "+12 V", 8, "B", color=ROUGE, align="R")

# Capteur
pdf.box(25, 92, 50, 44, fill=(255, 248, 230))
pdf.label(50, 98, "E3Z-S10N3", 9, "B", align="C")
pdf.label(50, 103, "capteur à réflexion, NPN", 7, color=GRIS, align="C")
pdf.label(50, 110, "Sortie active cible vue", 7.5, "B", align="C")
pdf.label(50, 114.5, "voyant allumé = cible vue", 7, color=GRIS, align="C")
pdf.label(50, 118.5, "potentiomètre = portée", 7, color=GRIS, align="C")
pdf.terminal(75, 102)
pdf.terminal(75, 124)
pdf.terminal(50, 136)

# Raspberry Pi
pdf.box(225, 40, 52, 120, fill=(235, 245, 235))
pdf.label(251, 46, "Raspberry Pi", 9, "B", align="C")
pdf.label(251, 51, "connecteur 40 broches", 7, color=GRIS, align="C")
for y, broche, nom, col in (
    (60, "broche 17", "3,3 V", ROUGE),
    (82, "broche 13", "GPIO27", VERT),
    (152, "broche 14", "GND (masse)", BLEU),
):
    pdf.terminal(225, y)
    pdf.label(229, y - 2.2, broche, 8, "B")
    pdf.label(229, y + 2.2, nom, 8, color=col)

# Fil marron : capteur + → +12 V
pdf.wire([(75, 102), (90, 102), (90, 66), (75, 66)], MARRON)
pdf.label(92, 99, "marron", 8, "B", color=MARRON)

# Fils bleus : 0 V commun (alimentation, capteur, Pi)
pdf.wire([(25, 66), (15, 66), (15, 152), (225, 152)], BLEU)
pdf.wire([(50, 136), (50, 152)], BLEU)
pdf.dot(50, 152, BLEU)
pdf.label(52, 143, "bleu", 8, "B", color=BLEU)
pdf.label(100, 148, "0 V commun : alimentation + capteur + Pi (indispensable)", 8, "B", BLEU, w=110)

# Fil noir : sortie → directement sur GPIO27 (pas de diode, 16/11)
pdf.wire([(75, 124), (190, 124), (190, 82)], NOIR)
pdf.label(92, 121, "noir (sortie) : directement sur la broche 13, sans diode", 8, "B", NOIR, w=100)

# Résistance 10 kΩ : 3,3 V → GPIO27
pdf.wire([(225, 60), (190, 60), (190, 64)], ROUGE)
pdf.resistor_v(190, 64, 76, NOIR)
pdf.wire([(190, 76), (190, 82)], VERT)
pdf.label(170, 68, "10 kΩ", 8, "B", align="R", w=40)
pdf.label(170, 72.5, "vers 3,3 V, jamais 12 V", 7, color=ROUGE, align="R", w=40)

# Nœud GPIO27
pdf.wire([(190, 82), (225, 82)], VERT)
pdf.dot(190, 82, VERT)

# Cadre pointillé : à monter près du Pi
pdf.set_draw_color(*GRIS)
pdf.set_dash_pattern(dash=1.5, gap=1.2)
pdf.rect(150, 55, 58, 32)
pdf.set_dash_pattern()
pdf.label(152, 84, "à souder près du Pi", 7, "I", GRIS)

# Encadrés sous le schéma
pdf.set_xy(15, 165)
pdf.set_font("DejaVu", "", 8)
pdf.multi_cell(
    267,
    4.2,
    "Fonctionnement : sans cible, la résistance tire GPIO27 à 3,3 V (lu 1). Quand le capteur voit "
    "la cible, son fil noir est relié au 0 V et GPIO27 descend vers 0,5 V (lu 0). Ce passage de 1 à 0 "
    "recale la coupole à 45°, exactement comme le microswitch. Pas de diode : le fil noir ne fait que "
    "relier GPIO27 au 0 V, il ne porte jamais de tension par lui-même (mesuré le 16/11 : 0 V au repos, "
    "0,5 V en détection). Une diode ajouterait 0,3 V et mettrait le niveau bas à la limite du Pi.",
)
pdf.ln(1)
pdf.set_x(15)
pdf.set_font("DejaVu", "B", 8)
pdf.set_text_color(*ROUGE)
pdf.multi_cell(
    267,
    4.2,
    "Ne jamais brancher le fil marron ni le +12 V sur le Pi. Ne pas alimenter le capteur avec le 36 V "
    "du driver moteur (le capteur accepte 12 à 24 V) ni avec le Shelly 24 V du cimier (coupé hors cycle).",
)
pdf.set_text_color(0, 0, 0)

# ── Page 2 : repérage des broches et essai sur table ─────────────────
pdf.add_page()
pdf.h1("1. Repérer les broches du Pi")
pdf.body(
    "Le connecteur 40 broches longe un bord de la carte. La broche 1 (prise par l'encodeur) a une "
    "pastille carrée ; elle est "
    "au bout du connecteur côté carte SD, à l’opposé des prises USB. Les broches impaires "
    "sont sur la rangée côté intérieur de la carte, les paires sur la rangée du bord."
)
y0 = pdf.get_y() + 4
x_imp, x_pair = 85, 125
noms = {
    1: ("3,3 V", ROUGE),
    2: ("5 V", GRIS),
    3: ("GPIO2", GRIS),
    4: ("5 V", GRIS),
    5: ("GPIO3", GRIS),
    6: ("GND", GRIS),
    7: ("GPIO4", GRIS),
    8: ("GPIO14", GRIS),
    9: ("GND", GRIS),
    10: ("GPIO15", GRIS),
    11: ("GPIO17", GRIS),
    12: ("GPIO18", GRIS),
    13: ("GPIO27", VERT),
    14: ("GND", BLEU),
    15: ("GPIO22", GRIS),
    16: ("GPIO23", GRIS),
    17: ("3,3 V", ROUGE),
    18: ("GPIO24", GRIS),
}
pdf.set_draw_color(60, 60, 60)
pdf.set_fill_color(40, 40, 40)
pdf.rect(x_imp - 3, y0 - 4, x_pair - x_imp + 6, 9 * 7 + 1, "D")
for n in range(1, 19):
    x = x_imp if n % 2 else x_pair
    y = y0 + ((n - 1) // 2) * 7
    nom, col = noms[n]
    utile = n in (13, 14, 17)
    pdf.set_fill_color(*(col if utile else (200, 200, 200)))
    if n == 1:
        pdf.rect(x - 1.8, y - 1.8, 3.6, 3.6, "F")
    else:
        pdf.ellipse(x - 1.8, y - 1.8, 3.6, 3.6, "F")
    if n % 2:
        pdf.label(
            x - 5, y, f"{nom}  ({n})", 8, "B" if utile else "", col if utile else GRIS, "R", 40
        )
    else:
        pdf.label(x + 5, y, f"({n})  {nom}", 8, "B" if utile else "", col if utile else GRIS)
pdf.set_y(y0 + 9 * 7 + 4)
pdf.body(
    "Pour le capteur, seules les broches 13, 14 et 17 servent ; la broche 1 reste à l'encodeur. "
    "Le microswitch actuel est déjà sur la broche 13 (GPIO27) et sur une masse : noter sur quelles "
    "broches il est branché avant de débrancher."
)

pdf.h1("2. Essai sur table, sans le Pi")
pdf.body(
    "Pour vérifier le capteur avant de le relier au Pi : marron sur +12 V, bleu sur 0 V, et une "
    "résistance de 10 kΩ entre le fil noir et le +12 V. Au voltmètre entre le noir et le bleu :"
)
pdf.bullet("sans cible : environ 12 V ;")
pdf.bullet("cible devant le capteur : moins de 0,8 V.")
pdf.warning_box(
    "Retirer ensuite cette résistance reliée au +12 V. Elle ne doit jamais rester en place quand le "
    "fil noir va sur le Pi : sur le Pi, la 10 kΩ va au 3,3 V (broche 17), jamais au 12 V."
)

# ── Page 3 : montage, réglage, contrôle ──────────────────────────────
pdf.add_page()
pdf.h1("3. Matériel")
pdf.bullet("Capteur E3Z-S10N3 (sortie NPN, vérifiée le 16/11 ; une version PNP ne convient pas).")
pdf.bullet("Bloc d'alimentation 12 V continu, 100 mA ou plus, branché en permanence.")
pdf.bullet("Résistance 10 kΩ (marron-noir-orange). Pas de diode.")
pdf.bullet(
    "Câble à 3 conducteurs entre le capteur et le boîtier du Pi si le câble de 2 m du capteur ne suffit pas "
    "(l'ancien câble du microswitch n'en a probablement que 2)."
)
pdf.bullet(
    "Une cible : petite plaque claire et mate fixée sur la partie tournante de la coupole, à 45°."
)

pdf.h1("4. Montage")
pdf.step(1, "Arrêter proprement le Pi (menu Arrêter), puis couper son alimentation.")
pdf.step(2, "Débrancher les deux fils du microswitch sur le Pi.")
pdf.step(3, "Souder la résistance 10 kΩ près du Pi, entre la broche 13 et la broche 17 (3,3 V).")
pdf.step(4, "Brancher le capteur : marron sur +12 V, bleu sur 0 V, noir sur la broche 13.")
pdf.step(5, "Relier le 0 V de l'alimentation 12 V à la masse du Pi, broche 14 (fil bleu commun).")
pdf.step(6, "Rebrancher l'alimentation 12 V, puis le Pi.")
pdf.warning_box(
    "Avant de rallumer le Pi, deux contrôles. Pi débranché, à l'ohmmètre : aucune continuité entre le "
    "fil marron (+12 V) et la broche 13. Puis alimentation 12 V branchée, Pi toujours éteint, au "
    "voltmètre entre la broche 13 et la masse : jamais plus de 3,3 V. Sinon, erreur de câblage : ne "
    "pas allumer."
)

pdf.h1("5. Pose et réglage du capteur")
pdf.bullet(
    "Fixer le capteur sur la partie fixe, face à la trajectoire de la cible, à 2-5 cm de celle-ci. "
    "Rien d'autre ne doit passer devant (fil, échelle, main)."
)
pdf.bullet(
    "Cible étroite (1 à 2 cm de large) : plus elle est étroite, plus le recalage est précis."
)
pdf.bullet(
    "Portée (potentiomètre) : partir du minimum, monter jusqu'à ce que le voyant s'allume "
    "franchement sur la cible, puis vérifier qu'il reste éteint sans la cible. S'il clignote "
    "sur la cible, rapprocher le capteur ou augmenter un peu la portée."
)

pdf.h1("6. Contrôle après la pose")
pdf.body("Au multimètre, entre la broche 13 (GPIO27) et la masse :")
pdf.bullet("cible devant le capteur : moins de 0,8 V (environ 0,5 V attendu) ;")
pdf.bullet("cible absente : environ 3,3 V.")
pdf.body(
    "Ou sur le Pi : ouvrir un terminal par-dessus le dashboard (Ctrl+Alt+T), taper « pinctrl get 27 ». "
    "On doit lire « lo » avec la cible devant, « hi » sans. Retour au dashboard par Alt+Tab."
)
pdf.success_box(
    "À renvoyer à JP : les deux tensions lues, une photo du montage, puis le zip des logs d'une soirée "
    "où la coupole a franchi 45° plusieurs fois dans les deux sens."
)

pdf.output(OUT)
print("PDF écrit :", OUT)
