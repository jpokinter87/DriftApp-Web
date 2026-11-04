"""Lancement du dashboard en kiosque au démarrage du Pi (scripts/kiosk.sh et
scripts/install_kiosk.sh), exercés dans un HOME et un PATH factices."""

import os
import stat
import subprocess
from pathlib import Path

import pytest

SCRIPTS = Path(__file__).resolve().parent.parent / "scripts"
KIOSK = SCRIPTS / "kiosk.sh"
INSTALL = SCRIPTS / "install_kiosk.sh"


def _outil(bin_dir: Path, nom: str, corps: str) -> None:
    chemin = bin_dir / nom
    chemin.write_text("#!/bin/bash\n" + corps + "\n")
    chemin.chmod(chemin.stat().st_mode | stat.S_IEXEC)


@pytest.fixture
def env(tmp_path):
    home = tmp_path / "home"
    home.mkdir()
    bin_dir = tmp_path / "bin"
    bin_dir.mkdir()
    _outil(bin_dir, "sleep", "exit 0")
    _outil(bin_dir, "firefox", f'echo "$@" > "{tmp_path}/firefox.args"')
    return {
        "HOME": str(home),
        "PATH": f"{bin_dir}:{os.environ['PATH']}",
        "XDG_RUNTIME_DIR": str(tmp_path),
        "_tmp": tmp_path,
        "_bin": bin_dir,
    }


def _lancer(script: Path, env: dict) -> subprocess.CompletedProcess:
    propre = {k: v for k, v in env.items() if not k.startswith("_")}
    return subprocess.run(
        ["bash", str(script)], env=propre, capture_output=True, text=True, timeout=30
    )


# --- kiosk.sh -----------------------------------------------------------------


def test_kiosque_attend_django_puis_ouvre_firefox(env):
    compteur = env["_tmp"] / "curl.n"
    # Django répond au 50e essai, soit après 100 s : au-delà des 60 s de l'ancien script.
    _outil(
        env["_bin"],
        "curl",
        f'n=$(( $(cat "{compteur}" 2>/dev/null || echo 0) + 1 )); echo $n > "{compteur}"; '
        "[ $n -ge 50 ]",
    )
    assert _lancer(KIOSK, env).returncode == 0
    assert compteur.read_text().strip() == "50"
    assert (env["_tmp"] / "firefox.args").read_text().split() == [
        "--kiosk",
        "http://localhost:8000",
    ]


def test_kiosque_ouvre_firefox_meme_sans_django(env):
    _outil(env["_bin"], "curl", "exit 7")
    assert _lancer(KIOSK, env).returncode == 0
    assert (env["_tmp"] / "firefox.args").exists()


# --- install_kiosk.sh ---------------------------------------------------------


def _ecrire(env, relatif: str, contenu: str) -> Path:
    chemin = Path(env["HOME"]) / relatif
    chemin.parent.mkdir(parents=True, exist_ok=True)
    chemin.write_text(contenu)
    return chemin


def test_remplace_le_lancement_labwc(env):
    f = _ecrire(
        env, ".config/labwc/autostart", "kanshi &\nfirefox --kiosk http://localhost:8000 &\n"
    )
    r = _lancer(INSTALL, env)
    assert r.returncode == 0, r.stderr
    assert f.read_text() == f'kanshi &\n"{KIOSK}" &\n'
    assert Path(str(f) + ".avant-kiosk").read_text().startswith("kanshi")
    assert not (Path(env["HOME"]) / ".config/autostart/driftapp-kiosk.desktop").exists()


def test_remplace_le_lancement_desktop(env):
    f = _ecrire(
        env,
        ".config/autostart/navigateur.desktop",
        "[Desktop Entry]\nType=Application\nExec=firefox --kiosk http://localhost:8000\n",
    )
    assert _lancer(INSTALL, env).returncode == 0
    assert f"Exec={KIOSK}\n" in f.read_text()
    assert "firefox" not in f.read_text()


def test_remplace_le_lancement_lxsession(env):
    f = _ecrire(env, ".config/lxsession/LXDE-pi/autostart", "@lxpanel\n@firefox --kiosk x\n")
    assert _lancer(INSTALL, env).returncode == 0
    assert f.read_text() == f"@lxpanel\n@{KIOSK}\n"


def test_remplace_le_lancement_wayfire(env):
    f = _ecrire(env, ".config/wayfire.ini", "[autostart]\nnav = firefox --kiosk x\n")
    assert _lancer(INSTALL, env).returncode == 0
    assert f.read_text() == f"[autostart]\nnav = {KIOSK}\n"


def test_sans_lancement_connu_cree_une_entree_autostart(env):
    r = _lancer(INSTALL, env)
    assert r.returncode == 0, r.stderr
    desktop = Path(env["HOME"]) / ".config/autostart/driftapp-kiosk.desktop"
    assert f"Exec={KIOSK}\n" in desktop.read_text()


def test_deuxieme_passage_ne_change_rien(env):
    f = _ecrire(env, ".config/labwc/autostart", "firefox --kiosk http://localhost:8000 &\n")
    _lancer(INSTALL, env)
    avant = f.read_text()
    r = _lancer(INSTALL, env)
    assert r.returncode == 0
    assert "déjà" in r.stdout
    assert f.read_text() == avant
    assert not (Path(env["HOME"]) / ".config/autostart/driftapp-kiosk.desktop").exists()
