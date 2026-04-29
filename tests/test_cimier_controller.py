"""Tests unitaires du module partage cimier_controller.

Le module est utilise a la fois en MicroPython (firmware Pico W) et en CPython
(ces tests). Aucun import GPIO/network ici, seul le module pur est teste via un
FakeHardwareAdapter mock.
"""

from __future__ import annotations

import sys
from dataclasses import dataclass, field
from pathlib import Path

# Importer le module partage (chemin firmware/cimier/)
_FIRMWARE_DIR = Path(__file__).resolve().parents[1] / "firmware" / "cimier"
sys.path.insert(0, str(_FIRMWARE_DIR))

import cimier_controller as cc  # noqa: E402


@dataclass
class FakeHardwareAdapter:
    """Mock GPIO pour tests : etat des switches + compteur d'appels."""
    open_triggered: bool = False
    closed_triggered: bool = False
    last_direction: int = -1
    step_count: int = 0
    direction_log: list = field(default_factory=list)

    def read_open_switch(self) -> bool:
        return self.open_triggered

    def read_closed_switch(self) -> bool:
        return self.closed_triggered

    def set_direction(self, direction: int) -> None:
        self.last_direction = direction
        self.direction_log.append(direction)

    def pulse_step(self) -> None:
        self.step_count += 1


class FakeClock:
    """Horloge controllee pour tests deterministes."""
    def __init__(self, t0: float = 1000.0):
        self.now = t0

    def __call__(self) -> float:
        return self.now

    def advance(self, seconds: float) -> None:
        self.now += seconds


def make_controller(open_triggered=False, closed_triggered=False,
                    invert_direction=False, cycle_timeout_s=90):
    hw = FakeHardwareAdapter(
        open_triggered=open_triggered,
        closed_triggered=closed_triggered,
    )
    clock = FakeClock()
    ctrl = cc.CimierController(
        hw, clock,
        cycle_timeout_s=cycle_timeout_s,
        invert_direction=invert_direction,
    )
    return ctrl, hw, clock


# ----------------------------------------------------------------------
# Initialisation : etat resolu depuis les switches
# ----------------------------------------------------------------------

def test_init_state_unknown_when_no_switch():
    ctrl, _, _ = make_controller()
    assert ctrl.state == cc.STATE_UNKNOWN


def test_init_state_closed_when_closed_switch():
    ctrl, _, _ = make_controller(closed_triggered=True)
    assert ctrl.state == cc.STATE_CLOSED


def test_init_state_open_when_open_switch():
    ctrl, _, _ = make_controller(open_triggered=True)
    assert ctrl.state == cc.STATE_OPEN


def test_init_state_error_when_both_switches():
    ctrl, _, _ = make_controller(open_triggered=True, closed_triggered=True)
    assert ctrl.state == cc.STATE_ERROR


# ----------------------------------------------------------------------
# start_open : transitions et idempotence
# ----------------------------------------------------------------------

def test_start_open_from_closed_transitions_to_opening():
    ctrl, hw, _ = make_controller(closed_triggered=True)
    ctrl.start_open()
    assert ctrl.state == cc.STATE_OPENING
    # Direction nominale ouverture = 1 (sans invert)
    assert hw.last_direction == 1


def test_start_open_from_open_is_noop():
    ctrl, hw, _ = make_controller(open_triggered=True)
    ctrl.start_open()
    assert ctrl.state == cc.STATE_OPEN
    # Pas de direction set (pas de cycle demarre)
    assert hw.last_direction == -1


def test_start_open_from_opening_is_noop():
    ctrl, hw, _ = make_controller(closed_triggered=True)
    ctrl.start_open()
    direction_count_before = len(hw.direction_log)
    ctrl.start_open()  # idempotent
    assert ctrl.state == cc.STATE_OPENING
    assert len(hw.direction_log) == direction_count_before


def test_start_open_aborts_closing_cycle():
    ctrl, hw, _ = make_controller(open_triggered=True)
    ctrl.start_close()
    assert ctrl.state == cc.STATE_CLOSING
    # Re-bascule en ouverture immediatement
    ctrl.start_open()
    assert ctrl.state == cc.STATE_OPENING
    # Direction d'ouverture appliquee
    assert hw.last_direction == 1


# ----------------------------------------------------------------------
# start_close : symetrique
# ----------------------------------------------------------------------

def test_start_close_from_open_transitions_to_closing():
    ctrl, hw, _ = make_controller(open_triggered=True)
    ctrl.start_close()
    assert ctrl.state == cc.STATE_CLOSING
    assert hw.last_direction == 0  # direction fermeture nominale


def test_start_close_from_closed_is_noop():
    ctrl, hw, _ = make_controller(closed_triggered=True)
    ctrl.start_close()
    assert ctrl.state == cc.STATE_CLOSED
    assert hw.last_direction == -1


def test_start_close_aborts_opening_cycle():
    ctrl, hw, _ = make_controller(closed_triggered=True)
    ctrl.start_open()
    assert ctrl.state == cc.STATE_OPENING
    ctrl.start_close()
    assert ctrl.state == cc.STATE_CLOSING
    assert hw.last_direction == 0


# ----------------------------------------------------------------------
# stop()
# ----------------------------------------------------------------------

def test_stop_during_opening_resyncs_state_from_switches():
    ctrl, hw, _ = make_controller(closed_triggered=True)
    ctrl.start_open()
    assert ctrl.state == cc.STATE_OPENING
    # Toujours en butee fermee (cycle pas avance) -> stop revient a closed
    ctrl.stop()
    assert ctrl.state == cc.STATE_CLOSED


def test_stop_when_idle_is_safe():
    ctrl, _, _ = make_controller(closed_triggered=True)
    ctrl.stop()
    assert ctrl.state == cc.STATE_CLOSED


# ----------------------------------------------------------------------
# tick() : progression de cycle
# ----------------------------------------------------------------------

def test_tick_in_idle_does_nothing():
    ctrl, hw, _ = make_controller(closed_triggered=True)
    assert ctrl.tick() is False
    assert hw.step_count == 0


def test_tick_in_opening_emits_step():
    ctrl, hw, _ = make_controller(closed_triggered=True)
    ctrl.start_open()
    # Apres start_open, le switch closed est encore vrai cote hw
    # (le moteur n'a pas bouge), mais l'etat machine est OPENING
    # On simule une lecture switch realiste : cimier en mouvement, ni l'un ni l'autre
    hw.closed_triggered = False
    assert ctrl.tick() is True
    assert hw.step_count == 1
    assert ctrl.state == cc.STATE_OPENING


def test_tick_in_opening_with_open_switch_finishes_cycle():
    ctrl, hw, _ = make_controller(closed_triggered=True)
    ctrl.start_open()
    hw.closed_triggered = False
    # Quelques pas
    hw.open_triggered = False
    for _ in range(5):
        ctrl.tick()
    # Switch open atteint
    hw.open_triggered = True
    result = ctrl.tick()
    assert result is False  # pas de step emis (cycle fini)
    assert ctrl.state == cc.STATE_OPEN


def test_tick_in_closing_with_closed_switch_finishes_cycle():
    ctrl, hw, _ = make_controller(open_triggered=True)
    ctrl.start_close()
    hw.open_triggered = False
    for _ in range(3):
        ctrl.tick()
    hw.closed_triggered = True
    result = ctrl.tick()
    assert result is False
    assert ctrl.state == cc.STATE_CLOSED


def test_tick_timeout_sets_error():
    ctrl, hw, clock = make_controller(closed_triggered=True, cycle_timeout_s=10)
    ctrl.start_open()
    hw.closed_triggered = False
    # Simuler le passage du temps au-dela du timeout
    clock.advance(11)
    result = ctrl.tick()
    assert result is False
    assert ctrl.state == cc.STATE_ERROR


def test_tick_step_count_exceeded_sets_error():
    ctrl, hw, _ = make_controller(closed_triggered=True)
    ctrl.start_open()
    hw.closed_triggered = False
    # Faire tres tres beaucoup de pas (simulation switch jamais atteint)
    # Limite = steps_per_cycle * 2 = 6400 par defaut
    for _ in range(6400):
        ctrl.tick()
    # Le 6401e tick declenche l'erreur
    result = ctrl.tick()
    assert result is False
    assert ctrl.state == cc.STATE_ERROR


# ----------------------------------------------------------------------
# Inversion de direction
# ----------------------------------------------------------------------

def test_invert_direction_swaps_open_and_close():
    ctrl, hw, _ = make_controller(closed_triggered=True, invert_direction=True)
    ctrl.start_open()
    # Direction nominale ouverture = 1, mais invert -> 0
    assert hw.last_direction == 0


def test_invert_direction_can_be_set_runtime():
    ctrl, hw, _ = make_controller(closed_triggered=True)
    assert ctrl.invert_direction is False
    ctrl.set_invert_direction(True)
    assert ctrl.invert_direction is True
    ctrl.start_open()
    assert hw.last_direction == 0  # inverse pris en compte


# ----------------------------------------------------------------------
# Serialisation REST
# ----------------------------------------------------------------------

def test_to_status_dict_format():
    ctrl, _, _ = make_controller(closed_triggered=True)
    status = ctrl.to_status_dict()
    expected_keys = {
        "state", "open_switch", "closed_switch",
        "cycle_steps_done", "last_action_ts", "error_message",
    }
    assert set(status.keys()) == expected_keys
    assert status["state"] == cc.STATE_CLOSED
    assert status["closed_switch"] is True
    assert status["open_switch"] is False


def test_to_info_dict_format():
    ctrl, _, _ = make_controller()
    info = ctrl.to_info_dict()
    expected_keys = {
        "firmware_version", "protocol_version",
        "steps_per_cycle", "cycle_timeout_s", "invert_direction",
    }
    assert set(info.keys()) == expected_keys
    assert info["firmware_version"] == cc.FIRMWARE_VERSION
    assert info["invert_direction"] is False


# ----------------------------------------------------------------------
# Cycle complet integration
# ----------------------------------------------------------------------

def test_full_open_cycle():
    """Scenario : depart cimier ferme, ouverture complete, switch atteint."""
    ctrl, hw, _ = make_controller(closed_triggered=True)
    assert ctrl.state == cc.STATE_CLOSED

    ctrl.start_open()
    assert ctrl.state == cc.STATE_OPENING

    # Le moteur quitte la butee fermee
    hw.closed_triggered = False

    # Boucle de progression
    steps_emitted = 0
    for _ in range(100):
        if ctrl.tick():
            steps_emitted += 1

    assert steps_emitted == 100
    assert ctrl.state == cc.STATE_OPENING

    # Le moteur atteint la butee ouverte
    hw.open_triggered = True
    ctrl.tick()
    assert ctrl.state == cc.STATE_OPEN
    assert ctrl.steps_done == 100  # n'a pas continue d'incrementer


def test_full_close_cycle():
    """Scenario symetrique : depart ouvert, fermeture complete."""
    ctrl, hw, _ = make_controller(open_triggered=True)
    assert ctrl.state == cc.STATE_OPEN

    ctrl.start_close()
    hw.open_triggered = False

    for _ in range(50):
        ctrl.tick()

    hw.closed_triggered = True
    ctrl.tick()
    assert ctrl.state == cc.STATE_CLOSED
    assert ctrl.steps_done == 50


def test_open_then_immediately_close_aborts_and_inverts():
    """Scenario : utilisateur change d'avis en plein cycle."""
    ctrl, hw, _ = make_controller(closed_triggered=True)
    ctrl.start_open()
    hw.closed_triggered = False
    # Quelques pas en ouverture
    for _ in range(10):
        ctrl.tick()
    # Demande fermeture en cours de route
    ctrl.start_close()
    assert ctrl.state == cc.STATE_CLOSING
    assert hw.last_direction == 0  # direction fermeture
    # Compteur de pas remis a zero
    assert ctrl.steps_done == 0


# ----------------------------------------------------------------------
# Cas hardware degrade
# ----------------------------------------------------------------------

def test_both_switches_during_cycle_does_not_overwrite_state():
    """Switches aberrants : les deux declenches simultanement.

    Pendant un cycle, le tick() ignore l'etat 'both' (ne refresh pas).
    L'erreur n'est detectee qu'au prochain stop()/refresh.
    """
    ctrl, hw, _ = make_controller(closed_triggered=True)
    ctrl.start_open()
    hw.closed_triggered = False
    # En plein cycle, les deux switches deviennent True (cas anormal)
    hw.open_triggered = True
    hw.closed_triggered = True
    # Le tick prend la fin de course OPEN comme arret valide
    ctrl.tick()
    assert ctrl.state == cc.STATE_OPEN  # arret legitime


def test_unknown_state_after_init_when_no_switch():
    """Boot sans aucune butee : etat unknown, l'utilisateur doit choisir."""
    ctrl, _, _ = make_controller()
    assert ctrl.state == cc.STATE_UNKNOWN
    # Une commande ouvre malgre tout
    ctrl.start_open()
    assert ctrl.state == cc.STATE_OPENING
