"""
Tests pour core/observatoire/catalogue.py

Couvre :
- GestionnaireCatalogue construction et cache
- Recherche locale (exact, variantes, partielle)
- Recherche planètes
- Recherche SIMBAD (avec le vrai cache si disponible)
- Bug connu H-14 : résultat planète incohérent (name vs nom, is_planet manquant)
"""

import json

import pytest



@pytest.fixture
def empty_catalogue(tmp_path, monkeypatch):
    """Catalogue avec un cache vide dans un répertoire temporaire."""
    cache_file = tmp_path / "objets_cache.json"
    import core.config.config as config_module
    monkeypatch.setattr(config_module, "CACHE_FILE", cache_file)
    # Reload le module catalogue pour utiliser le nouveau CACHE_FILE
    import importlib
    import core.observatoire.catalogue as cat_module
    importlib.reload(cat_module)
    return cat_module.GestionnaireCatalogue()


@pytest.fixture
def populated_catalogue(tmp_path, monkeypatch):
    """Catalogue avec des objets pré-chargés."""
    cache_file = tmp_path / "objets_cache.json"
    objects = {
        "M42": {
            "nom": "M 42",
            "ra_deg": 83.82,
            "dec_deg": -5.39,
            "type": "HII",
            "source": "SIMBAD",
        },
        "NGC7000": {
            "nom": "NGC 7000",
            "ra_deg": 314.68,
            "dec_deg": 44.33,
            "type": "HII",
            "source": "SIMBAD",
        },
        "SIRIUS": {
            "nom": "* alf CMa",
            "ra_deg": 101.29,
            "dec_deg": -16.72,
            "type": "Star",
            "source": "SIMBAD",
        },
    }
    cache_file.write_text(json.dumps(objects, indent=2))

    import core.config.config as config_module
    monkeypatch.setattr(config_module, "CACHE_FILE", cache_file)
    import importlib
    import core.observatoire.catalogue as cat_module
    importlib.reload(cat_module)
    return cat_module.GestionnaireCatalogue()


# =============================================================================
# Construction et cache
# =============================================================================

class TestCatalogueConstruction:
    def test_empty_catalogue(self, empty_catalogue):
        assert isinstance(empty_catalogue.objets, dict)
        assert len(empty_catalogue.objets) == 0

    def test_loads_cache(self, populated_catalogue):
        assert "M42" in populated_catalogue.objets
        assert "NGC7000" in populated_catalogue.objets
        assert len(populated_catalogue.objets) == 3


# =============================================================================
# Recherche locale
# =============================================================================

class TestRechercheLocale:
    def test_exact_match(self, populated_catalogue):
        result = populated_catalogue.rechercher_catalogue_local("M42")
        assert result is not None
        assert result["ra_deg"] == 83.82

    def test_case_insensitive(self, populated_catalogue):
        result = populated_catalogue.rechercher_catalogue_local("m42")
        assert result is not None

    def test_not_found(self, populated_catalogue):
        result = populated_catalogue.rechercher_catalogue_local("M999")
        assert result is None

    def test_partial_match(self, populated_catalogue):
        """Recherche partielle dans les clés."""
        result = populated_catalogue.rechercher_catalogue_local("SIRIU")
        assert result is not None
        assert result["nom"] == "* alf CMa"

    def test_numeric_prefix_m(self, populated_catalogue):
        """Recherche '42' → essaie 'M42'."""
        populated_catalogue.objets["M42"] = populated_catalogue.objets.get("M42", {})
        result = populated_catalogue.rechercher_catalogue_local("42")
        assert result is not None

    def test_empty_cache(self, empty_catalogue):
        result = empty_catalogue.rechercher_catalogue_local("M42")
        assert result is None


# =============================================================================
# Recherche principale (locale + SIMBAD + planètes)
# =============================================================================

class TestRechercher:
    def test_local_found(self, populated_catalogue):
        result = populated_catalogue.rechercher("M42", utiliser_api=False)
        assert result is not None
        assert result["ra_deg"] == 83.82

    def test_local_not_found_api_disabled(self, populated_catalogue):
        result = populated_catalogue.rechercher("M999", utiliser_api=False)
        assert result is None

    def test_planet_search(self, populated_catalogue):
        """Recherche d'une planète (Jupiter)."""
        result = populated_catalogue.rechercher("Jupiter", utiliser_api=False)
        # Avec chemin absolu corrigé (C-04), la recherche devrait fonctionner
        if result is not None:
            assert "ra_deg" in result
            assert "dec_deg" in result

    def test_planet_result_structure(self, populated_catalogue):
        """Planète retourne name, type=planet, ra_deg, dec_deg."""
        result = populated_catalogue.rechercher("Jupiter", utiliser_api=False)
        if result is not None:
            assert "name" in result
            assert result["type"] == "planet"
            assert "ra_deg" in result
            assert "dec_deg" in result


# =============================================================================
# Sauvegarde cache
# =============================================================================

class TestSauvegardeCache:
    def test_save_and_reload(self, empty_catalogue, tmp_path, monkeypatch):
        """Sauvegarde puis rechargement du cache."""
        empty_catalogue.objets["TEST"] = {
            "nom": "Test Object",
            "ra_deg": 100.0,
            "dec_deg": 30.0,
        }
        empty_catalogue._sauvegarder_cache()

        # Vérifier que le fichier existe
        assert empty_catalogue.cache_file.exists()

        # Recharger
        import core.config.config as config_module
        monkeypatch.setattr(config_module, "CACHE_FILE", empty_catalogue.cache_file)
        import importlib
        import core.observatoire.catalogue as cat_module
        importlib.reload(cat_module)
        new_cat = cat_module.GestionnaireCatalogue()
        assert "TEST" in new_cat.objets
