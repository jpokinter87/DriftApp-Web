"""
Tests du diff config local vs upstream (v5.12.0).

Couvre `web/health/config_diff.py:diff_config()` — la fonction pure utilisée
par l'endpoint `/api/health/update/config_diff/` et la modale UI de la MAJ OTA.
"""

from __future__ import annotations

import json
from unittest.mock import patch


from web.health.config_diff import diff_config, get_config_diff


# ============================================================================
# diff_config (fonction pure)
# ============================================================================


class TestDiffConfig:
    def test_no_diff_when_identical(self):
        cfg = {"a": 1, "b": {"c": 2}}
        assert diff_config(cfg, cfg) == []

    def test_added_key(self):
        local = {"a": 1}
        upstream = {"a": 1, "b": 2}
        diffs = diff_config(local, upstream)
        assert diffs == [{"path": "b", "op": "added", "local": None, "upstream": 2}]

    def test_removed_key(self):
        local = {"a": 1, "b": 2}
        upstream = {"a": 1}
        diffs = diff_config(local, upstream)
        assert diffs == [{"path": "b", "op": "removed", "local": 2, "upstream": None}]

    def test_modified_value(self):
        local = {"a": 1, "b": 2}
        upstream = {"a": 1, "b": 3}
        diffs = diff_config(local, upstream)
        assert diffs == [{"path": "b", "op": "modified", "local": 2, "upstream": 3}]

    def test_nested_diff_uses_dotted_path(self):
        local = {"section": {"key": "old"}}
        upstream = {"section": {"key": "new", "added": 42}}
        diffs = diff_config(local, upstream)
        assert {"path": "section.key", "op": "modified", "local": "old", "upstream": "new"} in diffs
        assert {"path": "section.added", "op": "added", "local": None, "upstream": 42} in diffs
        assert len(diffs) == 2

    def test_comments_are_ignored(self):
        local = {"_comment": "old comment", "a": 1}
        upstream = {"_comment": "new comment", "a": 1}
        assert diff_config(local, upstream) == []

    def test_comments_at_nested_level_ignored(self):
        local = {"section": {"_comment": "v1", "value": 10}}
        upstream = {"section": {"_comment": "v2", "value": 10}}
        assert diff_config(local, upstream) == []

    def test_dict_replaced_by_scalar(self):
        local = {"key": {"sub": 1}}
        upstream = {"key": "scalar"}
        diffs = diff_config(local, upstream)
        # Type différent → modified au niveau racine
        assert diffs == [{"path": "key", "op": "modified",
                          "local": {"sub": 1}, "upstream": "scalar"}]

    def test_realistic_meridian_anticipation_change(self):
        """Cas concret v5.11.2 : enabled false → true."""
        local = {
            "site": {"latitude": 44.15},
            "meridian_anticipation": {"enabled": False},
        }
        upstream = {
            "site": {"latitude": 44.15},
            "meridian_anticipation": {"enabled": True},
        }
        diffs = diff_config(local, upstream)
        assert diffs == [{
            "path": "meridian_anticipation.enabled",
            "op": "modified",
            "local": False,
            "upstream": True,
        }]


# ============================================================================
# get_config_diff (intégration : lit fichier local + git show upstream)
# ============================================================================


class TestGetConfigDiff:
    def test_local_missing_returns_clean_error(self, tmp_path):
        result = get_config_diff(tmp_path)
        assert result["has_diff"] is False
        assert result["local_exists"] is False
        assert "introuvable" in result["error"]

    def test_local_invalid_json_returns_error(self, tmp_path):
        (tmp_path / "data").mkdir()
        (tmp_path / "data" / "config.json").write_text("not json {")
        result = get_config_diff(tmp_path)
        assert result["has_diff"] is False
        assert result["local_exists"] is True
        assert "non parsable" in result["error"]

    def test_returns_diffs_when_upstream_differs(self, tmp_path):
        (tmp_path / "data").mkdir()
        (tmp_path / "data" / "config.json").write_text(
            json.dumps({"key": "local_value"})
        )
        with patch("web.health.config_diff.fetch_upstream_config",
                   return_value={"key": "upstream_value"}):
            result = get_config_diff(tmp_path)
        assert result["has_diff"] is True
        assert result["error"] is None
        assert len(result["diffs"]) == 1
        assert result["diffs"][0]["path"] == "key"
        assert result["diffs"][0]["op"] == "modified"

    def test_returns_no_diff_when_identical(self, tmp_path):
        cfg = {"a": 1, "b": {"c": 2}}
        (tmp_path / "data").mkdir()
        (tmp_path / "data" / "config.json").write_text(json.dumps(cfg))
        with patch("web.health.config_diff.fetch_upstream_config",
                   return_value=cfg):
            result = get_config_diff(tmp_path)
        assert result["has_diff"] is False
        assert result["diffs"] == []
        assert result["error"] is None

    def test_fetch_failure_propagates_as_error_field(self, tmp_path):
        (tmp_path / "data").mkdir()
        (tmp_path / "data" / "config.json").write_text(json.dumps({"a": 1}))
        with patch("web.health.config_diff.fetch_upstream_config",
                   side_effect=RuntimeError("git boom")):
            result = get_config_diff(tmp_path)
        assert result["has_diff"] is False
        assert result["error"] == "git boom"
