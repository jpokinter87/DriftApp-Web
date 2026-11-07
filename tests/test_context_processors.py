"""Tests des context processors Django (version, coordonnées du site pour le mode nuit)."""

import os
import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).parent.parent.resolve()
sys.path.insert(0, str(PROJECT_ROOT))
sys.path.insert(0, str(PROJECT_ROOT / "web"))
os.environ.setdefault("DJANGO_SETTINGS_MODULE", "driftapp_web.settings")
os.environ.setdefault("DRIFTAPP_DEBUG", "1")

import django

django.setup()

from django.test import Client

from core.config.config import SITE_LATITUDE, SITE_LONGITUDE
from driftapp_web.context_processors import site_coords


def test_site_coords_viennent_de_la_config():
    assert site_coords(None) == {"SITE_LAT": SITE_LATITUDE, "SITE_LON": SITE_LONGITUDE}


def test_base_html_porte_les_coordonnees_du_site():
    html = Client().get("/").content.decode()
    assert f'data-site-lat="{SITE_LATITUDE}"' in html
    assert f'data-site-lon="{SITE_LONGITUDE}"' in html


# --- Date de la dernière mise à jour du logiciel (pied de page du dashboard) ---

import json

from driftapp_web import context_processors


def _status(tmp_path, monkeypatch, payload):
    f = tmp_path / "update_status.json"
    if payload is not None:
        f.write_text(json.dumps(payload))
    monkeypatch.setattr(context_processors, "UPDATE_STATUS_FILE", f)
    return context_processors.last_software_update(None)["LAST_SOFTWARE_UPDATE"]


def test_derniere_maj_reussie_affichee(tmp_path, monkeypatch):
    payload = {"phase": "done", "success": True, "done": True, "timestamp": "2026-11-05 12:39:24"}
    assert _status(tmp_path, monkeypatch, payload) == "05/11/2026 à 12:39"


def test_maj_en_echec_rien_affiche(tmp_path, monkeypatch):
    payload = {"phase": "fetch", "success": False, "done": True, "timestamp": "2026-11-05 12:39:24"}
    assert _status(tmp_path, monkeypatch, payload) is None


def test_maj_en_cours_rien_affiche(tmp_path, monkeypatch):
    payload = {"phase": "deps", "success": None, "done": False, "timestamp": "2026-11-05 12:39:24"}
    assert _status(tmp_path, monkeypatch, payload) is None


def test_jamais_mis_a_jour_rien_affiche(tmp_path, monkeypatch):
    assert _status(tmp_path, monkeypatch, None) is None


def test_fichier_illisible_rien_affiche(tmp_path, monkeypatch):
    f = tmp_path / "update_status.json"
    f.write_text("{pas du json")
    monkeypatch.setattr(context_processors, "UPDATE_STATUS_FILE", f)
    assert context_processors.last_software_update(None)["LAST_SOFTWARE_UPDATE"] is None


def test_dashboard_affiche_la_date_de_maj(tmp_path, monkeypatch):
    f = tmp_path / "update_status.json"
    f.write_text(json.dumps({"phase": "done", "success": True, "timestamp": "2026-11-05 12:39:24"}))
    monkeypatch.setattr(context_processors, "UPDATE_STATUS_FILE", f)
    html = Client().get("/").content.decode()
    assert "Dernière mise à jour : 05/11/2026 à 12:39" in html
