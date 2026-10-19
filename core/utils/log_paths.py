"""Chemins des logs par thème (moteur, encodeur, cimier, web, diagnostics).

Bibliothèque standard seule et aucun effet de bord à l'import : le démon
encodeur et les settings Django l'importent sans dépendre du reste de `core`
(`core.config.config` lit data/config.json dès l'import).

Les fichiers de mise à jour (update*, restart*) restent à la racine de logs/ :
pendant une MAJ par l'interface c'est l'ancien script qui écrit leur état
(spec docs/superpowers/specs/2026-10-19-logs-sous-repertoires.md, décision 1).
"""

import os
from pathlib import Path
from typing import Iterable

_DEFAULT_ROOT = Path(__file__).resolve().parent.parent.parent / "logs"


def logs_root() -> Path:
    """DRIFTAPP_LOGS_DIR si défini (tests), sinon <projet>/logs. Lu à chaque appel."""
    return Path(os.environ.get("DRIFTAPP_LOGS_DIR") or _DEFAULT_ROOT)


def logs_subdir(nom: str) -> Path:
    """Sous-dossier `nom` de la racine des logs, créé si besoin.

    Créé sous `sudo` (scripts de diagnostic), il est rendu à l'utilisateur qui a
    tapé sudo : sinon les scripts lancés ensuite sans sudo ne pourraient plus y
    écrire. Un service root sous systemd (pas de SUDO_UID) garde son dossier.
    """
    dossier = logs_root() / nom
    if dossier.is_dir():
        return dossier
    dossier.mkdir(parents=True, exist_ok=True)
    sudo_uid = os.environ.get("SUDO_UID")
    if os.geteuid() == 0 and sudo_uid:
        try:
            os.chown(dossier, int(sudo_uid), int(os.environ.get("SUDO_GID", sudo_uid)))
        except (OSError, ValueError):
            pass
    return dossier


def ranger_anciens_logs(motifs: Iterable[str], nom: str) -> int:
    """Déplace dans le sous-dossier `nom` les fichiers de la racine qui
    correspondent à l'un des motifs glob, et renvoie le nombre déplacé.

    Un fichier déjà présent à destination n'est pas écrasé : l'ancien reste à
    la racine. Les erreurs sont avalées, fichier par fichier : ranger ne doit
    jamais empêcher un service de démarrer.
    """
    try:
        dossier = logs_subdir(nom)
    except OSError:
        return 0
    racine = logs_root()
    deplaces = 0
    for motif in motifs:
        for fichier in racine.glob(motif):
            cible = dossier / fichier.name
            if not fichier.is_file() or cible.exists():
                continue
            try:
                fichier.rename(cible)
            except OSError:
                continue
            deplaces += 1
    return deplaces
