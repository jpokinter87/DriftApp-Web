"""
Tests du firmware RP2040 : rampe pre-calculee (v6.16).

Le firmware tourne en MicroPython sur le Pico, mais `firmware/ramp.py` est du
Python pur et `firmware/step_generator.py` ne depend de `rp2`/`machine` que
pour l'acces materiel : des doublures suffisent a verrouiller la logique
d'emission, qui ne peut pas etre deboguee une fois flashee sur site.

Enjeu principal : prouver que la rampe pre-calculee emet exactement la meme
sequence d'impulsions que l'ancienne version calculee par pas. Le flash du
Pico est alors neutre tant que `motor_driver.delay_us` n'est pas modifie.
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

from ramp import RAMP_START_DELAY_US, RAMP_STEPS, Ramp  # noqa: E402
from step_generator import STOP_CHECK_INTERVAL, StepGenerator  # noqa: E402


@pytest.fixture
def sg():
    """StepGenerator adosse aux doublures."""
    return StepGenerator(step_pin=2, dir_pin=3)


# =============================================================================
# EQUIVALENCE AVEC L'ANCIENNE RAMPE (neutralite du flash)
# =============================================================================


class TestEquivalenceAncienneRampe:
    """La sequence emise doit etre identique a celle calculee par pas."""

    @pytest.mark.parametrize("target_us", [260, 200, 150, 124])
    def test_phase_acceleration_identique(self, sg, target_us):
        """Accel : meme sequence que `delay_func(0 + i)` pas a pas."""
        ramp = Ramp(20_000, target_us, "SCURVE")
        n = ramp.accel_end

        ancien = [sg._delay_us_to_cycles(ramp.get_delay(0 + i)) for i in range(n)]
        nouveau = sg.delays_to_cycles(ramp.delays_for(0, n))

        assert nouveau == ancien

    @pytest.mark.parametrize("target_us", [260, 200, 150, 124])
    def test_phase_deceleration_identique(self, sg, target_us):
        """Decel : l'index de depart `decel_start` est preserve.

        C'est le point ou un decalage d'un pas passerait inapercu et
        produirait un a-coup en fin de mouvement.
        """
        ramp = Ramp(20_000, target_us, "SCURVE")
        start = ramp.decel_start
        n = ramp.total_steps - start

        ancien = [sg._delay_us_to_cycles(ramp.get_delay(start + i)) for i in range(n)]
        nouveau = sg.delays_to_cycles(ramp.delays_for(start, n))

        assert nouveau == ancien

    def test_mouvement_court_rampe_proportionnelle(self, sg):
        """Les mouvements courts (< 2x RAMP_STEPS) restent identiques."""
        ramp = Ramp(800, 260, "SCURVE")
        n = ramp.accel_end

        assert n < RAMP_STEPS  # rampe proportionnelle, pas la rampe pleine
        ancien = [sg._delay_us_to_cycles(ramp.get_delay(i)) for i in range(n)]
        assert sg.delays_to_cycles(ramp.delays_for(0, n)) == ancien


# =============================================================================
# CONTINUITE DE VITESSE A L'ENTREE EN CROISIERE
# =============================================================================


class TestContinuiteVitesse:
    """La rampe doit relier le demarrage a la croisiere sans marche."""

    @pytest.mark.parametrize("target_us", [260, 200, 150, 124])
    def test_la_rampe_part_du_demarrage_et_atteint_la_cible(self, target_us):
        """Premier pas ~= RAMP_START_DELAY_US, dernier pas ~= cible."""
        ramp = Ramp(20_000, target_us, "SCURVE")
        delays = ramp.delays_for(0, ramp.accel_end)

        assert delays[0] == pytest.approx(RAMP_START_DELAY_US, rel=0.02)
        # L'ecart residuel a l'entree en croisiere doit rester marginal :
        # c'est lui qui provoquait le decrochage quand la rampe plafonnait.
        assert delays[-1] == pytest.approx(target_us, rel=0.02)

    @pytest.mark.parametrize("target_us", [260, 124])
    def test_acceleration_monotone(self, target_us):
        """Aucun pas ne doit etre plus lent que le precedent."""
        ramp = Ramp(20_000, target_us, "SCURVE")
        delays = ramp.delays_for(0, ramp.accel_end)

        assert all(b <= a for a, b in zip(delays, delays[1:]))


# =============================================================================
# EMISSION VERS LE PIO
# =============================================================================


class TestMoveStepsTable:
    """Boucle d'emission : ordre des mots, comptage, STOP."""

    def test_emet_deux_mots_par_pas_dans_l_ordre(self, sg):
        """Chaque pas pousse (0, demi-periode) — 0 = « un seul pas »."""
        cycles = [111, 222, 333]

        assert sg.move_steps_table(cycles) == 3
        assert sg._sm.words == [0, 111, 0, 222, 0, 333]

    def test_liste_vide_ne_fait_rien(self, sg):
        assert sg.move_steps_table([]) == 0
        assert sg._sm.words == []

    def test_state_machine_activee_puis_relachee(self, sg):
        sg.move_steps_table([100, 200])

        assert sg._sm.restarts == 1
        assert sg._sm.active_calls[0] == 1
        assert sg._sm.active_calls[-1] == 0
        assert sg.is_moving is False

    def test_stop_interrompt_entre_deux_tranches(self, sg):
        """STOP est honore sans attendre la fin de la table."""
        cycles = [50] * (STOP_CHECK_INTERVAL * 3)
        appels = {"n": 0}

        def stop_checker():
            appels["n"] += 1
            return appels["n"] > 2  # laisse passer deux tranches

        done = sg.move_steps_table(cycles, stop_checker=stop_checker)

        assert done == STOP_CHECK_INTERVAL * 2
        assert len(sg._sm.words) == 2 * done
        assert sg._stop_flag is True

    def test_stop_immediat_avant_le_premier_pas(self, sg):
        """Un STOP deja present n'emet aucune impulsion."""
        done = sg.move_steps_table([50] * 10, stop_checker=lambda: True)

        assert done == 0
        assert sg._sm.words == []
        assert sg._stop_flag is True

    def test_sans_stop_checker_toute_la_table_est_emise(self, sg):
        cycles = [42] * (STOP_CHECK_INTERVAL * 2 + 7)

        assert sg.move_steps_table(cycles) == len(cycles)
        assert len(sg._sm.words) == 2 * len(cycles)


# =============================================================================
# CONVERSION DELAI -> CYCLES
# =============================================================================


class TestDelaysToCycles:
    """Le PIO tourne a 125 MHz : 1 cycle = 8 ns."""

    def test_conversion_conforme_a_la_demi_periode(self, sg):
        """260 us -> 16248 demi-cycles (32503 cycles total, soit 260,02 us)."""
        assert sg.delays_to_cycles([260]) == [16248]

    def test_cible_boitier_constructeur(self, sg):
        """124 us (~90°/min) reste exactement representable."""
        (half,) = sg.delays_to_cycles([124])
        # periode = 2 demi-periodes + 5 cycles d'overhead du programme PIO
        periode_us = (2 * half + 5) / 125.0
        assert periode_us == pytest.approx(124, rel=0.001)

    def test_liste_preservee_dans_l_ordre(self, sg):
        assert sg.delays_to_cycles([3000, 1000, 260]) == [
            sg._delay_us_to_cycles(3000),
            sg._delay_us_to_cycles(1000),
            sg._delay_us_to_cycles(260),
        ]


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
    LEGACY_MIN_DELAY_US,
    ProfilAccelConstante,
    lire_accel,
    utilise_accel_constante,
)

ACCEL = 4545  # 110 us atteints en 2 s


def _vitesse(delay_us):
    return 1e6 / delay_us


def _tout(profil):
    return list(profil.paliers())


class TestChoixDuProfil:
    def test_rapide_avec_rampe(self):
        assert utilise_accel_constante(110, "SCURVE")
        assert utilise_accel_constante(259, "SCURVE")

    def test_vitesse_historique_inchangee(self):
        """260 us et plus lent : rampe v4.5, eprouvee (suivi, calibration)."""
        assert LEGACY_MIN_DELAY_US == 260
        assert not utilise_accel_constante(260, "SCURVE")
        assert not utilise_accel_constante(1000, "SCURVE")

    def test_sans_rampe_reste_sans_rampe(self):
        assert not utilise_accel_constante(110, "NONE")


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

    def test_state_machine_relachee(self, sg_rapide):
        sg_rapide.move_segments(iter([(10, 200)]))
        assert sg_rapide._sm.active_calls[-1] == 0
        assert sg_rapide.is_moving is False
