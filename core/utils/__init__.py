"""
Utilitaires partagés pour le projet Dome.
"""

from core.utils.angle_utils import (
    normalize_angle_360,
    normalize_angle_180,
    shortest_angular_distance,
    angles_are_close,
)

__all__ = [
    'normalize_angle_360',
    'normalize_angle_180',
    'shortest_angular_distance',
    'angles_are_close',
]