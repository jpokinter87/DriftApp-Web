"""Configuration de l'app Django `cimier` (v6.0 Phase 1).

Le nom de classe `CimierAppConfig` évite toute confusion d'import avec le
dataclass `core.config.config_loader.CimierConfig` qui décrit la section
"cimier" du fichier `data/config.json`.
"""

from django.apps import AppConfig


class CimierAppConfig(AppConfig):
    default_auto_field = "django.db.models.BigAutoField"
    name = "cimier"

    def ready(self):
        import os

        # Évite le double-run de l'autoreloader Django en dev.
        if os.environ.get("RUN_MAIN") == "true" or not os.environ.get("RUN_MAIN"):
            try:
                from core.config.config_resilience import ensure_config_ready
                from core.config.config_status_writer import write_config_status

                write_config_status(ensure_config_ready(force=True))
            except Exception:
                pass
