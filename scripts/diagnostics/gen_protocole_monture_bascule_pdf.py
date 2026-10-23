#!/usr/bin/env python3
"""Génère docs/protocole_monture_bascule_terrain.pdf.

Position de départ de la monture (écart de pointage vu le 21/10) et essai de
l'option « la coupole attend le retournement de la monture » (6.24).

Usage :
    uv run --with fpdf2 python scripts/diagnostics/gen_protocole_monture_bascule_pdf.py
"""

import os
import sys

sys.path.insert(0, "/home/jp/.claude/skills/pdf-report/scripts")
from pdf_report import Report  # noqa: E402

FONT_DIR = "/usr/share/fonts/truetype/dejavu/"
OUT = os.path.join(
    os.path.dirname(__file__), "..", "..", "docs", "protocole_monture_bascule_terrain.pdf"
)


class Protocole(Report):
    """Report + bloc de commandes en chasse fixe."""

    def __init__(self, **kw):
        super().__init__(**kw)
        self.add_font("Mono", "", os.path.join(FONT_DIR, "DejaVuSansMono.ttf"))

    def code_block(self, lines):
        self.ln(1)
        self.set_font("Mono", "", 7.5)
        self.set_fill_color(242, 242, 245)
        self.set_draw_color(205, 205, 212)
        self.set_text_color(20, 20, 20)
        for line in lines:
            self.cell(0, 4.4, "  " + line, border="LR", new_x="LMARGIN", new_y="NEXT", fill=True)
        self.cell(0, 0.6, "", border="LRT", new_x="LMARGIN", new_y="NEXT", fill=True)
        self.set_text_color(0, 0, 0)
        self.set_font("DejaVu", "", 9)
        self.ln(2)

    def bullet(self, text, indent=10):
        super().bullet(text, indent)
        self.set_x(self.l_margin)  # le multi_cell de la puce laisse le curseur à droite

    def attendu(self, texte):
        self.success_box("Résultat attendu : " + texte)


pdf = Protocole(
    title="Monture et bascule de la coupole",
    subtitle="Position de départ et option ASIAIR — DriftApp 6.25.0",
    header_text="Protocole monture et bascule — v6.25.0",
)

pdf.title_page(
    summary=(
        "Les logs du 21 et du 22/10 expliquent trois choses : la coupole qui retournait à 45° "
        "et le cimier qui se fermait le matin (corrigé dans la 6.24.1), les allers-retours de "
        "la monture après le méridien, et la lenteur du plate-solving juste après le "
        "retournement. Les deux derniers ont la même cause, côté monture : elle ne sait pas "
        "exactement où elle pointe, ses deux axes sont décalés d'environ 3°. Ce protocole la "
        "remet en place (de jour, 20 minutes), puis fait essayer, une nuit, l'option qui fait "
        "attendre la coupole jusqu'au retournement réel de la monture."
    ),
    extra_lines=[
        "Observatoire Ubik — DriftApp Web",
        "Destinataire : Serge, sur site",
        "Partie A de jour (environ 20 min), partie B pendant une nuit avec un passage au méridien",
        "Prérequis : mise à jour 6.25.0 installée (bouton « Mettre à jour »)",
        "Octobre 2026",
    ],
)

# ─────────────────────────────────────────────────────────────────────────────
pdf.add_page()
pdf.h1("Ce que la 6.24.1 corrige")
pdf.body(
    "Le 22/10 au matin, la coupole retournait à 45° une minute après le début du suivi, puis "
    "le cimier se fermait. Ce n'était pas la nouvelle bascule de la coupole (l'option n'était "
    "pas cochée), mais la fermeture automatique de fin de nuit du mode semi : elle "
    "considérait que « le soleil monte » jusqu'à midi, et refermait le cimier à chaque "
    "ouverture, de nouveau après chaque redémarrage des services."
)
pdf.bold_bullet(
    "Désormais :",
    "la fermeture de fin de nuit se fait une seule fois par matin, même si les services "
    "redémarrent. Si un suivi est relancé pendant qu'elle attend la coupole au parking, elle "
    "est annulée.",
)
pdf.bold_bullet(
    "Autre correction :",
    "au redémarrage des services, le cimier ne rejoue plus la dernière commande reçue avant "
    "(le 22/10, la fermeture de 04:08 a été refaite à 08:47, sans effet car le cimier était "
    "déjà fermé).",
)
pdf.bold_bullet(
    "Et pour le suivi :",
    "l'écart « ENC … (+4,2°) » vu le 21/10 après la bascule ne peut plus se produire. La "
    "coupole était restée 4° trop loin toute la nuit ; désormais la correction suivante la "
    "ramène sur sa cible.",
)
pdf.info_box(
    "Essais de jour : le plus simple reste de passer le cimier en mode « manuel » le temps des "
    "essais, puis de remettre « semi ». En semi, si aucune fermeture n'a eu lieu ce matin-là "
    "(pas de session la nuit précédente), la première ouverture sera refermée une fois."
)

# ─────────────────────────────────────────────────────────────────────────────
pdf.h1("Partie A — La position de départ de la monture")
pdf.h2("Ce que montrent les logs")
pdf.body(
    "Après chaque plate-solving, l'ASIAIR compare l'endroit où le télescope pointe vraiment "
    "(la photo) à l'endroit où la monture croit pointer (le comptage de ses moteurs). Le 21/10, "
    "l'écart était d'environ 3,5° en ascension droite et 3° en déclinaison :"
)
pdf.table(
    ["Moment", "Ciel réel (photo)", "Ce que croit la monture", "Écart"],
    [
        [
            "20:10, côté Ouest",
            "AD 21,30 h, Déc 34,3°",
            "AD 21,57 h, Déc 31,4°",
            "AD +0,27 h, Déc −3°",
        ],
        [
            "20:57, côté Est",
            "AD 21,31 h, Déc 34,3°",
            "AD 21,54 h, Déc 37,3°",
            "AD +0,23 h, Déc +3°",
        ],
    ],
    col_widths=[30, 45, 50, 45],
)
pdf.body(
    "L'écart en déclinaison change de signe quand la monture change de côté : c'est le signe "
    "d'une monture mise en route alors qu'elle n'était pas exactement dans sa position de "
    "départ (barre de contrepoids verticale vers le bas, tube vers le pôle). Elle compte "
    "ensuite tout à partir de cette fausse origine. L'heure et le lieu réglés dans l'ASIAIR, "
    "eux, sont bons (vérifié : le temps sidéral de l'ASIAIR est juste à 35 secondes près)."
)
pdf.h2("Pourquoi c'est gênant")
pdf.bold_bullet(
    "Mauvais côté :",
    "la monture décide du côté du pied d'après sa propre idée de la position de l'objet, qui est "
    "décalée de 0,23 h. Pour elle, l'objet passe le méridien environ 14 minutes trop tard. Le "
    "retournement automatique de l'ASIAIR impose le bon côté, mais un GOTO lancé à la main dans "
    "ce quart d'heure renvoie la monture côté Ouest, alors que la carte montre l'objet déjà à "
    "l'ouest. C'est ce qui s'est passé le 21/10 entre 21:00 et 21:04 (quatre changements de "
    "côté).",
)
pdf.bold_bullet(
    "Plate-solving lent :",
    "après le retournement, la correction de 3° apprise d'un côté devient fausse de l'autre côté. Au premier pointage "
    "après le retournement, la monture se retrouve à environ 6° de la cible (photo à Déc 28,3° "
    "pour une cible à 34,3° le 21/10). Avec le petit champ du C14, il faut chercher loin et "
    "s'y reprendre à plusieurs fois.",
)

pdf.h2("A1 — Vérifier")
pdf.body(
    "Dans l'ASIAIR, envoyer la monture à sa position de départ (commande « Home », celle "
    "utilisée le 22/10 à 09:08). Une fois arrêtée, regarder la monture."
)
pdf.attendu(
    "barre de contrepoids bien verticale vers le bas, tube parallèle à l'axe polaire (pointé "
    "vers le pôle). Un écart de quelques degrés sur l'un des deux axes confirme le problème."
)

pdf.h2("A2 — Corriger")
pdf.bullet("Éteindre la monture.")
pdf.bullet(
    "Desserrer les embrayages et placer la monture à la main exactement en position de départ : "
    "barre de contrepoids verticale (un niveau à bulle posé dessus aide), tube parallèle à l'axe "
    "polaire."
)
pdf.bullet("Resserrer les embrayages, rallumer la monture, reconnecter l'ASIAIR.")

pdf.h2("A3 — Contrôler")
pdf.body("Faire un GOTO sur une étoile ou un objet, puis un plate-solving.")
pdf.attendu("l'écart de pointage annoncé par l'ASIAIR tombe sous 0,5° environ, au lieu de 3 à 4°.")

pdf.h2("Les bons réflexes ensuite")
pdf.bullet("Toujours remettre la monture en position de départ avant de l'éteindre.")
pdf.bullet("Ne jamais desserrer les embrayages tant que la monture est allumée.")
pdf.bullet(
    "Juste après un retournement, éviter les GOTO à la main : laisser le recentrage "
    "automatique de l'ASIAIR finir, il impose le bon côté du pied."
)
pdf.warning_box(
    "Le 21/10, la caméra de guidage a aussi été déconnectée une fois par l'ASIAIR (« the camera "
    "has not completed a 4 sec exposure… disconnected »). Si ce message revient, vérifier le "
    "câble USB et l'alimentation de la caméra de guidage."
)

# ─────────────────────────────────────────────────────────────────────────────
pdf.h1("Partie B — L'option « la coupole attend le retournement »")
pdf.h2("Ce qu'elle fait")
pdf.body(
    "Sans l'option (comportement actuel) : la coupole bascule de l'autre côté au passage de "
    "l'objet au méridien, même si la monture n'a pas encore retourné. Avec des poses de 600 s, "
    "l'ASIAIR retourne souvent plusieurs minutes plus tard (environ 11 min le 16/10) : pendant ce "
    "temps, le télescope regarde l'intérieur de la coupole."
)
pdf.body(
    "Avec l'option : DriftApp lit toutes les 5 secondes le côté du pied de la monture sur "
    "l'ASIAIR. Tant que la monture est encore côté Ouest alors que l'objet a passé le méridien, "
    "la coupole ne bouge pas. Dès que la monture passe côté Est, la coupole part aussitôt, à "
    "pleine vitesse, pour être en place quand les poses reprennent."
)
pdf.bold_bullet(
    "Garde-fous :",
    "si l'ASIAIR ne répond plus depuis 30 s, la coupole bascule au méridien comme avant. Si la "
    "monture n'a pas retourné au bout de 30 minutes (réglage « max_wait_minutes »), la coupole "
    "bascule quand même.",
)
pdf.bold_bullet(
    "Elle ne recule jamais :",
    "si la monture repasse côté Ouest par erreur (GOTO à la main, voir partie A), la coupole se "
    "remet simplement en attente là où elle est.",
)

pdf.h2("Faut-il la cocher ?")
pdf.body(
    "Oui, pour un essai, mais après la partie A : tant que la monture a son écart de 3°, ses "
    "changements de côté à tort feraient attendre la coupole pour rien. Si l'essai déçoit, il "
    "suffit de la décocher pour revenir exactement au comportement d'avant."
)
pdf.info_box(
    "Une condition : DriftApp et l'ASIAIR doivent suivre le même objet. Le plus simple est de "
    "lancer le suivi avec le bouton « ASIAIR » du dashboard, qui reprend les coordonnées "
    "pointées par la monture. Autre limite : un suivi lancé après le méridien, sur une monture "
    "pas encore retournée, fait son premier positionnement du côté « après »."
)

pdf.h2("B1 — Cocher l'option")
pdf.bullet("Page Configuration du dashboard, section « asiair ».")
pdf.bullet(
    "Cocher « dome_flip_on_pierside ». Vérifier que « host » est bien l'adresse de l'ASIAIR."
)
pdf.bullet("Laisser « max_wait_minutes » à 30 (ne pas descendre sous 16 avec des poses de 600 s).")
pdf.bullet(
    "Enregistrer. Pas besoin de redémarrer les services : l'option est relue au démarrage de "
    "chaque suivi. Si un suivi est en cours, l'arrêter et le relancer."
)

pdf.h2("B2 — Pendant la nuit")
pdf.body(
    "Choisir un objet qui passe au méridien pendant la session. Sur le dashboard, sous « Suivi actif » :"
)
pdf.bullet("avant le méridien : « Monture : côté Ouest » ;")
pdf.bullet(
    "après le méridien, monture pas encore retournée : en orange « Attente retournement monture — "
    "n min / 30 », et au journal « Coupole en attente du retournement de la monture (ASIAIR) » ;"
)
pdf.bullet(
    "au retournement : « Monture retournée : bascule de la coupole » au journal, la coupole part "
    "dans les secondes qui suivent, puis « Monture : côté Est »."
)
pdf.body(
    "Faire l'essai si possible deux fois, avec le réglage ASIAIR « Flip Timing after Meridian » "
    "à 0 puis à 5 minutes. Avec la caméra du C14, regarder si la coupole est en place quand les "
    "poses reprennent."
)
pdf.h2("La surveillance ASIAIR")
pdf.body(
    "Depuis la version 6.25, elle tourne en permanence : tout ce que l'ASIAIR envoie est "
    "enregistré, un fichier par nuit, sans rien lancer. Pour vérifier qu'elle tourne, dans un "
    "terminal sur le Pi (Ctrl + Alt + T) :"
)
pdf.code_block(
    [
        "cd ~/DriftApp",
        "./scripts/asiair_sonde.sh etat",
    ]
)
pdf.warning_box(
    "Avec l'option cochée, DriftApp interroge l'ASIAIR deux fois (suivi et surveillance). Si "
    "l'ASIAIR se comporte bizarrement (déconnexion, alerte), noter l'heure."
)

pdf.h2("B3 — À noter et à me renvoyer")
pdf.bullet("L'objet, la durée des poses, le réglage « Flip Timing after Meridian ».")
pdf.bullet("L'heure approximative du retournement de la monture et celle du départ de la coupole.")
pdf.bullet("Toute anomalie de l'ASIAIR ou de la coupole, avec l'heure.")
pdf.bullet(
    "Les fichiers de la nuit : logs/moteur/ (lignes « dome_flip_wait »), logs/cimier/"
    "cimier_service.log, et le dossier logs/asiair/."
)

pdf.output(OUT)
print(f"PDF : {os.path.abspath(OUT)}")
