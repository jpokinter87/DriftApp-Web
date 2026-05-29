"""Mécanisme virtuel cimier pour la simulation (pivot Shelly v6.x).

Modélise le cimier comme une position normalisée 0.0 (fermé) → 1.0 (ouvert).
Le moteur, quand allumé, fait progresser la position dans le sens courant à
vitesse fixe (course complète en ``full_travel_s`` secondes). Les fins de
course sont dérivées de la position.

Analogue à ``core/hardware/moteur_simule`` pour la coupole, mais propre au
cimier (mécanisme binaire ouvert/fermé). Le temps est injecté via ``advance``
→ déterministe et testable sans threads.
"""

from __future__ import annotations

_INITIAL_POSITIONS = {"closed": 0.0, "open": 1.0, "mid": 0.5}


class CimierMechanismSim:
    """État partagé du cimier virtuel : position, moteur, sens."""

    def __init__(
        self,
        initial_state: str = "closed",
        full_travel_s: float = 60.0,
        force_both_switches: bool = False,
    ) -> None:
        if initial_state not in _INITIAL_POSITIONS:
            raise ValueError("initial_state must be one of {}".format(sorted(_INITIAL_POSITIONS)))
        if full_travel_s <= 0:
            raise ValueError("full_travel_s must be > 0")
        self._position = _INITIAL_POSITIONS[initial_state]
        self._full_travel_s = float(full_travel_s)
        self._force_both = bool(force_both_switches)
        self._motor_on = False
        self._opening = True  # sens courant : True = ouverture

    # --- commandes (pilotées par SimMotorShelly) -----------------------
    def set_direction(self, open_direction: bool) -> None:
        self._opening = bool(open_direction)

    def set_motor(self, on: bool) -> None:
        self._motor_on = bool(on)

    # --- progression temporelle ----------------------------------------
    def advance(self, elapsed_s: float) -> None:
        """Fait progresser la position si le moteur tourne."""
        if not self._motor_on or elapsed_s <= 0:
            return
        delta = elapsed_s / self._full_travel_s
        if self._opening:
            self._position = min(1.0, self._position + delta)
        else:
            self._position = max(0.0, self._position - delta)

    # --- lectures capteurs ---------------------------------------------
    @property
    def position(self) -> float:
        return self._position

    @property
    def open_switch(self) -> bool:
        return self._force_both or self._position >= 1.0

    @property
    def closed_switch(self) -> bool:
        return self._force_both or self._position <= 0.0

    @property
    def motor_on(self) -> bool:
        return self._motor_on
