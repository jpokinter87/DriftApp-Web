#!/usr/bin/env python3
"""Génère le PDF du protocole de déploiement terrain v6.7.0 (Serge).

Source : docs/deploiement_v6.7.0_terrain.md
Sortie : docs/deploiement_v6.7.0_terrain.pdf
"""

import os
import sys

sys.path.insert(0, "/home/jp/.claude/skills/pdf-report/scripts")
from pdf_report import Report  # noqa: E402

FONT_DIR = "/usr/share/fonts/truetype/dejavu/"


class DeployReport(Report):
    """Report + rendu de blocs de commandes en monospace."""

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.add_font("Mono", "", os.path.join(FONT_DIR, "DejaVuSansMono.ttf"))
        self.add_font("Mono", "B", os.path.join(FONT_DIR, "DejaVuSansMono-Bold.ttf"))

    def code(self, lines):
        """Bloc de commandes shell, fond gris, police monospace 8pt."""
        self.ln(1)
        self.set_font("Mono", "", 7.5)
        self.set_fill_color(244, 244, 244)
        self.set_draw_color(200, 200, 200)
        self.set_text_color(20, 20, 20)
        w = self.w - self.l_margin - self.r_margin
        # bordure haute
        self.set_line_width(0.2)
        for ln in lines:
            # wrap manuel léger : multi_cell gère la coupe
            self.set_x(self.l_margin)
            self.multi_cell(w, 4.6, "  " + ln, border=0, fill=True)
        self.ln(2)
        self.set_text_color(30, 30, 30)


def main():
    pdf = DeployReport(
        title="Déploiement DriftApp v6.7.0",
        subtitle="Protocole terrain — Serge",
        header_text="Déploiement DriftApp v6.7.0 — Protocole terrain (Serge)",
    )
    pdf.title_page(
        summary=(
            "Cimier « tout-Shelly » (V3) : le Pico W est supprimé. Fins de course lues par "
            "le Shelly Uni+ (.84), moteur piloté par Shelly MOT (.85) + UPDN (.86), alim par "
            "Shelly 24V (.83). Déploiement en 3 phases : la Phase A (mise à jour logicielle) "
            "est sans risque, cimier OFF. Les Phases B et C ne se font que si le matériel "
            "Shelly V3 est installé et alimenté."
        ),
        extra_lines=[
            "Observatoire Ubik",
            "Version cible : 6.7.0 (commit e1e7edf)",
            "Protocole généré le 2026-06-10",
        ],
    )

    # ── Tableau IP ────────────────────────────────────────────
    pdf.add_page()
    pdf.h1("Valeurs terrain (réservations DHCP)")
    pdf.table(
        ["Shelly", "IP", "Rôle"],
        [
            ["SHELLY-1-24V", "192.168.1.83", "Alimentation module cimier (power_switch)"],
            ["SHELLY-UNI+", "192.168.1.84", "Lecture microswitches HAUT/BAS (switch_reader)"],
            ["SHELLY-1-MOT", "192.168.1.85", "Marche/arrêt moteur (motor_shelly.host_motor)"],
            ["SHELLY-1-UPDN", "192.168.1.86", "Sens UP/DN via DPDT (motor_shelly.host_dir)"],
        ],
        col_widths=[32, 33, 105],
    )

    # ── Avant de commencer ────────────────────────────────────
    pdf.h1("Avant de commencer — 3 infos à renvoyer à JP")
    pdf.body("Avant la Phase A :")
    pdf.bullet("1. Le hostname/IP du Pi utilisé en SSH (slenk@???).")
    pdf.bullet(
        "2. Le matériel cimier V3 est-il en place sur site ? (les 4 Shelly ci-dessus + le "
        "contrôleur d'impulsions branché au DM556T). Oui / Non / Partiel."
    )
    pdf.bullet("3. Les 4 IP Shelly sont-elles bien celles du tableau ? (corrige si DHCP a changé)")

    # ── Phase 0 ───────────────────────────────────────────────
    pdf.h1("PHASE 0 — État des lieux (à recoller tel quel)")
    pdf.code([
        "ssh slenk@<TON-PI>",
        "cd ~/DriftApp",
        'echo "--- version courante ---"; grep \'^version\' pyproject.toml',
        'echo "--- branche + propreté ---"; git status -sb | head -20',
        'echo "--- services ---"; sudo systemctl is-active ems22d motor_service cimier_service driftapp_web',
        'echo "--- unit cimier présente ? ---"; systemctl list-unit-files | grep cimier_service || echo "PAS de cimier_service"',
    ])
    pdf.bold_bullet(
        "Attendu / à renvoyer :",
        "la version affichée, l'état git (propre ou fichiers modifiés listés), les 4 "
        "active/inactive, et si cimier_service existe.",
    )
    pdf.warning_box(
        "STOP — recoller ce bloc à JP. Selon la version et l'état git, JP indique quelle "
        "variante de Phase A suivre (la MAJ OTA a un déblocage one-shot connu si le Pi n'a "
        "jamais reçu la 6.6.2)."
    )

    # ── Phase A ───────────────────────────────────────────────
    pdf.add_page()
    pdf.h1("PHASE A — Mise à jour logicielle 6.7.0 (cimier OFF)")

    pdf.h2("A1. Sauvegarde de la config actuelle (indispensable — réutilisée en Phase B)")
    pdf.code([
        "cd ~/DriftApp",
        "cp data/config.json ~/config_AVANT_6.7.0_$(date +%F).json",
        'echo "Backup OK :"; ls -la ~/config_AVANT_6.7.0_*.json',
    ])
    pdf.bold_bullet("Attendu :", "le fichier backup listé.")

    pdf.h2("A2. Récupération du code 6.7.0 (JP confirme la voie après la Phase 0)")
    pdf.bold_bullet(
        "Voie 1 (recommandée si l'OTA marche) :",
        "bouton « Mettre à jour » dans l'interface web. Il gère le diff de config.json et "
        "demande quoi garder. → suivre l'assistant, garder le local pour site/moteur/encodeur.",
    )
    pdf.bold_bullet("Voie 2 (manuelle, si l'OTA refuse / Pi pas encore en 6.6.2) :", "")
    pdf.code([
        "cd ~/DriftApp",
        "git checkout -- scripts/update_driftapp.sh   # déblocage one-shot OTA (bug 6.6.2)",
        "git fetch origin",
        'git stash push -m "config-terrain-avant-6.7.0"   # écarte les modifs locales le temps du pull',
        "git pull --ff-only origin main",
        "uv sync --frozen",
    ])
    pdf.bold_bullet(
        "Attendu :",
        "Updating … 6.7.0, uv sync sans erreur. Si git pull refuse encore (« local "
        "changes »), s'arrêter et recoller le message à JP.",
    )

    pdf.h2("A3. Vérifier la version + redémarrer les services")
    pdf.code([
        "grep '^version' pyproject.toml          # doit afficher 6.7.0",
        "sudo systemctl restart ems22d motor_service driftapp_web",
        "sudo systemctl is-active ems22d motor_service driftapp_web",
    ])
    pdf.bold_bullet("Attendu :", 'version = "6.7.0", trois active.')

    pdf.h2("A4. Vérifier que le cœur fonctionne toujours (cimier encore OFF)")
    pdf.code([
        "cat /dev/shm/motor_status.json | python3 -m json.tool | head -15",
        "curl -s http://localhost:8000/api/health/ | head",
    ])
    pdf.bold_bullet(
        "Attendu :",
        "motor_status.json frais (status idle/tracking), health healthy. Dans le "
        "navigateur, le pied de page doit afficher 6.7.0.",
    )
    pdf.success_box(
        "Fin de Phase A. La 6.7.0 tourne, le cimier est inactif, rien d'autre n'a changé. "
        "Une session d'astrophoto normale est possible sans risque. Recoller A3+A4 à JP. "
        "Les Phases B/C se font quand le matériel V3 est prêt."
    )

    # ── Phase B ───────────────────────────────────────────────
    pdf.add_page()
    pdf.h1("PHASE B — Activation du cimier V3")
    pdf.body("(seulement si le matériel Shelly V3 est installé et alimenté)")

    pdf.h2("B1. Vérifier d'abord que les 4 Shelly répondent (avant de toucher la config)")
    pdf.code([
        'for ip in 83 84 85 86; do echo -n "192.168.1.$ip : "; \\',
        "  curl -s -m 3 http://192.168.1.$ip/status >/dev/null && echo OK || echo INJOIGNABLE; done",
        'echo "--- Uni+ entrées brutes ---"',
        "curl -s http://192.168.1.84/rpc/Input.GetStatus?id=1   # HAUT",
        "curl -s http://192.168.1.84/rpc/Input.GetStatus?id=0   # BAS",
    ])
    pdf.bold_bullet(
        "Attendu :",
        'les 4 OK, et l\'Uni+ renvoie du JSON {"id":…, "state":true/false}. Un INJOIGNABLE '
        "→ stop, régler le réseau/Shelly avant d'aller plus loin.",
    )

    pdf.h2("B2. Éditer la section cimier de data/config.json")
    pdf.code(["nano data/config.json"])
    pdf.body(
        "Remplacer uniquement le bloc \"cimier\": { … } par celui-ci (laisser intactes les "
        "sections site, moteur, encodeur, motor_driver) :"
    )
    pdf.code([
        '"cimier": {',
        '  "enabled": true,',
        '  "cycle_timeout_s": 90.0,',
        '  "post_off_quiet_s": 10.0,',
        '  "shelly_settle_s": 2.0,',
        '  "verbose_logging": true,',
        '  "switch_reader": {',
        '    "type": "shelly_uni",',
        '    "host": "192.168.1.84",',
        '    "api": "rpc",',
        '    "open_input_id": 1,',
        '    "closed_input_id": 0,',
        '    "invert": true,',
        '    "timeout_s": 3.0',
        '  },',
        '  "power_switch": { "type": "shelly_gen1", "host": "192.168.1.83", "switch_id": 0 },',
        '  "weather_provider": { "type": "noop" },',
        '  "automation": { "mode": "manual" },',
        '  "motor_shelly": {',
        '    "host_motor": "192.168.1.85",',
        '    "host_dir": "192.168.1.86",',
        '    "relay_motor": 0,',
        '    "relay_dir": 0,',
        '    "open_dir_state": true,',
        '    "motor_on_relay_state": false,',
        '    "api": "legacy",',
        '    "timer_safety_sec": 90.0',
        '  }',
        '}',
    ])
    pdf.warning_box(
        "Note : automation.mode = \"manual\" et verbose_logging = true exprès pour la "
        "première validation supervisée de l'install — pas d'ouverture/fermeture "
        "automatique le temps de vérifier, et logs détaillés. On repassera en full après (étape C5)."
    )

    pdf.h2("B3. Vérifier que le JSON est valide AVANT de redémarrer")
    pdf.code([
        "python3 -m json.tool data/config.json >/dev/null \\",
        '  && echo "JSON OK" || echo "JSON CASSE — ne pas redemarrer"',
    ])
    pdf.bold_bullet(
        "Attendu :",
        "JSON OK. Si CASSE → rouvrir nano, corriger (ou restaurer le backup A1 et recommencer).",
    )

    pdf.h2("B4. Redémarrer le cimier et vérifier qu'il démarre proprement")
    pdf.code([
        "sudo systemctl restart cimier_service",
        "sudo systemctl is-active cimier_service",
        "sudo journalctl -u cimier_service -n 20 --no-pager",
        "cat /dev/shm/cimier_status.json | python3 -m json.tool",
    ])
    pdf.bold_bullet(
        "Attendu :",
        "active, une ligne cimier_event=started switch_reader=192.168.1.84 …, et "
        "cimier_status.json présent avec un state non nul. Pas de Traceback.",
    )
    pdf.warning_box(
        "STOP — recoller B1, B4 à JP. On ne passe à la Phase C qu'une fois le service "
        "active et joignable."
    )

    # ── Phase C ───────────────────────────────────────────────
    pdf.add_page()
    pdf.h1("PHASE C — Validation des 3 conventions au banc")
    pdf.body("(le cimier bouge — voir consigne de sécurité ci-dessous)")
    pdf.warning_box(
        "Sécurité : pendant cette phase le mécanisme peut bouger. Garder le bouton STOP "
        "(UI ou coupure 24V) à portée. À faire de jour, à vue du cimier."
    )

    pdf.h2("C1. Convention des butées (switch_reader.invert) — SANS moteur")
    pdf.body(
        "Actionner à la main le microswitch HAUT, le maintenir, et lire :"
    )
    pdf.code([
        "curl -s http://192.168.1.84/rpc/Input.GetStatus?id=1; echo",
        "cat /dev/shm/cimier_status.json | python3 -m json.tool | grep -E \"open_switch|closed_switch\"",
    ])
    pdf.body(
        "Puis relâcher, et faire pareil avec le microswitch BAS (id=0, regarder closed_switch)."
    )
    pdf.bold_bullet(
        "Attendu (convention V3) :",
        "appui sur HAUT → open_switch passe à true ; sur BAS → closed_switch à true.",
    )
    pdf.bullet("OK si ça correspond → invert est bon.")
    pdf.bullet(
        "Si c'est inversé → repasser \"invert\": false (B2), json.tool + restart cimier_service, refaire C1."
    )

    pdf.h2("C2. Convention du sens (open_dir_state)")
    pdf.body(
        "Lancer une OUVERTURE depuis le dashboard (« Ouvrir cimier »), prêt à STOPPER."
    )
    pdf.bold_bullet("Attendu :", "le cimier part dans le sens de l'ouverture.")
    pdf.bullet(
        "S'il part en fermeture → STOP, inverser \"open_dir_state\": false (B2), restart, refaire C2."
    )

    pdf.h2("C3. Convention marche/arrêt moteur (motor_on_relay_state)")
    pdf.body("Pendant C2, observer :")
    pdf.bold_bullet(
        "Attendu :",
        "le moteur tourne pendant le cycle puis s'arrête à la butée (ou au STOP).",
    )
    pdf.bullet(
        "\"motor_on_relay_state\": false est la convention validée terrain (17-18/06) : le moteur "
        "doit tourner pendant le cycle. S'il reste à l'arrêt ou tourne en continu → essayer "
        "\"motor_on_relay_state\": true (B2), restart, refaire."
    )

    pdf.h2("C4. Cycle complet supervisé")
    pdf.body(
        "Une fois C1–C3 OK : lancer une ouverture puis une fermeture complètes, à vue."
    )
    pdf.code(["sudo journalctl -u cimier_service -f"])
    pdf.bold_bullet(
        "Attendu :",
        "dans les logs, la séquence power_on → set_direction → motor_on → switch_transition "
        "(open_switch true) → motor_off → power_off, et idem en fermeture (closed_switch true). "
        "Pas de both_switches, pas de timeout.",
    )
    pdf.warning_box(
        "STOP — recoller C1 à C4 à JP (retours cimier_status.json + observation physique). "
        "JP confirme les conventions finales."
    )

    pdf.h2("C5. Bascule en automatique (après validation)")
    pdf.body(
        "Quand tout est validé, repasser automation.mode en \"full\" (et éventuellement "
        "verbose_logging en false) dans data/config.json, json.tool + restart cimier_service."
    )

    # ── En cas de pépin ───────────────────────────────────────
    pdf.add_page()
    pdf.h1("En cas de pépin")
    pdf.bullet(
        "cimier_service redémarre en boucle / Traceback → recoller "
        "journalctl -u cimier_service -n 40."
    )
    pdf.bullet(
        "Un Shelly injoignable en cours de cycle → log set_direction_failed / "
        "precheck_unreachable (rappel : Shelly Gen 1 capricieux en WiFi déjà vus le 30-31/05 "
        "— hard reset / réappairage si besoin)."
    )
    pdf.bullet("Tout doute → STOP, couper le 24V (.83), recoller les logs.")

    pdf.ln(6)
    pdf.body(
        "Protocole généré le 2026-06-10 pour la v6.7.0 (commit e1e7edf). Les voies A2 "
        "(OTA vs manuel) seront tranchées après le retour de la Phase 0 (version réelle du "
        "Pi + état du matériel V3)."
    )

    out = "/home/jp/PythonProject/Dome_web_v4_6/docs/deploiement_v6.7.0_terrain.pdf"
    pdf.output(out)
    print(f"PDF généré : {out}")


if __name__ == "__main__":
    main()
