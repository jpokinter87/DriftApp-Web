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
