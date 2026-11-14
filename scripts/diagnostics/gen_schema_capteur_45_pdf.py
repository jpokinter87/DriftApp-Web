#!/usr/bin/env python3
"""Génère docs/schema_capteur_45_E3Z-D61.pdf : montage du capteur optique de recalage 45°.

Remplace le microswitch SS-5GL (GPIO27, front 1→0 = 45°) par un Omron E3Z-D61 (NPN).
Aucun changement de code : sortie NPN en mode L-ON = niveau bas quand la cible est vue.
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

    def diode_down(self, x, y_anode, y_cathode):
        """Diode verticale : anode en haut, cathode (barre) en bas."""
        self.set_fill_color(20, 20, 20)
        self.polygon([(x - 3.5, y_anode), (x + 3.5, y_anode), (x, y_cathode)], style="F")
        self.set_draw_color(20, 20, 20)
        self.set_line_width(0.9)
        self.line(x - 3.5, y_cathode, x + 3.5, y_cathode)
        self.set_line_width(0.2)


pdf = Schema(
    title="Capteur optique de recalage 45°",
    subtitle="Omron E3Z-D61 à la place du microswitch",
)

# ── Page 1 : schéma (paysage) ─────────────────────────────────────────
pdf.add_page(orientation="L")
pdf.set_font("DejaVu", "B", 14)
pdf.set_xy(15, 14)
pdf.cell(0, 8, "Schéma de câblage — capteur optique 45° (Omron E3Z-D61, sortie NPN)")
pdf.set_font("DejaVu", "", 9)
pdf.set_xy(15, 22)
pdf.cell(
    0,
    5,
    "Remplace le microswitch : mêmes broches du Pi (13 et 14), aucune modification du logiciel.",
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
pdf.label(50, 98, "Omron E3Z-D61", 9, "B", align="C")
pdf.label(50, 103, "capteur à réflexion, NPN", 7, color=GRIS, align="C")
pdf.label(50, 110, "Sélecteur sur L (L-ON)", 7.5, "B", align="C")
pdf.label(50, 114.5, "voyant orange = cible vue", 7, color=GRIS, align="C")
pdf.label(50, 118.5, "molette = sensibilité", 7, color=GRIS, align="C")
pdf.terminal(75, 102)
pdf.terminal(75, 124)
pdf.terminal(50, 136)

# Raspberry Pi
pdf.box(225, 40, 52, 120, fill=(235, 245, 235))
pdf.label(251, 46, "Raspberry Pi", 9, "B", align="C")
pdf.label(251, 51, "connecteur 40 broches", 7, color=GRIS, align="C")
for y, broche, nom, col in (
    (60, "broche 1", "3,3 V", ROUGE),
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

# Fil noir : sortie → cathode de la diode
pdf.wire([(75, 124), (190, 124), (190, 108)], NOIR)
pdf.label(92, 121, "noir (sortie)", 8, "B", color=NOIR)

# Diode : anode en haut (vers GPIO27), cathode en bas (vers fil noir)
pdf.wire([(190, 82), (190, 96)], VERT)
pdf.diode_down(190, 96, 104)
pdf.wire([(190, 104), (190, 108)], NOIR)
pdf.label(170, 96.5, "1N5819", 8, "B", align="R", w=40)
pdf.label(170, 101, "bague grise côté capteur", 7, align="R", w=40)
pdf.label(170, 105, "(fil noir)", 7, align="R", w=40)

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
pdf.rect(122, 55, 86, 60)
pdf.set_dash_pattern()
pdf.label(124, 112, "à souder près du Pi", 7, "I", GRIS)

# Encadrés sous le schéma
pdf.set_xy(15, 165)
pdf.set_font("DejaVu", "", 8)
pdf.multi_cell(
    267,
    4.2,
    "Fonctionnement : sans cible, la résistance tire GPIO27 à 3,3 V (lu 1). Quand le capteur voit "
    "la cible, son fil noir est relié au 0 V et GPIO27 descend sous 0,6 V (lu 0). Ce passage de 1 à 0 "
    "recale la coupole à 45°, exactement comme le microswitch. La diode protège le Pi : même en cas "
    "d'erreur sur le fil noir, aucune tension du 12 V ne peut remonter vers GPIO27.",
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

# ── Page 2 : repérage des broches et de la diode ──────────────────────
pdf.add_page()
pdf.h1("1. Repérer les broches du Pi")
pdf.body(
    "Le connecteur 40 broches longe un bord de la carte. La broche 1 a une pastille carrée ; elle est "
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
}
pdf.set_draw_color(60, 60, 60)
pdf.set_fill_color(40, 40, 40)
pdf.rect(x_imp - 3, y0 - 4, x_pair - x_imp + 6, 7 * 7 + 1, "D")
for n in range(1, 15):
    x = x_imp if n % 2 else x_pair
    y = y0 + ((n - 1) // 2) * 7
    nom, col = noms[n]
    utile = n in (1, 13, 14)
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
pdf.set_y(y0 + 7 * 7 + 4)
pdf.body(
    "Seules les broches 1, 13 et 14 servent. Le microswitch actuel est déjà sur la broche 13 "
    "(GPIO27) et sur une masse : noter sur quelles broches il est branché avant de débrancher."
)

pdf.h1("2. Sens de la diode 1N5819")
y = pdf.get_y() + 6
pdf.set_draw_color(0, 0, 0)
pdf.set_line_width(0.6)
pdf.line(72, y, 90, y)
pdf.line(120, y, 138, y)
pdf.set_line_width(0.2)
pdf.set_fill_color(30, 30, 30)
pdf.rect(90, y - 4, 30, 8, "F")
pdf.set_fill_color(190, 190, 190)
pdf.rect(113, y - 4, 4, 8, "F")
pdf.label(70, y, "côté Pi (GPIO27 + 10 kΩ)", 8, "B", VERT, "R", 50)
pdf.label(140, y, "côté capteur (fil noir)", 8, "B", NOIR)
pdf.label(115, y + 7, "bague grise", 7, "I", GRIS, "C", 30)
pdf.set_y(y + 12)
pdf.body(
    "La bague grise marque la cathode : elle va du côté du fil noir du capteur. Montée à l'envers, "
    "GPIO27 reste toujours à 1 et le recalage ne se fait plus (sans danger pour le Pi)."
)

# ── Page 3 : montage, réglage, contrôle ──────────────────────────────
pdf.add_page()
pdf.h1("3. Matériel")
pdf.bullet(
    "Capteur Omron E3Z-D61 (vérifier « D61 » sur l'étiquette : la version D81, PNP, ne convient pas)."
)
pdf.bullet("Bloc d'alimentation 12 V continu, 100 mA ou plus, branché en permanence.")
pdf.bullet("Diode 1N5819, résistance 10 kΩ (marron-noir-orange).")
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
pdf.step(3, "Souder la résistance et la diode près du Pi, comme sur le schéma de la page 1.")
pdf.step(4, "Relier GPIO27 (broche 13), le 3,3 V (broche 1) et la masse (broche 14).")
pdf.step(5, "Brancher le capteur : marron sur +12 V, bleu sur 0 V, noir sur la diode (côté bague).")
pdf.step(6, "Relier le 0 V de l'alimentation 12 V à la masse du Pi (fil bleu commun).")
pdf.step(7, "Mettre le sélecteur du capteur sur L (L-ON).")
pdf.step(8, "Rebrancher l'alimentation 12 V, puis le Pi.")
pdf.warning_box(
    "Avant de rallumer le Pi, mesurer au multimètre entre la broche 13 et la masse, alimentation 12 V "
    "branchée : on ne doit jamais lire plus de 3,3 V. Plus de 3,3 V = erreur de câblage, ne pas allumer."
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
    "Sensibilité (molette) : partir du minimum, monter jusqu'à ce que le voyant orange s'allume "
    "franchement sur la cible, puis vérifier qu'il reste éteint sans la cible."
)
pdf.bullet(
    "Voyant vert = signal stable. S'il clignote sur la cible, rapprocher le capteur ou augmenter un peu la sensibilité."
)

pdf.h1("6. Contrôle après la pose")
pdf.body("Au multimètre, entre la broche 13 (GPIO27) et la masse :")
pdf.bullet("cible devant le capteur : moins de 0,6 V ;")
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
