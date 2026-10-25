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
