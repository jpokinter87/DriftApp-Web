"""Tests du journal de nuit cimier (transitions pluie + événements cimier)."""

from __future__ import annotations

import json
from datetime import datetime, timedelta

from services import night_journal


class TestNightKey:
    def test_evening_belongs_to_its_own_date(self):
        assert night_journal.night_key(datetime(2026, 8, 14, 22, 30)) == "2026-08-14"

    def test_after_midnight_belongs_to_the_previous_date(self):
        # Une nuit ne doit pas être coupée en deux à minuit.
        assert night_journal.night_key(datetime(2026, 8, 15, 3, 15)) == "2026-08-14"

    def test_noon_starts_a_new_night(self):
        assert night_journal.night_key(datetime(2026, 8, 15, 12, 0)) == "2026-08-15"

    def test_just_before_noon_still_previous_night(self):
        assert night_journal.night_key(datetime(2026, 8, 15, 11, 59)) == "2026-08-14"


class TestAppendAndRead:
    def test_append_then_read_roundtrip(self, tmp_path):
        night_journal.append_event(
            "rain",
            at=datetime(2026, 8, 14, 22, 30),
            nights_dir=tmp_path,
            state="wet",
            armed=False,
        )
        events = night_journal.read_night("2026-08-14", nights_dir=tmp_path)
        assert len(events) == 1
        assert events[0]["event"] == "rain"
        assert events[0]["state"] == "wet"
        assert events[0]["armed"] is False
        assert events[0]["ts"].startswith("2026-08-14T22:30")

    def test_appends_accumulate_in_order(self, tmp_path):
        for minute, state in ((0, "wet"), (5, "dry"), (9, "wet")):
            night_journal.append_event(
                "rain",
                at=datetime(2026, 8, 14, 23, minute),
                nights_dir=tmp_path,
                state=state,
            )
        events = night_journal.read_night("2026-08-14", nights_dir=tmp_path)
        assert [e["state"] for e in events] == ["wet", "dry", "wet"]

    def test_events_after_midnight_land_in_the_same_file(self, tmp_path):
        night_journal.append_event(
            "rain", at=datetime(2026, 8, 14, 23, 50), nights_dir=tmp_path, state="wet"
        )
        night_journal.append_event(
            "rain", at=datetime(2026, 8, 15, 0, 10), nights_dir=tmp_path, state="dry"
        )
        assert len(night_journal.read_night("2026-08-14", nights_dir=tmp_path)) == 2

    def test_read_unknown_night_returns_empty(self, tmp_path):
        assert night_journal.read_night("1999-01-01", nights_dir=tmp_path) == []

    def test_corrupted_line_is_skipped_not_fatal(self, tmp_path):
        night_journal.append_event(
            "rain", at=datetime(2026, 8, 14, 22, 0), nights_dir=tmp_path, state="wet"
        )
        path = tmp_path / "2026-08-14.jsonl"
        with open(path, "a", encoding="utf-8") as fh:
            fh.write("{ceci n'est pas du json\n")
        assert len(night_journal.read_night("2026-08-14", nights_dir=tmp_path)) == 1

    def test_append_never_raises_on_io_error(self, tmp_path):
        # Un disque plein ne doit jamais empêcher une fermeture d'urgence.
        unwritable = tmp_path / "fichier"
        unwritable.write_text("", encoding="utf-8")
        assert (
            night_journal.append_event(
                "rain", at=datetime(2026, 8, 14, 22, 0), nights_dir=unwritable, state="wet"
            )
            is False
        )

    def test_append_never_raises_on_invalid_timestamp(self, tmp_path):
        # La promesse « ne lève jamais » vaut aussi pour un appelant fautif :
        # ce module est sur le chemin d'une fermeture d'urgence.
        assert (
            night_journal.append_event("rain", at="pas-une-date", nights_dir=tmp_path, state="wet")
            is False
        )


class TestListAndPurge:
    def test_list_nights_is_sorted_most_recent_first(self, tmp_path):
        for day in (12, 14, 13):
            night_journal.append_event(
                "rain", at=datetime(2026, 8, day, 22, 0), nights_dir=tmp_path, state="wet"
            )
        assert night_journal.list_nights(nights_dir=tmp_path) == [
            "2026-08-14",
            "2026-08-13",
            "2026-08-12",
        ]

    def test_purge_removes_files_older_than_retention(self, tmp_path):
        now = datetime(2026, 8, 14, 12, 0)
        old = now - timedelta(days=40)
        recent = now - timedelta(days=3)
        for moment in (old, recent):
            night_journal.append_event("rain", at=moment, nights_dir=tmp_path, state="wet")
        removed = night_journal.purge_old(nights_dir=tmp_path, retention_days=30, now=now)
        assert removed == 1
        remaining = night_journal.list_nights(nights_dir=tmp_path)
        assert remaining == [night_journal.night_key(recent)]

    def test_purge_keeps_everything_within_retention(self, tmp_path):
        now = datetime(2026, 8, 14, 12, 0)
        night_journal.append_event(
            "rain", at=now - timedelta(days=2), nights_dir=tmp_path, state="wet"
        )
        assert night_journal.purge_old(nights_dir=tmp_path, retention_days=30, now=now) == 0


class TestEventShapes:
    def test_decision_event(self, tmp_path):
        night_journal.append_event(
            "decision",
            at=datetime(2026, 8, 14, 23, 0),
            nights_dir=tmp_path,
            action="would_close",
            reason="rain",
        )
        e = night_journal.read_night("2026-08-14", nights_dir=tmp_path)[0]
        assert e["event"] == "decision"
        assert e["action"] == "would_close"

    def test_cimier_event(self, tmp_path):
        night_journal.append_event(
            "cimier",
            at=datetime(2026, 8, 14, 21, 0),
            nights_dir=tmp_path,
            action="open",
            result="ok",
        )
        e = night_journal.read_night("2026-08-14", nights_dir=tmp_path)[0]
        assert e["event"] == "cimier"
        assert e["result"] == "ok"

    def test_lines_are_valid_jsonl(self, tmp_path):
        night_journal.append_event(
            "rain", at=datetime(2026, 8, 14, 22, 0), nights_dir=tmp_path, state="dry"
        )
        raw = (tmp_path / "2026-08-14.jsonl").read_text(encoding="utf-8")
        assert raw.endswith("\n")
        json.loads(raw.strip())
