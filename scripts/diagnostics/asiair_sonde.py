"""
Surveillance de la monture via l'ASIAIR pendant une nuit (diagnostic, sans effet sur le suivi).

Objectif (20/10/2026) : savoir si l'ASIAIR signale lui-même le retournement au méridien, pour
que DriftApp fasse basculer la coupole à ce moment-là au lieu du passage au méridien.

Ce qu'on sait du firmware de l'ASIAIR (décompilé le 20/10, `zwoair_imager`, meridian_flip.cpp) :
le méridien est le moment où l'AD de la monture égale son temps sidéral (`scope_get_info`) ;
avant chaque pose, si elle ne peut pas finir avant le méridien, l'ASIAIR arrête le suivi de la
monture, attend méridien + « Flip Timing after Meridian » (5 min par défaut), puis fait un GOTO
sur la cible de l'autre côté du pied, réessayé toutes les 60 s si la monture refuse.

Le script ne parle qu'au port monture (4400, celui du bouton « ASIAIR ») et n'envoie que des
lectures : `scope_get_info`, `scope_get_pierside`, `scope_get_track_state`. Le port 4700 de
l'ASIAIR (qui publie l'événement MeridianFlip) refuse les clients non authentifiés.
Tout ce qui est reçu (réponses et événements non sollicités) part dans
logs/diagnostics/asiair_*.jsonl ; la console n'affiche que les changements utiles.

Usage (sur le Pi) : ./scripts/asiair_sonde.sh essai | demarrer | etat | arreter
"""

from __future__ import annotations

import argparse
import json
import socket
import sys
import time
from datetime import datetime
from pathlib import Path
from typing import Callable, Optional

PROJECT_ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(PROJECT_ROOT))

from core.utils.log_paths import logs_subdir  # noqa: E402

ID_INFO = 601
ID_PIED = 602
ID_SUIVI = 603
REQUETES = (
    (ID_INFO, "scope_get_info"),
    (ID_PIED, "scope_get_pierside"),
    (ID_SUIVI, "scope_get_track_state"),
)
RESUME_S = 60.0
RECONNEXION_S = 10.0


def range12(h: float) -> float:
    """Ramène un écart horaire dans [-12, 12[."""
    return (h + 12.0) % 24.0 - 12.0


def delta_meridien_h(ra_h: float, lst_h: float) -> float:
    """Écart au méridien selon l'ASIAIR : > 0 avant le passage, < 0 après."""
    return range12(ra_h - lst_h)


def _heure(t: float) -> str:
    return datetime.fromtimestamp(t).strftime("%H:%M:%S")


def _hms(h: float) -> str:
    s = round(h * 3600) % 86400
    return f"{s // 3600:02d}h{s // 60 % 60:02d}m{s % 60:02d}s"


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


def surveiller(
    host: str,
    port: int,
    periode_s: float,
    chemin: Path,
    duree_s: Optional[float] = None,
    afficher: Callable[[str], None] = print,
) -> None:
    """Interroge la monture toutes les `periode_s` et journalise tout ce qui est reçu.
    Se reconnecte seule ; s'arrête au bout de `duree_s` (None = jamais)."""
    fin = None if duree_s is None else time.monotonic() + duree_s
    etat = Etat()

    def restant() -> float:
        return float("inf") if fin is None else fin - time.monotonic()

    with chemin.open("a", encoding="utf-8") as fichier:

        def noter(enregistrement: dict) -> None:
            t = time.time()
            ligne = {"t": round(t, 3), "heure": _heure(t), **enregistrement}
            fichier.write(json.dumps(ligne, ensure_ascii=False) + "\n")

        def dire(texte: str) -> None:
            afficher(f"{_heure(time.time())}  {texte}")

        dire(f"Enregistrement dans {chemin}")
        while restant() > 0:
            try:
                with socket.create_connection((host, port), timeout=5.0) as s:
                    noter({"sonde": "connecté", "hote": f"{host}:{port}"})
                    dire(f"connecté à l'ASIAIR {host}:{port}")
                    _boucle(s, etat, periode_s, restant, noter, dire)
                    fichier.flush()
            except OSError as exc:
                noter({"sonde": "erreur", "motif": str(exc) or type(exc).__name__})
                dire(f"ASIAIR injoignable ({exc or type(exc).__name__}) ; nouvel essai dans 10 s")
                fichier.flush()
                attente = min(RECONNEXION_S, restant())
                if attente > 0:
                    time.sleep(attente)


def _boucle(s, etat: Etat, periode_s, restant, noter, dire) -> None:
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
            dire(etat.resume())
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
                dire(texte)


def _decoder(ligne: bytes) -> Optional[dict]:
    try:
        msg = json.loads(ligne.decode(errors="replace"))
    except json.JSONDecodeError:
        return None
    return msg if isinstance(msg, dict) else None


def main() -> int:
    parser = argparse.ArgumentParser(description="Surveillance de la monture via l'ASIAIR")
    parser.add_argument("--host", help="adresse de l'ASIAIR (sinon : section asiair de config)")
    parser.add_argument("--port", type=int, help="port monture (sinon : section asiair)")
    parser.add_argument("--periode", type=float, default=5.0, help="secondes entre deux lectures")
    args = parser.parse_args()

    from core.config.config_loader import load_config

    cfg = load_config().asiair
    host = args.host or cfg.host
    if not host:
        print("Adresse de l'ASIAIR non configurée (page Configuration → asiair → host).")
        return 1
    chemin = logs_subdir("diagnostics") / f"asiair_{datetime.now():%Y%m%d_%H%M%S}.jsonl"
    # Sortie redirigée (nohup … > fichier) : écrire chaque ligne tout de suite
    sys.stdout.reconfigure(line_buffering=True)
    try:
        surveiller(host, args.port or cfg.port, args.periode, chemin)
    except KeyboardInterrupt:
        print("\nArrêt demandé.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
