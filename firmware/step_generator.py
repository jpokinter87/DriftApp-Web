"""
Generateur d'impulsions STEP/DIR via PIO state machine (RP2040).

Utilise le PIO du RP2040 pour generer des impulsions STEP avec une
precision de 8 ns (125 MHz), eliminant le jitter de time.sleep().

Usage:
    sg = StepGenerator(step_pin=2, dir_pin=3)
    sg.set_direction(1)  # CW
    sg.move_steps(5000, 150)  # 5000 pas, 150 us entre chaque
"""

import rp2
from machine import Pin
import time


# Programme PIO : genere une impulsion STEP avec delai configurable.
#
# Le programme attend un mot de 32 bits dans le FIFO TX :
#   - bits [31:1] = nombre de cycles de delai (demi-periode)
#   - Le programme fait : pin HIGH, attend N cycles, pin LOW, attend N cycles
#
# A 125 MHz, chaque cycle = 8 ns.
# Pour un delai total de 150 us : cycles = 150 * 125 / 2 = 9375
#
# Instructions PIO :
#   pull block    : attend un mot du FIFO TX
#   mov x, osr    : copie dans X (compteur)
#   set pins, 1   : STEP HIGH
#   jmp x-- label : decompte X cycles (demi-delai)
#   set pins, 0   : STEP LOW
#   jmp x-- label : decompte X cycles (demi-delai)

@rp2.asm_pio(set_init=rp2.PIO.OUT_LOW)
def step_pulse():
    """Programme PIO pour generation d'impulsions STEP."""
    # Attendre un mot du FIFO (nombre de cycles pour demi-periode)
    pull(block)
    mov(x, osr)

    # STEP HIGH
    set(pins, 1)

    # Attendre X cycles (demi-periode haute)
    label("high_wait")
    jmp(x_dec, "high_wait")

    # Recharger le compteur depuis OSR pour la demi-periode basse
    mov(x, osr)

    # STEP LOW
    set(pins, 0)

    # Attendre X cycles (demi-periode basse)
    label("low_wait")
    jmp(x_dec, "low_wait")


# Frequence PIO (Hz) - horloge systeme du RP2040
PIO_FREQ = 125_000_000

# Overhead du programme PIO en cycles par impulsion
# pull(1) + mov(1) + set(1) + mov(1) + set(1) = 5 cycles
PIO_OVERHEAD_CYCLES = 5


class StepGenerator:
    """
    Generateur d'impulsions STEP/DIR via PIO.

    Attributes:
        step_pin: Broche GPIO pour STEP (defaut GP2)
        dir_pin: Broche GPIO pour DIR (defaut GP3)
    """

    def __init__(self, step_pin=2, dir_pin=3, sm_id=0):
        """
        Initialise le generateur PIO.

        Args:
            step_pin: Numero GPIO pour STEP (vers PUL+ du DM556T)
            dir_pin: Numero GPIO pour DIR (vers DIR+ du DM556T)
            sm_id: ID de la state machine PIO (0-7)
        """
        self._step_pin_num = step_pin
        self._dir_pin = Pin(dir_pin, Pin.OUT, value=0)
        self._direction = 0

        # Initialiser la state machine PIO
        self._sm = rp2.StateMachine(
            sm_id,
            step_pulse,
            freq=PIO_FREQ,
            set_base=Pin(step_pin),
        )

        # Compteur de pas executes (pour STOP)
        self._steps_done = 0
        self._steps_total = 0
        self._moving = False
        self._stop_flag = False

    def set_direction(self, direction):
        """
        Positionne la broche DIR.

        Args:
            direction: 0 = anti-horaire (CCW), 1 = horaire (CW)
        """
        self._direction = 1 if direction else 0
        self._dir_pin.value(self._direction)
        # Laisser le temps au DM556T de lire la direction (5 us min)
        time.sleep_us(10)

    def _delay_us_to_cycles(self, delay_us):
        """
        Convertit un delai en microsecondes en cycles PIO pour demi-periode.

        Args:
            delay_us: Delai total entre deux pas en microsecondes

        Returns:
            int: Nombre de cycles pour chaque demi-periode
        """
        # Cycles totaux pour le delai complet
        total_cycles = int(delay_us * (PIO_FREQ / 1_000_000))
        # Demi-periode (le PIO fait HIGH + wait + LOW + wait)
        half_cycles = total_cycles // 2
        # Soustraire l'overhead (reparti sur les deux demi-periodes)
        half_cycles -= PIO_OVERHEAD_CYCLES // 2
        # Minimum 1 cycle
        return max(1, half_cycles)

    def move_steps(self, steps, delay_us, delays=None):
        """
        Execute un nombre de pas avec delai uniforme ou variable.

        Args:
            steps: Nombre de pas a executer
            delay_us: Delai entre pas en microsecondes (utilise si delays=None)
            delays: Liste optionnelle de delais par pas (pour rampe)
                    Si fourni, delay_us est ignore.

        Returns:
            int: Nombre de pas effectivement executes
        """
        self._steps_done = 0
        self._steps_total = steps
        self._moving = True
        self._stop_flag = False

        # Activer la state machine
        self._sm.active(1)

        try:
            if delays is not None:
                # Mode rampe : delai variable par pas
                for i in range(steps):
                    if self._stop_flag:
                        break
                    cycles = self._delay_us_to_cycles(delays[i])
                    self._sm.put(cycles)
                    self._steps_done += 1
            else:
                # Mode uniforme : meme delai pour tous les pas
                cycles = self._delay_us_to_cycles(delay_us)
                for i in range(steps):
                    if self._stop_flag:
                        break
                    self._sm.put(cycles)
                    self._steps_done += 1
        finally:
            # Desactiver la state machine
            self._sm.active(0)
            self._moving = False

        return self._steps_done

    def stop(self):
        """
        Arrete le mouvement en cours.

        Returns:
            int: Nombre de pas executes avant l'arret
        """
        self._stop_flag = True
        # Attendre que move_steps termine sa boucle
        timeout = 100  # ms
        while self._moving and timeout > 0:
            time.sleep_ms(1)
            timeout -= 1
        # Desactiver la SM par securite
        self._sm.active(0)
        return self._steps_done

    @property
    def is_moving(self):
        """True si un mouvement est en cours."""
        return self._moving

    @property
    def steps_done(self):
        """Nombre de pas executes dans le mouvement courant/dernier."""
        return self._steps_done
