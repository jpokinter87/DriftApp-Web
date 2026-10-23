"""Les rapports des scripts de diagnostic vont dans logs/diagnostics/ (6.22.0).

Spec : docs/superpowers/specs/2026-10-19-logs-sous-repertoires.md
"""

import importlib.util
import sys
from pathlib import Path

import pytest

_DIAG = Path(__file__).resolve().parent.parent / "scripts" / "diagnostics"


def _charger(nom_fichier, nom_module):
    spec = importlib.util.spec_from_file_location(nom_module, _DIAG / nom_fichier)
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module  # requis par les dataclasses du script
    spec.loader.exec_module(module)
    return module


@pytest.fixture
def racine(tmp_path, monkeypatch):
    monkeypatch.setenv("DRIFTAPP_LOGS_DIR", str(tmp_path))
    return tmp_path


def test_calibration_vitesse_encodeur(racine):
    """Le rapport n'était pas écrit si logs/ n'existait pas (pas de mkdir)."""
    calib = _charger("calibration_vitesse_encodeur.py", "diag_calib_encodeur")
    mesure = {
        "delay_us": 124,
        "vitesse_mesuree": 90.2,
        "vitesse_theorique": 89.7,
        "rendement": 1.006,
        "tenu": True,
    }

    calib._rapport([mesure], None, 5394.0)

    assert len(list((racine / "diagnostics").glob("calibration_vitesse_*.json"))) == 1


@pytest.mark.parametrize(
    "fichier, prefixe",
    [
        ("diagnostic_moteur_complet.py", "diagnostic_moteur_"),
    ],
)
def test_rapports_fixes_a_l_import(racine, fichier, prefixe):
    module = _charger(fichier, "diag_" + fichier[:-3])

    assert module.RAPPORT_FILE.parent == racine / "diagnostics"
    assert module.RAPPORT_FILE.name.startswith(prefixe)


def test_rapport_de_detection_materielle(racine):
    from core.hardware.hardware_detector import HardwareDetector

    _, infos = HardwareDetector.detect_hardware()
    assert HardwareDetector.save_detection_report(infos) is True
    assert (racine / "diagnostics" / "hardware_detection.txt").exists()
