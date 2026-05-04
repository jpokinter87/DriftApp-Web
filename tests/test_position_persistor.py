"""Tests pour core/hardware/position_persistor.py (v6.4 Phase 1).

Couvre AC-1 (atomic write), AC-2 (throttling delta + temps), AC-3 (load robuste).
"""

import json
import logging

import pytest

from core.hardware.position_persistor import IMMOBILE_DELTA_DEG, PositionPersistor


@pytest.fixture
def persist_path(tmp_path):
    return tmp_path / "last_known_position.json"


# =============================================================================
# Construction & validation
# =============================================================================

class TestConstructor:
    def test_invalid_threshold_raises(self, persist_path):
        with pytest.raises(ValueError):
            PositionPersistor(persist_path, write_threshold_deg=0)

    def test_invalid_interval_raises(self, persist_path):
        with pytest.raises(ValueError):
            PositionPersistor(persist_path, write_interval_sec=-5)


# =============================================================================
# AC-1 — Écriture atomique
# =============================================================================

class TestAtomicWrite:
    def test_first_write_creates_file(self, persist_path):
        p = PositionPersistor(persist_path)
        assert p.maybe_write(180.0, calibrated=True) is True
        assert persist_path.exists()
        data = json.loads(persist_path.read_text())
        assert data["azimut_deg"] == 180.0
        assert isinstance(data["saved_at"], str)
        # ISO 8601 UTC parseable
        from datetime import datetime
        datetime.fromisoformat(data["saved_at"])

    def test_atomic_write_no_orphan_tmp(self, persist_path, tmp_path):
        p = PositionPersistor(persist_path)
        p.maybe_write(42.0, calibrated=True)
        orphans = list(tmp_path.glob("*.tmp"))
        assert orphans == []

    def test_write_payload_schema(self, persist_path):
        p = PositionPersistor(persist_path)
        p.maybe_write(123.456, calibrated=True)
        data = json.loads(persist_path.read_text())
        assert set(data.keys()) == {"azimut_deg", "saved_at"}
        assert isinstance(data["azimut_deg"], float)
        assert isinstance(data["saved_at"], str)

    def test_write_failure_no_crash(self, persist_path, monkeypatch):
        """OSError pendant tmp.replace() ne doit pas crasher le daemon."""
        from pathlib import Path

        def boom(self, *args, **kwargs):
            raise OSError("disk full")

        p = PositionPersistor(persist_path)
        monkeypatch.setattr(Path, "replace", boom)
        # Ne doit pas lever — le flag retour peut être True (l'écriture a été tentée).
        result = p.maybe_write(180.0, calibrated=True)
        assert result is True


# =============================================================================
# AC-2 — Throttling sur delta angulaire
# =============================================================================

class TestThrottlingDelta:
    def test_skip_below_threshold(self, persist_path):
        p = PositionPersistor(persist_path, write_threshold_deg=1.0)
        assert p.maybe_write(180.0, calibrated=True) is True
        first_mtime = persist_path.stat().st_mtime_ns
        # delta = 0.5 < 1.0, et interval << 30s → skip
        assert p.maybe_write(180.5, calibrated=True) is False
        assert persist_path.stat().st_mtime_ns == first_mtime

    def test_write_at_threshold(self, persist_path):
        p = PositionPersistor(persist_path, write_threshold_deg=1.0)
        p.maybe_write(180.0, calibrated=True)
        assert p.maybe_write(181.0, calibrated=True) is True

    def test_write_above_threshold(self, persist_path):
        p = PositionPersistor(persist_path, write_threshold_deg=1.0)
        p.maybe_write(180.0, calibrated=True)
        assert p.maybe_write(185.0, calibrated=True) is True

    def test_immobile_no_write(self, persist_path, monkeypatch):
        p = PositionPersistor(persist_path, write_threshold_deg=1.0, write_interval_sec=30.0)
        # Mock time pour avoir contrôle absolu : 1er write à t=0, 2e à t=100s.
        fake = {"now": 0.0}
        monkeypatch.setattr("core.hardware.position_persistor.time.time", lambda: fake["now"])
        p.maybe_write(180.0, calibrated=True)
        fake["now"] = 100.0
        # delta = 0.02 < IMMOBILE_DELTA_DEG (0.05) → skip même après l'interval.
        assert p.maybe_write(180.02, calibrated=True) is False

    def test_calibrated_false_no_write(self, persist_path):
        p = PositionPersistor(persist_path)
        assert p.maybe_write(180.0, calibrated=False) is False
        assert not persist_path.exists()


# =============================================================================
# AC-2 — Throttling sur intervalle temporel
# =============================================================================

class TestThrottlingTime:
    def test_skip_within_interval(self, persist_path, monkeypatch):
        p = PositionPersistor(persist_path, write_threshold_deg=1.0, write_interval_sec=30.0)
        fake = {"now": 0.0}
        monkeypatch.setattr("core.hardware.position_persistor.time.time", lambda: fake["now"])
        p.maybe_write(180.0, calibrated=True)
        fake["now"] = 10.0
        assert p.maybe_write(180.5, calibrated=True) is False

    def test_write_after_interval_with_movement(self, persist_path, monkeypatch):
        p = PositionPersistor(persist_path, write_threshold_deg=1.0, write_interval_sec=30.0)
        fake = {"now": 0.0}
        monkeypatch.setattr("core.hardware.position_persistor.time.time", lambda: fake["now"])
        p.maybe_write(180.0, calibrated=True)
        fake["now"] = 31.0
        # delta=0.5 < threshold MAIS > IMMOBILE_DELTA_DEG ET interval écoulé → write.
        assert p.maybe_write(180.5, calibrated=True) is True

    def test_no_write_after_interval_if_immobile(self, persist_path, monkeypatch):
        p = PositionPersistor(persist_path, write_threshold_deg=1.0, write_interval_sec=30.0)
        fake = {"now": 0.0}
        monkeypatch.setattr("core.hardware.position_persistor.time.time", lambda: fake["now"])
        p.maybe_write(180.0, calibrated=True)
        fake["now"] = 31.0
        # delta=0.02 ≤ IMMOBILE_DELTA_DEG → skip même après interval.
        assert p.maybe_write(180.02, calibrated=True) is False


# =============================================================================
# Wrap-around 359° / 1°
# =============================================================================

class TestAngleWrap:
    def test_wrap_around_359_to_1(self, persist_path):
        """Distance angulaire la plus courte = 2°, pas 358°."""
        p = PositionPersistor(persist_path, write_threshold_deg=1.0)
        p.maybe_write(359.0, calibrated=True)
        # delta réel = 2° via shortest_angular_distance → write.
        assert p.maybe_write(1.0, calibrated=True) is True


# =============================================================================
# AC-3 — load_last_position : robustesse corruption / absence
# =============================================================================

class TestLoadLastPosition:
    def test_load_missing_returns_none(self, persist_path, caplog):
        caplog.set_level(logging.WARNING)
        result = PositionPersistor.load_last_position(persist_path)
        assert result is None
        assert any("missing" in r.message for r in caplog.records)

    def test_load_empty_returns_none(self, persist_path, caplog):
        caplog.set_level(logging.WARNING)
        persist_path.write_text("")
        result = PositionPersistor.load_last_position(persist_path)
        assert result is None
        assert any("empty" in r.message for r in caplog.records)

    def test_load_invalid_json_returns_none(self, persist_path, caplog):
        caplog.set_level(logging.WARNING)
        persist_path.write_text("{not json")
        result = PositionPersistor.load_last_position(persist_path)
        assert result is None
        assert any("invalid_json" in r.message for r in caplog.records)

    def test_load_invalid_schema_returns_none(self, persist_path, caplog):
        caplog.set_level(logging.WARNING)
        persist_path.write_text(json.dumps({"foo": "bar"}))
        result = PositionPersistor.load_last_position(persist_path)
        assert result is None
        assert any("invalid_schema" in r.message for r in caplog.records)

    def test_load_valid_returns_dict(self, persist_path):
        persist_path.write_text(json.dumps({
            "azimut_deg": 187.3,
            "saved_at": "2026-05-03T19:54:12+00:00",
        }))
        result = PositionPersistor.load_last_position(persist_path)
        assert result is not None
        assert result["azimut_deg"] == 187.3
        assert result["saved_at"] == "2026-05-03T19:54:12+00:00"

    def test_load_azimut_out_of_range(self, persist_path, caplog):
        caplog.set_level(logging.WARNING)
        persist_path.write_text(json.dumps({
            "azimut_deg": 400.0,
            "saved_at": "2026-05-03T19:54:12+00:00",
        }))
        result = PositionPersistor.load_last_position(persist_path)
        assert result is None
        assert any("invalid_schema" in r.message for r in caplog.records)


# =============================================================================
# Sanity check : constante module
# =============================================================================

class TestConstants:
    def test_immobile_delta_deg_value(self):
        assert IMMOBILE_DELTA_DEG == 0.05
