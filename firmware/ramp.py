"""
Rampe d'acceleration/deceleration S-curve pour RP2040.

Port de core/hardware/acceleration_ramp.py adapte a MicroPython.
Memes parametres et meme comportement que la version Pi.

Usage:
    ramp = Ramp(total_steps=5000, target_delay_us=150, ramp_type="SCURVE")
    if ramp.compute_delays():                 # rampe active ?
        delays = ramp.delays_for(0, ramp.accel_end)   # delais de la phase accel
"""

import math


# Parametres de rampe (identiques a acceleration_ramp.py)
RAMP_START_DELAY_US = 3000   # 3 ms — delai de demarrage lent
RAMP_STEPS = 500             # Nombre de pas pour atteindre la vitesse nominale
MIN_STEPS_FOR_RAMP = 200     # Seuil minimum pour appliquer la rampe
SHORT_MOVEMENT_RATIO = 4     # Diviseur pour rampe proportionnelle


class Ramp:
    """
    Gestionnaire de rampe d'acceleration/deceleration.

    Calcule le delai optimal pour chaque pas en fonction de sa position
    dans le mouvement total.
    """

    def __init__(self, total_steps, target_delay_us, ramp_type="SCURVE"):
        """
        Args:
            total_steps: Nombre total de pas du mouvement
            target_delay_us: Delai cible (vitesse nominale) en microsecondes
            ramp_type: "SCURVE", "LINEAR", ou "NONE"
        """
        self.total_steps = total_steps
        self.target_delay_us = target_delay_us
        self.ramp_type = ramp_type.upper() if ramp_type else "NONE"

        self.ramp_enabled = False
        self.accel_end = 0
        self.decel_start = total_steps

        if self.ramp_type != "NONE":
            self._calculate_phases()

    def _calculate_phases(self):
        """Calcule les limites des phases d'acceleration et deceleration."""
        if self.total_steps < MIN_STEPS_FOR_RAMP:
            self.ramp_enabled = False
            return

        self.ramp_enabled = True

        if self.total_steps < 2 * RAMP_STEPS:
            # Mouvement court : rampe proportionnelle
            ramp_length = max(1, self.total_steps // SHORT_MOVEMENT_RATIO)
            self.accel_end = ramp_length
            self.decel_start = self.total_steps - ramp_length
        else:
            # Mouvement normal : rampe complete
            self.accel_end = RAMP_STEPS
            self.decel_start = self.total_steps - RAMP_STEPS

        # Securite
        if self.decel_start < self.accel_end:
            mid = self.total_steps // 2
            self.accel_end = mid
            self.decel_start = mid

    def _s_curve(self, t):
        """
        Fonction S-curve (sigmoide) pour transition douce.

        Args:
            t: Valeur normalisee entre 0 et 1

        Returns:
            Valeur interpolee avec courbe en S (0 a 1)
        """
        k = 10
        sigmoid = 1.0 / (1.0 + math.exp(-k * (t - 0.5)))
        sigmoid_0 = 1.0 / (1.0 + math.exp(-k * (-0.5)))
        sigmoid_1 = 1.0 / (1.0 + math.exp(-k * 0.5))
        return (sigmoid - sigmoid_0) / (sigmoid_1 - sigmoid_0)

    def _interpolate(self, t):
        """Interpole entre 0 et 1 selon le type de rampe."""
        if self.ramp_type == "SCURVE":
            return self._s_curve(t)
        # LINEAR
        return t

    def get_delay(self, step_index):
        """
        Calcule le delai pour un pas donne.

        Args:
            step_index: Index du pas actuel (0 a total_steps-1)

        Returns:
            int: Delai en microsecondes pour ce pas
        """
        if not self.ramp_enabled:
            return self.target_delay_us

        start = RAMP_START_DELAY_US
        target = self.target_delay_us

        # Phase d'acceleration
        if step_index < self.accel_end:
            if self.accel_end == 0:
                return target
            t = step_index / self.accel_end
            progress = self._interpolate(t)
            return int(start + (target - start) * progress)

        # Phase de deceleration
        if step_index >= self.decel_start:
            steps_in_decel = step_index - self.decel_start
            decel_length = self.total_steps - self.decel_start
            t = steps_in_decel / decel_length if decel_length > 0 else 1.0
            progress = self._interpolate(t)
            return int(target + (start - target) * progress)

        # Phase de croisiere
        return target

    def delays_for(self, start_index, count):
        """
        Pre-calcule les delais d'une tranche de pas.

        Appele une fois avant la phase, jamais pendant : get_delay() fait
        trois exp() et plafonnait la cadence quand il etait evalue par pas.

        Args:
            start_index: Index du premier pas de la tranche
            count: Nombre de pas

        Returns:
            list: Delais en microsecondes, un par pas
        """
        return [self.get_delay(start_index + i) for i in range(count)]

    def compute_delays(self):
        """
        Indique si la rampe est active (delais variables).

        Returns:
            True si rampe active (utiliser get_delay() par pas),
            None si delai uniforme
        """
        if not self.ramp_enabled:
            return None
        # Retourner True au lieu d'une liste pour eviter OOM sur RP2040
        # (53940 floats = ~430 KB > RAM disponible)
        # L'appelant utilise get_delay(i) pour chaque pas
        return True


# =============================================================================
# RAMPE A ACCELERATION CONSTANTE (v6.19) — mouvements plus rapides que 260 us
# =============================================================================
#
# La rampe ci-dessus interpole le DELAI sur 500 pas : la vitesse etant son
# inverse, tout le gain se fait a la fin (a 110 us : moitie de la vitesse en
# 14 ms, pic 738 000 pas/s^2 a pleine vitesse). Demarrages et arrets brutaux,
# decrochage a 100 us juste apres la rampe (terrain 27/09/2026).
#
# Ici la VITESSE croit lineairement (acceleration constante), en paliers de
# SEGMENT_S emis tels quels au PIO, qui les enchaine sans coupure. A 260 us et
# plus lent, la rampe historique reste utilisee (suivi, calibration : eprouves).

LEGACY_MIN_DELAY_US = 260    # a partir de ce delai : rampe historique
DEFAULT_ACCEL = 4545         # pas/s^2 si MOVE n'en precise pas (110 us en 2 s)
SEGMENT_S = 0.02             # duree d'un palier / d'un troncon de croisiere


def utilise_accel_constante(delay_us, ramp_type):
    """True si le mouvement releve de la rampe a acceleration constante."""
    return ramp_type != "NONE" and delay_us < LEGACY_MIN_DELAY_US


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
