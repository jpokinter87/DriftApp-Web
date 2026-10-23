"""
Surveillance permanente de la monture via l'ASIAIR (v6.25, service asiair_monitor).

Reprend la sonde de diagnostic de la 6.23.3, devenue indispensable pour comprendre
après coup ce qu'a fait la monture (retournement, GOTO de recentrage, synchronisations
EQMod). Sans effet sur le suivi : le service ne fait que lire et journaliser.

Ce qu'on sait du firmware de l'ASIAIR (décompilé le 20/10, `zwoair_imager`, meridian_flip.cpp) :
le méridien est le moment où l'AD de la monture égale son temps sidéral (`scope_get_info`) ;
avant chaque pose, si elle ne peut pas finir avant le méridien, l'ASIAIR arrête le suivi de la
monture, attend méridien + « Flip Timing after Meridian » (5 min par défaut), puis fait un GOTO
sur la cible de l'autre côté du pied, réessayé toutes les 60 s si la monture refuse.

Le service ne parle qu'au port monture (4400, celui du bouton « ASIAIR ») et n'envoie que des
lectures : `scope_get_info`, `scope_get_pierside`, `scope_get_track_state`. Le port 4700 de
l'ASIAIR (qui publie l'événement MeridianFlip) refuse les clients non authentifiés.

Journaux (spec docs/superpowers/specs/2026-10-23-surveillance-asiair-permanente.md) :
- logs/asiair/AAAA-MM-JJ.jsonl : tout ce qui est reçu, un fichier par nuit (midi → midi),
  14 nuits gardées ;
- logs/asiair/asiair_monitor.log : les changements utiles et les messages du pilote INDI.

Usage : `python -m services.asiair_monitor` (unité asiair_monitor.service).
"""

from __future__ import annotations

import json
import logging
import socket
import threading
import time
from datetime import datetime
from logging.handlers import RotatingFileHandler
from pathlib import Path
from typing import Callable, Optional

from core.config.config_loader import AsiairConfig, ConfigLoader
from core.utils.log_paths import logs_subdir
from services.night_journal import night_key, purge_old

logger = logging.getLogger(__name__)

ID_INFO = 601
ID_PIED = 602
ID_SUIVI = 603
REQUETES = (
    (ID_INFO, "scope_get_info"),
    (ID_PIED, "scope_get_pierside"),
    (ID_SUIVI, "scope_get_track_state"),
)
PERIODE_S = 5.0
RESUME_S = 60.0
RECONNEXION_S = 10.0
RETENTION_NUITS = 14

LOG_SUBDIR = "asiair"
LOG_FILE_NAME = "asiair_monitor.log"
LOG_MAX_BYTES = 1_000_000
LOG_BACKUP_COUNT = 3


def range12(h: float) -> float:
    """Ramène un écart horaire dans [-12, 12[."""
    return (h + 12.0) % 24.0 - 12.0


def delta_meridien_h(ra_h: float, lst_h: float) -> float:
    """Écart au méridien selon l'ASIAIR : > 0 avant le passage, < 0 après."""
    return range12(ra_h - lst_h)


def _hms(h: float) -> str:
    s = round(h * 3600) % 86400
    return f"{s // 3600:02d}h{s // 60 % 60:02d}m{s % 60:02d}s"


def _duree(s: float) -> str:
    return f"{s:.0f} s" if s < 120 else f"{s / 60:.0f} min"


def cible(cfg: AsiairConfig) -> Optional[tuple[str, int]]:
    """(hôte, port) à surveiller, ou None si la surveillance est désactivée ou sans hôte."""
    if not cfg.monitor_enabled or not cfg.host:
        return None
    return cfg.host, cfg.port


class Etat:
    """Dernières valeurs lues ; `traiter` renvoie les lignes à afficher pour un message."""

    def __init__(self) -> None:
        self.ra_h: Optional[float] = None
        self.lst_h: Optional[float] = None
        self.delta_h: Optional[float] = None
        self.pied: Optional[str] = None
        self.suivi = None
        self._erreurs_vues: set[int] = set()

    def traiter(self, msg: dict) -> list[str]:
        if "id" not in msg:
            return self._evenement(msg)
        if "error" in msg:
            if msg["id"] in self._erreurs_vues:
                return []
            self._erreurs_vues.add(msg["id"])
            return [f"réponse en erreur (id {msg['id']}) : {msg['error']}"]
        result = msg.get("result")
        if msg["id"] == ID_INFO and isinstance(result, dict):
            return self._info(result)
        if msg["id"] == ID_PIED:
            ancien, self.pied = self.pied, str(result)
            if ancien is None:
                return [f"côté du pied : {self.pied}"]
            if ancien != self.pied:
                return [f">>> CÔTÉ DU PIED CHANGÉ : {ancien} -> {self.pied}"]
        if msg["id"] == ID_SUIVI:
            ancien, self.suivi = self.suivi, result
            if ancien != result:
                return [f"suivi de la monture : {result}"]
        return []

    def _info(self, result: dict) -> list[str]:
        try:
            self.ra_h = float(result["RA"])
            self.lst_h = float(result["sidereal_time"])
        except (KeyError, TypeError, ValueError):
            return []
        ancien, self.delta_h = self.delta_h, delta_meridien_h(self.ra_h, self.lst_h)
        if ancien is not None and ancien >= 0.0 > self.delta_h and ancien < 1.0:
            return [">>> PASSAGE AU MÉRIDIEN (calcul de l'ASIAIR : AD monture = temps sidéral)"]
        return []

    def _evenement(self, msg: dict) -> list[str]:
        nom = str(msg.get("Event", msg.get("event", "")))
        if nom == "INDIServer" and "Msg" in msg:
            return [f"INDI {str(msg['Msg']).strip()}"]
        if nom.startswith("Scope") or "Merid" in nom or "Flip" in nom:
            return [f"événement {nom} : {json.dumps(msg, ensure_ascii=False)}"]
        return []

    def resume(self) -> str:
        if self.delta_h is None:
            return "en attente de scope_get_info"
        return (
            f"AD {_hms(self.ra_h)}  temps sidéral {_hms(self.lst_h)}  "
            f"méridien dans {self.delta_h * 60:+.1f} min  pied={self.pied}  suivi={self.suivi}"
        )


class JournalNuit:
    """Ajoute chaque enregistrement au fichier de la nuit en cours (midi → midi) et
    purge les nuits au-delà de la rétention à chaque changement de nuit."""

    def __init__(self, dossier: Path, horloge: Callable[[], datetime] = datetime.now):
        self.dossier = Path(dossier)
        self._horloge = horloge
        self._nuit: Optional[str] = None
        self._ecriture_en_echec = False

    def noter(self, enregistrement: dict) -> None:
        maintenant = self._horloge()
        nuit = night_key(maintenant)
        if nuit != self._nuit:
            self._nuit = nuit
            purge_old(self.dossier, RETENTION_NUITS, now=maintenant)
        ligne = {
            "t": round(maintenant.timestamp(), 3),
            "heure": maintenant.strftime("%H:%M:%S"),
            **enregistrement,
        }
        try:
            with (self.dossier / f"{nuit}.jsonl").open("a", encoding="utf-8") as fichier:
                fichier.write(json.dumps(ligne, ensure_ascii=False) + "\n")
        except OSError as exc:
            # Disque plein ou droits : on le dit une fois, la surveillance continue.
            if not self._ecriture_en_echec:
                logger.warning(f"journal ASIAIR non écrit : {exc}")
                self._ecriture_en_echec = True
        else:
            self._ecriture_en_echec = False


def surveiller(
    host: str,
    port: int,
    periode_s: float,
    journal: JournalNuit,
    duree_s: Optional[float] = None,
    afficher: Callable[[str], None] = print,
) -> None:
    """Interroge la monture toutes les `periode_s` et journalise tout ce qui est reçu.

    Une coupure (ASIAIR éteint de jour) n'est journalisée qu'à son début et à son retour.
    """
    fin = None if duree_s is None else time.monotonic() + duree_s
    etat = Etat()
    coupure_depuis: Optional[float] = None

    def restant() -> float:
        return float("inf") if fin is None else fin - time.monotonic()

    while restant() > 0:
        try:
            with socket.create_connection((host, port), timeout=5.0) as s:
                if coupure_depuis is None:
                    journal.noter({"sonde": "connecté", "hote": f"{host}:{port}"})
                    afficher(f"connecté à l'ASIAIR {host}:{port}")
                else:
                    duree = time.monotonic() - coupure_depuis
                    journal.noter({"sonde": "reconnecté", "coupure_min": round(duree / 60.0, 1)})
                    afficher(f"ASIAIR de retour après {_duree(duree)} de coupure")
                    coupure_depuis = None
                _boucle(s, etat, periode_s, restant, journal.noter, afficher)
        except OSError as exc:
            if coupure_depuis is None:
                coupure_depuis = time.monotonic()
                motif = str(exc) or type(exc).__name__
                journal.noter({"sonde": "erreur", "motif": motif})
                afficher(
                    f"ASIAIR injoignable ({motif}) ; nouvel essai toutes les "
                    f"{RECONNEXION_S:.0f} s, sans autre message jusqu'à son retour"
                )
            attente = min(RECONNEXION_S, restant())
            if attente > 0:
                time.sleep(attente)


def _boucle(s, etat: Etat, periode_s, restant, noter, afficher) -> None:
    prochaine_requete = 0.0
    prochain_resume = time.monotonic() + RESUME_S
    tampon = b""
    while restant() > 0:
        maintenant = time.monotonic()
        if maintenant >= prochaine_requete:
            for ident, methode in REQUETES:
                s.sendall((json.dumps({"id": ident, "method": methode}) + "\r\n").encode())
            prochaine_requete = maintenant + periode_s
        if maintenant >= prochain_resume:
            afficher(etat.resume())
            prochain_resume = maintenant + RESUME_S
        s.settimeout(max(0.05, min(prochaine_requete - maintenant, restant())))
        try:
            morceau = s.recv(65536)
        except TimeoutError:
            continue
        if not morceau:
            raise ConnectionError("connexion fermée par l'ASIAIR")
        tampon += morceau
        *lignes, tampon = tampon.split(b"\n")
        for ligne in lignes:
            msg = _decoder(ligne)
            if msg is None:
                continue
            noter({"msg": msg})
            for texte in etat.traiter(msg):
                afficher(texte)


def _decoder(ligne: bytes) -> Optional[dict]:
    try:
        msg = json.loads(ligne.decode(errors="replace"))
    except json.JSONDecodeError:
        return None
    return msg if isinstance(msg, dict) else None


def _build_log_handlers() -> list:
    """stdout (journald) + logs/asiair/asiair_monitor.log ; un logs/ non écrivable
    n'empêche pas le démarrage."""
    handlers: list[logging.Handler] = [logging.StreamHandler()]
    try:
        handlers.append(
            RotatingFileHandler(
                logs_subdir(LOG_SUBDIR) / LOG_FILE_NAME,
                maxBytes=LOG_MAX_BYTES,
                backupCount=LOG_BACKUP_COUNT,
                encoding="utf-8",
            )
        )
    except OSError as exc:
        logger.warning(f"journal lisible indisponible : {exc}")
    return handlers


def main() -> int:
    """Entry-point CLI : `python -m services.asiair_monitor`."""
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s  %(message)s",
        datefmt="%Y-%m-%d %H:%M:%S",
        handlers=_build_log_handlers(),
    )
    hote = cible(ConfigLoader().load().asiair)
    if hote is None:
        # On reste actif sans rien faire : systemd et l'OTA voient le service démarré.
        logger.info(
            "Surveillance ASIAIR inactive (asiair.monitor_enabled décoché ou asiair.host "
            "vide) ; appliquer un changement par « Redémarrer les services »"
        )
        threading.Event().wait()
        return 0
    dossier = logs_subdir(LOG_SUBDIR)
    logger.info(f"Surveillance ASIAIR {hote[0]}:{hote[1]}, journal dans {dossier}")
    surveiller(*hote, PERIODE_S, JournalNuit(dossier), afficher=logger.info)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
