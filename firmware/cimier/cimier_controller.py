"""
Logique métier cimier — module pur Python testable.

Tourne en :
  - MicroPython sur Pico W (firmware/cimier/main.py)
  - CPython sur dev machine (tests pytest)

Aucun import GPIO/Pin/Network ici. Hardware abstrait via duck typing
sur l'argument hardware_adapter qui doit exposer :
  - read_open_switch() -> bool       (True si butée ouverte atteinte)
  - read_closed_switch() -> bool     (True si butée fermée atteinte)
  - set_direction(direction: int)    (0 ou 1, sens moteur driver)
  - pulse_step()                     (un pas STEP au driver)
"""

# Constantes états (string pour sérialisation REST)
STATE_CLOSED = "closed"
STATE_OPENING = "opening"
STATE_OPEN = "open"
STATE_CLOSING = "closing"
STATE_ERROR = "error"
STATE_UNKNOWN = "unknown"

# Direction moteur (sens nominal, modifiable via invert_direction)
_DIR_OPEN_NOMINAL = 1
_DIR_CLOSE_NOMINAL = 0

# Limites de sécurité par défaut
DEFAULT_STEPS_PER_CYCLE = 3200       # 1 tour @ 16 microsteps
DEFAULT_CYCLE_TIMEOUT_S = 90         # > 60 s nominaux, marge sécurité

# Versions firmware
FIRMWARE_VERSION = "0.1.0"
FIRMWARE_PROTOCOL_VERSION = 1


def _direction_for(action_open, invert):
    """Calcule le bit de direction selon action et inversion config."""
    nominal = _DIR_OPEN_NOMINAL if action_open else _DIR_CLOSE_NOMINAL
    if invert:
        return 1 - nominal
    return nominal


class CimierController:
    """État machine + logique d'orchestration du cimier.

    Le hardware est abstrait : sur Pico W → vrai GPIO ; en tests → mock.
    Le temps est injecté pour tests reproductibles.
    """

    def __init__(self, hardware_adapter, time_provider,
                 steps_per_cycle=DEFAULT_STEPS_PER_CYCLE,
                 cycle_timeout_s=DEFAULT_CYCLE_TIMEOUT_S,
                 invert_direction=False):
        self._hw = hardware_adapter
        self._time = time_provider
        self._steps_per_cycle = steps_per_cycle
        self._cycle_timeout_s = cycle_timeout_s
        self._invert_direction = bool(invert_direction)

        self._state = STATE_UNKNOWN
        self._cycle_start_ts = None
        self._cycle_steps_done = 0
        self._last_action_ts = self._time()
        self._last_error_message = ""

        self._refresh_state_from_switches()

    # ------------------------------------------------------------------
    # Lecture switches → mise à jour de l'état au repos uniquement
    # ------------------------------------------------------------------

    def _refresh_state_from_switches(self):
        """Synchronise l'état machine sur la lecture physique des switches.

        Ne fait rien si un cycle est en cours (l'état serait écrasé).
        """
        if self._state in (STATE_OPENING, STATE_CLOSING):
            return

        open_triggered = bool(self._hw.read_open_switch())
        closed_triggered = bool(self._hw.read_closed_switch())

        if open_triggered and closed_triggered:
            self._state = STATE_ERROR
            self._last_error_message = "both_switches_triggered"
        elif open_triggered:
            self._state = STATE_OPEN
            self._last_error_message = ""
        elif closed_triggered:
            self._state = STATE_CLOSED
            self._last_error_message = ""
        else:
            self._state = STATE_UNKNOWN
            self._last_error_message = ""

    # ------------------------------------------------------------------
    # API publique : commandes
    # ------------------------------------------------------------------

    def start_open(self):
        """Démarre cycle ouverture. Idempotent si déjà open ou opening.

        Si fermeture en cours, l'arrête d'abord avant d'inverser.
        """
        self._refresh_state_from_switches()
        if self._state == STATE_OPEN:
            return  # déjà ouvert, no-op
        if self._state == STATE_OPENING:
            return  # déjà en cours
        if self._state == STATE_CLOSING:
            self._abort_cycle()

        self._begin_cycle(STATE_OPENING, action_open=True)

    def start_close(self):
        """Démarre cycle fermeture. Idempotent si déjà closed ou closing."""
        self._refresh_state_from_switches()
        if self._state == STATE_CLOSED:
            return
        if self._state == STATE_CLOSING:
            return
        if self._state == STATE_OPENING:
            self._abort_cycle()

        self._begin_cycle(STATE_CLOSING, action_open=False)

    def stop(self):
        """Arrête tout cycle en cours immédiatement et resync sur switches."""
        if self._state in (STATE_OPENING, STATE_CLOSING):
            self._abort_cycle()
        self._refresh_state_from_switches()
        self._last_action_ts = self._time()

    def tick(self):
        """À appeler périodiquement (haute fréquence) pendant un cycle.

        Lit les switches, émet un pas STEP si pas en butée, gère le timeout.
        Returns:
            bool: True si un pas a été émis, False sinon.
        """
        if self._state not in (STATE_OPENING, STATE_CLOSING):
            return False

        # Vérifier butée d'arrivée
        if self._state == STATE_OPENING and self._hw.read_open_switch():
            self._end_cycle(STATE_OPEN)
            return False
        if self._state == STATE_CLOSING and self._hw.read_closed_switch():
            self._end_cycle(STATE_CLOSED)
            return False

        # Vérifier timeout
        elapsed = self._time() - self._cycle_start_ts
        if elapsed > self._cycle_timeout_s:
            self._state = STATE_ERROR
            self._last_error_message = "cycle_timeout"
            self._cycle_start_ts = None
            self._last_action_ts = self._time()
            return False

        # Sécurité : pas dépassé le quota théorique
        if self._cycle_steps_done >= self._steps_per_cycle * 2:
            self._state = STATE_ERROR
            self._last_error_message = "step_count_exceeded"
            self._cycle_start_ts = None
            self._last_action_ts = self._time()
            return False

        # Émettre un pas
        self._hw.pulse_step()
        self._cycle_steps_done += 1
        return True

    # ------------------------------------------------------------------
    # Configuration runtime (POST /config)
    # ------------------------------------------------------------------

    def set_invert_direction(self, invert):
        """Modifie le sens moteur sans reflasher.

        Ne prend effet qu'au prochain cycle (pas en plein milieu).
        """
        self._invert_direction = bool(invert)

    @property
    def invert_direction(self):
        return self._invert_direction

    @property
    def state(self):
        return self._state

    @property
    def steps_done(self):
        return self._cycle_steps_done

    # ------------------------------------------------------------------
    # Sérialisation REST
    # ------------------------------------------------------------------

    def to_status_dict(self):
        """Format pour réponse GET /status."""
        return {
            "state": self._state,
            "open_switch": bool(self._hw.read_open_switch()),
            "closed_switch": bool(self._hw.read_closed_switch()),
            "cycle_steps_done": self._cycle_steps_done,
            "last_action_ts": self._last_action_ts,
            "error_message": self._last_error_message,
        }

    def to_info_dict(self):
        """Format pour réponse GET /info — métadonnées firmware."""
        return {
            "firmware_version": FIRMWARE_VERSION,
            "protocol_version": FIRMWARE_PROTOCOL_VERSION,
            "steps_per_cycle": self._steps_per_cycle,
            "cycle_timeout_s": self._cycle_timeout_s,
            "invert_direction": self._invert_direction,
        }

    # ------------------------------------------------------------------
    # Internals
    # ------------------------------------------------------------------

    def _begin_cycle(self, target_state, action_open):
        self._state = target_state
        self._cycle_start_ts = self._time()
        self._cycle_steps_done = 0
        self._last_action_ts = self._cycle_start_ts
        self._last_error_message = ""
        direction = _direction_for(action_open, self._invert_direction)
        self._hw.set_direction(direction)

    def _abort_cycle(self):
        self._cycle_start_ts = None
        self._cycle_steps_done = 0
        # état remis à STATE_UNKNOWN provisoirement, sera réécrit par
        # _refresh_state_from_switches() ensuite
        self._state = STATE_UNKNOWN

    def _end_cycle(self, final_state):
        self._state = final_state
        self._cycle_start_ts = None
        self._last_action_ts = self._time()
        self._last_error_message = ""
