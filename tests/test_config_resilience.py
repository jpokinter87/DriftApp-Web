"""Tests du noyau de résilience config (merge structurel + écriture atomique)."""

import json

from core.config.config_resilience import _structural_merge, _atomic_write_json


class TestStructuralMerge:
    def test_structure_identique_preserve_valeurs(self):
        user = {"a": 1, "b": {"c": 2}}
        template = {"a": 0, "b": {"c": 0}}
        merged, added, removed = _structural_merge(user, template)
        assert merged == {"a": 1, "b": {"c": 2}}  # valeurs user gardées
        assert added == []
        assert removed == []

    def test_nouvelle_cle_prend_le_defaut_template(self):
        user = {"a": 1}
        template = {"a": 0, "nouveau": 42}
        merged, added, removed = _structural_merge(user, template)
        assert merged == {"a": 1, "nouveau": 42}
        assert added == ["nouveau"]
        assert removed == []

    def test_cle_obsolete_retiree(self):
        user = {"a": 1, "vieux": 99}
        template = {"a": 0}
        merged, added, removed = _structural_merge(user, template)
        assert merged == {"a": 1}
        assert added == []
        assert removed == ["vieux"]

    def test_cles_imbriquees_chemins_pointes(self):
        user = {"cimier": {"motor_shelly": {"host_motor": "192.168.1.85"}}}
        template = {"cimier": {"motor_shelly": {"host_motor": "", "host_dir": ""}}}
        merged, added, removed = _structural_merge(user, template)
        assert merged["cimier"]["motor_shelly"]["host_motor"] == "192.168.1.85"
        assert merged["cimier"]["motor_shelly"]["host_dir"] == ""
        assert added == ["cimier.motor_shelly.host_dir"]
        assert removed == []

    def test_defaut_change_sur_cle_commune_valeur_user_conservee(self):
        # Verrou Option 1 : un changement de défaut n'est jamais propagé.
        user = {"motor_on_relay_state": True}
        template = {"motor_on_relay_state": False}
        merged, added, removed = _structural_merge(user, template)
        assert merged["motor_on_relay_state"] is True
        assert added == []
        assert removed == []

    def test_type_mismatch_garde_valeur_user_sans_crash(self):
        # template attend un dict, user a un scalaire (et inversement) :
        # on garde la valeur user, pas de récursion, pas de crash.
        user = {"a": "scalaire", "b": {"c": 1}}
        template = {"a": {"x": 0}, "b": 5}
        merged, added, removed = _structural_merge(user, template)
        assert merged["a"] == "scalaire"  # valeur user gardée malgré template dict
        assert merged["b"] == {"c": 1}  # valeur user gardée malgré template scalaire
        assert added == []
        assert removed == []


class TestAtomicWrite:
    def test_ecrit_via_tmp_puis_remplace(self, tmp_path):
        target = tmp_path / "config.json"
        _atomic_write_json(target, {"x": 1})
        assert json.loads(target.read_text()) == {"x": 1}
        # le .tmp ne doit pas subsister
        # aucun fichier .tmp résiduel (nom suffixé par PID)
        assert not list(tmp_path.glob("config.json.*.tmp"))

    def test_remplace_un_fichier_existant(self, tmp_path):
        target = tmp_path / "config.json"
        target.write_text('{"old": true}')
        _atomic_write_json(target, {"new": True})
        assert json.loads(target.read_text()) == {"new": True}


import json as _json  # noqa: E402
from dataclasses import asdict  # noqa: E402

from core.config.config_resilience import (  # noqa: E402
    ensure_config_ready,
    ConfigReport,
)


def _write(p, data):
    p.write_text(_json.dumps(data), encoding="utf-8")


class TestEnsureConfigReady:
    def _paths(self, tmp_path):
        return (
            tmp_path / "config.json",
            tmp_path / "config.template.json",
            tmp_path / ".config.lastgood.json",
        )

    def test_unchanged_ne_reecrit_pas_le_fichier(self, tmp_path):
        cfg, tpl, bak = self._paths(tmp_path)
        _write(tpl, {"a": 0})
        _write(cfg, {"a": 7})
        mtime_avant = cfg.stat().st_mtime_ns
        report = ensure_config_ready(cfg, tpl, bak, force=True)
        assert report.status == "unchanged"
        assert cfg.stat().st_mtime_ns == mtime_avant  # intact au bit près
        assert _json.loads(cfg.read_text()) == {"a": 7}

    def test_migrated_ajoute_nouvelle_cle_garde_valeurs(self, tmp_path):
        cfg, tpl, bak = self._paths(tmp_path)
        _write(tpl, {"a": 0, "nouveau": 42})
        _write(cfg, {"a": 7})
        report = ensure_config_ready(cfg, tpl, bak, force=True)
        assert report.status == "migrated"
        assert report.added == ["nouveau"]
        assert _json.loads(cfg.read_text()) == {"a": 7, "nouveau": 42}

    def test_bootstrap_depuis_template_si_absent(self, tmp_path):
        cfg, tpl, bak = self._paths(tmp_path)
        _write(tpl, {"a": 0, "b": 1})
        report = ensure_config_ready(cfg, tpl, bak, force=True)
        assert report.status == "bootstrapped_from_template"
        assert _json.loads(cfg.read_text()) == {"a": 0, "b": 1}

    def test_restore_depuis_backup_si_absent(self, tmp_path):
        cfg, tpl, bak = self._paths(tmp_path)
        _write(tpl, {"a": 0})
        _write(bak, {"a": 7})  # dernière config saine
        report = ensure_config_ready(cfg, tpl, bak, force=True)
        assert report.status == "restored_from_backup"
        assert _json.loads(cfg.read_text()) == {"a": 7}

    def test_recovered_corruption_restaure_backup(self, tmp_path):
        cfg, tpl, bak = self._paths(tmp_path)
        _write(tpl, {"a": 0})
        _write(bak, {"a": 7})
        cfg.write_text("{ ceci n'est pas du json", encoding="utf-8")
        report = ensure_config_ready(cfg, tpl, bak, force=True)
        assert report.status == "recovered_corruption"
        assert _json.loads(cfg.read_text()) == {"a": 7}

    def test_corruption_no_backup_regenere_template(self, tmp_path):
        cfg, tpl, bak = self._paths(tmp_path)
        _write(tpl, {"a": 0})
        cfg.write_text("CORROMPU", encoding="utf-8")
        report = ensure_config_ready(cfg, tpl, bak, force=True)
        assert report.status == "corruption_no_backup"
        assert _json.loads(cfg.read_text()) == {"a": 0}

    def test_lastgood_mis_a_jour_apres_chargement_valide(self, tmp_path):
        cfg, tpl, bak = self._paths(tmp_path)
        _write(tpl, {"a": 0})
        _write(cfg, {"a": 7})
        ensure_config_ready(cfg, tpl, bak, force=True)
        assert bak.exists()
        assert _json.loads(bak.read_text()) == {"a": 7}

    def test_report_est_un_dataclass_serialisable(self, tmp_path):
        cfg, tpl, bak = self._paths(tmp_path)
        _write(tpl, {"a": 0})
        _write(cfg, {"a": 7})
        report = ensure_config_ready(cfg, tpl, bak, force=True)
        assert isinstance(report, ConfigReport)
        d = asdict(report)
        assert set(d) >= {"status", "added", "removed", "backup_timestamp", "message"}
