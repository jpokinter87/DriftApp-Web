"""Double de test du driver MotorShelly (pivot Shelly v6.x).

Même interface publique que ``core/hardware/motor_shelly.MotorShelly``
(``set_direction`` / ``turn_on`` / ``turn_off``) mais pilote un
``CimierMechanismSim`` en mémoire au lieu d'émettre des requêtes HTTP vers
les Shelly. Permet de tester l'orchestration ``cimier_service`` (Bloc 2) et
d'animer le simulateur en dev, sans aucun hardware.
"""

from __future__ import annotations

from core.hardware.cimier_mechanism_sim import CimierMechanismSim


class SimMotorShelly:
    """Pilote un CimierMechanismSim, imite l'interface de MotorShelly."""

    host_motor = (
        "sim"  # diagnostic : permet à _call_motor_logged d'afficher host=sim au lieu de host=noop
    )

    def __init__(self, mechanism: CimierMechanismSim) -> None:
        self._m = mechanism
        self.last_timer_s: float = 0.0
        self.calls: list[tuple[str, object]] = []

    def set_direction(self, open_direction: bool) -> None:
        self._m.set_direction(bool(open_direction))
        self.calls.append(("set_direction", bool(open_direction)))

    def turn_on(self, timer_s: float = 0.0) -> None:
        if timer_s < 0:
            raise ValueError("timer_s must be >= 0, got " + str(timer_s))
        self.last_timer_s = float(timer_s)
        self._m.set_motor(True)
        self.calls.append(("turn_on", float(timer_s)))

    def turn_off(self) -> None:
        self._m.set_motor(False)
        self.calls.append(("turn_off", None))
