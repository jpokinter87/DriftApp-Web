"""Journal de nuit cimier — trace persistante des transitions.

La timeline du dashboard est un buffer mémoire de 50 entrées, perdu au
rechargement de la page : inutilisable pour relire une nuit le lendemain. Ce
module écrit sur disque ce qu'il faut pour reconstituer la nuit — les
transitions du capteur de pluie, les décisions de la protection, les cycles
cimier.

**Transitions, pas échantillons.** Une ligne n'est écrite que quand quelque
chose change. Échantillonner l'état toutes les 10 s produirait 8 640 points
par nuit pour la même information.

**Découpage midi → midi.** Une nuit d'observation traverse minuit : la
découper à minuit scinderait chaque session en deux fichiers. La nuit
``2026-08-14`` couvre donc du 14/08 12:00 au 15/08 11:59, heure locale.

Écriture en append avec ``flush`` immédiat : une coupure ne doit rien perdre.
Aucune erreur d'E/S n'est propagée — un disque plein ne doit jamais empêcher
une fermeture d'urgence.
"""

from __future__ import annotations

import json
import logging
from datetime import datetime, timedelta
from pathlib import Path
from typing import Any, Dict, List, Optional

logger = logging.getLogger(__name__)

DEFAULT_NIGHTS_DIR = Path(__file__).resolve().parents[1] / "data" / "nights"

# Heure locale à laquelle une nuit de journal commence.
NIGHT_BOUNDARY_HOUR = 12

# Les fichiers pèsent quelques kilo-octets : 30 jours couvrent une saison
# d'essais et permettent de comparer plusieurs épisodes de pluie entre eux.
RETENTION_DAYS = 30


def night_key(moment: datetime) -> str:
    """Nuit à laquelle appartient un instant, au format ``AAAA-MM-JJ``."""
    if moment.hour < NIGHT_BOUNDARY_HOUR:
        moment = moment - timedelta(days=1)
    return moment.strftime("%Y-%m-%d")


def _resolve_dir(nights_dir: Optional[Path]) -> Path:
    return Path(nights_dir) if nights_dir is not None else DEFAULT_NIGHTS_DIR


def append_event(
    event: str,
    *,
    at: Optional[datetime] = None,
    nights_dir: Optional[Path] = None,
    **fields: Any,
) -> bool:
    """Ajoute une ligne au journal de la nuit courante.

    Args:
        event: ``"rain"`` | ``"decision"`` | ``"cimier"``.
        at: instant de l'événement (heure locale). ``datetime.now()`` si absent.
        **fields: champs propres au type d'événement (``state``, ``armed``,
            ``action``, ``reason``, ``result``…).

    Returns:
        True si la ligne a été écrite, False si l'écriture a échoué (l'échec
        est journalisé, jamais propagé).
    """
    try:
        moment = at or datetime.now()
        directory = _resolve_dir(nights_dir)
        payload: Dict[str, Any] = {"ts": moment.isoformat(timespec="seconds"), "event": event}
        payload.update(fields)
        directory.mkdir(parents=True, exist_ok=True)
        target = directory / (night_key(moment) + ".jsonl")
        with open(target, "a", encoding="utf-8") as fh:
            fh.write(json.dumps(payload, ensure_ascii=False) + "\n")
            fh.flush()
        return True
    except (OSError, TypeError, ValueError, AttributeError) as exc:
        logger.warning("night_journal_event=append_failed event=%s exc=%s", event, exc)
        return False


def read_night(date_key: str, nights_dir: Optional[Path] = None) -> List[Dict[str, Any]]:
    """Lit les événements d'une nuit. Liste vide si le fichier n'existe pas.

    Une ligne corrompue est ignorée : un journal partiellement lisible reste
    plus utile qu'une erreur.
    """
    target = _resolve_dir(nights_dir) / (str(date_key) + ".jsonl")
    events: List[Dict[str, Any]] = []
    try:
        with open(target, "r", encoding="utf-8") as fh:
            for line in fh:
                line = line.strip()
                if not line:
                    continue
                try:
                    parsed = json.loads(line)
                except ValueError:
                    continue
                if isinstance(parsed, dict):
                    events.append(parsed)
    except OSError:
        return []
    return events


def list_nights(nights_dir: Optional[Path] = None) -> List[str]:
    """Nuits disponibles, de la plus récente à la plus ancienne."""
    directory = _resolve_dir(nights_dir)
    try:
        keys = [p.stem for p in directory.glob("*.jsonl")]
    except OSError:
        return []
    return sorted(keys, reverse=True)


def purge_old(
    nights_dir: Optional[Path] = None,
    retention_days: int = RETENTION_DAYS,
    now: Optional[datetime] = None,
) -> int:
    """Supprime les journaux au-delà de la rétention. Retourne le nombre supprimé."""
    directory = _resolve_dir(nights_dir)
    reference = now or datetime.now()
    cutoff = (reference - timedelta(days=int(retention_days))).strftime("%Y-%m-%d")
    removed = 0
    for key in list_nights(nights_dir=directory):
        if key >= cutoff:
            continue
        try:
            (directory / (key + ".jsonl")).unlink()
            removed += 1
        except OSError as exc:
            logger.warning("night_journal_event=purge_failed night=%s exc=%s", key, exc)
    return removed
