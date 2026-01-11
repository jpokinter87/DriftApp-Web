"""
Tests pour le module de rampe d'accélération/décélération.

Vérifie le comportement de la rampe S-curve pour la protection moteur.
VERSION 4.6 : Ajout tests pour warm-up
"""

import pytest
import math

from core.hardware.acceleration_ramp import (
    AccelerationRamp,
    RampConfig,
    create_ramp_for_rotation,
    RAMP_START_DELAY,
    RAMP_STEPS,
    MIN_STEPS_FOR_RAMP,
    WARMUP_DELAY,
    WARMUP_STEPS,
)


# Configuration sans warm-up pour les tests de rétro-compatibilité
NO_WARMUP_CONFIG = RampConfig(warmup_enabled=False)


class TestAccelerationRampBasics:
    """Tests basiques de la rampe d'accélération (sans warm-up)."""

    def test_ramp_creation(self):
        """La rampe peut être créée avec des paramètres valides."""
        ramp = AccelerationRamp(total_steps=10000, target_delay=0.00015, config=NO_WARMUP_CONFIG)
        assert ramp.total_steps == 10000
        assert ramp.target_delay == 0.00015
        assert ramp.ramp_enabled is True

    def test_ramp_disabled_for_small_movements(self):
        """La rampe est désactivée pour les petits mouvements."""
        ramp = AccelerationRamp(total_steps=100, target_delay=0.001, config=NO_WARMUP_CONFIG)
        assert ramp.ramp_enabled is False
        # Tous les pas utilisent le délai cible
        assert ramp.get_delay(0) == 0.001
        assert ramp.get_delay(50) == 0.001
        assert ramp.get_delay(99) == 0.001

    def test_ramp_phases_normal_movement(self):
        """Les phases sont correctement calculées pour un mouvement normal."""
        ramp = AccelerationRamp(total_steps=10000, target_delay=0.00015, config=NO_WARMUP_CONFIG)
        assert ramp.accel_end == RAMP_STEPS
        assert ramp.decel_start == 10000 - RAMP_STEPS
        assert ramp.ramp_enabled is True

    def test_ramp_phases_short_movement(self):
        """Les phases sont proportionnelles pour mouvements courts."""
        # Mouvement de 600 pas (< 2 * 500 = 1000)
        ramp = AccelerationRamp(total_steps=600, target_delay=0.001, config=NO_WARMUP_CONFIG)
        assert ramp.ramp_enabled is True
        # Rampe proportionnelle: 600 / 4 = 150 pas par phase
        assert ramp.accel_end == 150
        assert ramp.decel_start == 450


class TestAccelerationPhase:
    """Tests de la phase d'accélération (sans warm-up)."""

    def test_acceleration_starts_slow(self):
        """L'accélération démarre avec le délai lent."""
        ramp = AccelerationRamp(total_steps=10000, target_delay=0.00015, config=NO_WARMUP_CONFIG)
        first_delay = ramp.get_delay(0)
        # Doit être proche du délai de démarrage (3ms)
        assert first_delay == pytest.approx(RAMP_START_DELAY, rel=0.01)

    def test_acceleration_reaches_target(self):
        """L'accélération atteint le délai cible."""
        ramp = AccelerationRamp(total_steps=10000, target_delay=0.00015, config=NO_WARMUP_CONFIG)
        last_accel_delay = ramp.get_delay(ramp.accel_end - 1)
        # Doit être proche du délai cible
        assert last_accel_delay == pytest.approx(0.00015, rel=0.1)

    def test_acceleration_is_monotonic(self):
        """L'accélération est monotone décroissante (délais décroissants)."""
        ramp = AccelerationRamp(total_steps=10000, target_delay=0.00015, config=NO_WARMUP_CONFIG)
        delays = [ramp.get_delay(i) for i in range(0, ramp.accel_end, 10)]
        # Chaque délai doit être <= au précédent (vitesse croissante)
        for i in range(1, len(delays)):
            assert delays[i] <= delays[i-1], f"Délai non monotone à l'index {i}"


class TestCruisePhase:
    """Tests de la phase de croisière (sans warm-up)."""

    def test_cruise_uses_target_delay(self):
        """La phase de croisière utilise le délai cible constant."""
        ramp = AccelerationRamp(total_steps=10000, target_delay=0.00015, config=NO_WARMUP_CONFIG)
        # Milieu du mouvement
        mid = 5000
        assert ramp.get_delay(mid) == 0.00015

    def test_cruise_phase_is_constant(self):
        """Le délai est constant pendant la phase de croisière."""
        ramp = AccelerationRamp(total_steps=10000, target_delay=0.00015, config=NO_WARMUP_CONFIG)
        cruise_delays = [
            ramp.get_delay(i)
            for i in range(ramp.accel_end, ramp.decel_start, 100)
        ]
        assert all(d == 0.00015 for d in cruise_delays)


class TestDecelerationPhase:
    """Tests de la phase de décélération (sans warm-up)."""

    def test_deceleration_ends_slow(self):
        """La décélération se termine avec le délai lent."""
        ramp = AccelerationRamp(total_steps=10000, target_delay=0.00015, config=NO_WARMUP_CONFIG)
        last_delay = ramp.get_delay(9999)
        # Doit être proche du délai de démarrage (3ms)
        assert last_delay == pytest.approx(RAMP_START_DELAY, rel=0.1)

    def test_deceleration_starts_at_target(self):
        """La décélération commence au délai cible."""
        ramp = AccelerationRamp(total_steps=10000, target_delay=0.00015, config=NO_WARMUP_CONFIG)
        first_decel_delay = ramp.get_delay(ramp.decel_start)
        # Doit être proche du délai cible
        assert first_decel_delay == pytest.approx(0.00015, rel=0.1)

    def test_deceleration_is_monotonic(self):
        """La décélération est monotone croissante (délais croissants)."""
        ramp = AccelerationRamp(total_steps=10000, target_delay=0.00015, config=NO_WARMUP_CONFIG)
        delays = [
            ramp.get_delay(i)
            for i in range(ramp.decel_start, ramp.total_steps, 10)
        ]
        # Chaque délai doit être >= au précédent (vitesse décroissante)
        for i in range(1, len(delays)):
            assert delays[i] >= delays[i-1], f"Délai non monotone à l'index {i}"


class TestSCurve:
    """Tests de la fonction S-curve."""

    def test_s_curve_start_at_zero(self):
        """La S-curve commence à 0."""
        ramp = AccelerationRamp(total_steps=10000, target_delay=0.001)
        result = ramp._s_curve(0)
        assert result == pytest.approx(0, abs=0.01)

    def test_s_curve_ends_at_one(self):
        """La S-curve finit à 1."""
        ramp = AccelerationRamp(total_steps=10000, target_delay=0.001)
        result = ramp._s_curve(1)
        assert result == pytest.approx(1, abs=0.01)

    def test_s_curve_midpoint(self):
        """La S-curve passe par 0.5 au milieu."""
        ramp = AccelerationRamp(total_steps=10000, target_delay=0.001)
        result = ramp._s_curve(0.5)
        assert result == pytest.approx(0.5, abs=0.01)

    def test_s_curve_is_smooth(self):
        """La S-curve est monotone croissante."""
        ramp = AccelerationRamp(total_steps=10000, target_delay=0.001)
        values = [ramp._s_curve(t / 100) for t in range(101)]
        for i in range(1, len(values)):
            assert values[i] >= values[i-1], f"S-curve non monotone à {i}%"


class TestLinearInterpolation:
    """Tests de l'interpolation linéaire."""

    def test_linear_with_config(self):
        """L'interpolation linéaire fonctionne via config."""
        config = RampConfig(use_s_curve=False)
        ramp = AccelerationRamp(total_steps=10000, target_delay=0.001, config=config)
        # Milieu de l'accélération
        mid_accel = ramp.accel_end // 2
        delay = ramp.get_delay(mid_accel)
        # Doit être à mi-chemin entre start_delay et target_delay
        expected = (RAMP_START_DELAY + 0.001) / 2
        assert delay == pytest.approx(expected, rel=0.1)


class TestPhaseDetection:
    """Tests de la détection de phase (sans warm-up)."""

    def test_phase_acceleration(self):
        """Détection correcte de la phase d'accélération."""
        ramp = AccelerationRamp(total_steps=10000, target_delay=0.001, config=NO_WARMUP_CONFIG)
        assert ramp.get_phase(0) == 'acceleration'
        assert ramp.get_phase(100) == 'acceleration'

    def test_phase_cruise(self):
        """Détection correcte de la phase de croisière."""
        ramp = AccelerationRamp(total_steps=10000, target_delay=0.001, config=NO_WARMUP_CONFIG)
        assert ramp.get_phase(5000) == 'cruise'

    def test_phase_deceleration(self):
        """Détection correcte de la phase de décélération."""
        ramp = AccelerationRamp(total_steps=10000, target_delay=0.001, config=NO_WARMUP_CONFIG)
        assert ramp.get_phase(9800) == 'deceleration'
        assert ramp.get_phase(9999) == 'deceleration'

    def test_phase_disabled_ramp(self):
        """Phase 'cruise' si rampe désactivée."""
        ramp = AccelerationRamp(total_steps=50, target_delay=0.001, config=NO_WARMUP_CONFIG)
        assert ramp.get_phase(25) == 'cruise'


class TestRampStats:
    """Tests des statistiques de rampe (sans warm-up)."""

    def test_stats_normal_movement(self):
        """Statistiques correctes pour mouvement normal."""
        ramp = AccelerationRamp(total_steps=10000, target_delay=0.00015, config=NO_WARMUP_CONFIG)
        stats = ramp.stats
        assert stats['total_steps'] == 10000
        assert stats['target_delay'] == 0.00015
        assert stats['ramp_enabled'] is True
        assert stats['accel_steps'] == RAMP_STEPS
        assert stats['decel_steps'] == RAMP_STEPS
        assert stats['cruise_steps'] == 10000 - 2 * RAMP_STEPS

    def test_stats_disabled_ramp(self):
        """Statistiques correctes pour rampe désactivée."""
        ramp = AccelerationRamp(total_steps=50, target_delay=0.001, config=NO_WARMUP_CONFIG)
        stats = ramp.stats
        assert stats['ramp_enabled'] is False
        assert stats['accel_steps'] == 0
        assert stats['decel_steps'] == 0
        assert stats['cruise_steps'] == 50


class TestEdgeCases:
    """Tests des cas limites (sans warm-up)."""

    def test_zero_steps(self):
        """Gestion de 0 pas."""
        ramp = AccelerationRamp(total_steps=0, target_delay=0.001, config=NO_WARMUP_CONFIG)
        assert ramp.ramp_enabled is False
        # Ne doit pas planter
        assert ramp.get_delay(0) == 0.001

    def test_one_step(self):
        """Gestion de 1 seul pas."""
        ramp = AccelerationRamp(total_steps=1, target_delay=0.001, config=NO_WARMUP_CONFIG)
        assert ramp.ramp_enabled is False
        assert ramp.get_delay(0) == 0.001

    def test_negative_step_index(self):
        """Index négatif est clampé à 0."""
        ramp = AccelerationRamp(total_steps=10000, target_delay=0.001, config=NO_WARMUP_CONFIG)
        delay_neg = ramp.get_delay(-10)
        delay_zero = ramp.get_delay(0)
        assert delay_neg == delay_zero

    def test_step_index_beyond_total(self):
        """Index au-delà de total est clampé au dernier."""
        ramp = AccelerationRamp(total_steps=10000, target_delay=0.001, config=NO_WARMUP_CONFIG)
        delay_beyond = ramp.get_delay(20000)
        delay_last = ramp.get_delay(9999)
        assert delay_beyond == delay_last

    def test_very_fast_target_delay(self):
        """Fonctionnement avec délai cible très rapide (CONTINUOUS)."""
        ramp = AccelerationRamp(total_steps=50000, target_delay=0.00015, config=NO_WARMUP_CONFIG)
        # Vérifie que ça ne plante pas et que les phases sont correctes
        assert ramp.get_delay(0) > ramp.get_delay(1000)  # Accélération
        assert ramp.get_delay(25000) == 0.00015  # Croisière
        assert ramp.get_delay(49999) > ramp.get_delay(45000)  # Décélération


class TestCreateRampForRotation:
    """Tests de la fonction utilitaire create_ramp_for_rotation."""

    def test_create_ramp_for_10_degrees(self):
        """Création de rampe pour 10° de rotation."""
        # Avec ~1.94M steps/tour, 10° ≈ 53,940 steps
        steps_per_dome = 1941866
        ramp = create_ramp_for_rotation(
            angle_deg=10.0,
            steps_per_dome_revolution=steps_per_dome,
            target_delay=0.00015
        )
        expected_steps = int(10.0 / (360.0 / steps_per_dome))
        assert ramp.total_steps == expected_steps
        assert ramp.ramp_enabled is True

    def test_create_ramp_for_small_angle(self):
        """Rampe désactivée pour très petit angle."""
        steps_per_dome = 1941866
        ramp = create_ramp_for_rotation(
            angle_deg=0.001,  # Très petit angle
            steps_per_dome_revolution=steps_per_dome,
            target_delay=0.001
        )
        # Devrait avoir très peu de pas, rampe probablement désactivée
        assert ramp.total_steps < MIN_STEPS_FOR_RAMP

    def test_create_ramp_negative_angle(self):
        """L'angle négatif utilise la valeur absolue."""
        steps_per_dome = 1941866
        ramp_pos = create_ramp_for_rotation(10.0, steps_per_dome, 0.001)
        ramp_neg = create_ramp_for_rotation(-10.0, steps_per_dome, 0.001)
        assert ramp_pos.total_steps == ramp_neg.total_steps


class TestRampWithDifferentSpeeds:
    """Tests de la rampe avec différentes vitesses moteur (sans warm-up)."""

    def test_ramp_with_normal_speed(self):
        """Rampe avec vitesse NORMAL (2ms)."""
        ramp = AccelerationRamp(total_steps=10000, target_delay=0.002, config=NO_WARMUP_CONFIG)
        # Le délai de départ (3ms) n'est que 1.5x le délai cible
        # La rampe devrait quand même fonctionner
        assert ramp.get_delay(0) == pytest.approx(RAMP_START_DELAY, rel=0.01)
        assert ramp.get_delay(5000) == 0.002

    def test_ramp_with_critical_speed(self):
        """Rampe avec vitesse CRITICAL (1ms)."""
        ramp = AccelerationRamp(total_steps=10000, target_delay=0.001, config=NO_WARMUP_CONFIG)
        assert ramp.get_delay(0) == pytest.approx(RAMP_START_DELAY, rel=0.01)
        assert ramp.get_delay(5000) == 0.001

    def test_ramp_with_continuous_speed(self):
        """Rampe avec vitesse CONTINUOUS (0.15ms)."""
        ramp = AccelerationRamp(total_steps=50000, target_delay=0.00015, config=NO_WARMUP_CONFIG)
        # Grande différence entre start (3ms) et target (0.15ms)
        # La rampe est particulièrement importante ici
        assert ramp.get_delay(0) == pytest.approx(RAMP_START_DELAY, rel=0.01)
        assert ramp.get_delay(25000) == 0.00015
        # Vérifie que l'accélération est progressive
        delays = [ramp.get_delay(i) for i in range(0, ramp.accel_end, 50)]
        for i in range(1, len(delays)):
            assert delays[i] < delays[i-1], "Accélération non progressive"


class TestRampConfigCustom:
    """Tests avec configuration personnalisée (sans warm-up pour isoler les paramètres)."""

    def test_custom_start_delay(self):
        """Configuration avec délai de départ personnalisé."""
        config = RampConfig(start_delay=0.005, warmup_enabled=False)  # 5ms au lieu de 3ms
        ramp = AccelerationRamp(total_steps=10000, target_delay=0.001, config=config)
        assert ramp.get_delay(0) == pytest.approx(0.005, rel=0.01)

    def test_custom_ramp_steps(self):
        """Configuration avec nombre de pas de rampe personnalisé."""
        config = RampConfig(ramp_steps=1000, warmup_enabled=False)  # 1000 au lieu de 500
        ramp = AccelerationRamp(total_steps=10000, target_delay=0.001, config=config)
        assert ramp.accel_end == 1000
        assert ramp.decel_start == 9000

    def test_custom_min_steps(self):
        """Configuration avec seuil minimum personnalisé."""
        config = RampConfig(min_steps=50)  # 50 au lieu de 200
        ramp = AccelerationRamp(total_steps=100, target_delay=0.001, config=config)
        # Avec min_steps=50, une rampe de 100 pas devrait être activée
        assert ramp.ramp_enabled is True


class TestWarmupPhase:
    """Tests de la phase de warm-up (démarrage à froid)."""

    def test_warmup_enabled_by_default(self):
        """Le warm-up est activé par défaut."""
        ramp = AccelerationRamp(total_steps=10000, target_delay=0.001)
        assert ramp.warmup_enabled is True
        assert ramp.warmup_end == WARMUP_STEPS

    def test_warmup_returns_warmup_delay(self):
        """Les pas de warm-up utilisent le délai de warm-up."""
        ramp = AccelerationRamp(total_steps=10000, target_delay=0.001)
        # Premier pas = warmup delay (10ms par défaut)
        assert ramp.get_delay(0) == WARMUP_DELAY
        # Dernier pas de warmup
        assert ramp.get_delay(WARMUP_STEPS - 1) == WARMUP_DELAY

    def test_warmup_phase_detection(self):
        """La phase 'warmup' est correctement détectée."""
        ramp = AccelerationRamp(total_steps=10000, target_delay=0.001)
        assert ramp.get_phase(0) == 'warmup'
        assert ramp.get_phase(WARMUP_STEPS - 1) == 'warmup'
        # Après warm-up = accélération
        assert ramp.get_phase(WARMUP_STEPS) == 'acceleration'

    def test_warmup_followed_by_acceleration(self):
        """Après le warm-up, l'accélération commence."""
        ramp = AccelerationRamp(total_steps=10000, target_delay=0.001)
        # Le premier pas après warmup doit être start_delay (3ms)
        first_accel = ramp.get_delay(WARMUP_STEPS)
        assert first_accel == pytest.approx(RAMP_START_DELAY, rel=0.01)

    def test_warmup_disabled_via_config(self):
        """Le warm-up peut être désactivé via configuration."""
        config = RampConfig(warmup_enabled=False)
        ramp = AccelerationRamp(total_steps=10000, target_delay=0.001, config=config)
        assert ramp.warmup_enabled is False
        assert ramp.warmup_end == 0
        # Premier pas = début de l'accélération (start_delay)
        assert ramp.get_delay(0) == pytest.approx(RAMP_START_DELAY, rel=0.01)

    def test_warmup_custom_parameters(self):
        """Paramètres de warm-up personnalisables."""
        config = RampConfig(warmup_enabled=True, warmup_steps=20, warmup_delay=0.015)
        ramp = AccelerationRamp(total_steps=10000, target_delay=0.001, config=config)
        assert ramp.warmup_end == 20
        assert ramp.get_delay(0) == 0.015
        assert ramp.get_delay(19) == 0.015
        # Après warmup (20 pas) = accélération
        assert ramp.get_phase(20) == 'acceleration'

    def test_warmup_stats_included(self):
        """Les statistiques incluent les infos de warm-up."""
        ramp = AccelerationRamp(total_steps=10000, target_delay=0.001)
        stats = ramp.stats
        assert 'warmup_enabled' in stats
        assert stats['warmup_enabled'] is True
        assert stats['warmup_steps'] == WARMUP_STEPS
        assert stats['warmup_delay'] == WARMUP_DELAY

    def test_warmup_disabled_for_very_short_movement(self):
        """Warm-up désactivé si mouvement trop court."""
        # Mouvement de 5 pas (< WARMUP_STEPS)
        ramp = AccelerationRamp(total_steps=5, target_delay=0.001)
        assert ramp.warmup_enabled is False

    def test_warmup_with_ramp_phases_correct(self):
        """Les phases sont correctes avec warm-up + rampe."""
        ramp = AccelerationRamp(total_steps=10000, target_delay=0.001)
        # Warm-up: 0 à WARMUP_STEPS-1 (10 pas)
        # Accélération: WARMUP_STEPS à WARMUP_STEPS+RAMP_STEPS-1
        # Croisière: WARMUP_STEPS+RAMP_STEPS à total-RAMP_STEPS-1
        # Décélération: total-RAMP_STEPS à fin
        assert ramp.accel_end == WARMUP_STEPS + RAMP_STEPS  # 10 + 500 = 510
        assert ramp.decel_start == 10000 - RAMP_STEPS  # 9500

    def test_warmup_small_movement_proportional_ramp(self):
        """Mouvement court avec warm-up a une rampe proportionnelle."""
        # 600 pas avec warm-up de 10 pas
        ramp = AccelerationRamp(total_steps=600, target_delay=0.001)
        assert ramp.warmup_enabled is True
        assert ramp.warmup_end == WARMUP_STEPS
        # Rampe proportionnelle: (600-10) n'est pas < 2*500, mais 600 < 2*500
        # Donc rampe proportionnelle: 600 / 4 = 150 pas
        # accel_end = warmup + ramp = 10 + 150 = 160 (environ)
        assert ramp.ramp_enabled is True
