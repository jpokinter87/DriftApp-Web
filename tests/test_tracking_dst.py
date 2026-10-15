"""
Suivi à travers le changement d'heure (nuit du 24 au 25/10/2026).

À 3 h CEST l'horloge locale recule à 2 h CET. Le calculateur du suivi est
construit une fois au démarrage avec `tz_offset` figé (+2 l'été) : si le
suivi lui passe l'heure locale naïve, l'UTC calculé est faux d'une heure
pour le reste de la session (~7° d'azimut sur M31), et l'échéance des
corrections, elle aussi en heure locale naïve, gèle le suivi pendant 1 h.

On injecte une horloge fictive dans les modules du suivi : `now()` sans
fuseau rend l'heure locale de Paris (comme sur le Pi), `now(tz)` l'instant
réel. Le suivi doit rester juste quelle que soit l'heure murale.
"""

from datetime import datetime, timedelta, timezone
from pathlib import Path
from unittest.mock import patch
from zoneinfo import ZoneInfo

import pytest

import core.tracking.tracker as tracker_mod
import core.tracking.tracking_corrections_mixin as corrections_mod
import core.tracking.tracking_meridian_anticipation_mixin as anticipation_mod
from core.config.config_loader import load_config
from core.hardware.moteur_simule import MoteurSimule, set_simulated_position
from core.observatoire import AstronomicalCalculations
from core.tracking.tracking_logger import TrackingLogger
from core.tracking.tracker import TrackingSession

PARIS = ZoneInfo("Europe/Paris")
ABAQUE = Path(__file__).resolve().parent.parent / "data" / "Loi_coupole.xlsx"

# M31 (J2000)
RA, DEC = 10.6847, 41.2690

# 02:50 CEST, 10 minutes avant le recul de l'horloge
AVANT_BASCULE = datetime(2026, 10, 25, 0, 50, tzinfo=timezone.utc)


class _Horloge:
    instant = AVANT_BASCULE


class _FakeDatetime(datetime):
    @classmethod
    def now(cls, tz=None):
        if tz is None:
            return _Horloge.instant.astimezone(PARIS).replace(tzinfo=None)
        return _Horloge.instant.astimezone(tz)

    @classmethod
    def utcnow(cls):
        return _Horloge.instant.astimezone(timezone.utc).replace(tzinfo=None)


@pytest.fixture
def horloge():
    _Horloge.instant = AVANT_BASCULE
    with (
        patch.object(tracker_mod, "datetime", _FakeDatetime),
        patch.object(corrections_mod, "datetime", _FakeDatetime),
        patch.object(anticipation_mod, "datetime", _FakeDatetime),
    ):
        yield _Horloge


@pytest.fixture
def session(horloge):
    if not ABAQUE.exists():
        pytest.skip("Abaque Loi_coupole.xlsx non trouvé")
    config = load_config()
    set_simulated_position(0.0)
    # tz_offset figé à l'heure d'été, comme le fait TrackingHandler au démarrage
    calc = AstronomicalCalculations(config.site.latitude, config.site.longitude, 2)
    s = TrackingSession(
        moteur=MoteurSimule(),
        calc=calc,
        logger=TrackingLogger(),
        seuil=config.tracking.seuil_correction_deg,
        intervalle=config.tracking.intervalle_verification_sec,
        abaque_file=str(ABAQUE),
        motor_config=config.motor,
        encoder_config=config.encoder,
    )
    ok, msg = s.start("M31", skip_goto=True, coords=(RA, DEC))
    assert ok, msg
    return s


def test_coordonnees_justes_apres_recul_horloge(session, horloge):
    horloge.instant = AVANT_BASCULE + timedelta(minutes=40)  # 02:30 CET

    status = session.get_status()

    attendu_az, attendu_alt = session.calc.calculer_coords_horizontales(RA, DEC, horloge.instant)
    assert status["obj_az_raw"] == pytest.approx(attendu_az, abs=0.01)
    assert status["obj_alt"] == pytest.approx(attendu_alt, abs=0.01)


def test_corrections_non_gelees_apres_recul_horloge(session, horloge):
    # 20 min réelles plus tard l'heure murale (02:10 CET) est antérieure
    # à l'échéance posée au démarrage (02:50:30 CEST en heure naïve).
    horloge.instant = AVANT_BASCULE + timedelta(minutes=20)

    _, message = session.check_and_correct()

    # "" = « pas encore le moment » ; sinon la correction a été évaluée
    assert message != ""


def test_anticipation_projette_le_ciel_a_l_instant_reel(session, horloge):
    session._anticipation_enabled = True
    with patch.object(anticipation_mod, "build_lookahead_trajectory", return_value=[]) as build:
        session._compute_anticipation_schedule()

    sim_start = build.call_args.kwargs["sim_start"]
    az, _ = session.calc.calculer_coords_horizontales(RA, DEC, sim_start)
    attendu, _ = session.calc.calculer_coords_horizontales(RA, DEC, horloge.instant)
    assert az == pytest.approx(attendu, abs=0.01)
