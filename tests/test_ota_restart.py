"""Redémarrage des services : cascade OTA et bouton « Redémarrer » de l'UI.

Deux sujets liés, tous deux nécessaires pour qu'une mise à jour faite depuis
l'interface soit réellement appliquée sur le Pi sans accès SSH :

  1. la cascade de fin de MAJ doit relancer **tous** les services du dépôt —
     `cimier_service` en était absent, si bien qu'une MAJ laissait tourner
     l'ancien code cimier jusqu'au prochain reboot ;
  2. un changement de configuration fait depuis `/configuration/` n'a d'effet
     qu'après un redémarrage : sans bouton, la page est inutilisable à
     distance.
"""

from __future__ import annotations

from pathlib import Path

PROJECT_ROOT = Path(__file__).parent.parent.resolve()
UPDATE_SCRIPT = PROJECT_ROOT / "scripts" / "update_driftapp.sh"
RESTART_SCRIPT = PROJECT_ROOT / "scripts" / "restart_services.sh"
SUDOERS = PROJECT_ROOT / "setup" / "driftapp-updater.sudoers"


class TestUpdateCascade:
    """La MAJ doit relancer tous les services, sinon elle n'applique rien."""

    def test_restarts_cimier_service(self):
        assert "cimier_service.service" in UPDATE_SCRIPT.read_text(), (
            "update_driftapp.sh doit redémarrer cimier_service.service — sans "
            "cela le code cimier livré par la MAJ ne tourne jamais"
        )

    def test_restarts_every_service_of_the_repo(self):
        content = UPDATE_SCRIPT.read_text()
        for unit in sorted(p.name for p in PROJECT_ROOT.glob("*.service")):
            assert unit in content, f"{unit} absent de la cascade de redémarrage"

    def test_installs_every_service_unit_of_the_repo(self):
        # L'unité systemd doit être déployée par la MAJ : sinon un Pi qui ne
        # l'a jamais reçue (installation manuelle documentée) reste sans.
        content = UPDATE_SCRIPT.read_text()
        install_loop = content[content.find("ÉTAPE 4/5") : content.find("ÉTAPE 5/5")]
        for unit in sorted(p.name for p in PROJECT_ROOT.glob("*.service")):
            assert unit in install_loop, f"{unit} n'est pas installé par l'étape 4"

    def test_stops_cimier_service_before_pulling(self):
        # Un service qui tourne pendant que le code change sous ses pieds peut
        # importer un mélange d'ancien et de nouveau.
        content = UPDATE_SCRIPT.read_text()
        stop_stage = content[content.find("ÉTAPE 1/5") : content.find("ÉTAPE 2/5")]
        assert "cimier_service.service" in stop_stage

    def test_django_is_restarted_last(self):
        # Django porte la requête : le relancer avant les autres couperait le
        # script au milieu de la cascade.
        content = UPDATE_SCRIPT.read_text()
        idx_django = content.rfind("driftapp_web.service")
        for unit in ("ems22d.service", "motor_service.service", "cimier_service.service"):
            assert content.rfind(unit) < idx_django, f"{unit} doit précéder Django"


class TestRestartScript:
    """`scripts/restart_services.sh` — appliquer une config sans SSH."""

    def test_script_exists_and_is_executable(self):
        assert RESTART_SCRIPT.exists(), "scripts/restart_services.sh manquant"
        assert RESTART_SCRIPT.stat().st_mode & 0o111, "le script doit être exécutable"

    def test_restarts_the_three_backend_services(self):
        content = RESTART_SCRIPT.read_text()
        for unit in ("ems22d.service", "motor_service.service", "cimier_service.service"):
            assert unit in content, f"{unit} doit être redémarré"

    def test_never_restarts_django(self):
        # Django porte la requête HTTP du bouton : le relancer la couperait, et
        # c'est inutile — la sauvegarde de config invalide déjà son cache.
        assert "driftapp_web" not in RESTART_SCRIPT.read_text()

    def test_reports_result_as_json(self):
        # La vue lit ce JSON pour dire à l'utilisateur ce qui est reparti.
        content = RESTART_SCRIPT.read_text()
        assert "restart_status.json" in content


class TestRestartScriptExecution:
    """Exécution réelle du script, avec un `systemctl` de substitution.

    Le script est copié dans un arbre temporaire (il déduit son PROJECT_DIR de
    son propre emplacement) pour ne pas écrire dans les logs du dépôt.
    """

    def _sandbox(self, tmp_path, systemctl_body):
        scripts = tmp_path / "scripts"
        scripts.mkdir()
        (tmp_path / "logs").mkdir()
        target = scripts / "restart_services.sh"
        target.write_text(RESTART_SCRIPT.read_text(), encoding="utf-8")
        target.chmod(0o755)

        fake_bin = tmp_path / "bin"
        fake_bin.mkdir()
        systemctl = fake_bin / "systemctl"
        systemctl.write_text(systemctl_body, encoding="utf-8")
        systemctl.chmod(0o755)
        return target, fake_bin

    def _run(self, script, fake_bin):
        import os
        import subprocess

        env = dict(os.environ)
        env["PATH"] = f"{fake_bin}:{env['PATH']}"
        return subprocess.run(
            ["bash", str(script)], capture_output=True, text=True, env=env, timeout=60
        )

    def _status(self, tmp_path):
        import json

        return json.loads((tmp_path / "logs" / "restart_status.json").read_text())

    def test_all_services_active_is_a_success(self, tmp_path):
        script, fake_bin = self._sandbox(
            tmp_path,
            "#!/bin/bash\n"
            'case "$1" in\n'
            '  list-unit-files) echo "$2 enabled";;\n'
            "  is-active) exit 0;;\n"
            "esac\n"
            "exit 0\n",
        )
        result = self._run(script, fake_bin)
        assert result.returncode == 0
        status = self._status(tmp_path)
        assert [s["state"] for s in status["services"]] == ["active"] * 3

    def test_a_dead_service_fails_the_run_and_is_named(self, tmp_path):
        script, fake_bin = self._sandbox(
            tmp_path,
            "#!/bin/bash\n"
            'case "$1" in\n'
            '  list-unit-files) echo "$2 enabled";;\n'
            '  is-active) [[ "$*" == *cimier* ]] && exit 3; exit 0;;\n'
            "esac\n"
            "exit 0\n",
        )
        result = self._run(script, fake_bin)
        assert result.returncode == 1
        failed = [s["name"] for s in self._status(tmp_path)["services"] if s["state"] == "failed"]
        assert failed == ["cimier_service.service"]

    def test_absent_services_do_not_claim_a_restart(self, tmp_path):
        # Aucun service installé : annoncer « Services redémarrés » serait faux.
        script, fake_bin = self._sandbox(
            tmp_path,
            '#!/bin/bash\ncase "$1" in\n  list-unit-files) exit 0;;\nesac\nexit 0\n',
        )
        self._run(script, fake_bin)
        status = self._status(tmp_path)
        assert all(s["state"] == "absent" for s in status["services"])
        assert "redémarré" not in status["message"].lower()


class TestSudoersWhitelist:
    """La whitelist doit autoriser le nouveau script — et lui seul en plus."""

    def test_restart_script_is_whitelisted(self):
        assert "restart_services.sh" in SUDOERS.read_text(), (
            "sans entrée sudoers, le bouton échouera en demandant un mot de passe"
        )

    def test_systemctl_is_never_whitelisted_wholesale(self):
        # Propriété de sécurité d'origine : une compromission de Django ne doit
        # pas donner un systemctl root générique.
        for line in SUDOERS.read_text().splitlines():
            stripped = line.strip()
            if stripped.startswith("#") or not stripped:
                continue
            assert "/bin/systemctl" not in stripped and " systemctl" not in stripped

    def test_whitelisted_paths_match_the_repo_layout(self):
        # Le chemin d'installation terrain est /home/slenk/DriftApp.
        text = SUDOERS.read_text()
        assert "/home/slenk/DriftApp/scripts/restart_services.sh" in text
