"""La coupole suit la monture retournée avant le méridien (6.26).

Rejoue la nuit du 23/10 : objet RA 21h59m46.8s Déc +62°50′ (culmine au nord à
71°), monture côté Est alors que l'azimut DriftApp n'a pas encore passé 0°.
Vraie session de suivi, vrai abaque, horloge fictive, faux watcher.
"""

import logging
from datetime import datetime, timedelta, timezone
from unittest.mock import MagicMock, patch

import pytest

import core.tracking.tracker as tracker_mod
import core.tracking.tracking_corrections_mixin as corrections_mod
import core.tracking.tracking_meridian_anticipation_mixin as anticipation_mod
from core.hardware.asiair_client import EtatMonture
from core.utils.angle_utils import shortest_angular_distance
from tests.test_tracking_dome_flip_wait import ABAQUE, FauxWatcher, _FakeDatetime, _Horloge

RA, DEC = 329.7443588, 62.7072547  # J2000, objet du 23/10
DEBUT = datetime(2026, 10, 23, 19, 20, tzinfo=timezone.utc)  # 21:20 locales
FLIP = datetime(2026, 10, 23, 19, 24, tzinfo=timezone.utc)  # monture en avance
APRES = datetime(2026, 10, 23, 19, 31, tzinfo=timezone.utc)  # méridien passé


@pytest.fixture
def horloge():
    _Horloge.instant = DEBUT
    with (
        patch.object(tracker_mod, "datetime", _FakeDatetime),
        patch.object(corrections_mod, "datetime", _FakeDatetime),
        patch.object(anticipation_mod, "datetime", _FakeDatetime),
    ):
        yield _Horloge


def _session(watcher, max_min=15.0):
    from core.config.config_loader import MeridianAnticipationConfig, load_config
    from core.hardware.moteur_simule import MoteurSimule, set_simulated_position
    from core.observatoire import AstronomicalCalculations
    from core.tracking.tracker import TrackingSession
    from core.tracking.tracking_logger import TrackingLogger

    if not ABAQUE.exists():
        pytest.skip("Abaque Loi_coupole.xlsx non trouvé")
    _Horloge.instant = DEBUT
    config = load_config()
    set_simulated_position(0.0)
    s = TrackingSession(
        moteur=MoteurSimule(),
        calc=AstronomicalCalculations(config.site.latitude, config.site.longitude, 2),
        logger=TrackingLogger(),
        abaque_file=str(ABAQUE),
        motor_config=config.motor,
        encoder_config=config.encoder,
        meridian_anticipation_config=MeridianAnticipationConfig(enabled=False),
        pier_watcher=watcher,
        flip_max_wait_minutes=max_min,
    )
    ok, msg = s.start("essai", skip_goto=True, coords=(RA, DEC))
    assert ok, msg

    def bouge(delta, *_args):
        s.position_relative = (s.position_relative + delta) % 360.0

    s._apply_correction = MagicMock(side_effect=bouge)
    s.position_relative = s._calculate_target_position(*s._calculate_current_coords(DEBUT))[0]
    return s


def _correction_a(session, horloge, instant):
    horloge.instant = instant
    session.next_correction_time = instant
    return session.check_and_correct()


def _deltas(session):
    return [c.args[0] for c in session._apply_correction.call_args_list]


def test_rejeu_23_10_bascule_des_le_retournement(horloge, caplog):
    caplog.set_level(logging.INFO)
    watcher = FauxWatcher()
    session = _session(watcher)
    avant = session.position_relative
    assert 300.0 < avant < 330.0  # branche « avant » de l'abaque (~315°)

    watcher.etat = EtatMonture("pier_east", 0.08)
    applied, _ = _correction_a(session, horloge, FLIP)
    assert applied
    cible = session.position_relative
    assert 25.0 < cible < 45.0  # branche « après » (~36°)
    status = session.get_status()
    assert status["flip_early"] == {"target": round(cible, 1)}
    assert abs(shortest_angular_distance(status["position_cible"], cible)) < 0.1
    assert any("dome_flip_early_start" in r.message for r in caplog.records)

    # Jusqu'au méridien, la coupole ne revient pas côté « avant ».
    for minute in (1, 2, 3, 4):
        _correction_a(session, horloge, FLIP + timedelta(minutes=minute))
    assert len(_deltas(session)) == 1
    assert session.position_relative == cible

    # Méridien passé : fin de la tenue, reprise normale sans saut.
    watcher.etat = EtatMonture("pier_east", -0.02)
    _correction_a(session, horloge, APRES)
    assert all(abs(d) < 1.0 for d in _deltas(session)[1:])
    assert abs(shortest_angular_distance(session.position_relative, cible)) < 1.0
    assert session.get_status()["flip_early"] is None
    assert any("dome_flip_early_end | reason=transit" in r.message for r in caplog.records)


def test_asiair_muet_pendant_la_tenue_la_tenue_continue(horloge):
    watcher = FauxWatcher()
    session = _session(watcher)
    watcher.etat = EtatMonture("pier_east", 0.08)
    _correction_a(session, horloge, FLIP)
    cible = session.position_relative

    watcher.etat = None
    _correction_a(session, horloge, FLIP + timedelta(minutes=2))
    assert session.position_relative == cible
    assert session.get_status()["flip_early"] == {"target": round(cible, 1)}


def test_monture_renvoyee_cote_ouest_fin_de_la_tenue(horloge, caplog):
    caplog.set_level(logging.INFO)
    watcher = FauxWatcher()
    session = _session(watcher)
    watcher.etat = EtatMonture("pier_east", 0.08)
    _correction_a(session, horloge, FLIP)

    watcher.etat = EtatMonture("pier_west", 0.05)
    _correction_a(session, horloge, FLIP + timedelta(minutes=1))
    assert 300.0 < session.position_relative < 330.0
    assert session.get_status()["flip_early"] is None
    assert any("dome_flip_early_end | reason=pierside" in r.message for r in caplog.records)


def test_meridien_hors_fenetre_avertit_une_fois(horloge, caplog):
    watcher = FauxWatcher()
    session = _session(watcher, max_min=2)  # méridien à ~5 min : hors fenêtre
    watcher.etat = EtatMonture("pier_east", 0.08)
    _correction_a(session, horloge, FLIP)
    _correction_a(session, horloge, FLIP + timedelta(seconds=30))
    assert all(abs(d) < 1.0 for d in _deltas(session))
    hors = [r for r in caplog.records if "dome_flip_early_out_of_window" in r.message]
    assert len(hors) == 1 and hors[0].levelname == "WARNING"


def test_monture_cote_ouest_avant_le_meridien_rien_ne_change(horloge):
    watcher = FauxWatcher()
    session = _session(watcher)
    watcher.etat = EtatMonture("pier_west", 0.08)
    _correction_a(session, horloge, FLIP)
    assert all(abs(d) < 1.0 for d in _deltas(session))
    assert session.get_status()["flip_early"] is None


def test_sans_watcher_rien_ne_change(horloge):
    session = _session(None)
    _correction_a(session, horloge, FLIP)
    assert all(abs(d) < 1.0 for d in _deltas(session))
    assert session.get_status()["flip_early"] is None
