"""
Generation d'impulsions STEP/DIR pour driver DM560T cimier.

Software step generator simple : a ~50 Hz (cycle 60 s pour 3200 steps),
l'overhead MicroPython est negligeable. Pas besoin de PIO ici.

Pour le pilotage coupole haute frequence (kHz), voir firmware/step_generator.py.
"""

from machine import Pin
import time


# Largeur de l'impulsion STEP HIGH (microsecondes).
# DM560T accepte des pulses tres courts ; 5 us = marge confortable.
STEP_PULSE_WIDTH_US = 5


class SoftwareStepGenerator:
    """Generateur de pas STEP/DIR pilote en logiciel.

    Pas de timing batch : chaque pulse_step() est une impulsion immediate.
    Le caller (CimierController via tick()) controle la cadence via sleep.
    """

    def __init__(self, step_pin, dir_pin):
        self._step = Pin(step_pin, Pin.OUT, value=0)
        self._dir = Pin(dir_pin, Pin.OUT, value=0)

    def set_direction(self, direction):
        """Definit le sens (0 ou 1)."""
        self._dir.value(1 if direction else 0)

    def pulse_step(self):
        """Genere une impulsion STEP."""
        self._step.value(1)
        time.sleep_us(STEP_PULSE_WIDTH_US)
        self._step.value(0)
