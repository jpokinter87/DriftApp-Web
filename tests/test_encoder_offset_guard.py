"""
L'offset encodeur ne doit pas absorber un mouvement inachevé.

Terrain 12/10/2026 23:19 : un slew d'anticipation de 121,7° est coupé à 41 s
par le firmware (`ERROR memory allocation failed`) ; la re-sync post-méridien
recalcule l'offset sans borne (−0,2° → 57,8°) et toutes les corrections
suivantes pointent la coupole 58° à côté. Un écart de plusieurs degrés
n'est pas une dérive : c'est un mouvement qui n'est pas allé au bout.
"""

from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

from core.config.config_loader import load_config
from core.hardware.moteur_simule import MoteurSimule, set_simulated_position
from core.observatoire import AstronomicalCalculations
from core.tracking.tracking_logger import TrackingLogger
from core.tracking.tracker import TrackingSession

ABAQUE = Path(__file__).resolve().parent.parent / "data" / "Loi_coupole.xlsx"


@pytest.fixture
def session():
    if not ABAQUE.exists():
        pytest.skip("Abaque Loi_coupole.xlsx non trouvé")
    config = load_config()
    set_simulated_position(0.0)
    s = TrackingSession(
        moteur=MoteurSimule(),
        calc=AstronomicalCalculations(config.site.latitude, config.site.longitude, 2),
        logger=TrackingLogger(),
        abaque_file=str(ABAQUE),
        motor_config=config.motor,
        encoder_config=config.encoder,
    )
    s.encoder_available = True
    return s


def _encodeur_a(angle):
    reader = MagicMock()
    reader.read_angle.return_value = angle
    return reader


def test_resync_conserve_l_offset_si_le_mouvement_est_inacheve(session):
    session.encoder_offset = -0.2
    session.position_relative = 70.0
    with patch(
        "core.hardware.daemon_encoder_reader.get_daemon_reader", return_value=_encodeur_a(12.2)
    ):
        session._resync_encoder_offset(70.0)

    assert session.encoder_offset == pytest.approx(-0.2)
    # Position réellement atteinte : la correction suivante verra le grand
    # écart restant (allow_large) au lieu d'un delta logique minuscule.
    assert session.position_relative == pytest.approx(12.0)


def test_resync_n_absorbe_pas_un_depassement(session):
    """Terrain 21/10/2026 20:56 : le slew d'anticipation (sans feedback) va 3,8°
    trop loin ; l'écart absorbé (offset 0,4° → 4,2°) laisse la coupole décalée
    toute la nuit (« ENC 107,71° (+4,2°) » sur le dashboard). Encodeur calibré :
    l'offset ne bouge pas, la position atteinte est retenue et la correction
    suivante, avec feedback, ramène la coupole sur la cible."""
    session.encoder_offset = 0.4
    with patch(
        "core.hardware.daemon_encoder_reader.get_daemon_reader", return_value=_encodeur_a(106.2)
    ):
        session._resync_encoder_offset(110.4)

    assert session.encoder_offset == pytest.approx(0.4)
    assert session.position_relative == pytest.approx(106.6)


def test_goto_initial_inacheve_n_absorbe_pas_l_ecart(session):
    session.position_relative = 200.0
    session.moteur.rotation_avec_feedback = MagicMock(
        return_value={
            "success": False,
            "position_initiale": 45.0,
            "position_finale": 150.0,
            "erreur_finale": 50.0,
            "iterations": 1,
        }
    )
    with patch(
        "core.tracking.tracking_goto_mixin.get_daemon_reader", return_value=_encodeur_a(150.0)
    ):
        session._execute_initial_goto(200.0, 0.00026)

    assert session.encoder_offset == pytest.approx(0.0)
    assert session.position_relative == pytest.approx(150.0)


def test_goto_initial_reussi_garde_le_residu(session):
    session.moteur.rotation_avec_feedback = MagicMock(
        return_value={
            "success": True,
            "position_initiale": 45.0,
            "position_finale": 200.3,
            "erreur_finale": 0.3,
            "iterations": 2,
        }
    )
    with patch(
        "core.tracking.tracking_goto_mixin.get_daemon_reader", return_value=_encodeur_a(200.3)
    ):
        session._execute_initial_goto(200.0, 0.00026)

    assert session.encoder_offset == pytest.approx(-0.3)
