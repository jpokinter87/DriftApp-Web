"""Publie le ConfigReport en IPC (/dev/shm) pour surfaçage UI (chantier A)."""

from __future__ import annotations

import json
import logging
import os
from dataclasses import asdict
from pathlib import Path

from core.config.config_resilience import ConfigReport

logger = logging.getLogger(__name__)

DEFAULT_STATUS_PATH = Path("/dev/shm/config_status.json")


def write_config_status(report: ConfigReport, path: Path = DEFAULT_STATUS_PATH) -> None:
    """Sérialise le rapport. Ne lève jamais (le filet ne doit pas casser le boot).

    Tmp unique par process (démarrage parallèle des 3 services) + cleanup.
    """
    tmp = path.parent / f"{path.name}.{os.getpid()}.tmp"
    try:
        with open(tmp, "w", encoding="utf-8") as f:
            json.dump(asdict(report), f, ensure_ascii=False)
        os.replace(tmp, path)
    except Exception as exc:
        logger.warning(f"Écriture config_status échouée (ignorée) : {exc}")
    finally:
        try:
            if tmp.exists():
                tmp.unlink(missing_ok=True)
        except OSError:
            pass
