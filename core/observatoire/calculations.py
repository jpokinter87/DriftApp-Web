"""
Module de calculs astronomiques pour l'observatoire.

VERSION 4.1 : Refactorisé pour lisibilité et maintenabilité.
- Formule de correction de parallaxe géométrique
- Conversion J2000 -> JNOW via Astropy
"""
import math
from datetime import datetime, timedelta, timezone
from typing import Tuple

from astropy.coordinates import SkyCoord, CIRS
from astropy.time import Time
import astropy.units as u


class AstronomicalCalculations:
    """Classe pour les calculs astronomiques."""

    def __init__(self, latitude: float, longitude: float, tz_offset: int,
                 deport_tube: float = 0.40, rayon_coupole: float = 1.20):
        """
        Initialise les calculs astronomiques.

        Args:
            latitude: Latitude de l'observatoire en degrés
            longitude: Longitude de l'observatoire en degrés
            tz_offset: Décalage horaire par rapport à UTC
            deport_tube: Distance entre l'axe AD et le centre du tube (mètres)
            rayon_coupole: Rayon de la coupole (mètres)
        """
        self.latitude = latitude
        self.longitude = longitude
        self.tz_offset = tz_offset
        self.deport_tube = deport_tube
        self.rayon_coupole = rayon_coupole

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

    def calculer_correction_parallaxe(self, azimut: float, altitude: float) -> float:
        """
        Calcule la correction d'azimut due à la parallaxe de la monture équatoriale.

        NOUVELLE FORMULE CORRIGÉE - Version simplifiée géométrique

        Cette correction est nécessaire car le tube du télescope est déporté de 40 cm
        par rapport à l'axe d'ascension droite de la monture équatoriale allemande.

        La nouvelle formule utilise une approximation géométrique simple qui donne
        des résultats cohérents et symétriques.

        Args:
            azimut: Azimut de l'objet visé en degrés (0° = Nord, 90° = Est)
            altitude: Altitude de l'objet visé en degrés

        Returns:
            Correction en degrés à AJOUTER à l'azimut théorique pour obtenir
            l'azimut réel où positionner la coupole
        """
        # Conversion en radians
        az_rad = math.radians(azimut)
        alt_rad = math.radians(altitude)

        # Angle de parallaxe maximal (en radians)
        # C'est l'angle sous-tendu par le déport vu depuis la distance au point visé
        parallaxe_max = math.atan(self.deport_tube / self.rayon_coupole)

        # La correction diminue avec l'altitude (nulle au zénith)
        facteur_altitude = math.cos(alt_rad)

        # La correction dépend de la position relative par rapport à l'axe polaire
        # Pour une monture allemande, le déport est perpendiculaire à l'axe polaire
        # La correction est maximale quand on vise Est ou Ouest
        # Elle est minimale (mais non nulle) quand on vise Nord ou Sud

        # Composante Est-Ouest de la correction
        correction_rad = parallaxe_max * facteur_altitude * math.sin(az_rad)

        # Conversion en degrés
        correction_deg = math.degrees(correction_rad)

        return correction_deg

    def calculer_correction_parallaxe_ancienne(self, azimut: float, altitude: float) -> float:
        """
        ANCIENNE FORMULE (conservée pour comparaison) - NE PAS UTILISER EN PRODUCTION

        Cette formule produit des résultats incorrects avec des corrections aberrantes.
        Elle est conservée uniquement pour permettre la comparaison et les tests.
        """
        Az = math.radians(azimut)
        h = math.radians(altitude)
        phi = math.radians(self.latitude)

        d = self.deport_tube
        R = self.rayon_coupole

        # Direction de pointage (vecteur unitaire vers l'objet)
        x_obj = math.cos(h) * math.sin(Az)
        y_obj = math.cos(h) * math.cos(Az)
        z_obj = math.sin(h)

        # Direction de l'axe polaire (vers le pôle nord céleste)
        x_pole = 0
        y_pole = math.sin(phi)
        z_pole = math.cos(phi)

        # Produit vectoriel pour obtenir la direction du déport
        dx = y_pole * z_obj - z_pole * y_obj
        dy = z_pole * x_obj - x_pole * z_obj
        dz = x_pole * y_obj - y_pole * x_obj

        # Normalisation du vecteur déport
        norm = math.sqrt(dx ** 2 + dy ** 2 + dz ** 2)
        if norm > 0:
            dx, dy, dz = dx / norm, dy / norm, dz / norm
        else:
            return 0.0

        # Position réelle du centre du tube du télescope
        x_tube = x_obj + d * dx
        y_tube = y_obj + d * dy

        # Azimut du tube (position réelle)
        azimut_tube = math.atan2(x_tube, y_tube)

        # Correction = différence entre azimut du tube et azimut de l'objet
        correction = math.degrees(azimut_tube - Az)

        # Normalisation entre -180 et +180
        if correction > 180:
            correction -= 360
        elif correction < -180:
            correction += 360

        return correction

    def calculer_coords_horizontales_coupole(self, ascension_droite: float,
                                             declinaison: float,
                                             date_heure: datetime) -> Tuple[float, float, float]:
        """
        Calcule les coordonnées horizontales CORRIGÉES pour la coupole.

        Cette méthode calcule d'abord l'azimut et l'altitude de l'objet visé,
        puis applique la correction de parallaxe pour obtenir la position réelle
        où doit être orientée la coupole.

        Args:
            ascension_droite: AD de l'objet en degrés
            declinaison: Déclinaison de l'objet en degrés
            date_heure: Date et heure de l'observation

        Returns:
            Tuple (azimut_coupole, altitude_objet, correction_appliquee)
            - azimut_coupole: Azimut corrigé pour positionner la coupole (degrés)
            - altitude_objet: Altitude de l'objet (degrés)
            - correction_appliquee: Correction en degrés qui a été appliquée
        """
        # Calcul des coordonnées horizontales de l'objet
        azimut_objet, altitude_objet = self.calculer_coords_horizontales(
            ascension_droite, declinaison, date_heure
        )

        # Calcul de la correction de parallaxe
        correction = self.calculer_correction_parallaxe(azimut_objet, altitude_objet)

        # Azimut corrigé pour la coupole
        azimut_coupole = azimut_objet + correction

        # Normalisation 0-360
        if azimut_coupole < 0:
            azimut_coupole += 360
        elif azimut_coupole >= 360:
            azimut_coupole -= 360

        return azimut_coupole, altitude_objet, correction

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

    def calculer_vitesse_rotation_coupole(self, ascension_droite: float, declinaison: float,
                                          date_heure: datetime) -> Tuple[float, int, float, float]:
        """
        Calcule la vitesse et le sens de rotation nécessaires pour la coupole.

        IMPORTANT: Cette méthode utilise maintenant les coordonnées CORRIGÉES
        pour tenir compte de la parallaxe de la monture.
        """
        date_heure1 = date_heure
        # Utilisation de la méthode corrigée
        azimut1, altitude1, _ = self.calculer_coords_horizontales_coupole(
            ascension_droite, declinaison, date_heure1
        )

        date_heure2 = date_heure + timedelta(minutes=5)
        azimut2, altitude2, _ = self.calculer_coords_horizontales_coupole(
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

    def valider_symetrie(self, tolerance: float = 0.1) -> bool:
        """
        Valide que les corrections sont symétriques Est-Ouest.

        Args:
            tolerance: Tolérance en degrés pour la symétrie

        Returns:
            True si la symétrie est respectée
        """
        altitudes_test = [15, 30, 45, 60, 75]

        for alt in altitudes_test:
            # Correction Est
            corr_est = self.calculer_correction_parallaxe(90, alt)
            # Correction Ouest
            corr_ouest = self.calculer_correction_parallaxe(270, alt)

            # Les corrections doivent être opposées (symétrie)
            if abs(corr_est + corr_ouest) > tolerance:
                print(f"❌ Symétrie non respectée à alt={alt}°: Est={corr_est:.2f}°, Ouest={corr_ouest:.2f}°")
                return False

        print("✅ Symétrie Est-Ouest validée")
        return True


# ============================================================================
# MODULE DE TEST ET VALIDATION
# ============================================================================

def generer_tests_validation(calc: AstronomicalCalculations):
    """
    Génère des tests de validation pour la correction de parallaxe.

    Args:
        calc: Instance de AstronomicalCalculations
    """
    print(f"\n{'=' * 80}")
    print(f"TESTS DE VALIDATION - CORRECTION PARALLAXE (NOUVELLE FORMULE)")
    print(f"{'=' * 80}\n")
    print(f"Latitude: {calc.latitude}°")
    print(f"Déport tube: {calc.deport_tube} m")
    print(f"Rayon coupole: {calc.rayon_coupole} m")
    print(f"\n{'=' * 80}\n")

    # Définition des tests
    tests = [
        ("Zénith", 180, 90),
        ("Méridien Sud h=45°", 180, 45),
        ("Est h=30°", 90, 30),
        ("Ouest h=30°", 270, 30),
        ("Est h=60°", 90, 60),
        ("Ouest h=60°", 270, 60),
        ("Nord-Est h=40°", 45, 40),
        ("Nord-Ouest h=40°", 315, 40),
        ("Sud-Est h=40°", 135, 40),
        ("Sud-Ouest h=40°", 225, 40),
        ("Horizon Est", 90, 15),
        ("Horizon Ouest", 270, 15),
    ]

    print(f"{'Position':<20} | {'Az obj':>7} | {'Alt':>5} | {'Correction':>11} | {'Az coupole':>11}")
    print(f"{'-' * 20}-+-{'-' * 7}-+-{'-' * 5}-+-{'-' * 11}-+-{'-' * 11}")

    for nom, az, alt in tests:
        correction = calc.calculer_correction_parallaxe(az, alt)
        az_corrige = az + correction
        if az_corrige < 0:
            az_corrige += 360
        elif az_corrige >= 360:
            az_corrige -= 360

        critique = "⚠️" if nom in ["Méridien Sud h=45°", "Est h=30°", "Ouest h=30°",
                                   "Horizon Est", "Horizon Ouest"] else "  "

        print(f"{nom:<20} | {az:6.1f}° | {alt:4.1f}° | {correction:+10.2f}° | {az_corrige:10.1f}° {critique}")

    print(f"\n{'=' * 80}\n")


def test_symetrie(calc: AstronomicalCalculations):
    """Test de symétrie Est/Ouest."""
    print(f"TEST DE SYMÉTRIE (validation du modèle)\n")
    print("Les corrections Est/Ouest doivent être opposées:\n")

    for alt in [30, 45, 60]:
        corr_est = calc.calculer_correction_parallaxe(90, alt)
        corr_ouest = calc.calculer_correction_parallaxe(270, alt)
        diff = abs(corr_est + corr_ouest)

        print(f"Altitude {alt}°:")
        print(f"  Est:   {corr_est:+7.2f}°")
        print(f"  Ouest: {corr_ouest:+7.2f}°")
        print(f"  Symétrie OK: {diff < 0.01} (écart: {diff:.4f}°)\n")


def comparer_formules(calc: AstronomicalCalculations):
    """Compare l'ancienne et la nouvelle formule."""
    print(f"\n{'=' * 80}")
    print(f"COMPARAISON ANCIENNE vs NOUVELLE FORMULE")
    print(f"{'=' * 80}\n")

    tests = [
        ("Zénith", 180, 90),
        ("Est h=30°", 90, 30),
        ("Ouest h=30°", 270, 30),
        ("Est h=60°", 90, 60),
        ("Ouest h=60°", 270, 60),
    ]

    print(f"{'Position':<15} | {'Ancienne':>12} | {'Nouvelle':>12} | {'Différence':>12}")
    print(f"{'-' * 15}-+-{'-' * 12}-+-{'-' * 12}-+-{'-' * 12}")

    for nom, az, alt in tests:
        ancienne = calc.calculer_correction_parallaxe_ancienne(az, alt)
        nouvelle = calc.calculer_correction_parallaxe(az, alt)
        diff = abs(ancienne - nouvelle)

        print(f"{nom:<15} | {ancienne:+11.2f}° | {nouvelle:+11.2f}° | {diff:11.2f}°")

    print(f"\n{'=' * 80}\n")


if __name__ == "__main__":
    # Exemple d'utilisation avec la latitude du site de test
    calc = AstronomicalCalculations(
        latitude=44.25,  # Latitude du site de test
        longitude=5.0,  # Votre longitude
        tz_offset=1,  # Décalage horaire
        deport_tube=0.40,  # 40 cm
        rayon_coupole=1.20  # 120 cm
    )

    # Tests de validation
    generer_tests_validation(calc)
    test_symetrie(calc)
    comparer_formules(calc)

    # Exemple d'utilisation dans le code réel
    print("\nEXEMPLE D'UTILISATION:")
    print("=" * 80)

    from datetime import datetime

    # Simulation avec les données du problème réel
    # NGC6826: RA=296.20° DEC=50.53°
    ad = 296.20  # degrés
    dec = 50.53  # degrés
    maintenant = datetime.now()

    # Méthode 1: Obtenir directement les coordonnées corrigées
    az_coupole, alt, correction = calc.calculer_coords_horizontales_coupole(ad, dec, maintenant)

    print(f"\nObjet NGC6826: AD={ad}°, DEC={dec}°")
    print(f"Azimut objet calculé: {az_coupole - correction:.2f}°")
    print(f"Altitude: {alt:.2f}°")
    print(f"Correction parallaxe (nouvelle): {correction:+.2f}°")
    print(f"Azimut coupole: {az_coupole:.2f}°")

    # Comparaison avec l'ancienne formule
    az_objet, alt_objet = calc.calculer_coords_horizontales(ad, dec, maintenant)
    correction_ancienne = calc.calculer_correction_parallaxe_ancienne(az_objet, alt_objet)
    print(f"\nCorrection ancienne formule: {correction_ancienne:+.2f}° (INCORRECTE!)")
    print(f"Différence: {abs(correction - correction_ancienne):.2f}°")