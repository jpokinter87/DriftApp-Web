"""Vues de la page Configuration (chantier B) : lecture/écriture via le noyau A."""

import json

from rest_framework import status
from rest_framework.decorators import api_view
from rest_framework.response import Response

from core.config.config_resilience import (
    DEFAULT_BACKUP_PATH,
    DEFAULT_CONFIG_PATH,
    DEFAULT_TEMPLATE_PATH,
    ConfigValidationError,
    build_config_schema,
    write_user_config,
)

# Chemins du noyau A (surchargés dans les tests).
CONFIG_PATH = DEFAULT_CONFIG_PATH
TEMPLATE_PATH = DEFAULT_TEMPLATE_PATH
BACKUP_PATH = DEFAULT_BACKUP_PATH


def _load(path):
    with path.open(encoding="utf-8") as f:
        return json.load(f)


@api_view(["GET", "POST"])
def configuration_view(request):
    if request.method == "GET":
        template = _load(TEMPLATE_PATH)
        values = _load(CONFIG_PATH)
        return Response({"schema": build_config_schema(template), "values": values})

    # POST : sauvegarde
    values = request.data
    if not isinstance(values, dict):
        return Response(
            {"error": "Corps JSON attendu (objet)."},
            status=status.HTTP_400_BAD_REQUEST,
        )
    try:
        report = write_user_config(
            values,
            config_path=CONFIG_PATH,
            template_path=TEMPLATE_PATH,
            backup_path=BACKUP_PATH,
        )
    except ConfigValidationError as exc:
        return Response(
            {"error": str(exc), "path": exc.path},
            status=status.HTTP_400_BAD_REQUEST,
        )
    return Response(
        {
            "status": report.status,
            "message": report.message,
            "added": report.added,
            "removed": report.removed,
            "restart_required": True,
        }
    )
