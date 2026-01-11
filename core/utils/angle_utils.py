"""
Utilitaires pour les calculs d'angles.

Centralise la logique de normalisation et de calcul de delta angulaire
utilisée dans plusieurs modules du projet.

Usage:
    from core.utils.angle_utils import shortest_angular_distance, normalize_angle_360

    delta = shortest_angular_distance(current=350, target=10)  # -> 20
    angle = normalize_angle_360(370)  # -> 10
"""


def normalize_angle_360(angle: float) -> float:
    """
    Normalise un angle dans l'intervalle [0, 360[.

    Args:
        angle: Angle en degrés (peut être négatif ou > 360)

    Returns:
        Angle normalisé entre 0 et 360 (exclus)

    Examples:
        >>> normalize_angle_360(370)
        10.0
        >>> normalize_angle_360(-10)
        350.0
        >>> normalize_angle_360(360)
        0.0
    """
    return angle % 360


def normalize_angle_180(angle: float) -> float:
    """
    Normalise un angle dans l'intervalle [-180, 180].

    Args:
        angle: Angle en degrés

    Returns:
        Angle normalisé entre -180 et 180

    Examples:
        >>> normalize_angle_180(270)
        -90.0
        >>> normalize_angle_180(-270)
        90.0
        >>> normalize_angle_180(180)
        180.0
    """
    angle = angle % 360
    if angle > 180:
        angle -= 360
    return angle


def shortest_angular_distance(current: float, target: float) -> float:
    """
    Calcule la distance angulaire la plus courte entre deux angles.

    Retourne un delta avec signe indiquant la direction :
    - Positif : sens horaire
    - Négatif : sens anti-horaire

    Args:
        current: Angle actuel en degrés
        target: Angle cible en degrés

    Returns:
        Delta angulaire (entre -180 et +180)

    Examples:
        >>> shortest_angular_distance(350, 10)
        20.0
        >>> shortest_angular_distance(10, 350)
        -20.0
        >>> shortest_angular_distance(0, 180)
        180.0
    """
    delta = target - current

    # Normaliser dans [-180, 180]
    while delta > 180:
        delta -= 360
    while delta < -180:
        delta += 360

    return delta


def angles_are_close(angle1: float, angle2: float, tolerance: float = 0.5) -> bool:
    """
    Vérifie si deux angles sont proches à une tolérance donnée.

    Prend en compte le passage par 0°/360°.

    Args:
        angle1: Premier angle en degrés
        angle2: Deuxième angle en degrés
        tolerance: Tolérance en degrés (défaut: 0.5°)

    Returns:
        True si les angles sont proches

    Examples:
        >>> angles_are_close(359.8, 0.2, tolerance=0.5)
        True
        >>> angles_are_close(10, 11, tolerance=0.5)
        False
    """
    delta = abs(shortest_angular_distance(angle1, angle2))
    return delta < tolerance


def calculate_rotation_direction(current: float, target: float) -> int:
    """
    Détermine la direction de rotation optimale.

    Args:
        current: Angle actuel en degrés
        target: Angle cible en degrés

    Returns:
        +1 pour sens horaire, -1 pour sens anti-horaire, 0 si identiques
    """
    delta = shortest_angular_distance(current, target)
    if abs(delta) < 0.001:  # Quasi-identiques
        return 0
    return 1 if delta > 0 else -1


def calculate_steps_for_rotation(delta_deg: float, steps_per_revolution: int) -> int:
    """
    Calcule le nombre de pas moteur pour une rotation donnée.

    Args:
        delta_deg: Delta angulaire en degrés
        steps_per_revolution: Nombre de pas pour un tour complet (360°)

    Returns:
        Nombre de pas (toujours positif)
    """
    deg_per_step = 360.0 / steps_per_revolution
    return int(abs(delta_deg) / deg_per_step)


# =============================================================================
# CALCULS DE TEMPS ASTRONOMIQUE
# =============================================================================

def calculate_julian_day(dt_utc) -> float:
    """
    Calcule le jour Julien à partir d'une datetime UTC.

    Le jour Julien est un système de datation continue utilisé en astronomie.
    J2000.0 (1er janvier 2000 à 12h UTC) correspond à JD = 2451545.0.

    Args:
        dt_utc: datetime en UTC (naive, sans tzinfo)

    Returns:
        Jour Julien (float)

    Examples:
        >>> from datetime import datetime
        >>> # J2000.0 : 1er janvier 2000 à 12h UTC
        >>> calculate_julian_day(datetime(2000, 1, 1, 12, 0, 0))
        2451545.0
    """
    year, month = dt_utc.year, dt_utc.month
    day = dt_utc.day + (dt_utc.hour + (dt_utc.minute + dt_utc.second / 60.0) / 60.0) / 24.0

    if month <= 2:
        year -= 1
        month += 12

    century = year // 100
    leap_correction = 2 - century + century // 4

    jd = int(365.25 * (year + 4716)) + int(30.6001 * (month + 1)) + day + leap_correction - 1524.5
    return jd