"""Génère docs/schema_capteur_45_E3Z-D61.pdf : montage du capteur optique de recalage 45°.

Remplace le microswitch SS-5GL (GPIO27, front 1→0 = 45°) par un capteur E3Z-S10N3 (NPN).
Aucun changement de code : GPIO27 passe à 0 quand la cible est vue.
Avec optocoupleur PC817 (17/11) : sur table le capteur commute (10 kΩ vers +12 V :
12 V sans cible, 1,28 V avec), mais branché en direct le Pi ne le voit pas (masse 12 V
non commune). L'optocoupleur sépare les masses et met GPIO27 vers 0,2 V en détection.
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
VIOLET = (120, 60, 160)


class Schema(Report):
    def body(self, text):
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
    subtitle="E3Z-S10N3 à la place du microswitch, via optocoupleur PC817",
)

# ── Page 1 : schéma (paysage) ─────────────────────────────────────────
pdf.add_page(orientation="L")
pdf.set_font("DejaVu", "B", 14)
pdf.set_xy(15, 14)
pdf.cell(0, 8, "Schéma de câblage — capteur optique 45° (E3Z-S10N3) avec optocoupleur PC817")
pdf.set_font("DejaVu", "", 9)
pdf.set_xy(15, 22)
pdf.cell(
    0,
    5,
    "Remplace le microswitch : même entrée du Pi (broche 13), aucune modification du logiciel. "
    "Le 12 V et le Pi restent séparés.",
)

# Alimentation 12 V
pdf.box(25, 40, 50, 32)
pdf.label(50, 47, "Alimentation", 9, "B", align="C")
pdf.label(50, 52, "12 V continu", 9, "B", align="C")
pdf.label(50, 57, "(celle déjà utilisée", 7, color=GRIS, align="C")
pdf.label(50, 61, "pour l'essai sur table)", 7, color=GRIS, align="C")
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

# Optocoupleur PC817
pdf.box(124, 74, 42, 34, fill=(240, 232, 250))
pdf.label(145, 79, "PC817", 9, "B", align="C")
pdf.label(145, 91, "LED → transistor", 6.5, color=GRIS, align="C")
pdf.label(145, 95, "(lumière interne)", 6.5, color=GRIS, align="C")
for x, y, txt, align in (
    (125.5, 84, "1 anode", "L"),
    (125.5, 102, "2 cathode", "L"),
    (164.5, 84, "4 collecteur", "R"),
    (164.5, 102, "3 émetteur", "R"),
):
    pdf.label(x, y, txt, 6.5, "B", VIOLET, align, w=19)
for x, y in ((124, 84), (124, 102), (166, 84), (166, 102)):
    pdf.terminal(x, y)

# Raspberry Pi
pdf.box(225, 40, 52, 120, fill=(235, 245, 235))
pdf.label(251, 46, "Raspberry Pi", 9, "B", align="C")
pdf.label(251, 51, "connecteur 40 broches", 7, color=GRIS, align="C")
for y, broche, nom, col in (
    (60, "broche 17", "3,3 V", ROUGE),
    (84, "broche 13", "GPIO27", VERT),
    (152, "broche 14", "GND (masse)", BLEU),
):
    pdf.terminal(225, y)
    pdf.label(229, y - 2.2, broche, 8, "B")
    pdf.label(229, y + 2.2, nom, 8, color=col)

# Fil marron : capteur + → +12 V
pdf.wire([(75, 102), (90, 102), (90, 66), (75, 66)], MARRON)
pdf.dot(90, 66, ROUGE)
pdf.label(92, 99, "marron", 8, "B", color=MARRON)

# +12 V → 2,2 kΩ → anode (broche 1)
pdf.wire([(90, 66), (115, 66), (115, 70)], ROUGE)
pdf.resistor_v(115, 70, 80, NOIR)
pdf.wire([(115, 80), (115, 84), (124, 84)], ROUGE)
pdf.label(112, 73, "2,2 kΩ", 8, "B", align="R", w=20)

# Fil noir : sortie capteur → cathode (broche 2)
pdf.wire([(75, 124), (115, 124), (115, 102), (124, 102)], NOIR)
pdf.label(78, 121, "noir (sortie)", 8, "B", NOIR, w=30)

# Fils bleus : 0 V du 12 V, côté capteur seulement
pdf.wire([(25, 66), (15, 66), (15, 146), (50, 146)], BLEU)
pdf.wire([(50, 136), (50, 146)], BLEU)
pdf.dot(50, 146, BLEU)
pdf.label(52, 141, "bleu", 8, "B", color=BLEU)

# Côté Pi : 10 kΩ 3,3 V → GPIO27, collecteur → GPIO27, émetteur → GND Pi
pdf.wire([(225, 60), (190, 60), (190, 66)], ROUGE)
pdf.resistor_v(190, 66, 78, NOIR)
pdf.wire([(190, 78), (190, 84)], VERT)
pdf.label(187, 70, "10 kΩ", 8, "B", align="R", w=20)
pdf.label(187, 74.5, "(déjà posée)", 7, color=GRIS, align="R", w=20)
pdf.wire([(166, 84), (225, 84)], VERT)
pdf.dot(190, 84, VERT)
pdf.wire([(166, 102), (205, 102), (205, 152), (225, 152)], BLEU)
pdf.label(207, 120, "masse Pi", 7.5, "B", BLEU)

# Séparation des masses
pdf.set_draw_color(*ROUGE)
pdf.set_dash_pattern(dash=2, gap=1.5)
pdf.line(145, 112, 145, 160)
pdf.set_dash_pattern()
pdf.label(143, 150, "côté 12 V", 8, "B", ROUGE, "R", 40)
pdf.label(147, 150, "côté Pi", 8, "B", ROUGE)
pdf.label(145, 156, "aucun fil ne traverse cette ligne", 7.5, "I", ROUGE, "C", 80)

# Cadre pointillé : plaquette près du Pi
pdf.set_draw_color(*GRIS)
pdf.set_dash_pattern(dash=1.5, gap=1.2)
pdf.rect(106, 54, 104, 58)
pdf.set_dash_pattern()
pdf.label(108, 58, "petite plaquette près du Pi", 7, "I", GRIS)

# Encadrés sous le schéma
pdf.set_xy(15, 165)
pdf.set_font("DejaVu", "", 8)
pdf.multi_cell(
    267,
    4.2,
    "Fonctionnement : sans cible, le capteur ne fait rien, la LED du PC817 est éteinte et la 10 kΩ "
    "tient GPIO27 à 3,3 V (lu 1). Quand le capteur voit la cible, son fil noir est relié au 0 V du "
    "12 V : environ 4 mA traversent la 2,2 kΩ et la LED du PC817, dont le transistor relie alors "
    "GPIO27 à la masse du Pi, vers 0,2 V (lu 0). Ce passage de 1 à 0 recale la coupole à 45°, "
    "exactement comme le microswitch. Le 12 V et le Pi n'ont aucun fil en commun.",
)
pdf.ln(1)
pdf.set_x(15)
pdf.set_font("DejaVu", "B", 8)
pdf.set_text_color(*ROUGE)
pdf.multi_cell(
    267,
    4.2,
    "Ne jamais brancher un fil du capteur (marron, bleu, noir) ni le 12 V sur le Pi : seules les "
    "broches 3 et 4 du PC817 vont au Pi. Ne pas alimenter le capteur avec le 36 V du driver moteur "
    "(le capteur accepte 12 à 24 V) ni avec le Shelly 24 V du cimier (coupé hors cycle).",
)
pdf.set_text_color(0, 0, 0)

# ── Page 2 : repérage des broches, PC817, essai sur table ────────────
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
    "Côté Pi, seules les broches 13, 14 et 17 servent ; la broche 1 reste à l'encodeur. "
    "La 10 kΩ entre les broches 13 et 17 déjà posée reste en place."
)

pdf.h1("2. Repérer les broches du PC817")
pdf.body(
    "Le PC817 est un petit boîtier noir à 4 pattes, deux de chaque côté. Un point (ou une encoche) "
    "marque la broche 1. Vu de dessus, point en haut à gauche :"
)
pdf.bullet("à gauche, de haut en bas : broche 1 (anode), broche 2 (cathode) : côté 12 V ;")
pdf.bullet("à droite, de bas en haut : broche 3 (émetteur), broche 4 (collecteur) : côté Pi.")
pdf.body("La broche 4 est donc en face de la broche 1, la broche 3 en face de la broche 2.")

pdf.h1("3. Essai sur table (déjà fait le 17/11)")
pdf.body(
    "Marron sur +12 V, bleu sur 0 V, 10 kΩ entre le noir et le +12 V, voltmètre noir ↔ bleu : "
    "12 V sans cible, 1,28 V cible devant. Le capteur fonctionne. Retirer cette 10 kΩ reliée au "
    "+12 V : dans le montage final, c'est la 2,2 kΩ et le PC817 qui prennent sa place."
)

# ── Page 3 : montage, réglage, contrôle ──────────────────────────────
pdf.add_page()
pdf.h1("4. Matériel")
pdf.bullet("Capteur E3Z-S10N3 (sortie NPN, vérifiée les 16 et 17/11).")
pdf.bullet("Optocoupleur PC817 (boîtier à 4 pattes), quelques centimes.")
pdf.bullet("Résistance 2,2 kΩ (rouge-rouge-rouge), côté 12 V.")
pdf.bullet("Résistance 10 kΩ (marron-noir-orange) entre les broches 13 et 17 : déjà posée.")
pdf.bullet("Alimentation 12 V continu branchée en permanence, celle de l'essai sur table.")
pdf.bullet(
    "Une cible : petite plaque claire et mate fixée sur la partie tournante de la coupole, à 45°."
)

pdf.h1("5. Montage")
pdf.step(1, "Arrêter proprement le Pi (menu Arrêter), puis couper son alimentation et le 12 V.")
pdf.step(2, "Retirer le fil noir du capteur de la broche 13 et le fil bleu de la broche 14.")
pdf.step(3, "Côté 12 V : +12 V → 2,2 kΩ → broche 1 du PC817 ; fil noir du capteur → broche 2.")
pdf.step(4, "Capteur : marron sur +12 V, bleu sur le 0 V de l'alimentation 12 V (pas sur le Pi).")
pdf.step(5, "Côté Pi : broche 4 du PC817 → broche 13 du Pi ; broche 3 du PC817 → broche 14.")
pdf.warning_box(
    "Avant de rallumer, tout débranché, à l'ohmmètre : aucune continuité entre l'un des fils du "
    "capteur (marron, bleu, noir) et les broches 13, 14 ou 17 du Pi. Sinon, erreur de câblage : "
    "ne pas allumer."
)
pdf.step(6, "Rebrancher le 12 V, puis le Pi.")

pdf.h1("6. Pose et réglage du capteur")
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

pdf.h1("7. Contrôle après la pose")
pdf.body("Au multimètre, entre la broche 13 (GPIO27) et la broche 14 (masse) :")
pdf.bullet("cible absente : environ 3,3 V ;")
pdf.bullet("cible devant le capteur : moins de 0,4 V (environ 0,2 V attendu).")
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
