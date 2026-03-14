"""
Gestionnaire de catalogue d'objets astronomiques.

Ce module fournit des fonctionnalités pour gérer un catalogue d'objets astronomiques,
incluant la recherche locale, la recherche en ligne via SIMBAD

"""

import json
import logging
from datetime import datetime
from pathlib import Path
from typing import Dict, Optional, Any

from core.config.config import CACHE_FILE

logger = logging.getLogger(__name__)

# Importer astropy si disponible
try:
    import astropy  # noqa: F401
    ASTROPY_AVAILABLE = True
except Exception:
    ASTROPY_AVAILABLE = False

class GestionnaireCatalogue:
    """
    Gestionnaire de catalogue d'objets astronomiques utilisant des API en ligne
    ou des bibliothèques dédiées.
    
    Cette classe fournit des méthodes pour rechercher des objets célestes dans un
    catalogue local ou en ligne via SIMBAD, ainsi que pour importer et exporter
    des données de catalogue.
    
    Attributes:
        objets: Dictionnaire contenant les objets du catalogue
        cache_file: Chemin vers le fichier de cache JSON
        simbad: Instance de Simbad configurée avec des champs supplémentaires
    """
    
    def __init__(self) -> None:
        """
        Initialise le gestionnaire de catalogue.
        
        Charge le cache d'objets s'il existe et configure SIMBAD si disponible.
        """
        self.objets: Dict[str, Dict[str, Any]] = {}  # Catalogue local
        self.cache_file: Path = CACHE_FILE  # Fichier de cache
        
        # Charger le cache s'il existe
        self._charger_cache()
        
        # Configurer Simbad si disponible
        if ASTROPY_AVAILABLE:
            try:
                from astroquery.simbad import Simbad
                # Ajouter des colonnes à la requête Simbad
                self.simbad = Simbad()
                self.simbad.add_votable_fields('otype', 'ra(d)', 'dec(d)', 'flux(V)', 'morphtype')
            except ImportError:
                self.simbad = None
    
    def _charger_cache(self) -> None:
        """
        Charge le cache d'objets depuis un fichier JSON.
        
        Si le fichier de cache existe, tente de le charger dans le dictionnaire
        d'objets. En cas d'erreur, initialise un dictionnaire vide.
        """
        if self.cache_file.exists():
            try:
                with open(self.cache_file, 'r', encoding='utf-8') as f:
                    self.objets = json.load(f)
            except Exception as e:
                logger.warning(f"Erreur lors du chargement du cache: {e}")
                self.objets = {}
    
    def _sauvegarder_cache(self) -> None:
        """
        Sauvegarde le cache d'objets dans un fichier JSON.
        
        Tente d'écrire le dictionnaire d'objets dans le fichier de cache
        spécifié par self.cache_file.
        """
        try:
            # Vérifier si le répertoire parent existe, le créer si nécessaire
            self.cache_file.parent.mkdir(parents=True, exist_ok=True)
            
            with open(self.cache_file, 'w', encoding='utf-8') as f:
                json.dump(self.objets, f, indent=2, ensure_ascii=False)
        except Exception as e:
            logger.warning(f"Erreur lors de la sauvegarde du cache: {e}")


    def rechercher_simbad(self, identifiant: str) -> Optional[Dict[str, Any]]:
        """
                Recherche un objet dans la base de données SIMBAD.

                Cette méthode recherche d'abord l'objet dans le cache local, puis
                effectue une requête à SIMBAD si nécessaire. Les résultats sont
                mis en cache pour les futures recherches.

                Args:
                    identifiant: Identifiant de l'objet (M42, NGC7000, etc.)

                Returns:
                    Optional[Dict[str, Any]]: Informations sur l'objet ou None si non trouvé

                Example:
                    catalogue = GestionnaireCatalogue()
                    objet = catalogue.rechercher_simbad("M42")
                    if objet:
                    ...     print(f"Objet trouvé: {objet['nom']}, AD={objet['ad']}, DEC={objet['dec']}")
        """
        # BYPASS TEMPORAIRE - forcer la vérification
        try:
            from astroquery.simbad import Simbad
        except ImportError as e:
            logger.warning(f"Cette fonctionnalité nécessite astropy et astroquery: {e}")
            return None

        # Vérifier si l'objet est déjà dans le cache
        cache_key = identifiant.upper()
        if cache_key in self.objets:
            return self.objets[cache_key]

        try:

            # Configuration SIMPLE de Simbad (sans champs supplémentaires)
            from astroquery.simbad import Simbad
            simple_simbad = Simbad()


            # Exécuter la requête
            result_table = simple_simbad.query_object(identifiant)

            if result_table is None or len(result_table) == 0:
                logger.debug(f"Objet non trouvé via SIMBAD: {identifiant}")
                return None

            # Récupérer les données de la première ligne
            result = result_table[0]

            # Utiliser les colonnes par défaut de SIMBAD (noms en minuscules)
            main_id = result['main_id'].decode('utf-8') if isinstance(result['main_id'], bytes) else str(
                result['main_id'])

            # Coordonnées depuis les colonnes par défaut
            ra_coord = result['ra']
            dec_coord = result['dec']


            # Convertir en SkyCoord
            from astropy.coordinates import SkyCoord

            # Les coordonnées sont déjà en degrés selon le résultat
            coords = SkyCoord(ra=ra_coord, dec=dec_coord, unit='deg')


            ad_str = coords.ra.to_string(unit="hourangle", sep=('h', 'm', 's'), precision=2, pad=True)
            dec_str = coords.dec.to_string(unit="degree", sep=('°', '\'', '"'), precision=2, pad=True)

            # Créer l'objet avec les informations disponibles
            objet = {
                'nom': main_id,
                'ad': ad_str,
                'dec': dec_str,
                'ra_deg': coords.ra.degree,
                'dec_deg': coords.dec.degree,
                'type': 'Unknown',  # Type non disponible sans champs supplémentaires
                'source': 'SIMBAD',
                'date_ajout': datetime.now().strftime('%Y-%m-%d %H:%M:%S')
            }

            # Ajouter au cache
            self.objets[cache_key] = objet
            self._sauvegarder_cache()

            return objet

        except Exception as e:
            logger.warning(f"Erreur lors de la recherche de {identifiant}: {e}")
            return None

    def rechercher_catalogue_local(self, identifiant: str) -> Optional[Dict[str, Any]]:
        """
        Recherche un objet dans le catalogue local.
        
        Cette méthode tente de trouver un objet dans le catalogue local en utilisant
        son identifiant exact ou des variantes courantes. Elle effectue également une
        recherche partielle si nécessaire.
        
        Args:
            identifiant: Identifiant de l'objet
            
        Returns:
            Optional[Dict[str, Any]]: Informations sur l'objet ou None si non trouvé
        
        Example:
            catalogue = GestionnaireCatalogue()
            objet = catalogue.rechercher_catalogue_local("M42")
            if objet:
            ...     print(f"Objet trouvé: {objet['nom']}")
        """


        # Normaliser l'identifiant
        id_norm = identifiant.upper()

        # Recherche directe
        if id_norm in self.objets:
            # print(f"  ✅ Trouvé directement: '{id_norm}'")
            return self.objets[id_norm]

        # Essayer quelques variantes courantes
        variantes = [
            id_norm,
            id_norm.replace(' ', ''),
            'M' + id_norm if id_norm.isdigit() else id_norm,
            'NGC' + id_norm if id_norm.isdigit() else id_norm,
            'IC' + id_norm if id_norm.isdigit() else id_norm
        ]


        for var in variantes:
            if var in self.objets:
                return self.objets[var]

        # Recherche partielle
        correspondances = []
        for code, objet in self.objets.items():
            if id_norm in code or (objet.get('nom') and id_norm in objet['nom'].upper()):
                correspondances.append((code, objet))


        if correspondances:
            # Trier par pertinence (longueur du code)
            correspondances.sort(key=lambda x: len(x[0]))
            return correspondances[0][1]

        logger.debug(f"Aucune correspondance locale pour: {identifiant}")
        return None


    def rechercher(self, identifiant: str, utiliser_api: bool = True) -> Optional[Dict[str, Any]]:
        """
        Recherche un objet par son identifiant.
        
        Cette méthode recherche d'abord dans le catalogue local, puis en ligne
        via SIMBAD si nécessaire et autorisé.
        
        Args:
            identifiant: Identifiant de l'objet (M42, NGC7000, etc.)
            utiliser_api: Si True, recherche aussi dans les API en ligne
            
        Returns:
            Optional[Dict[str, Any]]: Informations sur l'objet ou None si non trouvé
        
        Example:
            catalogue = GestionnaireCatalogue()
            objet = catalogue.rechercher("M42")
            if objet:
            ...     print(f"Objet trouvé: {objet['nom']}")
        """

        from core.observatoire import PlanetaryEphemerides

        # D'abord vérifier si c'est une planète
        if PlanetaryEphemerides.is_planet(identifiant):
            # Pour les planètes, on a besoin de la position de l'observateur
            # On utilise les coordonnées par défaut du config.json
            try:
                import json
                from pathlib import Path
                cfg_path = Path("data") / "config.json"
                with open(cfg_path, "r", encoding="utf-8") as f:
                    cfg = json.load(f)
                lat = cfg["site"]["latitude"]
                lon = cfg["site"]["longitude"]

                # Calculer la position actuelle de la planète
                pos = PlanetaryEphemerides.get_planet_position(
                    identifiant, datetime.now(), lat, lon
                )

                if pos:
                    ra_deg, dec_deg = pos
                    return {
                        "name": identifiant.capitalize(),
                        "ra_deg": ra_deg,
                        "dec_deg": dec_deg,
                        "type": "planet"
                    }
            except Exception:
                pass

        objet = self.rechercher_catalogue_local(identifiant)

        if objet:
            return objet
        else:
            logger.debug(f"Objet non trouvé dans le catalogue local: {identifiant}")

        # 2. Si non trouvé localement et API activée, rechercher en ligne
        if objet is None and utiliser_api:
            objet = self.rechercher_simbad(identifiant)

            if not objet:
                logger.debug(f"Objet non trouvé via SIMBAD: {identifiant}")

        elif objet is None and not utiliser_api:
            logger.debug(f"API désactivée pour recherche: {identifiant}")

        return objet
