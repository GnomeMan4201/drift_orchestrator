#!/usr/bin/env python3
"""
tests/test_controlplane_journal.py

Run with:
    pytest tests/test_controlplane_journal.py -v
    python3 -m pytest tests/test_controlplane_journal.py -v
"""

from __future__ import annotations

import json
import sqlite3
import tempfile
from pathlib import Path

import pytest

from controlplane.journal import (
    append_event,
    export_jsonl,
    init_db,
    recent_events,
)


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

@pytest.fixture
def db(tmp_path):
    """Fresh in-temp-dir database, initialized."""
    p = tmp_path / "test_journal.db"
    init_db(p)
    return p


# ---------------------------------------------------------------------------
# init_db
# ---------------------------------------------------------------------------

def test_init_creates_table(db):
    conn = sqlite3.connect(str(db))
    tables = {
        r[0]
        for r in conn.execute(
            "SELECT name FROM sqlite_master WHERE type='table'"
        ).fetchall()
    }
    conn.close()
    assert "action_events" in tables


def test_init_is_idempotent(db):
    """Calling init_db a second time must not raise or drop data."""
    append_event(session_id="s1", action="analyze", db_path=db)
    init_db(db)
    events = recent_events(db_path=db)
    assert len(events) == 1


def test_init_creates_index(db):
    conn = sqlite3.connect(str(db))
    indexes = {
        r[0]
        for r in conn.execute(
            "SELECT name FROM sqlite_master WHERE type='index'"
        ).fetchall()
    }
    conn.close()
    assert "idx_ae_session" in indexes


# ---------------------------------------------------------------------------
# append_event
# ---------------------------------------------------------------------------

def test_append_returns_positive_int(db):
    row_id = append_event(session_id="s1", action="analyze", db_path=db)
    assert isinstance(row_id, int)
    assert row_id >= 1


def test_append_increments_id(db):
    id1 = append_event(session_id="s1", action="analyze", db_path=db)
    id2 = append_event(session_id="s1", action="findings", db_path=db)
    assert id2 > id1


def test_append_stores_all_fields(db):
    append_event(
        session_id="op_session",
        action="promote_candidate",
        target_type="session",
        target_id="abc12345",
        target_summary="control_set alpha=0.3180",
        result="ok",
        metadata={"alpha": 0.318},
        db_path=db,
    )
    events = recent_events(db_path=db)
    ev = events[0]
    assert ev["session_id"]     == "op_session"
    assert ev["action"]         == "promote_candidate"
    assert ev["target_type"]    == "session"
    assert ev["target_id"]      == "abc12345"
    assert ev["target_summary"] == "control_set alpha=0.3180"
    assert ev["result"]         == "ok"


def test_append_null_optional_fields(db):
    append_event(session_id="s1", action="refresh", db_path=db)
    ev = recent_events(db_path=db)[0]
    assert ev["target_type"]    is None
    assert ev["target_id"]      is None
    assert ev["target_summary"] is None
    assert ev["metadata_json"]  is None


def test_append_ts_is_iso8601(db):
    from datetime import datetime, timezone
    append_event(session_id="s1", action="analyze", db_path=db)
    ev = recent_events(db_path=db)[0]
    # must parse without raising
    dt = datetime.fromisoformat(ev["ts"])
    assert dt.tzinfo is not None


# ---------------------------------------------------------------------------
# recent_events
# ---------------------------------------------------------------------------

def test_recent_events_newest_first(db):
    append_event(session_id="s1", action="analyze",  db_path=db)
    append_event(session_id="s1", action="findings", db_path=db)
    append_event(session_id="s1", action="open_raw", db_path=db)
    events = recent_events(db_path=db)
    assert [e["action"] for e in events] == ["open_raw", "findings", "analyze"]


def test_recent_events_limit(db):
    for i in range(10):
        append_event(session_id="s1", action="a" + str(i), db_path=db)
    events = recent_events(limit=3, db_path=db)
    assert len(events) == 3


def test_recent_events_filter_by_session(db):
    append_event(session_id="op_A", action="analyze",  db_path=db)
    append_event(session_id="op_B", action="findings", db_path=db)
    append_event(session_id="op_A", action="open_raw", db_path=db)

    events_a = recent_events(session_id="op_A", db_path=db)
    events_b = recent_events(session_id="op_B", db_path=db)

    assert len(events_a) == 2
    assert all(e["session_id"] == "op_A" for e in events_a)
    assert len(events_b) == 1
    assert events_b[0]["action"] == "findings"


def test_recent_events_empty_db(db):
    events = recent_events(db_path=db)
    assert events == []


# ---------------------------------------------------------------------------
# export_jsonl
# ---------------------------------------------------------------------------

def test_export_creates_file(db, tmp_path):
    append_event(session_id="s1", action="analyze", db_path=db)
    out = tmp_path / "out.jsonl"
    export_jsonl(out, db_path=db)
    assert out.exists()


def test_export_returns_line_count(db, tmp_path):
    for i in range(5):
        append_event(session_id="s1", action="a" + str(i), db_path=db)
    out = tmp_path / "out.jsonl"
    count = export_jsonl(out, db_path=db)
    assert count == 5


def test_export_valid_jsonl(db, tmp_path):
    append_event(session_id="s1", action="analyze",  db_path=db)
    append_event(session_id="s1", action="findings", db_path=db)
    out = tmp_path / "out.jsonl"
    export_jsonl(out, db_path=db)
    lines = out.read_text(encoding="utf-8").strip().splitlines()
    assert len(lines) == 2
    for line in lines:
        obj = json.loads(line)   # must not raise
        assert "action" in obj
        assert "ts" in obj


def test_export_chronological_order(db, tmp_path):
    append_event(session_id="s1", action="first",  db_path=db)
    append_event(session_id="s1", action="second", db_path=db)
    out = tmp_path / "out.jsonl"
    export_jsonl(out, db_path=db)
    lines = out.read_text(encoding="utf-8").strip().splitlines()
    assert json.loads(lines[0])["action"] == "first"
    assert json.loads(lines[1])["action"] == "second"


def test_export_filter_by_session(db, tmp_path):
    append_event(session_id="op_A", action="analyze",  db_path=db)
    append_event(session_id="op_B", action="findings", db_path=db)
    out = tmp_path / "only_a.jsonl"
    count = export_jsonl(out, session_id="op_A", db_path=db)
    assert count == 1
    obj = json.loads(out.read_text().strip())
    assert obj["session_id"] == "op_A"


def test_export_empty_db(db, tmp_path):
    out = tmp_path / "empty.jsonl"
    count = export_jsonl(out, db_path=db)
    assert count == 0
    assert out.read_text() == ""


# ---------------------------------------------------------------------------
# metadata round-trip
# ---------------------------------------------------------------------------

def test_metadata_dict_round_trip(db):
    meta = {
        "alpha":  0.42,
        "label":  "control_set",
        "flags":  [1, 2, 3],
        "nested": {"k": "v"},
    }
    append_event(session_id="s1", action="promote", metadata=meta, db_path=db)
    ev = recent_events(db_path=db)[0]
    stored = json.loads(ev["metadata_json"])
    assert stored["alpha"]       == 0.42
    assert stored["label"]       == "control_set"
    assert stored["flags"]       == [1, 2, 3]
    assert stored["nested"]["k"] == "v"


def test_metadata_none_stores_null(db):
    append_event(session_id="s1", action="analyze", metadata=None, db_path=db)
    ev = recent_events(db_path=db)[0]
    assert ev["metadata_json"] is None


def test_metadata_empty_dict(db):
    append_event(session_id="s1", action="analyze", metadata={}, db_path=db)
    ev = recent_events(db_path=db)[0]
    stored = json.loads(ev["metadata_json"])
    assert stored == {}
