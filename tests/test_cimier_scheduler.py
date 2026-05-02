"""Tests pour services/cimier_scheduler.py (v6.0 Phase 3 sub-plan 03-01).

Tests offline avec injection complète : clock, sun_altitude_fn, sun_direction_fn,
mocks pour cimier_ipc + motor_ipc + weather_provider.
"""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from datetime import datetime, timedelta, timezone
from typing import Any, Dict, List

from core.config.config_loader import CimierAutomationConfig, SiteConfig
from services.cimier_scheduler import (
    CimierScheduler,
    CIMIER_STATE_CLOSED,
    CIMIER_STATE_OPEN,
    CIMIER_STATE_CYCLE,
)


# ----------------------------------------------------------------------
# Fixtures / mocks
# ----------------------------------------------------------------------


def _site():
    return SiteConfig(latitude=44.15, longitude=5.23, altitude=800.0, nom="Test", fuseau="Europe/Paris")


def _automation(**overrides):
    cfg = CimierAutomationConfig(mode="full")
    for k, v in overrides.items():
        setattr(cfg, k, v)
    return cfg


@dataclass
class FakeWeatherProvider:
    safe: bool = True
    call_count: int = 0

    def is_safe_to_open(self) -> bool:
        self.call_count += 1
        return self.safe

    def is_safe_to_keep_open(self) -> bool:
        return self.safe

    def describe(self) -> Dict[str, Any]:
        return {"provider": "fake", "safe": self.safe}


@dataclass
class FakeCimierIpc:
    commands: List[Dict[str, Any]] = field(default_factory=list)

    def write_command(self, command: Dict[str, Any]) -> None:
        self.commands.append(command)


@dataclass
class FakeMotorIpc:
    calls: List[tuple] = field(default_factory=list)

    def send_goto(self, angle: float) -> bool:
        self.calls.append(("goto", angle))
        return True

    def send_jog(self, delta: float) -> bool:
        self.calls.append(("jog", delta))
        return True

    def send_tracking_stop(self) -> bool:
        self.calls.append(("tracking_stop",))
        return True

    def send_stop(self) -> bool:
        self.calls.append(("stop",))
        return True


def _scheduler(automation, alt_fn, dir_fn, weather=None, clock_now=None):
    weather = weather or FakeWeatherProvider(safe=True)
    cimier = FakeCimierIpc()
    motor = FakeMotorIpc()
    if clock_now is None:
        clock_now = datetime(2026, 5, 15, 21, 0, tzinfo=timezone.utc)
    sched = CimierScheduler(
        automation_config=automation,
        site_config=_site(),
        weather_provider=weather,
        cimier_ipc=cimier,
        motor_ipc=motor,
        clock=lambda: clock_now,
        sun_altitude_fn=alt_fn,
        sun_direction_fn=dir_fn,
    )
    return sched, cimier, motor, weather


# ----------------------------------------------------------------------
# Tests
# ----------------------------------------------------------------------


def test_disabled_returns_skip_disabled():
    sched, cimier, motor, _ = _scheduler(
        automation=CimierAutomationConfig(mode="manual"),
        alt_fn=lambda *a, **kw: -15.0,
        dir_fn=lambda *a, **kw: "descending",
    )
    decision = sched.maybe_trigger(CIMIER_STATE_CLOSED)
    assert decision.trigger == "skip:disabled"
    assert cimier.commands == []
    assert motor.calls == []


def test_descending_below_threshold_with_closed_cimier_triggers_open():
    sched, cimier, motor, weather = _scheduler(
        automation=_automation(),
        alt_fn=lambda *a, **kw: -12.5,
        dir_fn=lambda *a, **kw: "descending",
    )
    decision = sched.maybe_trigger(CIMIER_STATE_CLOSED)
    assert decision.trigger == "open"
    assert decision.sun_alt_deg == -12.5
    assert decision.direction == "descending"
    # Cimier IPC : commande open
    assert len(cimier.commands) == 1
    assert cimier.commands[0]["action"] == "open"
    assert "id" in cimier.commands[0]
    # Motor IPC : jog +1.0° (déparking)
    assert ("jog", 1.0) in motor.calls
    # WeatherProvider consulté
    assert weather.call_count == 1


def test_descending_with_unsafe_weather_skips_open():
    weather = FakeWeatherProvider(safe=False)
    sched, cimier, motor, _ = _scheduler(
        automation=_automation(),
        alt_fn=lambda *a, **kw: -15.0,
        dir_fn=lambda *a, **kw: "descending",
        weather=weather,
    )
    decision = sched.maybe_trigger(CIMIER_STATE_CLOSED)
    assert decision.trigger == "skip:weather"
    assert cimier.commands == []
    assert motor.calls == []
    assert weather.call_count == 1


def test_descending_with_open_cimier_skips_state():
    sched, cimier, motor, _ = _scheduler(
        automation=_automation(),
        alt_fn=lambda *a, **kw: -15.0,
        dir_fn=lambda *a, **kw: "descending",
    )
    decision = sched.maybe_trigger(CIMIER_STATE_OPEN)
    assert decision.trigger == "skip:state"
    assert cimier.commands == []
    assert motor.calls == []


def test_rising_with_open_cimier_triggers_close_three_ipc_in_order():
    """alt_future projeté à +15min ≥ -6° (target) + state=open → trigger="close"."""
    # Alt actuel = -10° (encore sous l'horizon), alt projeté à +15min = -5° (au-dessus du target -6°)
    alt_values = {0: -10.0, 1: -5.0}  # 0 = now, 1 = future (advance + safety)
    call_count = [0]

    def alt_fn(when, *a, **kw):
        idx = call_count[0]
        call_count[0] += 1
        return alt_values.get(idx, -10.0)

    sched, cimier, motor, _ = _scheduler(
        automation=_automation(),
        alt_fn=alt_fn,
        dir_fn=lambda *a, **kw: "rising",
    )
    decision = sched.maybe_trigger(CIMIER_STATE_OPEN)
    assert decision.trigger == "close"
    # Ordre IPC : tracking_stop → goto 45° → close cimier
    assert motor.calls == [("tracking_stop",), ("goto", 45.0)]
    assert len(cimier.commands) == 1
    assert cimier.commands[0]["action"] == "close"


def test_rising_with_closed_cimier_skips_state():
    alt_values = [-10.0, -5.0]
    call_count = [0]

    def alt_fn(*a, **kw):
        idx = call_count[0]
        call_count[0] += 1
        return alt_values[idx] if idx < 2 else -10.0

    sched, cimier, motor, _ = _scheduler(
        automation=_automation(),
        alt_fn=alt_fn,
        dir_fn=lambda *a, **kw: "rising",
    )
    decision = sched.maybe_trigger(CIMIER_STATE_CLOSED)
    assert decision.trigger == "skip:state"
    assert cimier.commands == []
    assert motor.calls == []


def test_open_idempotent_within_cooldown_window():
    sched, cimier, motor, _ = _scheduler(
        automation=_automation(),
        alt_fn=lambda *a, **kw: -15.0,
        dir_fn=lambda *a, **kw: "descending",
    )
    # 1er trigger : open
    d1 = sched.maybe_trigger(CIMIER_STATE_CLOSED)
    assert d1.trigger == "open"
    # 2e appel immédiat : cooldown actif (default 12h)
    # Cimier serait revenu à closed en théorie (test simplifié)
    d2 = sched.maybe_trigger(CIMIER_STATE_CLOSED)
    assert d2.trigger == "skip:cooldown"
    # Aucune nouvelle commande
    assert len(cimier.commands) == 1
    assert len([c for c in motor.calls if c[0] == "jog"]) == 1


def test_open_re_trigger_after_cooldown_window():
    """Après retrigger_cooldown_hours, le scheduler peut re-déclencher."""
    automation = _automation(retrigger_cooldown_hours=1)  # 1h pour test rapide
    weather = FakeWeatherProvider(safe=True)
    cimier = FakeCimierIpc()
    motor = FakeMotorIpc()

    # Clock variable pour avancer le temps entre triggers
    state = {"now": datetime(2026, 5, 15, 21, 0, tzinfo=timezone.utc)}

    sched = CimierScheduler(
        automation_config=automation,
        site_config=_site(),
        weather_provider=weather,
        cimier_ipc=cimier,
        motor_ipc=motor,
        clock=lambda: state["now"],
        sun_altitude_fn=lambda *a, **kw: -15.0,
        sun_direction_fn=lambda *a, **kw: "descending",
    )

    d1 = sched.maybe_trigger(CIMIER_STATE_CLOSED)
    assert d1.trigger == "open"

    # Avancer 2h (> cooldown 1h)
    state["now"] = state["now"] + timedelta(hours=2)
    d2 = sched.maybe_trigger(CIMIER_STATE_CLOSED)
    assert d2.trigger == "open"
    # 2 commandes émises
    assert len(cimier.commands) == 2


def test_close_idempotent_within_cooldown_window():
    alt_values = [-10.0, -5.0, -10.0, -5.0]
    call_count = [0]

    def alt_fn(*a, **kw):
        idx = call_count[0]
        call_count[0] += 1
        return alt_values[idx] if idx < len(alt_values) else -10.0

    sched, cimier, motor, _ = _scheduler(
        automation=_automation(),
        alt_fn=alt_fn,
        dir_fn=lambda *a, **kw: "rising",
    )
    d1 = sched.maybe_trigger(CIMIER_STATE_OPEN)
    assert d1.trigger == "close"
    d2 = sched.maybe_trigger(CIMIER_STATE_OPEN)
    assert d2.trigger == "skip:cooldown"
    assert len(cimier.commands) == 1


def test_flat_direction_returns_skip_state():
    sched, cimier, motor, _ = _scheduler(
        automation=_automation(),
        alt_fn=lambda *a, **kw: 30.0,
        dir_fn=lambda *a, **kw: "flat",
    )
    decision = sched.maybe_trigger(CIMIER_STATE_CLOSED)
    assert decision.trigger == "skip:state"
    assert cimier.commands == []
    assert motor.calls == []


def test_astropy_runtime_error_returns_skip_none():
    def raise_astropy(*a, **kw):
        raise RuntimeError("astropy requis")

    sched, cimier, motor, _ = _scheduler(
        automation=_automation(),
        alt_fn=raise_astropy,
        dir_fn=lambda *a, **kw: "descending",
    )
    decision = sched.maybe_trigger(CIMIER_STATE_CLOSED)
    assert decision.trigger == "skip:none"
    assert cimier.commands == []
    assert motor.calls == []


def test_close_trigger_in_cycle_state_works():
    """Cimier en cycle (cycle de fermeture précédent par exemple) → trigger close encore une fois ne devrait pas re-tenter."""
    alt_values = [-10.0, -5.0]
    call_count = [0]

    def alt_fn(*a, **kw):
        idx = call_count[0]
        call_count[0] += 1
        return alt_values[idx] if idx < 2 else -10.0

    sched, cimier, motor, _ = _scheduler(
        automation=_automation(),
        alt_fn=alt_fn,
        dir_fn=lambda *a, **kw: "rising",
    )
    decision = sched.maybe_trigger(CIMIER_STATE_CYCLE)
    # Pour cycle state, on accepte quand même un close (rebascule pending command)
    assert decision.trigger == "close"
    assert len(cimier.commands) == 1


def test_descending_above_threshold_no_trigger():
    """Sun descendant mais alt = -8° (au-dessus du seuil -12°) → pas de trigger."""
    sched, cimier, motor, _ = _scheduler(
        automation=_automation(),
        alt_fn=lambda *a, **kw: -8.0,
        dir_fn=lambda *a, **kw: "descending",
    )
    decision = sched.maybe_trigger(CIMIER_STATE_CLOSED)
    assert decision.trigger == "skip:state"
    assert cimier.commands == []
    assert motor.calls == []


def test_close_uses_configured_parking_azimuth():
    """Vérifie que le scheduler envoie GOTO vers parking_target_azimuth_deg configuré."""
    automation = _automation(parking_target_azimuth_deg=180.0)
    alt_values = [-10.0, -5.0]
    call_count = [0]

    def alt_fn(*a, **kw):
        idx = call_count[0]
        call_count[0] += 1
        return alt_values[idx] if idx < 2 else -10.0

    sched, cimier, motor, _ = _scheduler(
        automation=automation,
        alt_fn=alt_fn,
        dir_fn=lambda *a, **kw: "rising",
    )
    decision = sched.maybe_trigger(CIMIER_STATE_OPEN)
    assert decision.trigger == "close"
    assert ("goto", 180.0) in motor.calls


# ----------------------------------------------------------------------
# AC-2 (sub-plan v6.0-04-01) : matrice 3 modes × 2 conditions (OPEN / CLOSE)
# ----------------------------------------------------------------------


class TestSchedulerModes:
    """Couvre les 3 modes (manual, semi, full) face aux 2 conditions astropy
    (OPEN remplies, CLOSE remplies). Total : 6 cas + 1 sanity check semi+OPEN+open_state.
    """

    @staticmethod
    def _make(mode, alt_fn, dir_fn):
        return _scheduler(
            automation=CimierAutomationConfig(mode=mode),
            alt_fn=alt_fn,
            dir_fn=dir_fn,
        )

    @staticmethod
    def _close_alt_fn():
        """alt(now)=-10 < target -6, alt(future)=-5 ≥ target -6 → CLOSE remplies."""
        alt_values = [-10.0, -5.0]
        idx = [0]

        def fn(*a, **kw):
            i = idx[0]
            idx[0] += 1
            return alt_values[i] if i < len(alt_values) else -10.0
        return fn

    def test_mode_manual_open_conditions_skipped(self):
        sched, cimier, motor, _ = self._make(
            "manual",
            alt_fn=lambda *a, **kw: -15.0,
            dir_fn=lambda *a, **kw: "descending",
        )
        decision = sched.maybe_trigger(CIMIER_STATE_CLOSED)
        assert decision.trigger == "skip:disabled"
        assert cimier.commands == []
        assert motor.calls == []

    def test_mode_manual_close_conditions_skipped(self):
        sched, cimier, motor, _ = self._make(
            "manual",
            alt_fn=self._close_alt_fn(),
            dir_fn=lambda *a, **kw: "rising",
        )
        decision = sched.maybe_trigger(CIMIER_STATE_OPEN)
        assert decision.trigger == "skip:disabled"
        assert cimier.commands == []
        assert motor.calls == []

    def test_mode_semi_open_conditions_skipped(self):
        """semi : OPEN cond remplies → skip:semi_no_open, IPC unchanged."""
        sched, cimier, motor, weather = self._make(
            "semi",
            alt_fn=lambda *a, **kw: -15.0,
            dir_fn=lambda *a, **kw: "descending",
        )
        decision = sched.maybe_trigger(CIMIER_STATE_CLOSED)
        assert decision.trigger == "skip:semi_no_open"
        assert cimier.commands == []
        assert motor.calls == []
        # WeatherProvider PAS consulté en semi (court-circuit avant)
        assert weather.call_count == 0

    def test_mode_semi_close_conditions_triggers_close(self):
        """semi : CLOSE cond remplies → trigger close (3 IPC writes)."""
        sched, cimier, motor, _ = self._make(
            "semi",
            alt_fn=self._close_alt_fn(),
            dir_fn=lambda *a, **kw: "rising",
        )
        decision = sched.maybe_trigger(CIMIER_STATE_OPEN)
        assert decision.trigger == "close"
        assert motor.calls == [("tracking_stop",), ("goto", 45.0)]
        assert len(cimier.commands) == 1
        assert cimier.commands[0]["action"] == "close"

    def test_mode_full_open_conditions_triggers_open(self):
        """full : OPEN cond remplies → trigger open (cimier IPC + motor jog)."""
        sched, cimier, motor, _ = self._make(
            "full",
            alt_fn=lambda *a, **kw: -15.0,
            dir_fn=lambda *a, **kw: "descending",
        )
        decision = sched.maybe_trigger(CIMIER_STATE_CLOSED)
        assert decision.trigger == "open"
        assert len(cimier.commands) == 1
        assert cimier.commands[0]["action"] == "open"
        assert ("jog", 1.0) in motor.calls

    def test_mode_full_close_conditions_triggers_close(self):
        """full : CLOSE cond remplies → trigger close (3 IPC writes)."""
        sched, cimier, motor, _ = self._make(
            "full",
            alt_fn=self._close_alt_fn(),
            dir_fn=lambda *a, **kw: "rising",
        )
        decision = sched.maybe_trigger(CIMIER_STATE_OPEN)
        assert decision.trigger == "close"
        assert motor.calls == [("tracking_stop",), ("goto", 45.0)]
        assert len(cimier.commands) == 1


# ----------------------------------------------------------------------
# AC-3 (sub-plan v6.0-04-01) : compute_next_triggers prévisionnel
# ----------------------------------------------------------------------


class TestComputeNextTriggers:
    """Couvre la méthode pure compute_next_triggers(now) pour countdown UI."""

    @staticmethod
    def _build(mode, alt_fn, dir_fn, clock_now=None):
        sched, _, _, _ = _scheduler(
            automation=CimierAutomationConfig(mode=mode),
            alt_fn=alt_fn,
            dir_fn=dir_fn,
            clock_now=clock_now,
        )
        return sched

    def test_mode_manual_returns_none_none(self):
        """mode=manual → court-circuit (None, None) sans appeler astropy."""
        astropy_calls = [0]

        def alt_fn(*a, **kw):
            astropy_calls[0] += 1
            return -10.0

        sched = self._build("manual", alt_fn, lambda *a, **kw: "descending")
        next_open, next_close = sched.compute_next_triggers(
            datetime(2026, 5, 15, 21, 0, tzinfo=timezone.utc)
        )
        assert (next_open, next_close) == (None, None)
        assert astropy_calls[0] == 0

    def test_mode_semi_open_is_always_none(self):
        """mode=semi → next_open=None toujours (ouverture manuelle), next_close calculé.

        Setup transitionnel pour fix « détection de transition » 2026-05-02 :
        alt(now+offset)<-6 (False), alt(now+sample+offset)>=-6 (True) → 1ère transition."""
        anchor = datetime(2026, 5, 15, 4, 0, tzinfo=timezone.utc)

        # alt(t) = -15 + 0.4*minutes_elapsed, linéaire
        # → alt(now+0)=-15, alt(now+20min)=-7 (encore <-6), alt(now+25min)=-5 (>=-6).
        # close_offset ≈ closing_advance(15) + safety_margin(0 par défaut) = 15min.
        # → à now (sample 0) : close_match = rising AND alt(15min)=-9 → False.
        # → à now+5min : close_match = rising AND alt(20min)=-7 → False.
        # → à now+10min : close_match = rising AND alt(25min)=-5 ≥ -6 → True. TRANSITION.
        def alt_fn(when, *a, **kw):
            elapsed_min = (when - anchor).total_seconds() / 60
            return -15.0 + elapsed_min * 0.4

        sched = self._build(
            "semi",
            alt_fn=alt_fn,
            dir_fn=lambda *a, **kw: "rising",
        )
        next_open, next_close = sched.compute_next_triggers(anchor)
        assert next_open is None
        # next_close trouvé via la transition False→True détectée
        assert next_close is not None
        assert next_close.tzinfo is not None

    def test_mode_full_returns_both_when_horizon_covers_them(self):
        """mode=full : alt et direction varient → next_open ET next_close trouvés."""
        # Stratégie : 1ère moitié horizon = descending sous seuil, 2e moitié = rising.
        # On utilise un compteur pour simuler la trajectoire.
        anchor = datetime(2026, 5, 15, 18, 0, tzinfo=timezone.utc)

        def dir_fn(when, before, *a, **kw):
            # premières 6h après anchor → descending, puis rising
            return "descending" if (when - anchor).total_seconds() < 6 * 3600 else "rising"

        def alt_fn(when, *a, **kw):
            elapsed_h = (when - anchor).total_seconds() / 3600
            # descend de 0 à -20, puis remonte
            if elapsed_h < 6:
                return -elapsed_h * 3.5  # va de 0 à -21°
            else:
                return -21.0 + (elapsed_h - 6) * 3.5  # remonte

        sched = self._build("full", alt_fn, dir_fn, clock_now=anchor)
        next_open, next_close = sched.compute_next_triggers(anchor)
        assert next_open is not None
        assert next_close is not None
        assert next_open < next_close  # ouverture précède fermeture

    def test_returns_tz_aware_utc_datetimes(self):
        """Garantie : les datetime retournés sont UTC tz-aware.

        Setup transitionnel : alt commence > seuil (condition False à now) puis
        descend sous le seuil → 1ère transition détectée = next_open."""
        anchor = datetime(2026, 5, 15, 18, 0, tzinfo=timezone.utc)

        def alt_fn(when, *a, **kw):
            elapsed_min = (when - anchor).total_seconds() / 60
            return -10.0 - elapsed_min * 0.1  # de -10 (>seuil -12) descend

        sched = self._build(
            "full",
            alt_fn=alt_fn,
            dir_fn=lambda *a, **kw: "descending",
        )
        next_open, _ = sched.compute_next_triggers(anchor)
        assert next_open is not None
        assert next_open.tzinfo == timezone.utc

    def test_naive_now_is_assumed_utc(self):
        """now naive (sans tzinfo) → assumé UTC silencieusement.

        Setup identique au test précédent (transition descendante)."""
        anchor_naive = datetime(2026, 5, 15, 18, 0)
        anchor_utc = anchor_naive.replace(tzinfo=timezone.utc)

        def alt_fn(when, *a, **kw):
            elapsed_min = (when - anchor_utc).total_seconds() / 60
            return -10.0 - elapsed_min * 0.1

        sched = self._build(
            "full",
            alt_fn=alt_fn,
            dir_fn=lambda *a, **kw: "descending",
        )
        next_open, _ = sched.compute_next_triggers(anchor_naive)
        assert next_open is not None
        assert next_open.tzinfo == timezone.utc

    def test_astropy_runtime_error_returns_none_none(self):
        """RuntimeError astropy → (None, None) silencieusement (warning loggé)."""
        def raise_astropy(*a, **kw):
            raise RuntimeError("astropy down")

        sched = self._build("full", raise_astropy, lambda *a, **kw: "descending")
        next_open, next_close = sched.compute_next_triggers(
            datetime(2026, 5, 15, 18, 0, tzinfo=timezone.utc)
        )
        assert (next_open, next_close) == (None, None)

    def test_already_in_open_window_returns_next_transition_not_immediate(self):
        """Bug fix 2026-05-02 : si la condition d'ouverture est déjà vraie à `now`
        (pleine nuit, alt déjà sous -12° descendant), `compute_next_triggers` ne doit
        PAS retourner now+sampling (1er sample où la condition est vraie). Il doit
        chercher la prochaine **transition** = soit la prochaine descente après une
        remontée intermédiaire, soit None si pas de transition dans l'horizon.

        Avant fix : retournait systématiquement now+5min en pleine nuit.
        Après fix : transition détectée seulement quand False→True."""
        anchor = datetime(2026, 5, 15, 23, 0, tzinfo=timezone.utc)  # pleine nuit

        # alt = -20° en permanence + descending → condition open déjà vraie.
        # Attendu : pas de transition False→True détectée → next_open = None.
        sched = self._build(
            "full",
            alt_fn=lambda *a, **kw: -20.0,
            dir_fn=lambda *a, **kw: "descending",
        )
        next_open, _ = sched.compute_next_triggers(anchor)
        assert next_open is None, (
            "next_open ne doit pas être retourné quand la condition est déjà "
            "vraie à now (sinon UI countdown affiche 4 min en boucle)"
        )

    def test_no_match_within_24h_returns_none(self):
        """Si aucun match dans l'horizon 24h → None (pas de plantage)."""
        # alt toujours positif et flat → ni open ni close ne matchent
        sched = self._build(
            "full",
            alt_fn=lambda *a, **kw: 30.0,
            dir_fn=lambda *a, **kw: "flat",
        )
        next_open, next_close = sched.compute_next_triggers(
            datetime(2026, 5, 15, 12, 0, tzinfo=timezone.utc)
        )
        assert (next_open, next_close) == (None, None)


# ----------------------------------------------------------------------
# Hot-reload mode (v6.0 Phase 4 sub-plan 04-02 fix UX)
# ----------------------------------------------------------------------


class TestRefreshModeFromConfig:
    """`CimierScheduler.refresh_mode_from_config` permet de propager au prochain
    tick scheduler un changement de mode persisté dans data/config.json (typiquement
    suite à un POST /api/cimier/automation/), sans nécessiter de redémarrage du
    cimier_service. Évite l'UX cryptique « ⚠ redémarrage cimier_service requis »."""

    @staticmethod
    def _build(initial_mode):
        sched, _, _, _ = _scheduler(
            automation=CimierAutomationConfig(mode=initial_mode),
            alt_fn=lambda *a, **kw: 0.0,
            dir_fn=lambda *a, **kw: "flat",
        )
        return sched

    def test_refresh_returns_true_when_mode_changes(self, tmp_path):
        sched = self._build("manual")
        config_file = tmp_path / "config.json"
        config_file.write_text(json.dumps({"cimier": {"automation": {"mode": "full"}}}))
        changed = sched.refresh_mode_from_config(config_file)
        assert changed is True
        assert sched._cfg.mode == "full"

    def test_refresh_returns_false_when_mode_unchanged(self, tmp_path):
        sched = self._build("semi")
        config_file = tmp_path / "config.json"
        config_file.write_text(json.dumps({"cimier": {"automation": {"mode": "semi"}}}))
        changed = sched.refresh_mode_from_config(config_file)
        assert changed is False
        assert sched._cfg.mode == "semi"

    def test_refresh_handles_legacy_enabled_true_as_full(self, tmp_path):
        sched = self._build("manual")
        config_file = tmp_path / "config.json"
        config_file.write_text(json.dumps({"cimier": {"automation": {"enabled": True}}}))
        assert sched.refresh_mode_from_config(config_file) is True
        assert sched._cfg.mode == "full"

    def test_refresh_handles_legacy_enabled_false_as_manual(self, tmp_path):
        sched = self._build("full")
        config_file = tmp_path / "config.json"
        config_file.write_text(json.dumps({"cimier": {"automation": {"enabled": False}}}))
        assert sched.refresh_mode_from_config(config_file) is True
        assert sched._cfg.mode == "manual"

    def test_refresh_returns_false_on_io_error(self, tmp_path):
        """Fichier absent → log warning + return False, mode in-memory inchangé."""
        sched = self._build("full")
        missing_file = tmp_path / "missing.json"
        changed = sched.refresh_mode_from_config(missing_file)
        assert changed is False
        assert sched._cfg.mode == "full"

    def test_refresh_returns_false_on_invalid_json(self, tmp_path):
        sched = self._build("semi")
        config_file = tmp_path / "config.json"
        config_file.write_text("{not json")
        changed = sched.refresh_mode_from_config(config_file)
        assert changed is False
        assert sched._cfg.mode == "semi"

    def test_refresh_falls_back_to_manual_for_invalid_mode(self, tmp_path):
        """Mode invalide ('yolo') et pas de legacy enabled → fallback 'manual'."""
        sched = self._build("full")
        config_file = tmp_path / "config.json"
        config_file.write_text(json.dumps({"cimier": {"automation": {"mode": "yolo"}}}))
        changed = sched.refresh_mode_from_config(config_file)
        assert changed is True
        assert sched._cfg.mode == "manual"
