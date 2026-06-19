"""Tests des vues de l'app configuration (GET schema+values, POST save)."""

import json
import os
import sys
from pathlib import Path

import pytest

PROJECT_ROOT = Path(__file__).parent.parent.resolve()
sys.path.insert(0, str(PROJECT_ROOT))
sys.path.insert(0, str(PROJECT_ROOT / "web"))
os.environ.setdefault("DJANGO_SETTINGS_MODULE", "driftapp_web.settings")
os.environ.setdefault("DRIFTAPP_DEBUG", "1")

import django  # noqa: E402

django.setup()

from rest_framework.test import APIClient  # noqa: E402

from core.config import config_resilience  # noqa: E402


@pytest.fixture
def api_client():
    return APIClient()


@pytest.fixture
def tmp_config(tmp_path, monkeypatch):
    """Redirige les chemins config du module vue vers des fichiers temporaires."""
    cfg = tmp_path / "config.json"
    tmpl = tmp_path / "config.template.json"
    backup = tmp_path / ".config.lastgood.json"
    template = {
        "_comment": "gabarit",
        "site": {"_comment": "le site", "latitude": 44.0, "nom": "x"},
        "moteur": {"microsteps": 4},
        "simulation": False,
    }
    config_resilience._atomic_write_json(tmpl, template)
    config_resilience._atomic_write_json(
        cfg,
        {
            "site": {"latitude": 45.5, "nom": "Ubik"},
            "moteur": {"microsteps": 4},
            "simulation": False,
        },
    )
    from configuration import views as cfg_views

    monkeypatch.setattr(cfg_views, "CONFIG_PATH", cfg)
    monkeypatch.setattr(cfg_views, "TEMPLATE_PATH", tmpl)
    monkeypatch.setattr(cfg_views, "BACKUP_PATH", backup)
    return cfg, tmpl, backup


class TestConfigurationGet:
    def test_get_renvoie_schema_et_valeurs(self, api_client, tmp_config):
        resp = api_client.get("/api/configuration/")
        assert resp.status_code == 200
        body = resp.json()
        assert "schema" in body and "values" in body
        section_keys = {s["key"] for s in body["schema"]}
        assert {"site", "moteur", "_general"} <= section_keys
        assert body["values"]["site"]["nom"] == "Ubik"


class TestConfigurationPost:
    def test_post_valide_persiste(self, api_client, tmp_config):
        cfg, _tmpl, _backup = tmp_config
        payload = {
            "site": {"latitude": 46.2, "nom": "Nouveau"},
            "moteur": {"microsteps": 8},
            "simulation": True,
        }
        resp = api_client.post("/api/configuration/", payload, format="json")
        assert resp.status_code == 200
        assert resp.json()["status"] == "saved"
        assert resp.json()["restart_required"] is True
        written = json.loads(cfg.read_text())
        assert written["site"]["latitude"] == 46.2
        assert written["site"]["nom"] == "Nouveau"
        assert written["simulation"] is True
        # _comment du template réinjecté
        assert written["site"]["_comment"] == "le site"

    def test_post_type_invalide_400_et_inchange(self, api_client, tmp_config):
        cfg, _tmpl, _backup = tmp_config
        avant = cfg.read_text()
        resp = api_client.post("/api/configuration/", {"site": {"latitude": "haut"}}, format="json")
        assert resp.status_code == 400
        assert resp.json()["path"] == "site.latitude"
        assert cfg.read_text() == avant  # config.json intact
