"""La coupole attend le retournement de la monture avant de basculer (6.24).

Rejoue la chronologie de l'essai du 21/10 (objet à Déc +68,75°, retournement
par l'ASIAIR au passage au méridien) avec une vraie session de suivi, le vrai
abaque, une horloge fictive et un faux watcher dont on choisit le côté du pied.
"""

import logging
from datetime import datetime, timedelta, timezone
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

import core.tracking.tracker as tracker_mod
import core.tracking.tracking_corrections_mixin as corrections_mod
import core.tracking.tracking_meridian_anticipation_mixin as anticipation_mod
from core.config.config_loader import MeridianAnticipationConfig, load_config
from core.hardware.asiair_client import EtatMonture
from core.hardware.moteur_simule import MoteurSimule, set_simulated_position
from core.observatoire import AstronomicalCalculations
from core.tracking.tracking_logger import TrackingLogger
from core.tracking.tracker import TrackingSession

ABAQUE = Path(__file__).resolve().parent.parent / "data" / "Loi_coupole.xlsx"
RA, DEC = 264.0, 68.75  # J2000, l'objet de l'essai du 21/10
DEBUT = datetime(2026, 10, 21, 14, 50, tzinfo=timezone.utc)


class _Horloge:
    instant = DEBUT


class _FakeDatetime(datetime):
    @classmethod
    def now(cls, tz=None):
        if tz is None:
            return _Horloge.instant.astimezone().replace(tzinfo=None)
        return _Horloge.instant.astimezone(tz)


class FauxWatcher:
    def __init__(self):
        self.etat = EtatMonture("pier_west", 0.3)

    def etat_frais(self, max_age_s=30.0):
        return self.etat


@pytest.fixture
def horloge():
    _Horloge.instant = DEBUT
    with (
        patch.object(tracker_mod, "datetime", _FakeDatetime),
        patch.object(corrections_mod, "datetime", _FakeDatetime),
        patch.object(anticipation_mod, "datetime", _FakeDatetime),
    ):
        yield _Horloge


def _session(watcher, max_min=30.0):
    if not ABAQUE.exists():
        pytest.skip("Abaque Loi_coupole.xlsx non trouvé")
    config = load_config()
    set_simulated_position(0.0)
    s = TrackingSession(
        moteur=MoteurSimule(),
        calc=AstronomicalCalculations(config.site.latitude, config.site.longitude, 2),
        logger=TrackingLogger(),
        abaque_file=str(ABAQUE),
        motor_config=config.motor,
        encoder_config=config.encoder,
        meridian_anticipation_config=MeridianAnticipationConfig(enabled=True),
        pier_watcher=watcher,
        flip_max_wait_minutes=max_min,
    )
    ok, msg = s.start("essai", skip_goto=True, coords=(RA, DEC))
    assert ok, msg
    s._apply_correction = MagicMock()
    return s


def _transit(session):
    return session.calc.calculer_heure_passage_meridien(RA, DEBUT, DEC)


def _correction_a(session, horloge, instant):
    horloge.instant = instant
    session.next_correction_time = instant  # échéance atteinte
    return session.check_and_correct()


def test_anticipation_neutralisee(horloge):
    session = _session(FauxWatcher())
    assert session._anticipation_enabled is False


def test_coupole_attend_le_retournement_puis_bascule_aussitot(horloge, caplog):
    caplog.set_level(logging.INFO)
    watcher = FauxWatcher()
    session = _session(watcher)
    transit = _transit(session)

    # Avant le méridien : corrections ordinaires.
    _, msg = _correction_a(session, horloge, transit - timedelta(minutes=2))
    assert msg != "dome_flip_wait"

    # Passé le méridien (DriftApp), monture encore côté Ouest : la coupole attend,
    # même si l'ASIAIR se croit encore juste avant son propre méridien.
    session._apply_correction.reset_mock()
    watcher.etat = EtatMonture("pier_west", +0.002)
    applied, msg = _correction_a(session, horloge, transit + timedelta(seconds=30))
    assert (applied, msg) == (False, "dome_flip_wait")
    session._apply_correction.assert_not_called()
    status = session.get_status()
    assert status["asiair_pier"] == "west"
    assert status["flip_wait"] == {"elapsed_s": 0, "max_s": 1800}

    # Revérification rapprochée, pas à 30 s.
    assert session.next_correction_time == horloge.instant + timedelta(seconds=5)
    horloge.instant += timedelta(minutes=4)
    assert session.check_and_correct() == (False, "dome_flip_wait")
    assert session.get_status()["flip_wait"]["elapsed_s"] == 240

    # Feu vert : la monture passe côté Est → bascule dans la même vérification.
    watcher.etat = EtatMonture("pier_east", -10.5)
    horloge.instant += timedelta(seconds=5)
    session.check_and_correct()
    session._apply_correction.assert_called_once()
    assert session.get_status()["flip_wait"] is None
    assert any("dome_flip_wait_start" in r.message for r in caplog.records)
    assert any("dome_flip_wait_end | reason=pierside" in r.message for r in caplog.records)


def test_delai_maximal_puis_bascule_avec_avertissement(horloge, caplog):
    watcher = FauxWatcher()
    watcher.etat = EtatMonture("pier_west", -0.01)
    session = _session(watcher, max_min=10)
    transit = _transit(session)

    assert _correction_a(session, horloge, transit + timedelta(seconds=30))[1] == "dome_flip_wait"
    _correction_a(session, horloge, transit + timedelta(minutes=11))
    session._apply_correction.assert_called_once()
    fin = [r for r in caplog.records if "dome_flip_wait_end" in r.message]
    assert fin and fin[0].levelname == "WARNING" and "reason=timeout" in fin[0].message


def test_asiair_muet_comportement_actuel(horloge):
    watcher = FauxWatcher()
    watcher.etat = None
    session = _session(watcher)
    _, msg = _correction_a(session, horloge, _transit(session) + timedelta(seconds=30))
    assert msg != "dome_flip_wait"
    assert session.get_status()["asiair_pier"] is None


def test_sans_watcher_rien_ne_change(horloge):
    session = _session(None)
    _, msg = _correction_a(session, horloge, _transit(session) + timedelta(seconds=30))
    assert msg != "dome_flip_wait"
    status = session.get_status()
    assert status["asiair_pier"] is None and status["flip_wait"] is None
    assert session._anticipation_enabled is True
