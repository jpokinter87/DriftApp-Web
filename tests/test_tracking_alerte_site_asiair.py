"""Alerte quand le site de l'ASIAIR n'est pas celui de l'observatoire (6.30).

Rejoue la nuit du 27/10 : la monture avait le site du téléphone (E 2°10'), son temps
sidéral retardait de 12 min 20 s sur celui du site de data/config.json (E 5,23°).
Les nuits du 23 et du 26/10 (site correct), l'écart était d'environ +30 s.
"""

import logging
from datetime import datetime, timezone

import pytest

from core.hardware.asiair_client import EtatMonture
from tests.test_tracking_dome_flip_wait import FauxWatcher, _session

# 27/10 à 22:15:36 locales : temps sidéral de la monture 23h49m10s (asiair_monitor.log).
LU_27 = datetime(2026, 10, 27, 21, 15, 36, tzinfo=timezone.utc).timestamp()
LST_27 = 23 + 49 / 60 + 10 / 3600
# 26/10 à 20:00:35 locales : 21h42m42s, site correct.
LU_26 = datetime(2026, 10, 26, 19, 0, 35, tzinfo=timezone.utc).timestamp()
LST_26 = 21 + 42 / 60 + 42 / 3600


def _avec_etat(lst_h, lu_a):
    watcher = FauxWatcher()
    watcher.etat = EtatMonture("pier_east", -0.5, lst_h, lu_a)
    return _session(watcher)


def test_site_correct_pas_d_alerte():
    session = _avec_etat(LST_26, LU_26)
    assert session.get_status()["asiair_site_alert"] is None


def test_site_du_telephone_alerte_chiffree():
    session = _avec_etat(LST_27, LU_27)
    alerte = session.get_status()["asiair_site_alert"]
    assert alerte["offset_min"] == pytest.approx(-12.3, abs=0.1)
    assert alerte["lon_deg"] == pytest.approx(2.15, abs=0.03)


def test_alerte_journalisee_une_fois_puis_retour_a_la_normale(caplog):
    caplog.set_level(logging.INFO)
    session = _avec_etat(LST_27, LU_27)
    session.get_status()
    session.get_status()
    alertes = [r for r in caplog.records if "asiair_site_mismatch" in r.message]
    assert len(alertes) == 1 and alertes[0].levelno == logging.WARNING

    session.pier_watcher.etat = EtatMonture("pier_east", -0.5, LST_26, LU_26)
    assert session.get_status()["asiair_site_alert"] is None
    assert any("asiair_site_ok" in r.message for r in caplog.records)


def test_sans_temps_sideral_ni_asiair_pas_d_alerte():
    session = _session(FauxWatcher())  # EtatMonture sans temps sidéral
    assert session.get_status()["asiair_site_alert"] is None
    session.pier_watcher.etat = None  # ASIAIR muet
    assert session.get_status()["asiair_site_alert"] is None


def test_sans_watcher_pas_de_cle_d_alerte_active():
    session = _session(None)
    assert session.get_status()["asiair_site_alert"] is None
