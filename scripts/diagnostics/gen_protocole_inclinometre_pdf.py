#!/usr/bin/env python3
"""Génère docs/protocole_inclinometre_terrain.pdf (mise en place de l'inclinomètre de la monture).

Usage :
    uv run --with fpdf2 python scripts/diagnostics/gen_protocole_inclinometre_pdf.py
"""

import os
import sys

sys.path.insert(0, "/home/jp/.claude/skills/pdf-report/scripts")
from pdf_report import Report  # noqa: E402

FONT_DIR = "/usr/share/fonts/truetype/dejavu/"
OUT = os.path.join(
    os.path.dirname(__file__), "..", "..", "docs", "protocole_inclinometre_terrain.pdf"
)
CMD = "./scripts/inclinometre.sh"


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

    def attendu(self, texte):
        self.success_box("Résultat attendu : " + texte)


pdf = Protocole(
    title="Inclinomètre de la monture",
    subtitle="Mise en place et initialisation — DriftApp 6.21.12",
    header_text="Protocole inclinomètre — v6.21.12",
)

pdf.title_page(
    summary=(
        "L'ASIAIR ne dit pas quand il retourne la monture : le 16/10, il l'a fait environ "
        "11 minutes après le passage au méridien, à la fin de la pose de 600 s en cours, alors "
        "que la coupole s'apprêtait à basculer au passage. L'idée : fixer l'inclinomètre "
        "WitMotion WT9011DCL-BT50 sur la monture et le faire lire par le Raspberry Pi en "
        "Bluetooth. Un retournement est une rotation d'un demi-tour : il doit se voir sans "
        "ambiguïté. Ce protocole installe le capteur, le teste de jour, puis enregistre une "
        "vraie nuit. Tout se fait directement sur le Pi, au clavier. Rien ne change encore "
        "dans le suivi : DriftApp se contente d'écouter."
    ),
    extra_lines=[
        "Observatoire Ubik — DriftApp Web",
        "Destinataire : Serge, sur site",
        "Étapes 1 à 6 de jour (environ 1 h), étape 7 pendant une nuit d'observation",
        "Prérequis : mise à jour 6.21.12 installée (bouton « Mettre à jour »)",
        "Octobre 2026",
    ],
)

# ─────────────────────────────────────────────────────────────────────────────
pdf.add_page()
pdf.h1("Avant de commencer")
pdf.bold_bullet(
    "Une seule connexion à la fois :",
    "le capteur n'accepte qu'un appareil connecté. Si le téléphone y est connecté "
    "(application WitMotion), le Pi ne le voit plus. Toujours fermer l'application "
    "avant les étapes sur le Pi.",
)
pdf.bold_bullet(
    "Le capteur est un lecteur :",
    "les commandes n'envoient aucun ordre, ni au capteur, ni à la coupole, ni à la "
    "monture. On peut les arrêter à tout moment.",
)
pdf.bold_bullet(
    "Wi-Fi et Bluetooth :",
    "sur le Pi, ils partagent la même puce. Si un Shelly du cimier devenait injoignable "
    "pendant les essais, le noter avec l'heure.",
)
pdf.warning_box(
    "Points que je ne connais pas et que ce protocole fait vérifier : l'autonomie réelle de la "
    "batterie (les fiches du commerce annoncent de 8 à 40 h), la portée du Bluetooth à travers "
    "la coupole, et le format exact des données de ce modèle (repris d'un modèle de la même "
    "famille)."
)

pdf.h1("Ouvrir un terminal sur le Pi")
pdf.body("Toutes les commandes de ce protocole se tapent dans un terminal, sur le Pi lui-même.")
pdf.bold_bullet(
    "Ouvrir :", "appuyer sur Ctrl + Alt + T. Une fenêtre noire s'ouvre par-dessus le dashboard."
)
pdf.bold_bullet(
    "Si rien ne s'ouvre :",
    "Alt + Tab pour passer au bureau, puis menu framboise (en haut à gauche) → Accessoires → Terminal.",
)
pdf.bold_bullet(
    "Revenir au dashboard :", "Alt + Tab. Le dashboard n'est pas fermé, il est juste derrière."
)
pdf.body("Dans chaque nouveau terminal, taper d'abord cette commande, puis Entrée :")
pdf.code_block(["cd ~/DriftApp"])
pdf.info_box(
    "Les commandes se tapent exactement comme écrites, espaces et points compris, puis Entrée. "
    "La flèche Haut du clavier rappelle la commande précédente : pratique pour la relancer sans "
    "tout retaper. Toutes les commandes du capteur commencent par ./scripts/inclinometre.sh"
)

# ─────────────────────────────────────────────────────────────────────────────
pdf.h1("Étape 1 — Charger et allumer le capteur")
pdf.body(
    "Suivre le guide papier fourni avec le capteur pour la charge (prise USB-C) et la mise en "
    "marche (bouton sur le dessus). Charger complètement avant de commencer : l'étape 6 mesure "
    "l'autonomie à partir d'une charge pleine."
)
pdf.attendu(
    "le voyant du capteur indique qu'il est allumé (voir le guide pour la signification "
    "des couleurs et clignotements)."
)

pdf.h1("Étape 2 — Vérifier le capteur avec le téléphone (facultatif)")
pdf.body(
    "Avec l'application WitMotion indiquée dans le guide : se connecter au capteur, le tourner à "
    "la main et vérifier que les angles bougent. Noter le nom affiché du capteur (commence "
    "normalement par « WT »)."
)
pdf.bullet("Ne modifier aucun réglage : la fréquence par défaut (10 mesures par seconde) convient.")
pdf.bullet("Pas besoin d'étalonnage : on cherche un demi-tour, pas une précision au degré.")
pdf.bullet("Fermer l'application et déconnecter le capteur à la fin.")

# ─────────────────────────────────────────────────────────────────────────────
pdf.add_page()
pdf.h1("Étape 3 — Vérifier le Bluetooth du Pi")
pdf.code_block(["bluetoothctl show"])
pdf.attendu("parmi les lignes affichées, « Powered: yes ».")
pdf.body(
    "Si « Powered: no », ou si la commande répond « No default controller available », taper "
    "ces trois commandes l'une après l'autre (le mot de passe demandé est celui de la session du Pi), "
    "puis refaire « bluetoothctl show » :"
)
pdf.code_block(
    [
        "sudo rfkill unblock bluetooth",
        "sudo systemctl enable --now bluetooth",
        "bluetoothctl power on",
    ]
)

pdf.h1("Étape 4 — Trouver le capteur depuis le Pi")
pdf.body("Capteur allumé, posé à côté du Pi, application du téléphone fermée :")
pdf.code_block([CMD + " scan"])
pdf.body(
    "La première fois, la commande télécharge la bibliothèque Bluetooth : le Pi doit avoir accès "
    "à internet, et cela peut prendre une minute. Le scan lui-même dure 10 s."
)
pdf.attendu(
    "une ligne du type « AA:BB:CC:DD:EE:FF  RSSI -55 dBm  WT901BLE68  <-- capteur WitMotion "
    "probable ». Il n'y a rien à recopier : les commandes suivantes retrouvent le capteur seules."
)
pdf.body(
    "Refaire le scan avec le capteur posé à l'endroit prévu sur la monture, et noter le RSSI "
    "(le nombre en dBm). Plus il est proche de 0, meilleure est la liaison : jusqu'à -85 dBm, ça "
    "devrait aller ; en dessous, il faudra rapprocher le Pi ou ajouter un adaptateur Bluetooth USB."
)
pdf.table(
    ["Position du capteur", "RSSI relevé"],
    [
        ["À côté du Pi", ""],
        ["Sur la monture, tube vers l'Est", ""],
        ["Sur la monture, tube vers l'Ouest", ""],
    ],
    col_widths=[110, 60],
)

pdf.add_page()
pdf.h1("Étape 5 — Essai à la main")
pdf.body("Capteur en main :")
pdf.code_block([CMD + " essai"])
pdf.attendu(
    "« Capteur trouvé », « Connecté à … », puis toutes les 10 s une ligne avec roulis, tangage, "
    "lacet et le nombre de mesures (environ 100 de plus à chaque ligne)."
)
pdf.body("Tourner alors lentement le capteur d'un quart de tour, puis le reposer et attendre 5 s :")
pdf.attendu(
    "« >>> MOUVEMENT de la monture », puis « <<< fin du mouvement : … s, roulis 90°, tangage … » "
    "(ou tangage 90°, selon l'axe autour duquel on a tourné)."
)
pdf.body("Arrêter avec Ctrl + C, puis vérifier que le fichier de mesures existe :")
pdf.code_block(["ls -l logs/inclinometre_*"])
pdf.attendu("au moins un fichier logs/inclinometre_<date>_<heure>.csv, de taille supérieure à 0.")

# ─────────────────────────────────────────────────────────────────────────────
pdf.add_page()
pdf.h1("Étape 6 — Fixer le capteur et simuler un retournement")
pdf.h2("6.1 Où le fixer")
pdf.bold_bullet(
    "Sur l'axe d'ascension droite :",
    "une pièce qui tourne avec lui, boîtier de déclinaison ou barre de contrepoids. C'est là que "
    "le retournement donne le signal le plus net. Sur le tube, ça marche aussi, mais le signal "
    "mélange les deux axes.",
)
pdf.bullet(
    "Fixation ferme (collier, adhésif double face épais, velcro), qui ne puisse pas glisser."
)
pdf.bullet(
    "Vérifier que le capteur ne gêne aucun mouvement de la monture ni le passage des câbles."
)
pdf.bullet("Le bouton doit rester accessible ; prévoir l'accès à la prise USB-C pour la recharge.")
pdf.bullet("Photographier le montage (on aura besoin de savoir dans quel sens il est posé).")

pdf.h2("6.2 Simuler un retournement de jour")
pdf.body(f"Lancer « {CMD} essai » comme à l'étape 5, puis avec l'ASIAIR :")
pdf.bullet("GOTO sur un objet à l'Est du méridien, attendre la fin du mouvement ;")
pdf.bullet("GOTO sur un objet à l'Ouest du méridien : la monture change de côté du pied ;")
pdf.bullet(
    "noter l'heure de chaque GOTO, et ce qu'affiche le terminal à la fin de chaque mouvement."
)
pdf.attendu(
    "deux mouvements détectés. Le second doit montrer une grande variation de roulis ou de "
    "tangage (de l'ordre de 90° à 180°) : c'est la signature d'un retournement."
)
pdf.table(
    ["GOTO", "Heure", "Durée affichée", "Roulis", "Tangage"],
    [["Objet à l'Est", "", "", "", ""], ["Objet à l'Ouest (retournement)", "", "", "", ""]],
    col_widths=[56, 26, 30, 29, 29],
)
pdf.body("Arrêter avec Ctrl + C.")

pdf.h2("6.3 Mesurer l'autonomie")
pdf.body(
    "Capteur rechargé à fond, lancer l'acquisition en tâche de fond : elle continue même si on "
    "ferme le terminal, et on peut revenir au dashboard."
)
pdf.code_block([CMD + " demarrer"])
pdf.body("Pour voir où on en est, à tout moment (dans un terminal, après « cd ~/DriftApp ») :")
pdf.code_block([CMD + " etat"])
pdf.attendu(
    "« Acquisition EN COURS » et, dans les dernières lignes, des relevés récents. Quand le "
    "capteur s'est éteint, on y voit « Aucun capteur WitMotion visible » ou des reconnexions en "
    "échec : noter l'heure de la dernière mesure."
)
pdf.body("Pour arrêter :")
pdf.code_block([CMD + " arreter"])
pdf.attendu(
    "une autonomie supérieure à une nuit d'observation (au moins 14 h en hiver). Sinon : "
    "alimenter le capteur par une petite batterie USB fixée sur la monture."
)
pdf.body("Autonomie mesurée : ............ h")

# ─────────────────────────────────────────────────────────────────────────────
pdf.add_page()
pdf.h1("Étape 7 — Une nuit d'enregistrement")
pdf.body(
    "Choisir une session dont l'objet passe au méridien haut dans le ciel, comme MWP 1 le 16/10. "
    f"Avant la session, capteur chargé et fixé, lancer « {CMD} demarrer » (étape 6.3), vérifier "
    "avec « etat », puis revenir au dashboard (Alt + Tab). L'acquisition tourne indépendamment "
    "de DriftApp."
)
pdf.body(
    "Pendant le passage au méridien, procéder comme le 16/10 si nécessaire : arrêter le suivi "
    "DriftApp avant le passage pour éviter que la coupole bascule trop tôt, puis le relancer une "
    "fois la monture retournée."
)
pdf.body("À noter pendant la nuit :")
pdf.table(
    ["Information", "Valeur"],
    [
        ["Objet", ""],
        ["Heure du passage au méridien (dashboard DriftApp)", ""],
        ["Heure du retournement de la monture (ASIAIR, ou journal ASIAIR)", ""],
        ["Durée des poses", ""],
        ["Heure d'arrêt et de reprise du suivi DriftApp (si arrêté)", ""],
        ["Remarque (Shelly injoignable, capteur déconnecté…)", ""],
    ],
    col_widths=[110, 60],
)
pdf.body(f"Le lendemain matin : « {CMD} arreter ».")

pdf.h1("Étape 8 — Ce qu'il faut m'envoyer")
pdf.body("Dans le dossier DriftApp/logs du Pi (comme pour les autres logs) :")
pdf.bullet("les fichiers inclinometre_*.csv de la nuit et inclinometre_console.txt ;")
pdf.bullet("les logs motor_service de la nuit (motor_service_*.log).")
pdf.bullet("le tableau de l'étape 7, les relevés des étapes 4 et 6, et la photo du montage.")
pdf.info_box(
    "Avec ces données, je vérifie que le retournement se distingue de tout autre mouvement (GOTO, "
    "recentrage). Si c'est le cas, l'étape suivante sera dans DriftApp : garder la coupole immobile "
    "au passage au méridien, basculer au signal du capteur, avec un délai maximal de sécurité et un "
    "bouton « Monture retournée » en secours."
)

# ─────────────────────────────────────────────────────────────────────────────
pdf.add_page()
pdf.h1("Dépannage")
pdf.table(
    ["Symptôme", "Cause probable", "Que faire"],
    [
        [
            "« Aucun fichier ou dossier de ce nom » en tapant ./scripts/inclinometre.sh",
            "Terminal pas dans le bon dossier, ou mise à jour 6.21.12 pas installée",
            "Taper « cd ~/DriftApp » puis recommencer ; sinon installer la mise à jour",
        ],
        [
            "Le scan ne montre aucun « WT… »",
            "Capteur éteint ou batterie vide ; téléphone encore connecté ; trop loin",
            "Recharger, fermer l'application WitMotion, rapprocher le capteur du Pi",
        ],
        [
            "« Aucun capteur WitMotion visible ; nouvel essai dans 10 s »",
            "Idem",
            "Idem ; le programme réessaie seul, inutile de le relancer",
        ],
        [
            "« Connexion perdue » ou « Erreur Bluetooth » à répétition",
            "Liaison trop faible (RSSI)",
            "Noter les heures ; rapprocher le Pi ou ajouter un adaptateur Bluetooth USB",
        ],
        [
            "« Not authorized » ou « Permission denied »",
            "Session pas autorisée à utiliser le Bluetooth",
            "sudo usermod -aG bluetooth $USER, puis redémarrer le Pi",
        ],
        [
            "Erreur au premier lancement, avant le scan",
            "Pas d'accès internet (téléchargement de la bibliothèque)",
            "Vérifier la connexion du Pi, relancer",
        ],
        [
            "Plusieurs « WT… » au scan",
            "Un autre capteur WitMotion à portée",
            "Ajouter son adresse : ./scripts/inclinometre.sh essai --adresse AA:BB:CC:DD:EE:FF",
        ],
        [
            "Connecté, mais le nombre de mesures n'augmente pas",
            "Format de données différent sur ce modèle",
            "Prendre une photo de l'écran et me l'envoyer : le décodage sera à adapter",
        ],
    ],
    col_widths=[52, 53, 65],
)

pdf.output(OUT)
print(f"PDF écrit : {os.path.abspath(OUT)}")
