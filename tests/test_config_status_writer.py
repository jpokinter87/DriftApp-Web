import json

from core.config.config_resilience import ConfigReport
from core.config.config_status_writer import write_config_status


def test_write_config_status_serialise_le_rapport(tmp_path):
    out = tmp_path / "config_status.json"
    report = ConfigReport(status="migrated", added=["x"], removed=[], message="m")
    write_config_status(report, path=out)
    data = json.loads(out.read_text())
    assert data["status"] == "migrated"
    assert data["added"] == ["x"]
    assert data["message"] == "m"


def test_write_config_status_jamais_levee(tmp_path):
    # chemin impossible → ne doit pas lever (le filet ne doit pas casser le boot)
    bad = tmp_path / "inexistant" / "sub" / "config_status.json"
    report = ConfigReport(status="unchanged")
    write_config_status(report, path=bad)  # pas d'exception


def test_fichier_d_un_autre_service_n_est_pas_une_erreur(tmp_path, caplog):
    """/dev/shm a le sticky bit : Django (slenk) ne peut pas remplacer le
    rapport publié par motor_service (root) — EPERM attendu, pas un échec."""
    import logging
    from unittest.mock import patch

    out = tmp_path / "config_status.json"
    with patch("core.config.config_status_writer.os.replace",
               side_effect=PermissionError(1, "Operation not permitted")), \
         caplog.at_level(logging.INFO, logger="core.config.config_status_writer"):
        write_config_status(ConfigReport(status="unchanged"), path=out)

    assert not [r for r in caplog.records if r.levelno >= logging.WARNING]
    assert not list(tmp_path.glob("*.tmp"))
