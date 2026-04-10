"""
Generateur d'impulsions STEP/DIR via PIO state machine (RP2040).

Version 2 : PIO autonome avec compteur interne.
Le PIO genere N pas en autonome sans intervention Python par pas,
eliminant l'overhead de l'interpreteur MicroPython (~10-20us/pas).

Deux modes :
- Autonome (croisiere) : PIO recoit N + delai, boucle en interne
- Variable (rampe) : PIO recoit 1 pas + delai a chaque iteration

Usage:
    sg = StepGenerator(step_pin=2, dir_pin=3)
    sg.set_direction(1)  # CW
    sg.move_steps(5000, 150)  # 5000 pas, 150 us — PIO autonome
"""

import rp2
from machine import Pin
import time


# Programme PIO autonome : genere N impulsions STEP avec compteur interne.
#
# Lit 2 mots du FIFO TX :
#   1. Nombre de pas - 1 (Y = compteur, jmp y-- fait N+1 iterations)
#   2. Demi-periode en cycles (delai entre fronts montant/descendant)
#
# Boucle interne : HIGH → wait X cycles → LOW → wait X cycles → Y--
# Quand Y atteint 0, retourne en attente (wrap vers pull block).
#
# A 125 MHz, chaque cycle = 8 ns.
# Pour 116 us (cible 96°/min) : cycles = 116 * 125 / 2 = 7250
#
# Pour mode variable (rampe) : envoyer N-1=0 et delai pour chaque pas.
# Le PIO execute 1 pas puis retourne en attente.
#
# 10 instructions (max 32).

@rp2.asm_pio(set_init=rp2.PIO.OUT_LOW)
def step_pulse_auto():
    """Programme PIO autonome pour generation de N impulsions STEP."""
    # Lire nombre de pas (N-1) depuis FIFO
    pull(block)                         # [0] Attend step count
    mov(y, osr)                         # [1] Y = compteur de pas

    # Lire demi-periode en cycles depuis FIFO
    pull(block)                         # [2] Attend half_period
    # OSR conserve la valeur — reutilisable via mov(x, osr)

    # Boucle principale : generer un pas par iteration
    label("loop_step")
    set(pins, 1)                        # [3] STEP HIGH
    mov(x, osr)                         # [4] X = demi-periode
    label("high_wait")
    jmp(x_dec, "high_wait")             # [5] Attendre X cycles

    set(pins, 0)                        # [6] STEP LOW
    mov(x, osr)                         # [7] X = demi-periode
    label("low_wait")
    jmp(x_dec, "low_wait")              # [8] Attendre X cycles

    jmp(y_dec, "loop_step")             # [9] Pas suivant (Y--)
    # Y=0 : tombe ici, wrap auto vers [0] pull(block) → attend prochain MOVE


# Frequence PIO (Hz) - horloge systeme du RP2040
PIO_FREQ = 125_000_000

# Overhead du programme PIO en cycles par impulsion
# set(1) + mov(1) + set(1) + mov(1) + jmp_y(1) = 5 cycles
# Les jmp de decompte sont inclus dans le delai
PIO_OVERHEAD_CYCLES = 5

# Intervalle de verification STOP pour mode variable (en pas)
STOP_CHECK_INTERVAL = 100


class StepGenerator:
    """
    Generateur d'impulsions STEP/DIR via PIO autonome.

    Le PIO genere les pas en interne (compteur Y), eliminant
    l'overhead de la boucle MicroPython (~10-20us/pas).

    Deux modes :
    - move_steps() : N pas a delai constant, PIO autonome
    - move_steps_variable() : N pas a delai variable (rampe accel/decel)
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
            step_pulse_auto,
            freq=PIO_FREQ,
            set_base=Pin(step_pin),
        )

        # Etat du mouvement
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

    def move_steps(self, steps, delay_us, stop_checker=None):
        """
        Execute N pas en mode PIO autonome (delai constant).

        Le PIO recoit le nombre de pas et le delai, puis genere
        toutes les impulsions en interne sans intervention Python.
        Python ne fait que surveiller le STOP pendant l'execution.

        Args:
            steps: Nombre de pas a executer
            delay_us: Delai entre pas en microsecondes
            stop_checker: Fonction retournant True si STOP recu

        Returns:
            int: Nombre de pas effectivement executes
        """
        if steps <= 0:
            return 0

        self._steps_done = 0
        self._steps_total = steps
        self._moving = True
        self._stop_flag = False

        cycles = self._delay_us_to_cycles(delay_us)
        start_ms = time.ticks_ms()
        expected_ms = (steps * delay_us) // 1000 + 1  # +1 pour arrondi

        # Reset instruction pointer puis activer la SM
        self._sm.restart()
        self._sm.active(1)
        self._sm.put(steps - 1)   # N-1 car jmp y-- compte N+1 iterations
        self._sm.put(cycles)      # Demi-periode en cycles

        # Le PIO tourne en autonome — Python surveille STOP et completion
        try:
            while True:
                elapsed_ms = time.ticks_diff(time.ticks_ms(), start_ms)

                # Completion : temps ecoule >= temps attendu
                if elapsed_ms >= expected_ms:
                    # Marge pour le dernier pas
                    time.sleep_us(delay_us)
                    self._steps_done = steps
                    return steps

                # Verification STOP
                if stop_checker and stop_checker():
                    self._stop_flag = True
                    self._sm.active(0)
                    # Securite : STEP pin LOW apres arret
                    self._sm.exec("set(pins, 0)")
                    # Estimer les pas faits depuis le temps ecoule
                    elapsed_us = elapsed_ms * 1000
                    self._steps_done = min(steps, elapsed_us // delay_us)
                    return self._steps_done

                time.sleep_ms(10)  # Poll toutes les 10ms
        finally:
            self._sm.active(0)
            self._moving = False

    def move_steps_variable(self, steps, delay_func, start_index=0,
                            stop_checker=None):
        """
        Execute N pas avec delai variable (pour phases de rampe).

        Utilise le mode pas-par-pas : chaque pas envoie 2 mots au PIO
        (count=0 pour 1 pas, puis le delai). L'overhead MicroPython est
        acceptable car les delais de rampe sont grands (3000 → 260us).

        Args:
            steps: Nombre de pas a executer
            delay_func: Fonction(index) retournant le delai en us pour ce pas
            start_index: Index de depart pour delay_func (position absolue)
            stop_checker: Fonction retournant True si STOP recu

        Returns:
            int: Nombre de pas effectivement executes
        """
        if steps <= 0:
            return 0

        self._moving = True
        self._stop_flag = False
        steps_done = 0

        # Reset instruction pointer puis activer la SM
        self._sm.restart()
        self._sm.active(1)

        try:
            for i in range(steps):
                # Verification STOP periodique
                if stop_checker and i % STOP_CHECK_INTERVAL == 0 and i > 0:
                    if stop_checker():
                        self._stop_flag = True
                        break

                delay_us = delay_func(start_index + i)
                cycles = self._delay_us_to_cycles(delay_us)

                # 1 pas : count=0 (jmp y-- avec Y=0 fait 1 iteration)
                self._sm.put(0)
                self._sm.put(cycles)
                # Le prochain put() bloquera si le FIFO est plein,
                # ce qui synchronise naturellement avec le PIO

                steps_done += 1
        finally:
            self._sm.active(0)
            self._moving = False

        self._steps_done += steps_done
        return steps_done

    def stop(self):
        """
        Arrete le mouvement en cours.

        Returns:
            int: Nombre de pas executes avant l'arret
        """
        self._stop_flag = True
        self._sm.active(0)
        # Securite : STEP pin LOW apres arret
        try:
            self._sm.exec("set(pins, 0)")
        except Exception:
            pass
        self._moving = False
        return self._steps_done

    @property
    def is_moving(self):
        """True si un mouvement est en cours."""
        return self._moving

    @property
    def steps_done(self):
        """Nombre de pas executes dans le mouvement courant/dernier."""
        return self._steps_done
