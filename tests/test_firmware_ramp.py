"""
Tests du firmware RP2040 : rampe a acceleration constante (v6.19, v6.19.1).

Le firmware tourne en MicroPython sur le Pico, mais `firmware/ramp.py` est du
Python pur et `firmware/step_generator.py` ne depend de `rp2`/`machine` que
pour l'acces materiel : des doublures suffisent a verrouiller la logique
d'emission, qui ne peut pas etre deboguee une fois flashee sur site.

Depuis la v6.19.1, tous les mouvements avec rampe utilisent le profil a
acceleration constante : la rampe v4.5 (delai interpole sur 500 pas) et ses
tests d'equivalence ont ete retires avec elle.
"""

import sys
import types
from pathlib import Path

import pytest

FIRMWARE_DIR = Path(__file__).resolve().parent.parent / "firmware"


# =============================================================================
# DOUBLURES MICROPYTHON
# =============================================================================


class FakeStateMachine:
    """Enregistre les mots pousses dans le FIFO TX du PIO."""

    def __init__(self, *args, **kwargs):
        self.words = []
        self.active_calls = []
        self.restarts = 0

    def restart(self):
        self.restarts += 1

    def active(self, value):
        self.active_calls.append(value)

    def put(self, value):
        self.words.append(value)

    def exec(self, instruction):
        pass


class FakePin:
    OUT = 1

    def __init__(self, *args, **kwargs):
        self._value = kwargs.get("value", 0)

    def value(self, v=None):
        if v is None:
            return self._value
        self._value = v


def _install_micropython_doubles():
    """Injecte des doublures `rp2`/`machine` avant l'import du firmware."""
    rp2 = types.ModuleType("rp2")

    class PIO:
        OUT_LOW = 0

    rp2.PIO = PIO
    # Le decorateur ne doit jamais executer le corps assembleur (pull, mov...)
    rp2.asm_pio = lambda *a, **k: (lambda fn: object())
    rp2.StateMachine = FakeStateMachine

    machine = types.ModuleType("machine")
    machine.Pin = FakePin

    sys.modules.setdefault("rp2", rp2)
    sys.modules.setdefault("machine", machine)


_install_micropython_doubles()
if str(FIRMWARE_DIR) not in sys.path:
    sys.path.insert(0, str(FIRMWARE_DIR))

from step_generator import StepGenerator  # noqa: E402


@pytest.fixture
def sg():
    """StepGenerator adosse aux doublures."""
    return StepGenerator(step_pin=2, dir_pin=3)


# =============================================================================
# CONVERSION DELAI -> DEMI-PERIODE PIO
# =============================================================================


class TestDelaysToCycles:
    """Le PIO tourne a 125 MHz : 1 cycle = 8 ns."""

    def test_conversion_conforme_a_la_demi_periode(self, sg):
        """260 us -> 16248 demi-cycles (32503 cycles total, soit 260,02 us)."""
        assert sg._delay_us_to_cycles(260) == 16248

    def test_cible_boitier_constructeur(self, sg):
        """124 us (~90°/min) reste exactement representable."""
        half = sg._delay_us_to_cycles(124)
        # periode = 2 demi-periodes + 5 cycles d'overhead du programme PIO
        periode_us = (2 * half + 5) / 125.0
        assert periode_us == pytest.approx(124, rel=0.001)


# =============================================================================
# RAMPE A ACCELERATION CONSTANTE ET STOP DOUX (v6.19)
# =============================================================================
#
# Terrain 27/09/2026 : a 110 us, la rampe v4.5 gagne la moitie de la vitesse
# en 14 ms (pic 738 000 pas/s^2, a pleine vitesse) — demarrages et arrets
# brutaux, decrochage a 100 us juste apres la rampe. Les mouvements plus
# rapides que 260 us passent a une rampe a acceleration constante, emise en
# paliers PIO de 20 ms. Spec : docs/superpowers/specs/2026-09-27-rampe-acceleration-constante.md

from ramp import (  # noqa: E402
    DEFAULT_ACCEL,
    RAMP_START_DELAY_US,
    STOP_IMMEDIAT_DELAY_US,
    ProfilAccelConstante,
    arret_doux,
    lire_accel,
)

ACCEL = 4545  # 110 us atteints en 2 s


def _vitesse(delay_us):
    return 1e6 / delay_us


def _tout(profil):
    return list(profil.paliers())


class TestArretDoux:
    """STOP doux au-dessus de 260 us ; immediat a 260 us et plus lent.

    La calibration envoie un STOP au microswitch 45° puis avance de 0,5°
    (plafond : contacts de charge des batteries) : un STOP doux a 260 us y
    ajouterait ~0,34° de glissement (decision JP, 27/09/2026).
    """

    def test_rapide_stop_doux(self):
        assert arret_doux(110)
        assert arret_doux(259)

    def test_lent_stop_immediat(self):
        assert STOP_IMMEDIAT_DELAY_US == 260
        assert not arret_doux(260)
        assert not arret_doux(1000)


class TestJogLent:
    """v6.19.1 : la fin d'un JOG 1° a 260 us etait brutale (terrain Serge).

    La rampe v4.5 y perdait la moitie de la vitesse en 48 ms (pic
    74 000 pas/s^2) : les mouvements lents passent eux aussi au profil a
    acceleration constante.
    """

    ACCEL_124 = 4032  # 124 us atteints en 2 s

    def test_jog_1_degre_trapezoidal(self):
        profil = ProfilAccelConstante(5394, 260, self.ACCEL_124)
        paliers = _tout(profil)
        assert sum(n for n, _ in paliers) == 5394
        assert min(d for _, d in paliers) == 260  # croisiere atteinte
        k = len(profil.rampe)
        assert paliers[-k:] == list(reversed(profil.rampe))  # descente douce

    def test_deceleration_bornee(self):
        profil = ProfilAccelConstante(5394, 260, self.ACCEL_124)
        descente = list(reversed(profil.rampe))
        for (n1, d1), (_, d2) in zip(descente, descente[1:]):
            decel = (_vitesse(d1) - _vitesse(d2)) / (n1 * d1 / 1e6)
            assert decel <= self.ACCEL_124 * 1.15

    def test_correction_de_suivi_triangulaire(self):
        """0,3° (1618 pas) : trop court pour atteindre 260 us, total exact."""
        profil = ProfilAccelConstante(1618, 260, self.ACCEL_124)
        paliers = _tout(profil)
        assert sum(n for n, _ in paliers) == 1618
        assert paliers[0][1] < RAMP_START_DELAY_US


class TestLireAccel:
    """6e jeton optionnel de MOVE : compatible avec l'ancien protocole."""

    def test_absent_donne_le_defaut(self):
        assert lire_accel(["MOVE", "100", "1", "110", "SCURVE"]) == DEFAULT_ACCEL

    def test_present(self):
        assert lire_accel(["MOVE", "100", "1", "110", "SCURVE", "3000"]) == 3000

    @pytest.mark.parametrize("jeton", ["abc", "0", "-5"])
    def test_invalide_donne_le_defaut(self, jeton):
        assert lire_accel(["MOVE", "100", "1", "110", "SCURVE", jeton]) == DEFAULT_ACCEL


class TestProfilAccelConstante:
    @pytest.mark.parametrize("total", [200_000, 20_000, 16_182, 5_000, 300, 5, 1])
    def test_total_de_pas_exact(self, total):
        profil = ProfilAccelConstante(total, 110, ACCEL)
        assert sum(n for n, _ in _tout(profil)) == total

    def test_montee_monotone_jusqu_a_la_cible(self):
        profil = ProfilAccelConstante(200_000, 110, ACCEL)
        delais = [d for _, d in profil.rampe]
        assert all(b < a for a, b in zip(delais, delais[1:]))
        assert delais[-1] == pytest.approx(110, rel=0.01)
        assert delais[-1] >= 110  # jamais plus vite que la cible

    def test_duree_de_montee_conforme_a_l_acceleration(self):
        """110 us a 4545 pas/s^2 : ~2 s."""
        profil = ProfilAccelConstante(200_000, 110, ACCEL)
        duree_s = sum(n * d for n, d in profil.rampe) / 1e6
        assert duree_s == pytest.approx(2.0, rel=0.05)

    def test_acceleration_bornee(self):
        """Aucun saut de vitesse entre paliers au-dela de l'acceleration demandee."""
        profil = ProfilAccelConstante(200_000, 110, ACCEL)
        for (n1, d1), (_, d2) in zip(profil.rampe, profil.rampe[1:]):
            duree_s = n1 * d1 / 1e6
            assert (_vitesse(d2) - _vitesse(d1)) / duree_s <= ACCEL * 1.15

    def test_pic_tres_inferieur_a_la_rampe_historique(self):
        """Le cas qui motive le chantier : 738 000 pas/s^2 a 110 us."""
        profil = ProfilAccelConstante(200_000, 110, ACCEL)
        pic = max(
            (_vitesse(d2) - _vitesse(d1)) / (n1 * d1 / 1e6)
            for (n1, d1), (_, d2) in zip(profil.rampe, profil.rampe[1:])
        )
        assert pic < 738_000 / 50

    def test_descente_miroir_de_la_montee(self):
        profil = ProfilAccelConstante(200_000, 110, ACCEL)
        paliers = _tout(profil)
        k = len(profil.rampe)
        assert paliers[:k] == profil.rampe
        assert paliers[-k:] == list(reversed(profil.rampe))

    def test_croisiere_a_la_cible_en_troncons_courts(self):
        """Tronçons courts : un STOP est pris en compte rapidement."""
        profil = ProfilAccelConstante(200_000, 110, ACCEL)
        k = len(profil.rampe)
        croisiere = _tout(profil)[k:-k]
        assert croisiere
        assert all(d == 110 for _, d in croisiere)
        assert all(n * 110 <= 25_000 for n, _ in croisiere)  # <= 25 ms

    def test_mouvement_court_triangulaire(self):
        """Trop court pour monter jusqu'a la cible : on redescend a mi-course."""
        profil = ProfilAccelConstante(5_000, 110, ACCEL)
        delais = [d for _, d in _tout(profil)]
        assert min(delais) > 110
        pic = delais.index(min(delais))
        assert all(b <= a for a, b in zip(delais[:pic], delais[1:pic + 1]))
        assert all(b >= a for a, b in zip(delais[pic:], delais[pic + 1:]))


class TestStopDoux:
    def test_stop_en_croisiere_redescend_depuis_la_cible(self):
        profil = ProfilAccelConstante(200_000, 110, ACCEL)
        k = len(profil.rampe)
        gen = profil.paliers()
        emis = [next(gen) for _ in range(k + 3)]  # montee + 3 tronçons
        profil.demander_arret()
        reste = list(gen)

        assert reste == list(reversed(profil.rampe))
        assert sum(n for n, _ in emis + reste) < 200_000

    def test_stop_en_montee_redescend_depuis_la_vitesse_atteinte(self):
        profil = ProfilAccelConstante(200_000, 110, ACCEL)
        gen = profil.paliers()
        emis = [next(gen) for _ in range(10)]
        profil.demander_arret()
        reste = list(gen)

        assert reste == list(reversed(emis))

    def test_stop_en_descente_termine_la_descente(self):
        profil = ProfilAccelConstante(200_000, 110, ACCEL)
        paliers = _tout(ProfilAccelConstante(200_000, 110, ACCEL))
        gen = profil.paliers()
        emis = [next(gen) for _ in range(len(paliers) - 5)]
        profil.demander_arret()
        reste = list(gen)

        assert emis + reste == paliers

    def test_stop_avant_tout_palier(self):
        profil = ProfilAccelConstante(200_000, 110, ACCEL)
        profil.demander_arret()
        assert _tout(profil) == []


class TestMoveSegments:
    """Emission des paliers vers le PIO."""

    @pytest.fixture
    def sg_rapide(self, sg):
        sg._ticks_ms = lambda: 0
        sg._attendre_fin = lambda debut_ms, duree_us: None
        return sg

    def test_deux_mots_par_palier(self, sg_rapide):
        paliers = [(10, 3000), (20, 1000), (5, 110)]
        done, stopped = sg_rapide.move_segments(iter(paliers))

        assert (done, stopped) == (35, False)
        attendu = []
        for n, d in paliers:
            attendu += [n - 1, sg_rapide._delay_us_to_cycles(d)]
        assert sg_rapide._sm.words == attendu

    def test_stop_appelle_on_stop_et_continue_la_descente(self, sg_rapide):
        profil = ProfilAccelConstante(200_000, 110, ACCEL)
        appels = {"n": 0}

        def stop_checker():
            appels["n"] += 1
            return appels["n"] == 5

        done, stopped = sg_rapide.move_segments(
            profil.paliers(), stop_checker=stop_checker, on_stop=profil.demander_arret
        )

        mots = sg_rapide._sm.words
        emis = [(mots[i] + 1, mots[i + 1]) for i in range(0, len(mots), 2)]
        assert stopped is True
        assert done == sum(n for n, _ in emis)
        assert emis[-4:] == list(reversed(emis[:4]))  # redescente miroir

    def test_stop_immediat_sans_on_stop(self, sg):
        """Mouvement lent : STOP coupe net, pas emis deduits du temps ecoule."""
        sg._ticks_ms = lambda: 0
        sg._ms_depuis = lambda debut_ms: 15  # STOP recu 15 ms apres le debut
        sg._attendre_fin = lambda debut_ms, duree_us: None
        paliers = [(10, 1000), (20, 500), (100, 260), (100, 260)]
        appels = {"n": 0}

        def stop_checker():
            appels["n"] += 1
            return appels["n"] == 4

        done, stopped = sg.move_segments(iter(paliers), stop_checker=stop_checker)

        # 10 pas en 10 ms, puis 5 ms a 500 us = 10 pas
        assert (done, stopped) == (20, True)
        assert len(sg._sm.words) == 6  # le 4e palier n'est jamais pousse
        assert sg._sm.active_calls[-1] == 0

    def test_state_machine_relachee(self, sg_rapide):
        sg_rapide.move_segments(iter([(10, 200)]))
        assert sg_rapide._sm.active_calls[-1] == 0
        assert sg_rapide.is_moving is False
