#!/usr/bin/env python3
"""Analyse en lecture seule du delta à pousser pour le skill pre-push.

Ne modifie RIEN (pas de git add/commit/push, pas d'écriture pyproject).
Produit un rapport que le skill exploite pour dérouler sa checklist :
  - fichiers modifiés (commits non poussés + working tree + non suivis)
  - périmètre cimier détecté (→ décision de bump)
  - valeurs en dur ajoutées dans le diff (IP, /dev/tty, /dev/shm, localhost)
  - mapping fichiers → tests pytest + détection code partagé
  - version courante pyproject.toml

Usage : python3 check_push_readiness.py [--repo <chemin>]
Sortie : rapport texte sur stdout, exit 0 (aide, ne bloque pas par lui-même).
"""
from __future__ import annotations

import argparse
import re
import subprocess
import sys
from pathlib import Path

# Valeurs terrain qui ne doivent jamais être codées en dur (feedback_no_hardcoded_ips).
HARDCODED_PATTERNS = {
    "IP 192.168.x.x": re.compile(r"192\.168\.\d{1,3}\.\d{1,3}"),
    "device tty": re.compile(r"/dev/tty\w*"),
    "shm IPC": re.compile(r"/dev/shm/\S+"),
    "localhost": re.compile(r"\blocalhost\b"),
    "127.0.0.1": re.compile(r"127\.0\.0\.1"),
}
# Le scan ne regarde que les LIGNES AJOUTÉES et ignore les tests/fixtures :
# un /dev/shm pré-existant dans ipc_manager.py ne déclenchera pas de faux positif.
SCAN_DIRS = ("core/", "services/", "web/")
TEST_EXCLUDE = re.compile(r"(^|/)(tests?/|conftest|test_|fixtures?/)")

# Code partagé : si touché, lancer la suite complète plutôt que des tests ciblés.
SHARED_CODE = (
    "core/config/config.py",
    "core/config/config_loader.py",
    "services/ipc_manager.py",
    "core/tracking/tracker.py",
)


def git(repo: Path, *args: str) -> str:
    out = subprocess.run(
        ["git", "-C", str(repo), *args],
        capture_output=True, text=True,
    )
    return out.stdout


def upstream_ref(repo: Path) -> str | None:
    ref = git(repo, "rev-parse", "--abbrev-ref", "--symbolic-full-name", "@{u}").strip()
    return ref or None


def changed_files(repo: Path, base: str) -> tuple[list[str], list[str]]:
    """Retourne (fichiers suivis modifiés vs base, fichiers non suivis)."""
    tracked = git(repo, "diff", base, "--name-only").splitlines()
    untracked = git(repo, "ls-files", "--others", "--exclude-standard").splitlines()
    return [f for f in tracked if f], [f for f in untracked if f]


def scan_hardcoded(repo: Path, base: str, untracked: list[str]) -> list[tuple[str, str, str]]:
    """Cherche les valeurs terrain dans les lignes AJOUTÉES (diff + non suivis)."""
    findings: list[tuple[str, str, str]] = []
    added: list[tuple[str, str]] = []  # (fichier, ligne)

    # Lignes ajoutées du diff suivi.
    diff = git(repo, "diff", base, "--unified=0", "--", *SCAN_DIRS)
    current = "?"
    for line in diff.splitlines():
        if line.startswith("+++ b/"):
            current = line[6:]
        elif line.startswith("+") and not line.startswith("+++"):
            added.append((current, line[1:]))

    # Fichiers non suivis sous les répertoires scannés = tout le contenu est "ajouté".
    for f in untracked:
        if f.startswith(SCAN_DIRS) and not TEST_EXCLUDE.search(f):
            try:
                for ln in (repo / f).read_text(errors="ignore").splitlines():
                    added.append((f, ln))
            except OSError:
                pass

    for fname, content in added:
        if TEST_EXCLUDE.search(fname):
            continue
        for label, pat in HARDCODED_PATTERNS.items():
            m = pat.search(content)
            if m:
                findings.append((fname, label, m.group(0)))
    return findings


def is_cimier(path: str) -> bool:
    p = path.lower()
    return "cimier" in p or p.startswith("firmware/")


def changed_python(files: list[str]) -> list[str]:
    """Fichiers .py modifiés à passer à ruff (scope = périmètre touché).

    Exclut .claude/ (outillage skill) pour ne cibler que le code du projet.
    """
    return [
        f for f in files
        if f.endswith(".py") and not f.startswith(".claude/")
    ]


def map_tests(repo: Path, files: list[str]) -> tuple[list[str], bool]:
    candidates: list[str] = []
    shared = False
    for f in files:
        if f in SHARED_CODE:
            shared = True
        if f.startswith(("core/", "services/")) and f.endswith(".py"):
            stem = Path(f).stem
            cand = f"tests/test_{stem}.py"
            if (repo / cand).exists() and cand not in candidates:
                candidates.append(cand)
    return candidates, shared


def current_version(repo: Path) -> str:
    pp = repo / "pyproject.toml"
    if pp.exists():
        for line in pp.read_text().splitlines():
            m = re.match(r'\s*version\s*=\s*"([^"]+)"', line)
            if m:
                return m.group(1)
    return "<introuvable>"


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--repo", default=".")
    args = ap.parse_args()
    repo = Path(args.repo).resolve()

    base = upstream_ref(repo) or "HEAD"
    tracked, untracked = changed_files(repo, base)
    all_files = tracked + untracked

    print("=== PRE-PUSH — ANALYSE DU DELTA ===")
    print(f"Base de comparaison : {base}")
    print(f"Version pyproject   : {current_version(repo)}")
    print()

    print(f"--- Fichiers concernés ({len(all_files)}) ---")
    for f in tracked:
        print(f"  M  {f}")
    for f in untracked:
        print(f"  ?? {f}")
    if not all_files:
        print("  (aucun — rien à pousser ?)")
    print()

    cimier_hits = [f for f in all_files if is_cimier(f)]
    print("--- Décision de bump ---")
    if cimier_hits:
        print("  PÉRIMÈTRE CIMIER détecté → proposer PAS de bump (chantier en cours).")
        for f in cimier_hits:
            print(f"      {f}")
    else:
        print("  Hors cimier → proposer un bump PATCH dans pyproject.toml.")
    print("  (Confirmation utilisateur requise dans tous les cas.)")
    print()

    findings = scan_hardcoded(repo, base, untracked)
    print("--- Valeurs en dur ajoutées (hors tests) ---")
    if findings:
        print("  ⛔ À CORRIGER avant push (déplacer dans data/config.json) :")
        for fname, label, value in findings:
            print(f"      {fname}: {label} → {value}")
    else:
        print("  ✓ Aucune valeur terrain en dur dans les lignes ajoutées.")
    print()

    py = changed_python(all_files)
    print("--- Format + lint (cible ruff = fichiers Python modifiés) ---")
    if py:
        joined = " ".join(py)
        print(f"  uv run --extra dev ruff format {joined}")
        print(f"  uv run --extra dev ruff check {joined}")
    else:
        print("  Aucun fichier Python modifié → étape format/lint sans objet.")
    print("  (Ne JAMAIS lancer ruff repo-wide : reformaterait du code non concerné.)")
    print()

    tests, shared = map_tests(repo, all_files)
    print("--- Tests à lancer ---")
    if shared:
        print("  Code partagé touché → SUITE COMPLÈTE recommandée :")
        print("      uv run --extra dev pytest -q")
    elif tests:
        print("  Tests ciblés :")
        print("      uv run --extra dev pytest " + " ".join(tests) + " -q")
    else:
        print("  Aucun test ciblé déduit (vérifier manuellement le périmètre).")
    print()

    print("=== FIN ANALYSE ===")
    return 0


if __name__ == "__main__":
    sys.exit(main())
