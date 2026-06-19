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

    def test_cles_metadata_underscore_non_reportees(self):
        # _comment / _version ne doivent jamais polluer added/removed.
        user = {"a": 1, "_version": "1.0"}
        template = {"a": 0, "_version": "2.0", "_comment": "doc", "nouveau": 5}
        merged, added, removed = _structural_merge(user, template)
        # la vraie nouvelle clé est reportée, pas les métadonnées
        assert added == ["nouveau"]
        assert removed == []
        # valeur user sacrée préservée sur la clé commune
        assert merged["a"] == 1
        assert merged["_version"] == "1.0"

    def test_cle_underscore_obsolete_non_reportee(self):
        user = {"a": 1, "_vieux_comment": "x"}
        template = {"a": 0}
        merged, added, removed = _structural_merge(user, template)
        assert removed == []  # _vieux_comment retiré du merged mais pas reporté


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


from core.config.config_resilience import (  # noqa: E402
    ADVANCED_SECTIONS,
    build_config_schema,
)


class TestBuildConfigSchema:
    def test_infere_les_types_et_ignore_les_underscore(self):
        template = {
            "_comment": "global",
            "site": {"latitude": 44.15, "altitude": 800, "nom": "Ubik"},
            "simulation": False,
        }
        schema = build_config_schema(template)
        sections = {s["key"]: s for s in schema}

        # 'simulation' (scalaire top-level) regroupé sous la section synthétique 'Général'
        assert "_general" in sections
        gen_fields = {f["key"]: f for f in sections["_general"]["fields"]}
        assert gen_fields["simulation"]["type"] == "bool"

        site_fields = {f["path"]: f for f in sections["site"]["fields"]}
        assert site_fields["site.latitude"]["type"] == "float"
        assert site_fields["site.altitude"]["type"] == "int"
        assert site_fields["site.nom"]["type"] == "str"
        # aucune clé _-préfixée n'est devenue un champ
        assert all(not f["key"].startswith("_") for f in site_fields.values())

    def test_bool_avant_int(self):
        # isinstance(True, int) is True → bool doit être testé en premier
        template = {"flags": {"enabled": True}}
        schema = build_config_schema(template)
        field = schema[0]["fields"][0]
        assert field["type"] == "bool"

    def test_section_avancee_marquee(self):
        template = {
            "site": {"latitude": 44.0},
            "moteur": {"microsteps": 4},
        }
        schema = {s["key"]: s for s in build_config_schema(template)}
        assert schema["site"]["advanced"] is False
        assert schema["moteur"]["advanced"] is True
        assert "moteur" in ADVANCED_SECTIONS

    def test_aide_extraite_du_comment_voisin(self):
        template = {
            "motor_driver": {"serial": {"port": "/dev/ttyACM0", "_port_comment": "Port USB CDC"}}
        }
        schema = build_config_schema(template)
        fields = {f["path"]: f for f in schema[0]["fields"]}
        assert fields["motor_driver.serial.port"]["help"] == "Port USB CDC"

    def test_enum_detecte_depuis_le_registre(self):
        template = {"cimier": {"automation": {"mode": "full"}}}
        schema = build_config_schema(template)
        field = schema[0]["fields"][0]
        assert field["path"] == "cimier.automation.mode"
        assert field["enum"] == ["manual", "semi", "full"]

    def test_groupe_sous_section_renseigne(self):
        template = {"cimier": {"motor_shelly": {"host_motor": ""}}}
        schema = build_config_schema(template)
        field = schema[0]["fields"][0]
        assert field["group"] == "motor_shelly"


import pytest  # noqa: E402

from core.config.config_resilience import (  # noqa: E402
    ConfigValidationError,
    validate_and_coerce,
)


class TestValidateAndCoerce:
    def test_types_corrects_preserves(self):
        template = {"site": {"latitude": 44.0, "altitude": 800, "nom": "x"}}
        values = {"site": {"latitude": 45.1, "altitude": 810, "nom": "Ubik"}}
        out = validate_and_coerce(values, template)
        assert out == {"site": {"latitude": 45.1, "altitude": 810, "nom": "Ubik"}}
        assert isinstance(out["site"]["altitude"], int)

    def test_int_vers_float_si_champ_float(self):
        template = {"site": {"latitude": 44.0}}
        out = validate_and_coerce({"site": {"latitude": 45}}, template)
        assert out["site"]["latitude"] == 45.0
        assert isinstance(out["site"]["latitude"], float)

    def test_chaine_vide_autorisee_pour_str(self):
        template = {"cimier": {"motor_shelly": {"host_motor": "192.168.1.85"}}}
        out = validate_and_coerce({"cimier": {"motor_shelly": {"host_motor": ""}}}, template)
        assert out["cimier"]["motor_shelly"]["host_motor"] == ""

    def test_texte_dans_champ_numerique_rejete(self):
        template = {"site": {"altitude": 800}}
        with pytest.raises(ConfigValidationError) as exc:
            validate_and_coerce({"site": {"altitude": "abc"}}, template)
        assert exc.value.path == "site.altitude"

    def test_bool_non_accepte_pour_int(self):
        template = {"site": {"altitude": 800}}
        with pytest.raises(ConfigValidationError) as exc:
            validate_and_coerce({"site": {"altitude": True}}, template)
        assert exc.value.path == "site.altitude"


from core.config.config_resilience import _REPORT_CACHE, write_user_config  # noqa: E402


class TestWriteUserConfig:
    def _paths(self, tmp_path):
        return (
            tmp_path / "config.json",
            tmp_path / "config.template.json",
            tmp_path / ".config.lastgood.json",
        )

    def test_ecrit_valeurs_et_reinjecte_comment(self, tmp_path):
        cfg, tmpl, backup = self._paths(tmp_path)
        _atomic_write_json(
            tmpl,
            {
                "_comment": "gabarit",
                "site": {"_comment": "le site", "latitude": 44.0, "nom": "x"},
            },
        )
        report = write_user_config(
            {"site": {"latitude": 45.5, "nom": "Ubik"}},
            config_path=cfg,
            template_path=tmpl,
            backup_path=backup,
        )
        written = json.loads(cfg.read_text())
        assert written["site"]["latitude"] == 45.5
        assert written["site"]["nom"] == "Ubik"
        assert written["site"]["_comment"] == "le site"  # _comment réinjecté
        assert written["_comment"] == "gabarit"
        assert report.status == "saved"
        # lastgood rafraîchi à l'identique
        assert json.loads(backup.read_text()) == written

    def test_type_invalide_leve_et_n_ecrit_pas(self, tmp_path):
        cfg, tmpl, backup = self._paths(tmp_path)
        _atomic_write_json(tmpl, {"site": {"altitude": 800}})
        with pytest.raises(ConfigValidationError):
            write_user_config(
                {"site": {"altitude": "haut"}},
                config_path=cfg,
                template_path=tmpl,
                backup_path=backup,
            )
        assert not cfg.exists()  # rien écrit

    def test_invalide_le_cache_report(self, tmp_path):
        cfg, tmpl, backup = self._paths(tmp_path)
        _atomic_write_json(tmpl, {"site": {"nom": "x"}})
        _atomic_write_json(cfg, {"site": {"nom": "ancien"}})
        ensure_config_ready(cfg, tmpl, backup)  # peuple _REPORT_CACHE
        assert str(cfg) in _REPORT_CACHE
        write_user_config(
            {"site": {"nom": "neuf"}},
            config_path=cfg,
            template_path=tmpl,
            backup_path=backup,
        )
        assert str(cfg) not in _REPORT_CACHE  # cache invalidé


from core.config import config_resilience as _cr  # noqa: E402


class TestSchemaRefinements:
    def test_enum_int_pour_indices_shelly(self):
        template = {"cimier": {"motor_shelly": {"relay_motor": 0}}}
        schema = build_config_schema(template)
        field = schema[0]["fields"][0]
        assert field["enum"] == [0, 1]
        assert field["type"] == "int"

    def test_enum_int_mode_spi(self):
        template = {"encodeur": {"spi": {"mode": 0}}}
        schema = build_config_schema(template)
        field = schema[0]["fields"][0]
        assert field["enum"] == [0, 1, 2, 3]

    def test_help_fallback_registry(self, monkeypatch):
        monkeypatch.setitem(_cr.HELP_REGISTRY, "site.latitude", "Latitude (degrés).")
        template = {"site": {"latitude": 44.0}}
        field = build_config_schema(template)[0]["fields"][0]
        assert field["help"] == "Latitude (degrés)."

    def test_comment_template_prioritaire_sur_registry(self, monkeypatch):
        monkeypatch.setitem(_cr.HELP_REGISTRY, "site.latitude", "depuis registry")
        template = {"site": {"latitude": 44.0, "_latitude_comment": "depuis template"}}
        field = build_config_schema(template)[0]["fields"][0]
        assert field["help"] == "depuis template"
