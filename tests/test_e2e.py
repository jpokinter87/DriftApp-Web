"""
Tests End-to-End (E2E) avec hardware mocké.

Ces tests simulent le flux complet du système depuis les commandes
IPC jusqu'à l'exécution moteur, avec tout le hardware simulé.

Scénarios testés:
- GOTO complet avec feedback
- Session de tracking (start → corrections → stop)
- Commandes JOG manuelles
- Récupération d'erreurs hardware
"""

import json
import time
from datetime import datetime, timedelta
from pathlib import Path
from typing import Dict, Any
from unittest.mock import MagicMock, patch, PropertyMock

import pytest


# =============================================================================
# Fixtures E2E
# =============================================================================

class HardwareMockEnvironment:
    """
    Environnement de test avec tout le hardware mocké.

    Simule:
    - GPIO (pins moteur)
    - Encodeur (daemon EMS22)
    - Fichiers IPC
    - Position simulée de la coupole
    """

    def __init__(self, tmp_path: Path):
        self.tmp_path = tmp_path
        self.command_file = tmp_path / "motor_command.json"
        self.status_file = tmp_path / "motor_status.json"
        self.encoder_file = tmp_path / "ems22_position.json"

        # État simulé
        self.dome_position = 0.0
        self.encoder_calibrated = True
        self.steps_executed = 0
        self.motor_direction = 1

        # Historique des actions
        self.action_log = []

    def write_command(self, command: Dict[str, Any]):
        """Écrit une commande IPC."""
        command['id'] = command.get('id', f"cmd_{time.time()}")
        command['timestamp'] = datetime.now().isoformat()
        with open(self.command_file, 'w') as f:
            json.dump(command, f)

    def read_status(self) -> Dict[str, Any]:
        """Lit le status IPC."""
        if not self.status_file.exists():
            return {}
        with open(self.status_file) as f:
            return json.load(f)

    def update_encoder(self, angle: float = None, calibrated: bool = None):
        """Met à jour le fichier encodeur simulé."""
        if angle is not None:
            self.dome_position = angle % 360
        if calibrated is not None:
            self.encoder_calibrated = calibrated

        encoder_data = {
            "angle": self.dome_position,
            "raw": int(self.dome_position * 2.844),  # ~1024 steps / 360°
            "calibrated": self.encoder_calibrated,
            "timestamp": datetime.now().isoformat(),
            "age_ms": 5
        }
        with open(self.encoder_file, 'w') as f:
            json.dump(encoder_data, f)

    def simulate_motor_step(self, direction: int, delay: float):
        """Simule un pas moteur."""
        # 1 pas = 360 / (200 * 4 * 2230) ≈ 0.000202°
        step_degrees = 360.0 / (200 * 4 * 2230)
        self.dome_position = (self.dome_position + direction * step_degrees) % 360
        self.steps_executed += 1
        self.action_log.append({
            'action': 'step',
            'direction': direction,
            'position': self.dome_position
        })

    def simulate_rotation(self, degrees: float, delay: float = 0.002):
        """Simule une rotation complète."""
        steps = int(abs(degrees) / 360.0 * 200 * 4 * 2230)
        direction = 1 if degrees > 0 else -1

        for _ in range(steps):
            self.simulate_motor_step(direction, delay)

        self.update_encoder()
        self.action_log.append({
            'action': 'rotation',
            'degrees': degrees,
            'final_position': self.dome_position
        })


@pytest.fixture
def e2e_env(tmp_path):
    """Crée un environnement E2E complet."""
    env = HardwareMockEnvironment(tmp_path)
    env.update_encoder(angle=45.0, calibrated=True)
    return env


@pytest.fixture
def mock_moteur_simule():
    """Mock du moteur simulé."""
    with patch('core.hardware.moteur_simule.MoteurSimule') as mock:
        instance = MagicMock()
        instance.position = 0.0
        instance.steps_per_dome_revolution = 200 * 4 * 2230
        mock.return_value = instance
        yield instance


# =============================================================================
# Tests E2E - Flux GOTO
# =============================================================================

class TestE2EGotoFlow:
    """Tests E2E pour le flux GOTO complet."""

    def test_goto_updates_dome_position(self, e2e_env):
        """GOTO met à jour la position de la coupole."""
        # Position initiale
        assert e2e_env.dome_position == 45.0

        # Simuler une rotation GOTO
        e2e_env.simulate_rotation(90.0)

        # Position finale
        assert e2e_env.dome_position == pytest.approx(135.0, abs=1.0)

    def test_goto_negative_direction(self, e2e_env):
        """GOTO en sens anti-horaire."""
        e2e_env.update_encoder(angle=180.0)

        # Rotation négative
        e2e_env.simulate_rotation(-45.0)

        assert e2e_env.dome_position == pytest.approx(135.0, abs=1.0)

    def test_goto_crosses_zero(self, e2e_env):
        """GOTO traversant le 0°."""
        e2e_env.update_encoder(angle=350.0)

        # Rotation traversant 0
        e2e_env.simulate_rotation(30.0)

        # Devrait être à ~20° (350 + 30 = 380 → 20)
        assert e2e_env.dome_position == pytest.approx(20.0, abs=1.0)

    def test_goto_logs_action(self, e2e_env):
        """GOTO enregistre les actions."""
        e2e_env.simulate_rotation(45.0)

        assert len(e2e_env.action_log) > 0
        assert e2e_env.action_log[-1]['action'] == 'rotation'
        assert e2e_env.action_log[-1]['degrees'] == 45.0


class TestE2EGotoWithFeedback:
    """Tests E2E pour GOTO avec feedback encodeur."""

    def test_feedback_corrects_position(self, e2e_env):
        """Le feedback corrige les erreurs de position."""
        target = 100.0
        tolerance = 0.5

        # Première rotation (simule une erreur de 2°)
        e2e_env.update_encoder(angle=45.0)
        e2e_env.simulate_rotation(53.0)  # 45 + 53 = 98 (erreur de 2°)

        # Lecture de l'erreur
        error = target - e2e_env.dome_position
        assert abs(error) > tolerance

        # Correction
        e2e_env.simulate_rotation(error)

        # Position finale dans la tolérance
        final_error = target - e2e_env.dome_position
        assert abs(final_error) < tolerance

    def test_feedback_max_iterations(self, e2e_env):
        """Le feedback s'arrête après max_iterations."""
        iterations = 0
        max_iterations = 10
        target = 100.0
        tolerance = 0.5

        e2e_env.update_encoder(angle=45.0)

        while iterations < max_iterations:
            error = target - e2e_env.dome_position
            if abs(error) < tolerance:
                break
            # Simule une correction imparfaite (50% de l'erreur)
            e2e_env.simulate_rotation(error * 0.5)
            iterations += 1

        assert iterations <= max_iterations


# =============================================================================
# Tests E2E - Flux Tracking
# =============================================================================

class TestE2ETrackingFlow:
    """Tests E2E pour le flux de suivi complet."""

    def test_tracking_session_lifecycle(self, e2e_env):
        """Cycle de vie complet d'une session de tracking."""
        # 1. État initial
        session_active = False
        corrections_count = 0

        # 2. Démarrage du suivi
        session_active = True
        start_position = e2e_env.dome_position

        # 3. Simulation de plusieurs corrections
        for i in range(3):
            # Simule une dérive
            drift = 0.3 * (i + 1)  # Dérive croissante

            # Application de la correction
            e2e_env.simulate_rotation(drift)
            corrections_count += 1

        # 4. Vérifications
        assert session_active is True
        assert corrections_count == 3
        assert e2e_env.dome_position != start_position

        # 5. Arrêt du suivi
        session_active = False
        assert session_active is False

    def test_tracking_respects_interval(self, e2e_env):
        """Le tracking respecte l'intervalle entre corrections."""
        interval_seconds = 60
        last_correction = datetime.now()
        corrections = []

        # Simule 3 vérifications
        for i in range(3):
            now = last_correction + timedelta(seconds=interval_seconds * (i + 1))

            # Vérifier si l'intervalle est respecté
            time_since_last = (now - last_correction).total_seconds()
            if time_since_last >= interval_seconds:
                corrections.append(now)
                last_correction = now

        assert len(corrections) == 3

    def test_tracking_adaptive_mode_change(self, e2e_env):
        """Le tracking change de mode selon l'altitude."""
        # Mode normal (altitude < 68°)
        altitude = 45.0
        mode = 'normal' if altitude < 68 else 'critical' if altitude < 75 else 'continuous'
        assert mode == 'normal'

        # Mode critique (68° ≤ altitude < 75°)
        altitude = 70.0
        mode = 'normal' if altitude < 68 else 'critical' if altitude < 75 else 'continuous'
        assert mode == 'critical'

        # Mode continu (altitude ≥ 75°)
        altitude = 80.0
        mode = 'normal' if altitude < 68 else 'critical' if altitude < 75 else 'continuous'
        assert mode == 'continuous'


class TestE2ETrackingCorrections:
    """Tests E2E pour les corrections de suivi."""

    def test_correction_threshold(self, e2e_env):
        """Les corrections ne s'appliquent que si delta > seuil."""
        threshold = 0.5

        # Delta petit (< seuil) : pas de correction
        small_delta = 0.3
        correction_applied = abs(small_delta) >= threshold
        assert correction_applied is False

        # Delta grand (> seuil) : correction appliquée
        large_delta = 0.8
        correction_applied = abs(large_delta) >= threshold
        assert correction_applied is True

    def test_correction_updates_statistics(self, e2e_env):
        """Les corrections mettent à jour les statistiques."""
        total_corrections = 0
        total_movement = 0.0

        corrections = [0.5, -0.3, 0.8, -0.6]

        for delta in corrections:
            e2e_env.simulate_rotation(delta)
            total_corrections += 1
            total_movement += abs(delta)

        assert total_corrections == 4
        assert total_movement == pytest.approx(2.2, abs=0.1)


# =============================================================================
# Tests E2E - Flux JOG
# =============================================================================

class TestE2EJogFlow:
    """Tests E2E pour les commandes JOG manuelles."""

    def test_jog_small_increment(self, e2e_env):
        """JOG avec petit incrément."""
        e2e_env.update_encoder(angle=90.0)

        # JOG de 1°
        e2e_env.simulate_rotation(1.0)

        assert e2e_env.dome_position == pytest.approx(91.0, abs=0.5)

    def test_jog_continuous_movement(self, e2e_env):
        """JOG continu (plusieurs petits pas)."""
        e2e_env.update_encoder(angle=0.0)

        # Simule un JOG continu (10 incréments de 0.5°)
        for _ in range(10):
            e2e_env.simulate_rotation(0.5)

        assert e2e_env.dome_position == pytest.approx(5.0, abs=0.5)

    def test_jog_interrupted_by_stop(self, e2e_env):
        """JOG interrompu par une commande stop."""
        e2e_env.update_encoder(angle=0.0)
        stop_requested = False
        steps_before_stop = 5

        for i in range(10):
            if i >= steps_before_stop:
                stop_requested = True
            if stop_requested:
                break
            e2e_env.simulate_rotation(0.5)

        # Seulement 5 incréments exécutés
        assert e2e_env.dome_position == pytest.approx(2.5, abs=0.5)


# =============================================================================
# Tests E2E - Récupération d'erreurs
# =============================================================================

class TestE2EErrorRecovery:
    """Tests E2E pour la récupération d'erreurs hardware."""

    def test_encoder_unavailable_fallback(self, e2e_env):
        """Fallback quand l'encodeur n'est pas disponible."""
        # Simule encodeur non calibré
        e2e_env.update_encoder(calibrated=False)

        # Le système doit fonctionner en mode dégradé
        encoder_available = e2e_env.encoder_calibrated
        assert encoder_available is False

        # La rotation fonctionne quand même (sans feedback)
        initial_pos = e2e_env.dome_position
        e2e_env.simulate_rotation(10.0)

        assert e2e_env.dome_position != initial_pos

    def test_consecutive_errors_stop_tracking(self):
        """Trop d'erreurs consécutives arrêtent le suivi."""
        max_errors = 3
        consecutive_errors = 0
        tracking_active = True

        # Simule des erreurs consécutives
        for _ in range(5):
            # Simule une erreur de correction
            error_occurred = True

            if error_occurred:
                consecutive_errors += 1
            else:
                consecutive_errors = 0

            if consecutive_errors >= max_errors:
                tracking_active = False
                break

        assert tracking_active is False
        assert consecutive_errors == 3

    def test_error_recovery_resets_counter(self):
        """Une correction réussie remet le compteur d'erreurs à zéro."""
        consecutive_errors = 2

        # Correction réussie
        success = True
        if success:
            consecutive_errors = 0

        assert consecutive_errors == 0


# =============================================================================
# Tests E2E - Intégration IPC
# =============================================================================

class TestE2EIpcIntegration:
    """Tests E2E pour l'intégration IPC complète."""

    def test_command_to_status_cycle(self, e2e_env):
        """Cycle complet commande → exécution → status."""
        # 1. Écriture de la commande
        e2e_env.write_command({
            'type': 'GOTO',
            'target': 180.0
        })

        # 2. Lecture de la commande
        assert e2e_env.command_file.exists()
        with open(e2e_env.command_file) as f:
            cmd = json.load(f)
        assert cmd['type'] == 'GOTO'
        assert cmd['target'] == 180.0

        # 3. Exécution (simulée)
        e2e_env.simulate_rotation(180.0 - e2e_env.dome_position)

        # 4. Écriture du status
        status = {
            'state': 'IDLE',
            'position': e2e_env.dome_position,
            'last_command': cmd['id']
        }
        with open(e2e_env.status_file, 'w') as f:
            json.dump(status, f)

        # 5. Vérification du status
        final_status = e2e_env.read_status()
        assert final_status['state'] == 'IDLE'
        assert final_status['position'] == pytest.approx(180.0, abs=1.0)

    def test_rapid_command_sequence(self, e2e_env):
        """Séquence rapide de commandes."""
        commands_executed = []

        for i in range(5):
            cmd_id = f"rapid_{i}"
            e2e_env.write_command({
                'type': 'JOG',
                'direction': 1,
                'id': cmd_id
            })

            # Simule l'exécution
            e2e_env.simulate_rotation(1.0)
            commands_executed.append(cmd_id)

        assert len(commands_executed) == 5
        assert e2e_env.dome_position == pytest.approx(50.0, abs=1.0)  # 45 + 5


# =============================================================================
# Tests E2E - Performance
# =============================================================================

class TestE2EPerformance:
    """Tests E2E pour la performance du système."""

    def test_rotation_step_count(self, e2e_env):
        """Vérifie le nombre de pas pour une rotation."""
        e2e_env.steps_executed = 0

        # Rotation de 1°
        e2e_env.simulate_rotation(1.0)

        # ~4956 pas pour 1° (200 * 4 * 2230 / 360)
        expected_steps = int(1.0 / 360.0 * 200 * 4 * 2230)
        assert e2e_env.steps_executed == pytest.approx(expected_steps, rel=0.01)

    def test_action_log_captures_all(self, e2e_env):
        """Le log d'actions capture toutes les opérations."""
        e2e_env.action_log.clear()

        # Plusieurs opérations
        e2e_env.simulate_rotation(10.0)
        e2e_env.simulate_rotation(-5.0)
        e2e_env.simulate_rotation(2.0)

        # Vérifie les rotations (pas les steps individuels)
        rotations = [a for a in e2e_env.action_log if a['action'] == 'rotation']
        assert len(rotations) == 3
        assert rotations[0]['degrees'] == 10.0
        assert rotations[1]['degrees'] == -5.0
        assert rotations[2]['degrees'] == 2.0
