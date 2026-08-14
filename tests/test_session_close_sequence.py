"""Tests de la séquence unique de fermeture de session.

Elle existait en deux copies divergentes (bug de parking 6.11.3) : ces tests
verrouillent l'ordre des opérations pour les trois appelants.
"""

from __future__ import annotations

from services.session_close_sequence import close_session


class RecordingMotorIpc:
    def __init__(self, tracking_stop_confirmed=True):
        self.calls = []
        self._confirmed = tracking_stop_confirmed

    def send_tracking_stop(self):
        self.calls.append("tracking_stop")
        return True

    def wait_tracking_stopped(self):
        self.calls.append("wait")
        return self._confirmed

    def send_goto(self, angle):
        self.calls.append("goto:%s" % angle)
        return True


def test_order_is_stop_then_wait_then_goto():
    # L'attente entre les deux est le cœur du fix 6.11.3 : motor_command.json
    # n'a qu'un slot, un goto émis trop tôt écrase le tracking_stop.
    motor = RecordingMotorIpc()
    close_session(motor, lambda: True, 45.0, reason="rain")
    assert motor.calls == ["tracking_stop", "wait", "goto:45.0"]


def test_close_callable_is_invoked():
    called = []
    close_session(RecordingMotorIpc(), lambda: called.append(True) or True, 45.0, reason="auto")
    assert called == [True]


def test_returns_outcome_of_each_step():
    result = close_session(RecordingMotorIpc(), lambda: True, 45.0, reason="rain")
    assert result["tracking_stop_sent"] is True
    assert result["tracking_stop_confirmed"] is True
    assert result["goto_sent"] is True
    assert result["cimier_close_sent"] is True
    assert result["parking_target_deg"] == 45.0


def test_timeout_on_confirmation_does_not_stop_the_sequence():
    # Best-effort : mieux vaut un parking imparfait qu'un cimier resté ouvert.
    motor = RecordingMotorIpc(tracking_stop_confirmed=False)
    result = close_session(motor, lambda: True, 45.0, reason="rain")
    assert motor.calls == ["tracking_stop", "wait", "goto:45.0"]
    assert result["tracking_stop_confirmed"] is False
    assert result["cimier_close_sent"] is True


def test_failing_close_is_reported_not_raised():
    result = close_session(RecordingMotorIpc(), lambda: False, 45.0, reason="rain")
    assert result["cimier_close_sent"] is False


def test_raising_close_is_caught():
    def _boom():
        raise RuntimeError("IPC mort")

    result = close_session(RecordingMotorIpc(), _boom, 45.0, reason="rain")
    assert result["cimier_close_sent"] is False


def test_logs_reason(caplog):
    import logging

    with caplog.at_level(logging.INFO, logger="services.session_close_sequence"):
        close_session(RecordingMotorIpc(), lambda: True, 45.0, reason="rain")
    assert "reason=rain" in caplog.text
