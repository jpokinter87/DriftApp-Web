"""
Tests de non-régression du bug OTA « uv.lock bloque le git pull ».

Contexte : sur le Pi, `uv sync` (sans --frozen) pouvait réécrire `uv.lock`
(contraintes `>=` larges dans pyproject + version uv différente). Le fichier
tracké devenait modifié-localement et entrait en collision avec la version
upstream à chaque pull OTA, bloquant la mise à jour (« supprimer uv.lock à la
main »).

Deux volets de correction, tous deux verrouillés ici :
1. Scénario git : prouver que normaliser uv.lock à l'état du dépôt AVANT le
   pull résout le blocage (test de mécanisme, indépendant du script).
2. Guard tests : vérifier que les scripts OTA appliquent bien --frozen et la
   normalisation uv.lock (cassent si quelqu'un retire le fix).
"""

from __future__ import annotations

import os
import subprocess
from pathlib import Path

import pytest

PROJECT_ROOT = Path(__file__).resolve().parent.parent
UPDATE_SCRIPT = PROJECT_ROOT / "scripts" / "update_driftapp.sh"


def _git(args: list[str], cwd: Path) -> subprocess.CompletedProcess:
    """Exécute git en environnement isolé (messages en anglais, pas de prompt)."""
    env = {
        **os.environ,
        "LC_ALL": "C",
        "LANG": "C",
        "GIT_TERMINAL_PROMPT": "0",
        "GIT_CONFIG_GLOBAL": "/dev/null",
        "GIT_CONFIG_SYSTEM": "/dev/null",
    }
    base = [
        "git",
        "-c",
        "user.email=test@driftapp.local",
        "-c",
        "user.name=Test",
        "-c",
        "init.defaultBranch=main",
        "-c",
        "advice.detachedHead=false",
    ]
    return subprocess.run(base + args, cwd=str(cwd), capture_output=True, text=True, env=env)


@pytest.fixture
def repo_pair(tmp_path: Path):
    """Crée un dépôt 'origin' (avec uv.lock tracké) + un clone 'work'.

    Les deux partent du commit C0 (uv.lock = 'v1'). 'origin' avance ensuite
    sur C1 (uv.lock = 'v2'), simulant l'upstream qui a bougé le lock.
    """
    origin = tmp_path / "origin"
    origin.mkdir()
    _git(["init"], origin)
    (origin / "uv.lock").write_text("lock-content-v1\n")
    (origin / "app.py").write_text("print('c0')\n")
    _git(["add", "."], origin)
    _git(["commit", "-m", "C0"], origin)

    work = tmp_path / "work"
    res = _git(["clone", str(origin), str(work)], tmp_path)
    assert res.returncode == 0, res.stderr

    # origin avance : nouvelle version du lock (upstream a changé uv.lock)
    (origin / "uv.lock").write_text("lock-content-v2\n")
    (origin / "app.py").write_text("print('c1')\n")
    _git(["add", "."], origin)
    _git(["commit", "-m", "C1 (bump deps)"], origin)

    # le clone récupère la référence distante sans merger
    _git(["fetch", "origin", "main"], work)
    return work


def test_local_modified_uvlock_blocks_pull(repo_pair: Path):
    """REPRODUIT LE BUG : un uv.lock modifié localement fait échouer le pull."""
    work = repo_pair
    (work / "uv.lock").write_text("lock-content-LOCAL-divergent\n")

    res = _git(["pull", "--ff-only", "origin", "main"], work)

    # git refuse d'écraser la modif locale et nomme le fichier coupable
    assert res.returncode != 0
    assert "uv.lock" in (res.stderr + res.stdout)


def test_normalizing_uvlock_unblocks_pull(repo_pair: Path):
    """VALIDE LE FIX : restaurer uv.lock à l'état dépôt avant le pull résout tout."""
    work = repo_pair
    (work / "uv.lock").write_text("lock-content-LOCAL-divergent\n")

    # ---- la séquence du fix : normaliser uv.lock à l'état tracké ----
    tracked = _git(["ls-files", "--error-unmatch", "uv.lock"], work)
    assert tracked.returncode == 0, "uv.lock doit être tracké"
    restore = _git(["checkout", "--", "uv.lock"], work)
    assert restore.returncode == 0, restore.stderr

    # ---- le pull passe désormais et amène la version upstream ----
    res = _git(["pull", "--ff-only", "origin", "main"], work)
    assert res.returncode == 0, res.stderr
    assert (work / "uv.lock").read_text() == "lock-content-v2\n"


# --------------------------------------------------------------------------
# Guard tests : le script OTA doit appliquer le fix (cassent si on le retire)
# --------------------------------------------------------------------------


def test_update_script_uses_frozen_sync():
    """L'étape uv sync doit utiliser --frozen pour ne jamais réécrire uv.lock."""
    content = UPDATE_SCRIPT.read_text()
    assert "uv sync --extra dev --frozen" in content, (
        "update_driftapp.sh doit lancer `uv sync --extra dev --frozen`"
    )


def test_update_script_normalizes_uvlock_before_modified_scan():
    """La normalisation uv.lock doit précéder le scan des fichiers modifiés/stash."""
    content = UPDATE_SCRIPT.read_text()
    idx_norm = content.find("ls-files --error-unmatch uv.lock")
    idx_modified = content.find("MODIFIED_FILES=")
    assert idx_norm != -1, "update_driftapp.sh doit normaliser uv.lock"
    assert idx_modified != -1
    assert idx_norm < idx_modified, (
        "uv.lock doit être normalisé AVANT le calcul de MODIFIED_FILES/stash"
    )


# --------------------------------------------------------------------------
# Bug terrain 2026-06-01 : `git stash push --include-untracked=false` est une
# syntaxe git INVALIDE (l'option booléenne n'accepte aucune valeur). Le stash
# échouait donc à chaque OTA depuis v5.8.0 → fallback « pull sur arbre sale » →
# avortement dès qu'un fichier tracké modifié localement était aussi changé
# upstream (sur le terrain : scripts/update_driftapp.sh copié à la main).
# --------------------------------------------------------------------------


def test_invalid_stash_flag_fails_and_blocks_pull(repo_pair: Path):
    """REPRODUIT LE BUG : le flag invalide fait échouer le stash, et le pull
    sur arbre sale avorte sur le fichier tracké modifié localement."""
    work = repo_pair
    # app.py est modifié upstream (C1) ET localement → collision si non stashé
    (work / "app.py").write_text("print('LOCAL edit')\n")

    bad = _git(["stash", "push", "--include-untracked=false", "-m", "x"], work)
    assert bad.returncode != 0, "le flag invalide doit faire échouer le stash"
    assert "include-untracked" in (bad.stderr + bad.stdout)

    # stash mort → pull --ff-only sur arbre sale → blocage nommant app.py
    res = _git(["pull", "--ff-only", "origin", "main"], work)
    assert res.returncode != 0
    assert "app.py" in (res.stderr + res.stdout)


def test_valid_stash_unblocks_pull(repo_pair: Path):
    """VALIDE LE FIX : `git stash push` seul (untracked exclus par défaut)
    écarte la modif locale → le pull fast-forward passe."""
    work = repo_pair
    (work / "app.py").write_text("print('LOCAL edit')\n")

    good = _git(["stash", "push", "-m", "x"], work)
    assert good.returncode == 0, good.stderr

    res = _git(["pull", "--ff-only", "origin", "main"], work)
    assert res.returncode == 0, res.stderr
    assert (work / "app.py").read_text() == "print('c1')\n"


def test_update_script_stash_invocation_is_valid():
    """GUARD : le script ne doit jamais utiliser `--include-untracked=false`
    (syntaxe invalide). `git stash push` exclut déjà les untracked par défaut."""
    content = UPDATE_SCRIPT.read_text()
    assert "--include-untracked=false" not in content, (
        "`git stash push --include-untracked=false` est invalide → stash échoue "
        "silencieusement (bug terrain 2026-06-01) ; utiliser `git stash push` seul"
    )
    assert "git stash push" in content, "le script doit toujours stasher les modifs locales"
