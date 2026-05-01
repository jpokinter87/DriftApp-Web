"""Configuration de l'app Django `cimier` (v6.0 Phase 1).

Le nom de classe `CimierAppConfig` évite toute confusion d'import avec le
dataclass `core.config.config_loader.CimierConfig` qui décrit la section
"cimier" du fichier `data/config.json`.
"""

from django.apps import AppConfig


class CimierAppConfig(AppConfig):
    default_auto_field = "django.db.models.BigAutoField"
    name = "cimier"
