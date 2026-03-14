"""
Module de calculs astronomiques pour l'observatoire.

VERSION 4.4 : Suppression du calcul de parallaxe géométrique.
La correction de parallaxe est maintenant gérée par la méthode abaque
(mesures terrain dans Loi_coupole.xlsx).
- Conversion J2000 -> JNOW via Astropy
- Coordonnées horizontales (azimut, altitude)
- Temps sidéral et angle horaire
"""
import math
from datetime import datetime, timedelta, timezone
from typing import Tuple

from astropy.coordinates import SkyCoord, CIRS
from astropy.time import Time
import astropy.units as u


class AstronomicalCalculations:
    """Classe pour les calculs astronomiques."""

    def __init__(self, latitude: float, longitude: float, tz_offset: int):
        """
        Initialise les calculs astronomiques.

        Args:
            latitude: Latitude de l'observatoire en degrés
            longitude: Longitude de l'observatoire en degrés
            tz_offset: Décalage horaire par rapport à UTC

        Note:
            Les paramètres deport_tube et rayon_coupole ont été supprimés (v4.4).
            La méthode abaque (mesures terrain) remplace le calcul géométrique de parallaxe.
        """
        self.latitude = latitude
        self.longitude = longitude
        self.tz_offset = tz_offset

    # =========================================================================
    # UTILITAIRES
    # =========================================================================

    @staticmethod
    def _normaliser_angle_180(angle: float) -> float:
        """Normalise un angle entre -180° et +180°."""
        while angle > 180:
            angle -= 360
        while angle < -180:
            angle += 360
        return angle

    @staticmethod
    def _normaliser_angle_360(angle: float) -> float:
        """Normalise un angle entre 0° et 360°."""
        angle = angle % 360
        if angle < 0:
            angle += 360
        return angle

    # =========================================================================
    # CONVERSION DE COORDONNÉES
    # =========================================================================

    def convertir_j2000_vers_jnow(self, ad_j2000: float, dec_j2000: float,
                                  date_heure: datetime) -> Tuple[float, float]:
        """
        Convertit les coordonnées J2000 en coordonnées JNOW (époque actuelle).

        Args:
            ad_j2000: Ascension droite J2000 en degrés
            dec_j2000: Déclinaison J2000 en degrés
            date_heure: Date/heure d'observation

        Returns:
            Tuple (ad_jnow, dec_jnow) en degrés
        """
        from astropy.coordinates import CIRS

        # Créer une coordonnée J2000
        coord_j2000 = SkyCoord(ra=ad_j2000 * u.degree, dec=dec_j2000 * u.degree,
                               frame='icrs')

        # Convertir en temps Astropy
        if date_heure.tzinfo is None:
            dt_utc = date_heure - timedelta(hours=self.tz_offset)
        else:
            dt_utc = date_heure.astimezone(timezone.utc).replace(tzinfo=None)

        temps_obs = Time(dt_utc, scale='utc')

        # Appliquer précession/nutation vers l'époque actuelle
        coord_jnow = coord_j2000.transform_to(CIRS(obstime=temps_obs))

        return coord_jnow.ra.degree, coord_jnow.dec.degree

    def calculer_temps_sideral(self, date_heure: datetime) -> float:
        """Temps sidéral local (degrés) au méridien de l'observatoire."""
        # Si datetime locale naive: convertir en UTC avec tz_offset
        dt = date_heure
        if dt.tzinfo is None:
            dt_utc = dt - timedelta(hours=self.tz_offset)
        else:
            # si aware, la passer en UTC et enlever tzinfo pour le calcul
            dt_utc = dt.astimezone(timezone.utc).replace(tzinfo=None)

        JD = self._calculate_julian_day(dt_utc)
        GMST_deg = self._calculate_greenwich_sidereal_time(JD)
        # LST = GMST + longitude (Est positif)
        return (GMST_deg + self.longitude) % 360.0

    @staticmethod
    def _calculate_julian_day(dt_utc: datetime) -> float:
        """Jour Julien à partir d'une datetime UTC naive."""
        y, m = dt_utc.year, dt_utc.month
        d = dt_utc.day + (dt_utc.hour + (dt_utc.minute + dt_utc.second / 60.0) / 60.0) / 24.0
        if m <= 2:
            y -= 1
            m += 12
        A = y // 100
        B = 2 - A + A // 4
        JD = int(365.25 * (y + 4716)) + int(30.6001 * (m + 1)) + d + B - 1524.5
        return JD

    @staticmethod
    def _calculate_greenwich_sidereal_time(JD: float) -> float:
        """GMST (degrés) – formule IAU approchée."""
        T = (JD - 2451545.0) / 36525.0
        # GMST en secondes
        GMST_sec = 67310.54841 + (876600.0 * 3600 + 8640184.812866) * T + 0.093104 * T ** 2 - 6.2e-6 * T ** 3
        GMST_sec %= 86400.0
        if GMST_sec < 0:
            GMST_sec += 86400.0
        return GMST_sec / 240.0  # 86400 s -> 360°, donc 1° = 240 s

    @staticmethod
    def _add_time_component(theta_G0: float, hour: int, minute: int,
                            second: int, microsecond: int) -> float:
        """Ajoute la composante temporelle au temps sidéral."""
        time_seconds = hour * 3600 + minute * 60 + second + microsecond / 1000000.0
        return theta_G0 + 15.04106728 * (time_seconds / 3600.0)

    def calculer_angle_horaire(self, ascension_droite: float, date_heure: datetime,
                               deja_jnow: bool = False) -> float:
        """
        Calcule l'angle horaire en degrés.

        Args:
            ascension_droite: AD en degrés (J2000 ou JNOW selon deja_jnow)
            date_heure: Date/heure d'observation
            deja_jnow: Si True, AD déjà en JNOW (pas de conversion)
        """
        if not deja_jnow:
            ad_jnow, _ = self.convertir_j2000_vers_jnow(ascension_droite, 0, date_heure)
        else:
            ad_jnow = ascension_droite

        lst = self.calculer_temps_sideral(date_heure)
        ha = lst - ad_jnow

        while ha > 180:
            ha -= 360
        while ha < -180:
            ha += 360

        return ha

    def calculer_coords_horizontales(self, ascension_droite: float, declinaison: float,
                                     date_heure: datetime) -> Tuple[float, float]:
        """Convertit les coordonnées équatoriales en coordonnées horizontales."""
        # Conversion J2000 -> JNOW
        ad_jnow, dec_jnow = self.convertir_j2000_vers_jnow(ascension_droite, declinaison, date_heure)

        # Calcul angle horaire avec coordonnées JNOW (déjà converties)
        ha = self.calculer_angle_horaire(ad_jnow, date_heure, deja_jnow=True)
        return self._convert_to_horizontal(ha, dec_jnow)

    def _convert_to_horizontal(self, ha: float, declinaison: float) -> Tuple[float, float]:
        """Effectue la conversion vers les coordonnées horizontales."""
        ha_rad = math.radians(ha)
        dec_rad = math.radians(declinaison)
        lat_rad = math.radians(self.latitude)

        sin_alt = math.sin(lat_rad) * math.sin(dec_rad) + math.cos(lat_rad) * math.cos(dec_rad) * math.cos(ha_rad)
        alt_rad = math.asin(sin_alt)

        numerator = math.sin(ha_rad)
        denominator = math.cos(ha_rad) * math.sin(lat_rad) - math.tan(dec_rad) * math.cos(lat_rad)

        if denominator == 0:
            az_rad = math.pi / 2 if numerator > 0 else 3 * math.pi / 2
        else:
            az_rad = math.atan2(numerator, denominator)

        az_deg = (math.degrees(az_rad) + 180) % 360
        alt_deg = self._apply_refraction_correction(math.degrees(alt_rad))

        return az_deg, alt_deg

    @staticmethod
    def _apply_refraction_correction(altitude_deg: float) -> float:
        """Applique la correction pour la réfraction atmosphérique."""
        if altitude_deg < -0.5:
            return altitude_deg

        altitude_min = max(altitude_deg, 0.0)
        tan_term = math.tan(math.radians(altitude_min + 10.3 / 60 / (altitude_min + 5.11)))
        refraction_deg = 1.02 / 60 / tan_term

        return altitude_deg + refraction_deg

    def calculer_heure_passage_meridien(self, ad_deg: float, date_reference: datetime) -> datetime:
        """Calcule l'heure exacte du passage au méridien pour un objet."""
        minuit = date_reference.replace(hour=0, minute=0, second=0, microsecond=0)
        lst_minuit = self.calculer_temps_sideral(minuit)

        diff_deg = (ad_deg - lst_minuit) % 360
        diff_heures = diff_deg / 15.0
        diff_heures_solaires = diff_heures * (24.0 / 23.934469444)

        heures = int(diff_heures_solaires)
        minutes_reste = (diff_heures_solaires - heures) * 60
        minutes = int(minutes_reste)
        secondes = int((minutes_reste - minutes) * 60)

        passage = minuit.replace(hour=heures, minute=minutes, second=secondes)
        return passage

    def calculer_coords_horizontales_coupole(self, ascension_droite: float,
                                             declinaison: float,
                                             date_heure: datetime) -> Tuple[float, float, float]:
        """
        Calcule les coordonnées horizontales pour la coupole.

        Note v4.4: La correction de parallaxe géométrique a été supprimée.
        La méthode abaque (mesures terrain) est utilisée à la place pour le tracking.
        Cette méthode retourne maintenant les coordonnées horizontales brutes
        avec une correction de 0.

        Args:
            ascension_droite: AD de l'objet en degrés
            declinaison: Déclinaison de l'objet en degrés
            date_heure: Date et heure de l'observation

        Returns:
            Tuple (azimut, altitude, correction=0.0)
        """
        azimut, altitude = self.calculer_coords_horizontales(
            ascension_droite, declinaison, date_heure
        )
        return azimut, altitude, 0.0

    def calculer_vitesse_rotation_coupole(self, ascension_droite: float, declinaison: float,
                                          date_heure: datetime) -> Tuple[float, int, float, float]:
        """
        Calcule la vitesse et le sens de rotation nécessaires pour la coupole.

        Note v4.4: Utilise maintenant les coordonnées horizontales brutes
        (la correction de parallaxe est gérée par la méthode abaque).
        """
        date_heure1 = date_heure
        azimut1, altitude1 = self.calculer_coords_horizontales(
            ascension_droite, declinaison, date_heure1
        )

        date_heure2 = date_heure + timedelta(minutes=5)
        azimut2, altitude2 = self.calculer_coords_horizontales(
            ascension_droite, declinaison, date_heure2
        )

        delta_azimut = azimut2 - azimut1

        if delta_azimut > 180:
            delta_azimut -= 360
        elif delta_azimut < -180:
            delta_azimut += 360

        vitesse_horaire = delta_azimut / (5 / 60)
        vitesse_relative = abs(vitesse_horaire) / 360
        sens = 1 if delta_azimut >= 0 else -1

        return vitesse_relative, sens, azimut1, altitude1

    def est_proche_meridien(self, ad_deg: float, date_heure: datetime,
                            seuil_minutes: int = 5) -> Tuple[bool, float]:
        """Vérifie si un objet est proche du passage au méridien."""
        angle_horaire = self.calculer_angle_horaire(ad_deg, date_heure, deja_jnow=True)
        temps_avant_passage_secondes = -angle_horaire * 240
        est_proche = abs(temps_avant_passage_secondes) < seuil_minutes * 60

        return est_proche, temps_avant_passage_secondes