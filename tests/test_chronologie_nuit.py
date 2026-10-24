"""Tests de scripts/diagnostics/chronologie_nuit.py (analyse d'une nuit terrain)."""

from __future__ import annotations

import importlib.util
import sys
import zipfile
from pathlib import Path

# Le script vit dans scripts/diagnostics/ (pas un package) → import par chemin.
_SPEC = importlib.util.spec_from_file_location(
    "chronologie_nuit",
    Path(__file__).resolve().parents[1] / "scripts" / "diagnostics" / "chronologie_nuit.py",
)
chronologie_nuit = importlib.util.module_from_spec(_SPEC)
sys.modules["chronologie_nuit"] = chronologie_nuit  # requis par @dataclass
_SPEC.loader.exec_module(chronologie_nuit)

MOTEUR = """\
2026-10-23 20:10:00,001 - __main__ - INFO - heartbeat | uptime=10 tracking=False object=none
2026-10-23 21:00:00,000 - services.command_handlers - INFO - Démarrage suivi de: M 27 (skip_goto=False)
2026-10-23 21:00:30,000 - core.tracking.tracker - INFO - correction | delta=+0.4 az=120 alt=40
2026-10-23 21:01:00,000 - core.tracking.tracker - INFO - correction | delta=-1.2 az=121 alt=40
2026-10-23 21:28:00,000 - core.tracking.tracker - WARNING - asiair_pier_unreachable | err=timeout
2026-10-23 21:28:05,000 - core.tracking.tracker - WARNING - asiair_pier_unreachable | err=timeout
2026-10-23 21:28:09,000 - core.tracking.tracker - WARNING - asiair_pier_unreachable | err=timeout
2026-10-24 02:00:00,000 - services.command_handlers - ERROR - Erreur GOTO: boom
Traceback (most recent call last):
  File "x.py", line 1, in <module>
ValueError: boom
═══════════════════════
"""

CIMIER = """\
2026-10-23 20:30:00,000 [DEBUG] __main__: cimier_event=poll_status open_switch=false
2026-10-23 20:31:00,000 [INFO] __main__: cimier_event=cycle_start action=open id=abc
2026-10-24 06:45:00,000 [INFO] __main__: cimier_event=cycle_start action=close id=def
"""

DJANGO = "WARNING 2026-10-23 22:00:00,000 views Requête lente\n"
ENCODEUR = "[ems22d] 2026-10-23 20:05:00,000 INFO 🔧 Démarrage du démon EMS22A\n"
MAJ = "[2026-10-23 19:00:00] === Mise à jour DriftApp Web ===\n[2026-10-23 19:00:05] Pull OK : 1acd410 → 62bf855\n"
ASIAIR = "2026-10-23 21:27:50,000  pierside East → West\n"
JOURNAL = '{"ts": "2026-10-23T23:00:00", "event": "rain", "state": "wet", "armed": true}\n'
# Nuit précédente : doit être écartée par le découpage midi → midi.
VEILLE = "2026-10-23 11:59:00,000 - __main__ - INFO - Motor Service démarré - En attente\n"


def _zip(tmp_path: Path, rangee: bool) -> Path:
    chemin = tmp_path / "logs.zip"
    fichiers = {
        "moteur/motor_service_20261023_200000.log": MOTEUR,
        "moteur/motor_service_20261023_080000.log": VEILLE,
        "cimier/cimier_service.log.1": CIMIER,
        "web/django_20261023_200000.log": DJANGO,
        "encodeur/ems22d_20261023_200500.log": ENCODEUR,
        "update.log": MAJ,
        "asiair/asiair_monitor.log": ASIAIR,
        "asiair/2026-10-23.jsonl": '{"t": 1, "msg": "brut, ignoré"}\n',
        "nights/2026-10-23.jsonl": JOURNAL,
        "__MACOSX/logs/._update.log": "ignoré",
    }
    with zipfile.ZipFile(chemin, "w") as z:
        for nom, contenu in fichiers.items():
            if not rangee and not nom.startswith(("__MACOSX", "asiair/", "nights/")):
                nom = nom.split("/")[-1]
            z.writestr(f"logs/{nom}", contenu)
    return chemin


def _texte(tmp_path: Path, rangee: bool = True, **options) -> str:
    evts = chronologie_nuit.charger(_zip(tmp_path, rangee))
    return chronologie_nuit.rapport(evts, **options)


def test_toutes_les_sources_lues_quelle_que_soit_la_structure(tmp_path):
    for rangee in (True, False):
        texte = _texte(tmp_path, rangee=rangee)
        for attendu in (
            "[moteur] INFO  Démarrage suivi de: M 27",
            "[cimier] INFO  cimier_event=cycle_start action=open",
            "[web] WARNING Requête lente",
            "[encodeur] INFO  🔧 Démarrage du démon EMS22A",
            "[maj] INFO  === Mise à jour DriftApp Web ===",
            "[asiair] INFO  pierside East → West",
            "[nuit] INFO  rain state=wet armed=True",
        ):
            assert attendu in texte, (rangee, attendu)
        assert "brut, ignoré" not in texte


def test_nuit_midi_a_midi_par_defaut_la_derniere_avec_suivi(tmp_path):
    texte = _texte(tmp_path)
    assert "Nuit du 2026-10-23" in texte
    assert "Nuits dans les logs : 2026-10-22 (1), 2026-10-23 (" in texte
    assert "06:45:00 [cimier]" in texte  # le matin appartient à la nuit de la veille
    assert "11:59:00" not in texte  # la matinée du 23 appartient à la nuit du 22


def test_bruit_filtre_sauf_avec_tout(tmp_path):
    texte = _texte(tmp_path)
    assert "heartbeat" not in texte
    assert "poll_status" not in texte
    assert "correction | delta" not in texte
    assert "═══" not in texte
    assert "heartbeat" in _texte(tmp_path, tout=True)


def test_lignes_identiques_regroupees(tmp_path):
    texte = _texte(tmp_path)
    assert texte.count("asiair_pier_unreachable") == 2  # une dans la chronologie, une en synthèse
    assert (
        "21:28:00 [moteur] WARNING asiair_pier_unreachable | err=timeout  (×3 jusqu'à 21:28:09)"
        in texte
    )


def test_traceback_rattachee_a_son_erreur(tmp_path):
    texte = _texte(tmp_path)
    assert "Erreur GOTO: boom\n      Traceback" in texte
    assert "ValueError: boom" in texte


def test_synthese(tmp_path):
    texte = _texte(tmp_path)
    assert "Objets suivis : M 27" in texte
    assert "Corrections de suivi : 2 (plus grand écart 1.2°)" in texte
    assert "Mises à jour : 19:00:05 (Pull OK : 1acd410 → 62bf855)" in texte
    assert "3 × WARNING [moteur] asiair_pier_unreachable | err=timeout" in texte


def test_fenetre_horaire_traverse_minuit(tmp_path):
    texte = _texte(tmp_path, de="23:30", a="03:00")
    assert "02:00:00 [moteur]" in texte
    assert "21:00:00" not in texte
    assert "06:45:00" not in texte


def test_autre_nuit(tmp_path):
    texte = _texte(tmp_path, nuit="2026-10-22")
    assert "Nuit du 2026-10-22" in texte
    assert "11:59:00 [moteur] INFO  Motor Service démarré" in texte
