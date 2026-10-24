#!/usr/bin/env python3
"""
Chronologie d'une nuit terrain à partir du zip de logs envoyé par Serge.

S'exécute sur la machine de dev, jamais sur le Pi. Fusionne en une seule chronologie
les logs moteur, cimier, Django, encodeur, ASIAIR (`asiair_monitor.log`), mise à jour,
redémarrage et le journal de nuit (`AAAA-MM-JJ.jsonl`) s'il est dans le zip. Le zip est
lu sans être extrait, qu'il soit à plat (avant la 6.22) ou rangé par thème.

Une nuit va de midi à midi, comme `services/night_journal.py`. Le bruit répétitif
(heartbeat, corrections de suivi, DEBUG…) est retiré et les lignes identiques
consécutives sont regroupées. Spec : docs/superpowers/specs/2026-10-24-analyse-nuit.md.

Usage :
    python3 scripts/diagnostics/chronologie_nuit.py                  # dernier zip de logs/terrain/
    python3 scripts/diagnostics/chronologie_nuit.py logs/terrain/2026-10-23.zip --de 21:00 --a 22:00
    python3 scripts/diagnostics/chronologie_nuit.py dossier/ --nuit 2026-10-22 --tout
"""

from __future__ import annotations

import argparse
import json
import re
import zipfile
from collections import Counter
from dataclasses import dataclass
from datetime import datetime, timedelta
from pathlib import Path, PurePosixPath

DOSSIER_TERRAIN = Path(__file__).resolve().parents[2] / "logs" / "terrain"

# (source, motif du nom de fichier)
SOURCES = [
    ("moteur", re.compile(r"motor_service_.*\.log$")),
    ("cimier", re.compile(r"cimier_service\.log(\.\d+)?$")),
    ("web", re.compile(r"django_.*\.log$")),
    ("encodeur", re.compile(r"ems22d_.*\.log$")),
    ("asiair", re.compile(r"asiair_monitor\.log(\.\d+)?$")),
    ("maj", re.compile(r"update\.log$")),
    ("services", re.compile(r"restart\.log$")),
]
JOURNAL_NUIT = re.compile(r"\d{4}-\d\d-\d\d\.jsonl$")

_D = r"(?P<d>\d{4}-\d\d-\d\d \d\d:\d\d:\d\d)"
_N = r"(?P<n>DEBUG|INFO|WARNING|ERROR|CRITICAL)"
FORMATS = [
    re.compile(rf"^{_D},\d+ - \S+ - {_N} - (?P<m>.*)"),  # moteur
    re.compile(rf"^{_D},\d+ \[{_N}\] \S+: (?P<m>.*)"),  # cimier
    re.compile(rf"^{_N} {_D},\d+ \S+ (?P<m>.*)"),  # Django
    re.compile(rf"^\[ems22d\] {_D},\d+ {_N} (?P<m>.*)"),  # encodeur
    re.compile(rf"^\[{_D}\] (?P<m>.*)"),  # mise à jour, redémarrage
    re.compile(rf"^{_D},\d+  (?P<m>.*)"),  # asiair_monitor
]
# Lignes sans horodatage gardées (rattachées à la ligne précédente) : traces d'erreur.
SUITE_UTILE = re.compile(r"Traceback|^\s+File |Error|Exception|[Ff]ailed")
BRUIT = re.compile(
    r"^(heartbeat \||ipc_snapshot \||correction \||session_health \||Rotation avec feedback"
    r"|Rotation feedback réussie|Correction feedback réussie|Chargement configuration"
    r"|Configuration chargée|\s+(Site|Moteur|Encodeur|Driver|Mode):|config_status déjà publié)"
    r"|^\W*$"
)
DELTA = re.compile(r"^correction \| delta=([+-]?\d+(?:\.\d+)?)")
SUIVI = re.compile(r"^Démarrage suivi de: (.*?)(?: \(skip_goto=\w+\))?$")
DEMARRAGE = re.compile(r"Motor Service démarré|cimier_event=started|Démarrage du démon")


@dataclass
class Evenement:
    moment: datetime
    source: str
    niveau: str
    message: str
    fin: datetime | None = None
    nombre: int = 1


def _source(nom: str) -> str | None:
    chemin = PurePosixPath(nom)
    if "__MACOSX" in chemin.parts:
        return None
    if JOURNAL_NUIT.search(chemin.name):
        return None if "asiair" in chemin.parts else "nuit"
    return next((s for s, motif in SOURCES if motif.search(chemin.name)), None)


def _lire_log(source: str, texte: str) -> list[Evenement]:
    evts: list[Evenement] = []
    for ligne in texte.splitlines():
        for motif in FORMATS:
            m = motif.match(ligne)
            if m:
                niveau = m.groupdict().get("n") or "INFO"
                moment = datetime.strptime(m["d"], "%Y-%m-%d %H:%M:%S")
                evts.append(Evenement(moment, source, niveau, m["m"].rstrip()))
                break
        else:
            if evts and SUITE_UTILE.search(ligne):
                evts[-1].message += "\n      " + ligne.strip()
    return evts


def _lire_journal(texte: str) -> list[Evenement]:
    evts = []
    for ligne in texte.splitlines():
        try:
            d = json.loads(ligne)
            moment = datetime.fromisoformat(d.pop("ts"))
        except (ValueError, KeyError, TypeError):
            continue
        champs = " ".join(f"{k}={v}" for k, v in d.items() if k != "event")
        evts.append(Evenement(moment, "nuit", "INFO", f"{d.get('event', '?')} {champs}"))
    return evts


def charger(chemin: Path) -> list[Evenement]:
    """Tous les événements d'un zip ou d'un dossier de logs, triés par heure."""
    chemin = Path(chemin)
    if chemin.is_dir():
        fichiers = {
            str(p.relative_to(chemin)): p.read_bytes for p in chemin.rglob("*") if p.is_file()
        }
    else:
        z = zipfile.ZipFile(chemin)
        fichiers = {n: (lambda n=n: z.read(n)) for n in z.namelist() if not n.endswith("/")}
    evts: list[Evenement] = []
    for nom, lire in fichiers.items():
        source = _source(nom)
        if source is None:
            continue
        texte = lire().decode("utf-8", errors="replace")
        evts += _lire_journal(texte) if source == "nuit" else _lire_log(source, texte)
    uniques = {(e.moment, e.source, e.message): e for e in evts}
    return sorted(uniques.values(), key=lambda e: e.moment)


def nuit_de(moment: datetime) -> str:
    """Nuit (midi → midi) d'un instant, comme services.night_journal.night_key."""
    return (moment - timedelta(hours=12)).strftime("%Y-%m-%d")


def _minutes_de_nuit(hhmm: str) -> int:
    h, m = (int(x) for x in hhmm.split(":"))
    return (h - 12) % 24 * 60 + m


def _regrouper(evts: list[Evenement]) -> list[Evenement]:
    groupes: list[Evenement] = []
    for e in evts:
        precedent = groupes[-1] if groupes else None
        if precedent and (precedent.source, precedent.niveau, precedent.message) == (
            e.source,
            e.niveau,
            e.message,
        ):
            precedent.nombre += 1
            precedent.fin = e.moment
        else:
            groupes.append(Evenement(e.moment, e.source, e.niveau, e.message))
    return groupes


def _synthese(evts: list[Evenement], sources: Counter) -> list[str]:
    deltas = [abs(float(m[1])) for e in evts if (m := DELTA.match(e.message))]
    objets = list(dict.fromkeys(m[1] for e in evts if (m := SUIVI.match(e.message))))
    demarrages = Counter(e.source for e in evts if DEMARRAGE.search(e.message))
    maj = [e for e in evts if e.source == "maj" and e.message.startswith("Pull OK")]
    alertes = Counter(
        (e.niveau, e.source, e.message.split("\n")[0][:120])
        for e in evts
        if e.niveau in ("WARNING", "ERROR", "CRITICAL")
    )
    lignes = [
        "Sources : " + ", ".join(f"{s} ({n})" for s, n in sorted(sources.items())),
        "Objets suivis : " + (", ".join(objets) or "aucun"),
        f"Corrections de suivi : {len(deltas)}"
        + (f" (plus grand écart {max(deltas):.1f}°)" if deltas else ""),
        "Démarrages de services : "
        + (", ".join(f"{s} ×{n}" for s, n in sorted(demarrages.items())) or "aucun"),
        "Mises à jour : "
        + (", ".join(f"{e.moment:%H:%M:%S} ({e.message})" for e in maj) or "aucune"),
        "Avertissements et erreurs :" if alertes else "Avertissements et erreurs : aucun",
    ]
    lignes += [f"  {n} × {niv} [{src}] {msg}" for (niv, src, msg), n in alertes.most_common(25)]
    if "nuit" not in sources:
        lignes.append("⚠ Pas de journal de nuit (logs/nuits/AAAA-MM-JJ.jsonl) dans les logs.")
    return lignes


def rapport(
    evts: list[Evenement],
    nuit: str | None = None,
    de: str | None = None,
    a: str | None = None,
    tout: bool = False,
) -> str:
    """Synthèse puis chronologie d'une nuit (par défaut la dernière où un suivi a démarré)."""
    if not evts:
        return "Aucun log reconnu."
    presentes = Counter(nuit_de(e.moment) for e in evts)
    if nuit is None:
        suivis = [e for e in evts if SUIVI.match(e.message)] or evts
        nuit = nuit_de(suivis[-1].moment)
    evts = [e for e in evts if nuit_de(e.moment) == nuit]
    debut = _minutes_de_nuit(de) if de else 0
    fin = _minutes_de_nuit(a) if a else 24 * 60
    evts = [e for e in evts if debut <= _minutes_de_nuit(f"{e.moment:%H:%M}") <= fin]
    sources = Counter(e.source for e in evts)
    lignes = [
        f"══ Nuit du {nuit} (midi → midi) ══",
        "Nuits dans les logs : " + ", ".join(f"{n} ({c})" for n, c in sorted(presentes.items())),
        *_synthese(evts, sources),
        "",
        "══ Chronologie ══",
    ]
    if not tout:
        evts = [e for e in evts if e.niveau != "DEBUG" and not BRUIT.search(e.message)]
    for e in _regrouper(evts):
        ligne = f"{e.moment:%H:%M:%S} [{e.source}] {e.niveau:<5} {e.message}"
        if e.nombre > 1:
            ligne += f"  (×{e.nombre} jusqu'à {e.fin:%H:%M:%S})"
        lignes.append(ligne)
    return "\n".join(lignes)


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    parser.add_argument(
        "chemin",
        nargs="?",
        type=Path,
        help="zip ou dossier (défaut : dernier zip de logs/terrain/)",
    )
    parser.add_argument("--nuit", help="AAAA-MM-JJ, date du soir (défaut : la dernière)")
    parser.add_argument("--de", help="HH:MM, début de la fenêtre")
    parser.add_argument("--a", help="HH:MM, fin de la fenêtre (peut passer minuit)")
    parser.add_argument("--tout", action="store_true", help="garder le bruit et le DEBUG")
    args = parser.parse_args()
    chemin = args.chemin
    if chemin is None:
        zips = sorted(DOSSIER_TERRAIN.glob("*.zip"), key=lambda p: p.stat().st_mtime)
        if not zips:
            parser.error(f"aucun zip dans {DOSSIER_TERRAIN}")
        chemin = zips[-1]
    print(f"Fichier : {chemin}")
    print(rapport(charger(chemin), args.nuit, args.de, args.a, args.tout))


if __name__ == "__main__":
    main()
