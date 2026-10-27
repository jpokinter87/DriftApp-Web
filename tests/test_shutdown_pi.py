"""Script d'extinction du Pi lancé par le bouton du dashboard (6.29.0).

Le script est copié dans un arbre temporaire (il déduit son PROJECT_DIR de son
propre emplacement) et ``systemctl`` est remplacé par un faux qui note son appel.
"""

from __future__ import annotations

import os
import subprocess
import time
from pathlib import Path

PROJECT_ROOT = Path(__file__).parent.parent.resolve()
SHUTDOWN_SCRIPT = PROJECT_ROOT / "scripts" / "shutdown_pi.sh"
SUDOERS = PROJECT_ROOT / "setup" / "driftapp-updater.sudoers"


class TestShutdownScript:
    def _sandbox(self, tmp_path, modele: str | None):
        scripts = tmp_path / "scripts"
        scripts.mkdir()
        target = scripts / "shutdown_pi.sh"
        target.write_text(SHUTDOWN_SCRIPT.read_text(), encoding="utf-8")
        target.chmod(0o755)

        fake_bin = tmp_path / "bin"
        fake_bin.mkdir()
        appel = tmp_path / "systemctl_appel"
        systemctl = fake_bin / "systemctl"
        systemctl.write_text(f'#!/bin/bash\necho "$*" > {appel}\n', encoding="utf-8")
        systemctl.chmod(0o755)

        model_file = tmp_path / "model"
        if modele is not None:
            model_file.write_text(modele, encoding="utf-8")
        return target, fake_bin, model_file, appel

    def _run(self, script, fake_bin, model_file):
        env = dict(os.environ)
        env["PATH"] = f"{fake_bin}:{env['PATH']}"
        env["DRIFTAPP_MODEL_FILE"] = str(model_file)
        return subprocess.run(
            ["bash", str(script)], capture_output=True, text=True, env=env, timeout=10
        )

    def test_existe_et_executable(self):
        assert SHUTDOWN_SCRIPT.exists()
        assert os.access(SHUTDOWN_SCRIPT, os.X_OK)

    def test_refuse_hors_raspberry_pi(self, tmp_path):
        # En dev, un essai ne doit jamais éteindre le PC.
        script, fake_bin, model_file, appel = self._sandbox(tmp_path, None)
        result = self._run(script, fake_bin, model_file)
        assert result.returncode != 0
        time.sleep(4)
        assert not appel.exists()

    def test_programme_l_extinction_sur_un_pi(self, tmp_path):
        script, fake_bin, model_file, appel = self._sandbox(
            tmp_path, "Raspberry Pi 5 Model B Rev 1.0\x00"
        )
        debut = time.monotonic()
        result = self._run(script, fake_bin, model_file)
        # La réponse HTTP doit partir avant l'arrêt : le script rend la main tout de suite.
        assert result.returncode == 0
        assert time.monotonic() - debut < 2
        assert "SHUTDOWN_SCHEDULED" in result.stdout
        for _ in range(60):
            if appel.exists():
                break
            time.sleep(0.1)
        assert appel.read_text().strip() == "poweroff"
        assert "Extinction" in (tmp_path / "logs" / "shutdown.log").read_text()


class TestSudoers:
    def test_script_autorise(self):
        assert "/home/slenk/DriftApp/scripts/shutdown_pi.sh" in SUDOERS.read_text()

    def test_aucun_argument_autorise(self):
        # La ligne se termine par le script : pas d'argument arbitraire.
        lignes = [x for x in SUDOERS.read_text().splitlines() if "shutdown_pi.sh" in x]
        assert lignes == ["slenk ALL=(root) NOPASSWD: /home/slenk/DriftApp/scripts/shutdown_pi.sh"]
