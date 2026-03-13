"""
Gestionnaire d'abaque empirique pour le suivi de coupole.

Ce module charge les données réelles mesurées sur site et utilise
une interpolation 2D pour déterminer la position optimale de la coupole
en fonction de l'altitude et de l'azimut de l'objet.

L'abaque est basée sur des mesures réelles qui prennent en compte :
- La géométrie réelle de la monture
- La géométrie de la coupole
- Les dimensions de la trappe
- Tous les effets physiques réels du système
"""

import json
import logging
from pathlib import Path
from typing import Dict, Tuple

import numpy as np
import openpyxl


class AbaqueManager:
    """
    Gère l'abaque empirique pour le positionnement de la coupole.
    
    L'abaque fournit une correspondance directe entre :
    - (altitude_objet, azimut_objet) → azimut_coupole optimal
    
    Cette approche remplace les calculs vectoriels théoriques par
    des données empiriques mesurées sur le terrain.
    """
    
    def __init__(self, abaque_file: str = "data/Loi_coupole.xlsx"):
        """
        Initialise le gestionnaire d'abaque.
        
        Args:
            abaque_file: Chemin vers le fichier Excel contenant l'abaque
        """
        self.abaque_file = Path(abaque_file)
        self.logger = logging.getLogger(__name__)
        
        # Données brutes de l'abaque
        self.data_by_altitude: Dict[float, Dict[str, list]] = {}
        
        # Interpolateur 2D
        self.interpolator = None
        
        # Statistiques
        self.n_altitudes = 0
        self.n_azimuths = 0
        self.altitude_range = (0.0, 0.0)
        self.azimuth_range = (0.0, 0.0)
        
        # État
        self.is_loaded = False
    
    def load_abaque(self) -> bool:
        """
        Charge l'abaque depuis le fichier Excel.
        
        Returns:
            True si le chargement a réussi, False sinon
        """
        if not self.abaque_file.exists():
            self.logger.error(f"Fichier abaque introuvable: {self.abaque_file}")
            return False
        
        try:
            self.logger.info(f"Chargement de l'abaque depuis {self.abaque_file}")
            
            # Charger le fichier Excel
            wb = openpyxl.load_workbook(self.abaque_file)
            ws = wb.active
            
            # Parser les données
            current_altitude = None
            
            for row in ws.iter_rows(values_only=True):
                # Détecter une nouvelle altitude
                if row[1] and isinstance(row[1], str) and 'Hauteur' in row[1]:
                    altitude_str = row[1].replace('Hauteur ', '').replace('°', '').strip()
                    try:
                        current_altitude = float(altitude_str)
                        self.data_by_altitude[current_altitude] = {
                            'az_astre': [],
                            'az_coupole': []
                        }
                    except ValueError:
                        pass
                
                # Ignorer les lignes d'en-tête
                elif row[1] == 'Az astre':
                    continue
                
                # Lire les données
                elif current_altitude is not None and row[1] is not None:
                    try:
                        az_astre = float(row[1])
                        az_coupole = float(row[2]) if row[2] is not None else None
                        
                        if az_coupole is not None:
                            self.data_by_altitude[current_altitude]['az_astre'].append(az_astre)
                            self.data_by_altitude[current_altitude]['az_coupole'].append(az_coupole)
                    except (ValueError, TypeError):
                        pass
            
            # Calculer les statistiques
            self._compute_statistics()
            
            # Créer l'interpolateur
            self._create_interpolator()
            
            self.is_loaded = True
            
            self.logger.info("=" * 50)
            self.logger.info("ABAQUE CHARGÉE AVEC SUCCÈS")
            self.logger.info(f"  Altitudes: {self.n_altitudes} points ({self.altitude_range[0]:.0f}° - {self.altitude_range[1]:.0f}°)")
            self.logger.info(f"  Azimuts: {self.n_azimuths} points par altitude")
            self.logger.info(f"  Points totaux: {self.n_altitudes * self.n_azimuths}")
            self.logger.info("=" * 50)
            
            return True
            
        except Exception as e:
            self.logger.error(f"Erreur lors du chargement de l'abaque: {e}")
            return False
    
    def _compute_statistics(self):
        """Calcule les statistiques sur l'abaque chargée."""
        if not self.data_by_altitude:
            return
        
        self.n_altitudes = len(self.data_by_altitude)
        
        # Nombre d'azimuts (on prend le premier)
        first_alt = next(iter(self.data_by_altitude.values()))
        self.n_azimuths = len(first_alt['az_astre'])
        
        # Plages
        altitudes = sorted(self.data_by_altitude.keys())
        self.altitude_range = (altitudes[0], altitudes[-1])
        
        all_azimuths = []
        for data in self.data_by_altitude.values():
            all_azimuths.extend(data['az_astre'])
        self.azimuth_range = (min(all_azimuths), max(all_azimuths))
    
    def _create_interpolator(self):
        """
        Crée l'interpolateur 2D à partir des données de l'abaque.
        
        Utilise une interpolation bilinéaire pour estimer les positions
        intermédiaires non mesurées.
        """
        # Préparer les données pour l'interpolation
        altitudes = sorted(self.data_by_altitude.keys())
        
        # Vérifier que tous les azimuts sont identiques pour chaque altitude
        first_alt = self.data_by_altitude[altitudes[0]]
        azimuths = sorted(first_alt['az_astre'])
        
        # Créer une grille régulière
        alt_grid = np.array(altitudes)
        az_grid = np.array(azimuths)
        
        # Sauvegarder les grilles pour référence
        self._alt_grid = alt_grid
        self._az_grid = az_grid
        self._data_dict = self.data_by_altitude

        self.logger.info(f"Grille créée {len(alt_grid)}x{len(az_grid)} (interpolation manuelle)")

    def _interpolate_circular(self, alt, az):
        """Interpolation bilinéaire avec gestion angles circulaires."""
        # Trouver indices grille
        i_alt = np.searchsorted(self._alt_grid, alt) - 1
        i_az = np.searchsorted(self._az_grid, az) - 1

        # Bornes
        i_alt = max(0, min(i_alt, len(self._alt_grid) - 2))
        i_az = max(0, min(i_az, len(self._az_grid) - 2))

        alt1, alt2 = self._alt_grid[i_alt], self._alt_grid[i_alt + 1]
        az1, az2 = self._az_grid[i_az], self._az_grid[i_az + 1]

        # Récupérer les 4 valeurs
        def get_val(altitude, azimut):
            data = self._data_dict[altitude]
            idx = list(data['az_astre']).index(azimut)
            return data['az_coupole'][idx]

        v11 = get_val(alt1, az1)
        v12 = get_val(alt1, az2)
        v21 = get_val(alt2, az1)
        v22 = get_val(alt2, az2)

        # Interpolation avec gestion circularité
        def interp_angle(angle1, angle2, frac):
            delta = angle2 - angle1
            if delta > 180:
                delta -= 360
            elif delta < -180:
                delta += 360
            return (angle1 + frac * delta) % 360

        # Interpolation azimut
        frac_az = (az - az1) / (az2 - az1)
        v1 = interp_angle(v11, v12, frac_az)
        v2 = interp_angle(v21, v22, frac_az)

        # Interpolation altitude
        frac_alt = (alt - alt1) / (alt2 - alt1)
        return interp_angle(v1, v2, frac_alt)

    def get_dome_position(
        self,
        altitude_objet: float,
        azimut_objet: float
    ) -> Tuple[float, Dict]:
        """
        Retourne la position optimale de la coupole pour un objet donné.
        
        Args:
            altitude_objet: Altitude de l'objet en degrés (0-90°)
            azimut_objet: Azimut de l'objet en degrés (0-360°)
        
        Returns:
            Tuple (azimut_coupole, infos_debug)
            - azimut_coupole: Position optimale de la coupole (0-360°)
            - infos_debug: Dictionnaire avec les détails du calcul
        """
        if not self.is_loaded:
            raise RuntimeError("Abaque non chargée. Appelez load_abaque() d'abord.")
        
        # Normaliser l'azimut dans [0, 360[
        azimut_objet = azimut_objet % 360
        
        # Vérifier si on est dans les limites de l'abaque
        in_bounds = (
            self.altitude_range[0] <= altitude_objet <= self.altitude_range[1] and
            self.azimuth_range[0] <= azimut_objet <= self.azimuth_range[1]
        )
        
        # Interpoler la position
        try:
            azimut_coupole = self._interpolate_circular(altitude_objet, azimut_objet)
            method = "interpolation" if in_bounds else "extrapolation"
        except Exception as e:
            self.logger.error(f"Erreur d'interpolation: {e}")
            # Fallback: trouver le point le plus proche
            azimut_coupole = self._nearest_neighbor(altitude_objet, azimut_objet)
            method = "nearest_neighbor"
        
        # Informations de debug
        infos = {
            "altitude_objet": altitude_objet,
            "azimut_objet": azimut_objet,
            "azimut_coupole": azimut_coupole,
            "method": method,
            "in_bounds": in_bounds,
            "altitude_range": self.altitude_range,
            "azimut_range": self.azimuth_range
        }
        
        return azimut_coupole, infos
    
    def _nearest_neighbor(self, altitude: float, azimut: float) -> float:
        """
        Trouve la position de coupole du point le plus proche dans l'abaque.
        
        Méthode de secours en cas d'échec de l'interpolation.
        """
        min_dist = float('inf')
        nearest_coupole = 0.0
        
        for alt in self.data_by_altitude:
            data = self.data_by_altitude[alt]
            for az_astre, az_coupole in zip(data['az_astre'], data['az_coupole']):
                # Distance euclidienne (pondérée car les échelles sont différentes)
                dist = np.sqrt(
                    ((altitude - alt) / 90.0) ** 2 +
                    ((azimut - az_astre) / 360.0) ** 2
                )
                if dist < min_dist:
                    min_dist = dist
                    nearest_coupole = az_coupole
        
        return nearest_coupole
    
    def get_diagnostics(self) -> Dict:
        """
        Retourne un diagnostic complet de l'abaque.
        
        Returns:
            Dictionnaire avec les informations de diagnostic
        """
        if not self.is_loaded:
            return {
                "status": "not_loaded",
                "message": "Abaque non chargée"
            }
        
        return {
            "status": "loaded",
            "file": str(self.abaque_file),
            "statistics": {
                "n_altitudes": self.n_altitudes,
                "n_azimuths": self.n_azimuths,
                "total_points": self.n_altitudes * self.n_azimuths,
                "altitude_range": self.altitude_range,
                "azimuth_range": self.azimuth_range
            },
            "altitudes_available": sorted(self.data_by_altitude.keys())
        }
    
    def export_to_json(self, output_file: str = "data/abaque_export.json"):
        """
        Exporte l'abaque au format JSON pour sauvegarde/analyse.
        
        Args:
            output_file: Chemin du fichier de sortie
        """
        if not self.is_loaded:
            self.logger.error("Abaque non chargée")
            return False
        
        try:
            export_data = {
                "metadata": {
                    "source_file": str(self.abaque_file),
                    "n_altitudes": self.n_altitudes,
                    "n_azimuths": self.n_azimuths,
                    "altitude_range": self.altitude_range,
                    "azimuth_range": self.azimuth_range
                },
                "data": self.data_by_altitude
            }
            
            output_path = Path(output_file)
            output_path.parent.mkdir(parents=True, exist_ok=True)
            
            with open(output_path, 'w', encoding='utf-8') as f:
                json.dump(export_data, f, indent=2, ensure_ascii=False)
            
            self.logger.info(f"Abaque exportée vers {output_file}")
            return True
            
        except Exception as e:
            self.logger.error(f"Erreur lors de l'export: {e}")
            return False
