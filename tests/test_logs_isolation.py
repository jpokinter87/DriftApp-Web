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


def _importer_ems22d():
    # Le démon importe lgpio au chargement (cf. test_ems22d_force_calibration).
    with patch.dict(sys.modules, {"lgpio": MagicMock()}):
        sys.modules.pop("ems22d_calibrated", None)
        module = importlib.import_module("ems22d_calibrated")
        sys.modules.pop("ems22d_calibrated", None)
    return module


def test_ems22d_ecrit_dans_le_dossier_de_test():
    module = _importer_ems22d()
    assert module.LOG_DIR == Path(os.environ["DRIFTAPP_LOGS_DIR"]) / "encodeur"


def test_ems22d_range_ses_anciens_logs(tmp_path, monkeypatch):
    """Au démarrage, le démon range dans encodeur/ ses logs restés à la racine
    avant sa purge (10 derniers), qui sinon ne les verrait plus."""
    monkeypatch.setenv("DRIFTAPP_LOGS_DIR", str(tmp_path))
    (tmp_path / "ems22d_20261001_120000.log").write_text("ancien")
    (tmp_path / "update.log").write_text("maj")

    module = _importer_ems22d()

    encodeur = tmp_path / "encodeur"
    assert (encodeur / "ems22d_20261001_120000.log").read_text() == "ancien"
    assert module.LOG_FILE.parent == encodeur
    assert not list(tmp_path.glob("ems22d_*.log"))
    assert (tmp_path / "update.log").exists()


def test_django_ecrit_dans_le_dossier_de_test():
    os.environ.setdefault("DJANGO_SETTINGS_MODULE", "driftapp_web.settings")
    sys.path.insert(0, str(Path(__file__).parent.parent / "web"))
    import django

    django.setup()
    from django.conf import settings

    assert settings.LOGS_DIR == Path(os.environ["DRIFTAPP_LOGS_DIR"]) / "web"


def test_django_range_ses_anciens_logs(tmp_path):
    """Au chargement des settings, les logs Django restés à la racine sont
    rangés dans web/ avant la purge à 7 jours ; les fichiers de mise à jour,
    lus par web/health/views.py, restent à la racine (spec, décision 1)."""
    import subprocess

    (tmp_path / "django_20261001_120000.log").write_text("ancien")
    for nom in ("update.log", "update_status.json", "restart_status.json"):
        (tmp_path / nom).write_text("{}")
    projet = Path(__file__).resolve().parent.parent
    env = dict(os.environ, DRIFTAPP_LOGS_DIR=str(tmp_path))
    sortie = subprocess.run(
        [sys.executable, "-c", "import driftapp_web.settings as s; print(s.DJANGO_LOG_FILE)"],
        cwd=projet / "web",
        env=env,
        check=True,
        capture_output=True,
        text=True,
    )

    web = tmp_path / "web"
    assert (web / "django_20261001_120000.log").read_text() == "ancien"
    assert Path(sortie.stdout.strip()).parent == web
    assert not list(tmp_path.glob("django_*.log"))
    for nom in ("update.log", "update_status.json", "restart_status.json"):
        assert (tmp_path / nom).exists(), nom
