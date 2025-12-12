
"""
Module de calcul des éphémérides des planètes du système solaire.
Utilise les algorithmes VSOP87 simplifiés pour calculer les positions planétaires.
"""

import math
from datetime import datetime
from typing import Tuple, Optional

# Imports conditionnels pour Astropy
try:
    from astropy.time import Time
    from astropy.coordinates import get_body, EarthLocation
    import astropy.units as u
    ASTROPY_AVAILABLE = True
except ImportError:
    ASTROPY_AVAILABLE = False
    Time = None
    get_body = None
    EarthLocation = None
    u = None

class PlanetaryEphemerides:
    """Calcul des positions des planètes."""

    # Liste des planètes supportées (nom français/anglais -> nom Astropy)
    PLANETS = {
        "mercure": "mercury", "mercury": "mercury",
        "venus": "venus", "vénus": "venus",
        "mars": "mars",
        "jupiter": "jupiter",
        "saturne": "saturn", "saturn": "saturn",
        "uranus": "uranus",
        "neptune": "neptune",
        "lune": "moon", "moon": "moon",
        "soleil": "sun", "sun": "sun",
    }

    # Éléments orbitaux moyens simplifiés (J2000)
    # Format: [L0, L1, a, e, i, Omega, omega]
    # L = longitude moyenne, a = demi-grand axe (UA), e = excentricité
    # i = inclinaison, Omega = longitude nœud ascendant, omega = argument périhélie
    ORBITAL_ELEMENTS = {
        "mercury": [252.25, 149472.67, 0.387, 0.206, 7.00, 48.33, 77.46],
        "venus":   [181.98, 58517.82,  0.723, 0.007, 3.39, 76.68, 131.53],
        "mars":    [355.43, 19140.30,  1.524, 0.093, 1.85, 49.56, 336.04],
        "jupiter": [34.40,  3034.90,   5.203, 0.048, 1.31, 100.46, 14.75],
        "saturn":  [49.94,  1222.11,   9.537, 0.054, 2.49, 113.72, 92.43],
        "uranus":  [313.23, 428.48,    19.191, 0.047, 0.77, 74.23, 170.96],
        "neptune": [304.88, 218.46,    30.069, 0.009, 1.77, 131.72, 44.97],
    }

    @staticmethod
    def is_planet(name: str) -> bool:
        """Vérifie si le nom correspond à une planète."""
        return name.lower() in PlanetaryEphemerides.PLANETS

    @staticmethod
    def get_planet_position(name: str, date_heure: datetime,
                            latitude: float, longitude: float) -> Optional[Tuple[float, float]]:
        """
        Calcule la position d'une planète (AD, DEC).

        Args:
            name: Nom de la planète
            date_heure: Date et heure de l'observation
            latitude: Latitude de l'observateur (degrés)
            longitude: Longitude de l'observateur (degrés)

        Returns:
            Tuple (ascension_droite, declinaison) en degrés, ou None si erreur
        """
        if not ASTROPY_AVAILABLE:
            # Astropy n'est pas installé, utiliser des calculs simplifiés
            return PlanetaryEphemerides._simple_planet_position(name, date_heure)

        try:
            planet_name_en = PlanetaryEphemerides.PLANETS.get(name.lower())
            if not planet_name_en:
                return None

            # Créer la localisation de l'observateur
            location = EarthLocation(
                lat=latitude * u.deg,
                lon=longitude * u.deg,
                height=0 * u.m
            )

            # Convertir la date en format Astropy
            time = Time(date_heure)

            # Obtenir les coordonnées de la planète
            planet_coord = get_body(planet_name_en.lower(), time, location)

            # Extraire RA et DEC (en degrés)
            ra_deg = planet_coord.ra.deg
            dec_deg = planet_coord.dec.deg

            return ra_deg, dec_deg

        except Exception:
            return None

    @staticmethod
    def _simple_planet_position(name: str, date_heure: datetime) -> Optional[Tuple[float, float]]:
        """
        Calcul simplifié des positions planétaires (approximation).
        Utilisé si Astropy n'est pas disponible.

        NOTE: Approximations grossières, uniquement pour le développement.
        """
        # Récupérer les éléments orbitaux
        planet_key = PlanetaryEphemerides.PLANETS.get(name.lower(), "")
        if planet_key not in PlanetaryEphemerides.ORBITAL_ELEMENTS:
            return None

        elem = PlanetaryEphemerides.ORBITAL_ELEMENTS[planet_key]
        l0, l1, _, eccentricity, inclination, _, omega_perihelion = elem

        # Siècles juliens depuis J2000
        jd = PlanetaryEphemerides._julian_date(date_heure)
        t_centuries = (jd - 2451545.0) / 36525.0

        # Calcul des anomalies
        mean_longitude = (l0 + l1 * t_centuries) % 360.0
        mean_anomaly_rad = math.radians((mean_longitude - omega_perihelion) % 360.0)

        # Équation de Kepler (10 itérations)
        eccentric_anomaly = mean_anomaly_rad
        for _ in range(10):
            eccentric_anomaly = mean_anomaly_rad + eccentricity * math.sin(eccentric_anomaly)

        # RA et DEC approximatifs (ATTENTION: très imprécis)
        ra_approx = (mean_longitude + 90) % 360.0
        dec_approx = math.degrees(
            math.asin(math.sin(math.radians(inclination)) * math.sin(mean_anomaly_rad))
        )

        return ra_approx, dec_approx

    @staticmethod
    def _julian_date(dt: datetime) -> float:
        """Calcule le jour Julien pour une date donnée."""
        year, month = dt.year, dt.month
        day = dt.day + (dt.hour + (dt.minute + dt.second / 60.0) / 60.0) / 24.0

        if month <= 2:
            year -= 1
            month += 12

        century = year // 100
        leap_correction = 2 - century + century // 4

        jd = int(365.25 * (year + 4716)) + int(30.6001 * (month + 1)) + day + leap_correction - 1524.5
        return jd


# Test si exécuté directement
if __name__ == "__main__":
    print("Test de calcul des positions planétaires\n")

    if ASTROPY_AVAILABLE:
        print("✓ Astropy disponible - calculs précis\n")
    else:
        print("⚠ Astropy non disponible - calculs approximatifs\n")

    planets_to_test = ["Jupiter", "Mars", "Venus", "Saturn"]
    now = datetime.now()

    for planet in planets_to_test:
        if PlanetaryEphemerides.is_planet(planet):
            pos = PlanetaryEphemerides.get_planet_position(
                planet, now, latitude=45.0, longitude=5.0
            )
            if pos:
                ra, dec = pos
                print(f"{planet:10s} : RA = {ra:7.2f}°  DEC = {dec:+7.2f}°")
            else:
                print(f"{planet:10s} : Erreur de calcul")
        else:
            print(f"{planet:10s} : Non reconnu comme planète")