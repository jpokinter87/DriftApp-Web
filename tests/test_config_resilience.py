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


class TestAtomicWrite:
    def test_ecrit_via_tmp_puis_remplace(self, tmp_path):
        target = tmp_path / "config.json"
        _atomic_write_json(target, {"x": 1})
        assert json.loads(target.read_text()) == {"x": 1}
        # le .tmp ne doit pas subsister
        assert not (tmp_path / "config.json.tmp").exists()

    def test_remplace_un_fichier_existant(self, tmp_path):
        target = tmp_path / "config.json"
        target.write_text('{"old": true}')
        _atomic_write_json(target, {"new": True})
        assert json.loads(target.read_text()) == {"new": True}
