"""
Tests unitaires pour l'orchestration de l'anticipation méridien.

Couvre les AC du Plan v5.9-02-02 :
- AC-1 : flag désactivé = comportement v5.10 strict
- AC-2 : schedule calculé au start() quand enabled + flip détectable
- AC-3 : slew déclenché au bon moment et consommé une seule fois
- AC-4 : planètes exclues

Stratégie : mocks ciblés sur MeridianFlipDetector / MeridianSlewScheduler /
build_lookahead_trajectory pour isoler l'orchestration de astropy/abaque
(déjà couverts par Phase 1). On ne charge pas le vrai abaque.
"""

from __future__ import annotations

import logging
from datetime import datetime, timedelta
from unittest.mock import MagicMock, patch

import pytest

from core.config.config_loader import MeridianAnticipationConfig
from core.tracking.meridian_anticipation import FlipInfo, SlewSchedule
from core.tracking.tracking_meridian_anticipation_mixin import (
    TrackingMeridianAnticipationMixin,
)


# ============================================================================
# Helpers / fixtures
# ============================================================================


class _SessionStub(TrackingMeridianAnticipationMixin):
    """Stub minimal pour tester le mixin sans instancier TrackingSession complète."""

    def __init__(
        self,
        enabled: bool,
        is_planet: bool = False,
        running: bool = True,
        position_relative: float = 100.0,
        encoder_available: bool = False,
    ):
        self.logger = logging.getLogger("_SessionStub")
        self.moteur = MagicMock()
        self.moteur.steps_per_dome_revolution = 200 * 4 * 2230  # ~1.78M
        self.calc = MagicMock()
        self.abaque_manager = MagicMock()
        self.ra_deg = 150.0
        self.dec_deg = 30.0
        self.is_planet = is_planet
        self.objet = "TEST_OBJECT"
        self.position_relative = position_relative
        self.encoder_available = encoder_available
        self.running = running
        self.total_corrections = 0
        self.total_movement = 0.0
        self._init_anticipation(MeridianAnticipationConfig(enabled=enabled))

    def _resync_encoder_offset(self, position_cible_logique: float):
        """Stub de la méthode de TrackingCorrectionsMixin."""
        self._resync_called_with = position_cible_logique


@pytest.fixture
def sample_flip() -> FlipInfo:
    """Flip synthétique : amplitude 90°, sens CW (signed<0), durée 60s."""
    return FlipInfo(
        start=1200.0,
        end=1260.0,
        duration=60.0,
        amplitude=90.0,
        signed_amplitude=-90.0,
        pre_target=260.0,
        post_target=170.0,
    )


@pytest.fixture
def sample_schedule(sample_flip) -> SlewSchedule:
    """Schedule dérivé : direction -1, target 170°, t_start_offset 60s."""
    return SlewSchedule(
        t_start=1140.0,
        t_start_offset=60.0,
        target=170.0,
        direction=-1,
        flip=sample_flip,
    )


# ============================================================================
# AC-1 : flag désactivé
# ============================================================================


class TestAnticipationDisabled:
    """AC-1 : enabled=False → comportement strictement v5.10."""

    def test_schedule_not_computed_when_disabled(self):
        stub = _SessionStub(enabled=False)
        stub._compute_anticipation_schedule()
        assert stub._anticipation_schedule is None
        assert stub._anticipation_enabled is False

    def test_should_execute_returns_false_when_disabled(self):
        stub = _SessionStub(enabled=False)
        stub._compute_anticipation_schedule()
        assert stub._should_execute_anticipatory_slew(datetime.utcnow()) is False

    def test_no_rotation_absolue_call_when_disabled(self):
        stub = _SessionStub(enabled=False)
        stub._compute_anticipation_schedule()
        stub._should_execute_anticipatory_slew(datetime.utcnow())
        stub.moteur.rotation_absolue.assert_not_called()


# ============================================================================
# AC-2 : schedule calculé
# ============================================================================


class TestAnticipationScheduleComputation:
    """AC-2 : enabled=True → schedule calculé ou None selon flip détecté."""

    def test_schedule_computed_when_flip_detected(self, sample_flip, sample_schedule, caplog):
        stub = _SessionStub(enabled=True)
        with patch(
            "core.tracking.tracking_meridian_anticipation_mixin.build_lookahead_trajectory",
            return_value=[MagicMock()],
        ), patch(
            "core.tracking.tracking_meridian_anticipation_mixin.MeridianFlipDetector"
        ) as DetCls, patch(
            "core.tracking.tracking_meridian_anticipation_mixin.MeridianSlewScheduler"
        ) as SchCls:
            DetCls.return_value.detect.return_value = sample_flip
            SchCls.return_value.schedule.return_value = sample_schedule

            with caplog.at_level(logging.INFO, logger="_SessionStub"):
                stub._compute_anticipation_schedule()

        assert stub._anticipation_schedule is sample_schedule
        assert stub._anticipation_anchor_utc is not None
        assert any("meridian_anticipation_scheduled" in r.message for r in caplog.records)

    def test_no_schedule_when_no_flip_in_window(self, caplog):
        stub = _SessionStub(enabled=True)
        with patch(
            "core.tracking.tracking_meridian_anticipation_mixin.build_lookahead_trajectory",
            return_value=[MagicMock()],
        ), patch(
            "core.tracking.tracking_meridian_anticipation_mixin.MeridianFlipDetector"
        ) as DetCls:
            DetCls.return_value.detect.return_value = None

            with caplog.at_level(logging.DEBUG, logger="_SessionStub"):
                stub._compute_anticipation_schedule()

        assert stub._anticipation_schedule is None
        assert any("meridian_anticipation_no_flip" in r.message for r in caplog.records)

    def test_compute_failure_falls_back_silently(self, caplog):
        stub = _SessionStub(enabled=True)
        with patch(
            "core.tracking.tracking_meridian_anticipation_mixin.build_lookahead_trajectory",
            side_effect=RuntimeError("abaque boom"),
        ):
            with caplog.at_level(logging.WARNING, logger="_SessionStub"):
                stub._compute_anticipation_schedule()

        assert stub._anticipation_schedule is None
        assert any("meridian_anticipation_compute_failed" in r.message for r in caplog.records)


# ============================================================================
# AC-3 : slew déclenché et consommé
# ============================================================================


class TestAnticipationSlewExecution:
    """AC-3 : slew exécuté au bon moment, une seule fois."""

    def _prime_schedule(self, stub: _SessionStub, schedule: SlewSchedule, anchor_offset_sec: float):
        """Injecte un schedule avec un anchor qui place t_start dans le passé ou le futur.

        anchor_offset_sec positif = anchor dans le passé (donc t_start déjà atteint).
        """
        stub._anticipation_schedule = schedule
        stub._anticipation_anchor_utc = datetime.utcnow() - timedelta(seconds=anchor_offset_sec)

    def test_slew_triggers_at_t_start(self, sample_schedule):
        stub = _SessionStub(enabled=True)
        # anchor 1200s dans le passé → elapsed >= schedule.t_start (1140s)
        self._prime_schedule(stub, sample_schedule, anchor_offset_sec=1200.0)
        assert stub._should_execute_anticipatory_slew(datetime.utcnow()) is True

        stub._execute_anticipatory_slew()

        stub.moteur.rotation_absolue.assert_called_once()
        call_kwargs = stub.moteur.rotation_absolue.call_args.kwargs
        assert call_kwargs["position_cible_deg"] == 170.0
        assert call_kwargs["force_direction"] == -1
        assert stub._anticipation_consumed is True
        assert stub.position_relative == 170.0
        assert stub.total_corrections == 1

    def test_slew_not_triggered_before_t_start(self, sample_schedule):
        stub = _SessionStub(enabled=True)
        # anchor 10s dans le passé → elapsed (10s) < schedule.t_start (1140s)
        self._prime_schedule(stub, sample_schedule, anchor_offset_sec=10.0)
        assert stub._should_execute_anticipatory_slew(datetime.utcnow()) is False
        stub.moteur.rotation_absolue.assert_not_called()

    def test_slew_consumed_once(self, sample_schedule):
        stub = _SessionStub(enabled=True)
        self._prime_schedule(stub, sample_schedule, anchor_offset_sec=1200.0)

        stub._execute_anticipatory_slew()
        assert stub._anticipation_consumed is True

        # Deuxième appel : _should_execute renvoie False, rotation_absolue pas rappelée
        assert stub._should_execute_anticipatory_slew(datetime.utcnow()) is False
        stub._execute_anticipatory_slew()  # idempotent, ne ré-exécute pas
        stub.moteur.rotation_absolue.assert_called_once()

    def test_slew_direction_zero_uses_shortest_path(self, sample_flip, caplog):
        stub = _SessionStub(enabled=True)
        schedule_zero = SlewSchedule(
            t_start=1140.0,
            t_start_offset=60.0,
            target=170.0,
            direction=0,
            flip=sample_flip,
        )
        self._prime_schedule(stub, schedule_zero, anchor_offset_sec=1200.0)

        with caplog.at_level(logging.WARNING, logger="_SessionStub"):
            stub._execute_anticipatory_slew()

        call_kwargs = stub.moteur.rotation_absolue.call_args.kwargs
        assert call_kwargs["force_direction"] == 0
        assert any(
            "meridian_anticipation_direction_indeterminate" in r.message
            for r in caplog.records
        )
        assert stub._anticipation_consumed is True

    def test_slew_failure_consumes_schedule(self, sample_schedule, caplog):
        stub = _SessionStub(enabled=True)
        self._prime_schedule(stub, sample_schedule, anchor_offset_sec=1200.0)
        stub.moteur.rotation_absolue.side_effect = RuntimeError("move boom")

        with caplog.at_level(logging.ERROR, logger="_SessionStub"):
            stub._execute_anticipatory_slew()

        assert stub._anticipation_consumed is True
        assert any(
            "meridian_anticipation_slew_failed" in r.message for r in caplog.records
        )

    def test_slew_resyncs_encoder_when_available(self, sample_schedule):
        stub = _SessionStub(enabled=True, encoder_available=True)
        self._prime_schedule(stub, sample_schedule, anchor_offset_sec=1200.0)

        stub._execute_anticipatory_slew()
        assert hasattr(stub, "_resync_called_with")
        assert stub._resync_called_with == 170.0


# ============================================================================
# AC-4 : planètes exclues
# ============================================================================


class TestAnticipationSkipPlanet:
    """AC-4 : planètes → schedule=None même si enabled=True."""

    def test_planet_skipped_even_when_enabled(self, caplog):
        stub = _SessionStub(enabled=True, is_planet=True)
        with caplog.at_level(logging.INFO, logger="_SessionStub"):
            stub._compute_anticipation_schedule()
        assert stub._anticipation_schedule is None
        assert any(
            "meridian_anticipation_skipped_planet" in r.message for r in caplog.records
        )


# ============================================================================
# Hook dans check_and_correct (intégration)
# ============================================================================


class TestCheckAndCorrectHook:
    """Vérifie le hook inséré dans TrackingCorrectionsMixin.check_and_correct()."""

    def _build_session(self, enabled: bool):
        """Instancie un TrackingSession minimal avec moteur et abaque mockés.

        Utilisé uniquement pour tester le court-circuit du hook — pas de start().
        """
        # Import différé pour éviter les imports lourds en haut de fichier
        from unittest.mock import patch as _patch

        with _patch("core.tracking.tracker.get_daemon_reader"), _patch(
            "core.tracking.abaque_manager.AbaqueManager.load_abaque", return_value=True
        ):
            from core.tracking.tracker import TrackingSession
            from core.tracking.tracking_logger import TrackingLogger

            moteur = MagicMock()
            moteur.steps_per_dome_revolution = 200 * 4 * 2230
            calc = MagicMock()
            encoder_config = MagicMock()
            encoder_config.enabled = False

            session = TrackingSession(
                moteur=moteur,
                calc=calc,
                logger=TrackingLogger(),
                abaque_file="data/Loi_coupole.xlsx",
                motor_config=None,
                encoder_config=encoder_config,
                meridian_anticipation_config=MeridianAnticipationConfig(enabled=enabled),
            )
            session.running = True
            session.next_correction_time = None
            session.position_relative = 100.0
            session.objet = "TEST"
            return session

    def test_hook_shortcircuits_when_slew_due(self, sample_schedule):
        session = self._build_session(enabled=True)
        # Injecter un schedule déjà dû
        session._anticipation_schedule = sample_schedule
        session._anticipation_anchor_utc = datetime.utcnow() - timedelta(seconds=1200)

        # Mock _calculate_current_coords pour prouver qu'il n'est PAS appelé
        with patch.object(session, "_calculate_current_coords") as mock_calc:
            applied, msg = session.check_and_correct()

        assert applied is True
        assert msg == "meridian_anticipation_slew_executed"
        mock_calc.assert_not_called()
        session.moteur.rotation_absolue.assert_called_once()
        assert session._anticipation_consumed is True
        assert session.next_correction_time is not None

    def test_hook_noop_when_disabled(self):
        session = self._build_session(enabled=False)
        assert session._anticipation_schedule is None
        # Le hook doit laisser passer vers la logique abaque normale.
        # On vérifie qu'avant d'atteindre la logique abaque, le hook retourne False
        # (ici on s'arrête avant : _calculate_current_coords serait appelé ensuite).
        assert session._should_execute_anticipatory_slew(datetime.utcnow()) is False


# ============================================================================
# Re-scan glissant (v5.11.1)
# ============================================================================


class TestAnticipationRescan:
    """Re-scan périodique de la fenêtre 1h tant qu'aucun schedule n'est armé."""

    def test_rescan_noop_when_disabled(self):
        stub = _SessionStub(enabled=False)
        with patch.object(stub, "_compute_anticipation_schedule") as mock_compute:
            stub._maybe_rescan_anticipation(datetime.utcnow())
        mock_compute.assert_not_called()

    def test_rescan_first_call_runs_compute(self):
        stub = _SessionStub(enabled=True)
        # last_scan_at est None à l'init → le premier appel doit déclencher.
        # `_compute_anticipation_schedule` (mocké ici) est responsable du set
        # de `_anticipation_last_scan_at`, donc le test contractuel ne vérifie
        # que l'appel à compute.
        with patch.object(stub, "_compute_anticipation_schedule") as mock_compute:
            stub._maybe_rescan_anticipation(datetime.utcnow())
        mock_compute.assert_called_once_with(log_no_flip=False)

    def test_compute_sets_last_scan_at(self):
        """Le compute (start ou rescan) initialise le timer pour le throttle."""
        stub = _SessionStub(enabled=True)
        assert stub._anticipation_last_scan_at is None
        with patch(
            "core.tracking.tracking_meridian_anticipation_mixin.build_lookahead_trajectory",
            return_value=[MagicMock()],
        ), patch(
            "core.tracking.tracking_meridian_anticipation_mixin.MeridianFlipDetector"
        ) as DetCls:
            DetCls.return_value.detect.return_value = None
            stub._compute_anticipation_schedule()
        assert stub._anticipation_last_scan_at is not None

    def test_rescan_throttled_within_5_min(self):
        stub = _SessionStub(enabled=True)
        now = datetime.utcnow()
        stub._anticipation_last_scan_at = now
        with patch.object(stub, "_compute_anticipation_schedule") as mock_compute:
            stub._maybe_rescan_anticipation(now + timedelta(seconds=120))  # < 300s
        mock_compute.assert_not_called()

    def test_rescan_runs_after_5_min(self):
        stub = _SessionStub(enabled=True)
        now = datetime.utcnow()
        stub._anticipation_last_scan_at = now
        with patch.object(stub, "_compute_anticipation_schedule") as mock_compute:
            stub._maybe_rescan_anticipation(now + timedelta(seconds=301))  # > 300s
        mock_compute.assert_called_once_with(log_no_flip=False)

    def test_rescan_skips_when_schedule_armed(self, sample_schedule):
        """Schedule armé non consommé → on ne re-scan pas (timing protégé)."""
        stub = _SessionStub(enabled=True)
        stub._anticipation_schedule = sample_schedule
        stub._anticipation_anchor_utc = datetime.utcnow()
        stub._anticipation_consumed = False
        with patch.object(stub, "_compute_anticipation_schedule") as mock_compute:
            stub._maybe_rescan_anticipation(datetime.utcnow() + timedelta(seconds=600))
        mock_compute.assert_not_called()

    def test_rescan_runs_after_consumption(self, sample_schedule):
        """Schedule consommé → re-scan permis pour ré-armement."""
        stub = _SessionStub(enabled=True)
        stub._anticipation_schedule = sample_schedule
        stub._anticipation_consumed = True
        with patch.object(stub, "_compute_anticipation_schedule") as mock_compute:
            stub._maybe_rescan_anticipation(datetime.utcnow())
        mock_compute.assert_called_once_with(log_no_flip=False)

    def test_compute_resets_consumed_flag(self, sample_flip, sample_schedule):
        """Un re-scan qui trouve un nouveau flip ré-arme _consumed=False."""
        stub = _SessionStub(enabled=True)
        # État post-consommation
        stub._anticipation_schedule = sample_schedule
        stub._anticipation_consumed = True
        with patch(
            "core.tracking.tracking_meridian_anticipation_mixin.build_lookahead_trajectory",
            return_value=[MagicMock()],
        ), patch(
            "core.tracking.tracking_meridian_anticipation_mixin.MeridianFlipDetector"
        ) as DetCls, patch(
            "core.tracking.tracking_meridian_anticipation_mixin.MeridianSlewScheduler"
        ) as SchCls:
            DetCls.return_value.detect.return_value = sample_flip
            SchCls.return_value.schedule.return_value = sample_schedule
            stub._compute_anticipation_schedule(log_no_flip=False)

        assert stub._anticipation_consumed is False
        assert stub._anticipation_schedule is sample_schedule

    def test_rescan_no_flip_logs_debug(self, caplog):
        """Re-scan sans flip → DEBUG, pas INFO (évite spam log toutes les 5 min)."""
        stub = _SessionStub(enabled=True)
        with patch(
            "core.tracking.tracking_meridian_anticipation_mixin.build_lookahead_trajectory",
            return_value=[MagicMock()],
        ), patch(
            "core.tracking.tracking_meridian_anticipation_mixin.MeridianFlipDetector"
        ) as DetCls:
            DetCls.return_value.detect.return_value = None
            with caplog.at_level(logging.DEBUG, logger="_SessionStub"):
                stub._compute_anticipation_schedule(log_no_flip=False)

        info_records = [r for r in caplog.records if r.levelno == logging.INFO]
        debug_records = [r for r in caplog.records if r.levelno == logging.DEBUG]
        assert not any("meridian_anticipation_no_flip" in r.message for r in info_records)
        assert any("meridian_anticipation_rescan_no_flip" in r.message for r in debug_records)
