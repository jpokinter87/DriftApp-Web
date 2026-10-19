"""Les tests n'écrivent pas dans le vrai dossier logs/.

motor_service, ems22d_calibrated et les settings Django ouvrent leur fichier de
log dès l'import (et motor_service/Django purgent les logs de plus de 7 jours) :
sans DRIFTAPP_LOGS_DIR, chaque lancement de pytest ajoutait des fichiers dans
logs/ et pouvait y effacer les vrais logs de la machine.
"""

import importlib
import os
import sys
from pathlib import Path
from unittest.mock import MagicMock, patch


def test_conftest_redirige_les_logs():
    assert Path(os.environ["DRIFTAPP_LOGS_DIR"]).resolve() != (Path("logs")).resolve()


def test_motor_service_ecrit_dans_le_dossier_de_test():
    import services.motor_service as motor_service

    assert motor_service.LOGS_DIR == Path(os.environ["DRIFTAPP_LOGS_DIR"]) / "moteur"


def test_motor_service_range_ses_anciens_logs(tmp_path):
    """Au démarrage, motor_service range dans moteur/ ses logs restés à la
    racine (sinon plus jamais purgés) et y ouvre son log de démarrage.
    Sous-processus : ne pas recharger le module partagé par les autres tests."""
    import subprocess

    (tmp_path / "motor_service_20261001_120000.log").write_text("ancien")
    (tmp_path / "update_status.json").write_text("{}")
    projet = Path(__file__).resolve().parent.parent
    env = dict(os.environ, DRIFTAPP_LOGS_DIR=str(tmp_path))
    subprocess.run(
        [sys.executable, "-c", "import services.motor_service"],
        cwd=projet,
        env=env,
        check=True,
        capture_output=True,
    )

    moteur = tmp_path / "moteur"
    assert (moteur / "motor_service_20261001_120000.log").read_text() == "ancien"
    assert len(list(moteur.glob("motor_service_*.log"))) == 2  # + log de démarrage
    assert not list(tmp_path.glob("motor_service_*.log"))
    assert (tmp_path / "update_status.json").exists()


def test_ems22d_ecrit_dans_le_dossier_de_test():
    # Le démon importe lgpio au chargement (cf. test_ems22d_force_calibration).
    with patch.dict(sys.modules, {"lgpio": MagicMock()}):
        sys.modules.pop("ems22d_calibrated", None)
        module = importlib.import_module("ems22d_calibrated")
        sys.modules.pop("ems22d_calibrated", None)
    assert module.LOG_DIR == Path(os.environ["DRIFTAPP_LOGS_DIR"])


def test_django_ecrit_dans_le_dossier_de_test():
    os.environ.setdefault("DJANGO_SETTINGS_MODULE", "driftapp_web.settings")
    sys.path.insert(0, str(Path(__file__).parent.parent / "web"))
    import django

    django.setup()
    from django.conf import settings

    assert settings.LOGS_DIR == Path(os.environ["DRIFTAPP_LOGS_DIR"])
