"""
Rampe a acceleration constante pour RP2040 (v6.19).

La vitesse croit lineairement (acceleration constante) en paliers de
SEGMENT_S, emis tels quels au PIO qui les enchaine sans coupure.

Remplace la rampe v4.5, qui interpolait le DELAI sur 500 pas : la vitesse
etant son inverse, tout le gain se faisait a la fin (a 110 us : moitie de la
vitesse en 14 ms, pic 738 000 pas/s^2 a pleine vitesse ; a 260 us : 48 ms).
Demarrages et arrets brutaux, decrochage a 100 us juste apres la rampe
(terrain 27/09/2026). v6.19 : mouvements rapides ; v6.19.1 : tous (la fin
d'un JOG 1° a 260 us restait brutale).

Usage:
    profil = ProfilAccelConstante(total_steps=5000, target_delay_us=124, accel=4032)
    for n, delai_us in profil.paliers():   # (nombre de pas, delai) a emettre
        ...
"""

import math

RAMP_START_DELAY_US = 3000   # 3 ms — delai de demarrage lent

STOP_IMMEDIAT_DELAY_US = 260 # a partir de ce delai : STOP immediat (calibration)
DEFAULT_ACCEL = 4545         # pas/s^2 si MOVE n'en precise pas (110 us en 2 s)
SEGMENT_S = 0.02             # duree d'un palier / d'un troncon de croisiere


def arret_doux(delay_us):
    """True si un STOP doit decelerer (mouvements rapides) plutot que couper net.

    A 260 us et plus lent, STOP immediat : la calibration envoie un STOP au
    microswitch 45° puis avance de 0,5° au plus (contacts de charge des
    batteries) ; un STOP doux y ajouterait ~0,34° de glissement.
    """
    return delay_us < STOP_IMMEDIAT_DELAY_US


def lire_accel(parts):
    """Acceleration (pas/s^2) : 6e jeton optionnel de MOVE, sinon le defaut.

    Optionnel pour rester compatible dans les deux sens : l'ancien firmware
    ignore ce jeton, et un Pi non mis a jour ne l'envoie pas.
    """
    if len(parts) > 5:
        try:
            accel = int(parts[5])
            if accel > 0:
                return accel
        except ValueError:
            pass
    return DEFAULT_ACCEL


class ProfilAccelConstante:
    """
    Profil trapezoidal de vitesse, en paliers (nombre_de_pas, delai_us).

    - montee : `rampe`, de RAMP_START_DELAY_US vers la cible ;
    - croisiere : troncons de SEGMENT_S a la cible ;
    - descente : miroir de la montee.

    Mouvement trop court : profil triangulaire (on redescend a mi-course).
    `demander_arret()` fait redescendre depuis la vitesse atteinte : le
    nombre total de pas emis reste exactement la somme des paliers produits.
    """

    def __init__(self, total_steps, target_delay_us, accel=DEFAULT_ACCEL):
        self.total_steps = total_steps
        self._arret = False

        v0 = 1_000_000 / RAMP_START_DELAY_US
        vt = 1_000_000 / target_delay_us

        rampe = []
        if vt > v0:
            duree = (vt - v0) / accel
            k_max = max(1, math.ceil(duree / SEGMENT_S))
            dt = duree / k_max
            for k in range(k_max):
                v = v0 + accel * (k + 0.5) * dt
                # Delai non arrondi : le PIO resout 8 ns, 1 us d'arrondi
                # ferait des sauts de vitesse de ~1 % entre paliers.
                delai = max(target_delay_us, 1_000_000 / v)
                rampe.append((max(1, int(v * dt + 0.5)), delai))

        # Troncature triangulaire : montee + descente doivent tenir dans le mouvement
        cumul = 0
        garde = 0
        for n, _ in rampe:
            if 2 * (cumul + n) > total_steps:
                break
            cumul += n
            garde += 1
        complet = garde == len(rampe)
        self.rampe = rampe[:garde]

        if complet:
            self.croisiere_delay = target_delay_us
        elif self.rampe:
            self.croisiere_delay = self.rampe[-1][1]
        else:
            self.croisiere_delay = RAMP_START_DELAY_US
        self.plateau = total_steps - 2 * cumul
        self._troncon = max(1, int(SEGMENT_S * 1_000_000 / self.croisiere_delay))

    def demander_arret(self):
        """STOP doux : redescendre depuis la vitesse atteinte."""
        self._arret = True

    def paliers(self):
        """Genere les paliers (nombre_de_pas, delai_us) a emettre."""
        montes = 0
        for palier in self.rampe:
            if self._arret:
                break
            yield palier
            montes += 1

        if self._arret:
            for palier in reversed(self.rampe[:montes]):
                yield palier
            return

        reste = self.plateau
        while reste > 0:
            if self._arret:
                break
            n = min(self._troncon, reste)
            yield (n, self.croisiere_delay)
            reste -= n

        for palier in reversed(self.rampe):
            yield palier
