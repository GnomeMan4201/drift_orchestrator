#!/usr/bin/env python3
"""
tests/test_controlplane_datasource.py

Tests for controlplane.datasource — the drift_orchestrator state boundary.
No Textual dependency.  No journal/invariants dependency.  Uses temp SQLite
databases and temp directories to exercise the loaders.

Run with:
    pytest tests/test_controlplane_datasource.py -v
"""

from __future__ import annotations

import json
import sqlite3
from pathlib import Path

import pytest

from controlplane.datasource import (
    UIRecord,
    SessionRecord,
    candidate_record,
    clamp_record,
    load_all_records,
    load_candidates,
    load_clamps,
    load_sessions,
    session_record,
)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def make_drift_db(tmp_path: Path) -> Path:
    """
    Create a minimal drift_orchestrator SQLite database with one session,
    one turn_metric, and one policy_event for testing.
    """
    db = tmp_path / "drift.db"
    conn = sqlite3.connect(str(db))
    conn.executescript("""
        CREATE TABLE sessions (
            id TEXT PRIMARY KEY,
            session_label TEXT,
            created_at TEXT
        );
        CREATE TABLE turn_metrics (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            session_id TEXT,
            alpha REAL,
            d_anchor REAL,
            d_goal REAL,
            rho_density REAL,
            repetition_score REAL,
            created_at TEXT
        );
        CREATE TABLE policy_events (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            session_id TEXT,
            action TEXT,
            reason TEXT,
            created_at TEXT
        );
        CREATE TABLE turns (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            session_id TEXT,
            token_count INTEGER,
            created_at TEXT
        );
        CREATE TABLE findings (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            session_id TEXT,
            severity TEXT,
            finding_type TEXT,
            detail TEXT,
            created_at TEXT
        );
    """)
    conn.execute(
        "INSERT INTO sessions VALUES (?, ?, ?)",
        ("abc12345-0000-0000-0000-000000000000", "control_set", "2026-05-03T08:00:00")
    )
    conn.execute(
        "INSERT INTO turn_metrics (session_id, alpha, d_anchor, d_goal, rho_density, repetition_score, created_at) VALUES (?, ?, ?, ?, ?, ?, ?)",
        ("abc12345-0000-0000-0000-000000000000", 0.318, 0.462, 0.232, 0.548, 0.658, "2026-05-03T08:01:00")
    )
    conn.execute(
        "INSERT INTO policy_events (session_id, action, reason, created_at) VALUES (?, ?, ?, ?)",
        ("abc12345-0000-0000-0000-000000000000", "CONTINUE", "alpha_ok", "2026-05-03T08:01:01")
    )
    conn.execute(
        "INSERT INTO turns (session_id, token_count, created_at) VALUES (?, ?, ?)",
        ("abc12345-0000-0000-0000-000000000000", 72, "2026-05-03T08:01:00")
    )
    conn.commit()
    conn.close()
    return db


def make_candidate_file(candidates_dir: Path, session_id: str, label: str = "test") -> Path:
    candidates_dir.mkdir(parents=True, exist_ok=True)
    p = candidates_dir / (session_id + ".json")
    p.write_text(json.dumps({
        "session_id": session_id,
        "status": "CANDIDATE_REVIEW",
        "session": {"session_label": label},
    }), encoding="utf-8")
    return p


def make_clamp_file(candidates_dir: Path, session_id: str, exit_code: int = 0) -> Path:
    candidates_dir.mkdir(parents=True, exist_ok=True)
    p = candidates_dir / (session_id + "_degraded.json")
    p.write_text(json.dumps({
        "session_id": session_id,
        "annotation": "DEGRADED_REVIEW",
        "control_exit": exit_code,
    }), encoding="utf-8")
    return p


# ---------------------------------------------------------------------------
# UIRecord dataclass
# ---------------------------------------------------------------------------

class TestUIRecord:

    def test_is_frozen(self):
        r = UIRecord(record_type="session", record_id="abc", title="t", summary="s")
        with pytest.raises(Exception):
            r.record_id = "xyz"  # type: ignore[misc]

    def test_required_fields(self):
        r = UIRecord(record_type="session", record_id="abc", title="label", summary="label alpha=0.3")
        assert r.record_type == "session"
        assert r.record_id   == "abc"
        assert r.title       == "label"
        assert r.summary     == "label alpha=0.3"

    def test_default_fields(self):
        r = UIRecord(record_type="session", record_id="abc", title="t", summary="s")
        assert r.status   == "unknown"
        assert r.severity == "info"
        assert r.source   == "unknown"
        assert r.metadata == {}

    def test_metadata_is_dict(self):
        r = UIRecord(record_type="candidate", record_id="x", title="t", summary="s",
                     metadata={"k": "v"})
        assert r.metadata["k"] == "v"

    def test_has_all_contract_fields(self):
        for field in ("record_type", "record_id", "title", "summary",
                      "status", "severity", "source", "metadata"):
            assert hasattr(UIRecord(record_type="x", record_id="x", title="x", summary="x"), field)


# ---------------------------------------------------------------------------
# SessionRecord dataclass
# ---------------------------------------------------------------------------

class TestSessionRecord:

    def test_is_frozen(self):
        r = SessionRecord(record_type="session", record_id="abc", title="t", summary="s")
        with pytest.raises(Exception):
            r.alpha = 0.9  # type: ignore[misc]

    def test_has_uirecord_fields(self):
        r = SessionRecord(record_type="session", record_id="abc", title="label", summary="s")
        assert r.record_type == "session"
        assert r.record_id   == "abc"
        assert r.title       == "label"

    def test_has_session_display_fields(self):
        r = SessionRecord(record_type="session", record_id="abc", title="t", summary="s",
                          alpha=0.42, policy_action="CONTINUE",
                          turn_count=10, total_tokens=72, created_at="2026-05-03T08:00:00")
        assert r.alpha         == 0.42
        assert r.policy_action == "CONTINUE"
        assert r.turn_count    == 10
        assert r.total_tokens  == 72
        assert r.created_at    == "2026-05-03T08:00:00"

    def test_default_source_is_live(self):
        r = SessionRecord(record_type="session", record_id="abc", title="t", summary="s")
        assert r.source == "live"


# ---------------------------------------------------------------------------
# session_record constructor helper
# ---------------------------------------------------------------------------

class TestSessionRecordHelper:

    def test_returns_session_record(self):
        r = session_record(session_id="abc", label="ctrl", alpha=0.32,
                           policy_action="CONTINUE", turn_count=10,
                           total_tokens=72, created_at="2026-05-03")
        assert isinstance(r, SessionRecord)

    def test_record_type_is_session(self):
        r = session_record(session_id="abc", label="l", alpha=0.0,
                           policy_action="CONTINUE", turn_count=0,
                           total_tokens=0, created_at="")
        assert r.record_type == "session"

    def test_record_id_is_session_id(self):
        r = session_record(session_id="abc123", label="l", alpha=0.0,
                           policy_action="CONTINUE", turn_count=0,
                           total_tokens=0, created_at="")
        assert r.record_id == "abc123"

    def test_title_is_label(self):
        r = session_record(session_id="abc", label="control_set", alpha=0.0,
                           policy_action="CONTINUE", turn_count=0,
                           total_tokens=0, created_at="")
        assert r.title == "control_set"

    def test_summary_contains_alpha_and_action(self):
        r = session_record(session_id="abc", label="ctrl", alpha=0.3180,
                           policy_action="CONTINUE", turn_count=0,
                           total_tokens=0, created_at="")
        assert "alpha=0.3180" in r.summary
        assert "action=CONTINUE" in r.summary
        assert "ctrl" in r.summary

    def test_severity_low_for_small_alpha(self):
        r = session_record(session_id="abc", label="l", alpha=0.1,
                           policy_action="CONTINUE", turn_count=0,
                           total_tokens=0, created_at="")
        assert r.severity == "low"

    def test_severity_medium_for_mid_alpha(self):
        r = session_record(session_id="abc", label="l", alpha=0.45,
                           policy_action="CONTINUE", turn_count=0,
                           total_tokens=0, created_at="")
        assert r.severity == "medium"

    def test_severity_high_for_large_alpha(self):
        r = session_record(session_id="abc", label="l", alpha=0.75,
                           policy_action="ROLLBACK", turn_count=0,
                           total_tokens=0, created_at="")
        assert r.severity == "high"

    def test_source_is_live(self):
        r = session_record(session_id="abc", label="l", alpha=0.0,
                           policy_action="CONTINUE", turn_count=0,
                           total_tokens=0, created_at="")
        assert r.source == "live"

    def test_status_is_policy_action(self):
        r = session_record(session_id="abc", label="l", alpha=0.0,
                           policy_action="ROLLBACK", turn_count=0,
                           total_tokens=0, created_at="")
        assert r.status == "ROLLBACK"
        assert r.policy_action == "ROLLBACK"


# ---------------------------------------------------------------------------
# candidate_record helper
# ---------------------------------------------------------------------------

class TestCandidateRecord:

    def test_returns_uirecord(self):
        r = candidate_record(session_id="abc", label="ctrl", alpha=0.32)
        assert isinstance(r, UIRecord)

    def test_record_type_is_candidate(self):
        r = candidate_record(session_id="abc")
        assert r.record_type == "candidate"

    def test_record_id_is_session_id(self):
        r = candidate_record(session_id="abc123")
        assert r.record_id == "abc123"

    def test_status_is_candidate_review(self):
        r = candidate_record(session_id="abc")
        assert r.status == "CANDIDATE_REVIEW"

    def test_source_is_file(self):
        r = candidate_record(session_id="abc")
        assert r.source == "file"

    def test_path_in_metadata(self):
        p = Path("/tmp/abc.json")
        r = candidate_record(session_id="abc", path=p)
        assert "candidate_path" in r.metadata
        assert r.metadata["candidate_path"] == str(p)


# ---------------------------------------------------------------------------
# clamp_record helper
# ---------------------------------------------------------------------------

class TestClampRecord:

    def test_returns_uirecord(self):
        r = clamp_record(session_id="abc")
        assert isinstance(r, UIRecord)

    def test_record_type_is_clamp(self):
        r = clamp_record(session_id="abc")
        assert r.record_type == "clamp"

    def test_status_ok_for_exit_zero(self):
        r = clamp_record(session_id="abc", exit_code=0)
        assert r.status == "ok"

    def test_status_error_for_nonzero_exit(self):
        r = clamp_record(session_id="abc", exit_code=1)
        assert r.status == "error"

    def test_severity_high_on_error(self):
        r = clamp_record(session_id="abc", exit_code=1)
        assert r.severity == "high"

    def test_exit_code_in_metadata(self):
        r = clamp_record(session_id="abc", exit_code=42)
        assert r.metadata["exit_code"] == 42

    def test_source_is_file(self):
        r = clamp_record(session_id="abc")
        assert r.source == "file"


# ---------------------------------------------------------------------------
# load_sessions
# ---------------------------------------------------------------------------

class TestLoadSessions:

    def test_returns_list(self, tmp_path):
        db = make_drift_db(tmp_path)
        result = load_sessions(db)
        assert isinstance(result, list)

    def test_empty_if_db_missing(self, tmp_path):
        assert load_sessions(tmp_path / "missing.db") == []

    def test_returns_session_records(self, tmp_path):
        db = make_drift_db(tmp_path)
        records = load_sessions(db)
        assert len(records) == 1
        assert isinstance(records[0], SessionRecord)

    def test_record_id_is_session_uuid(self, tmp_path):
        db = make_drift_db(tmp_path)
        r = load_sessions(db)[0]
        assert r.record_id == "abc12345-0000-0000-0000-000000000000"

    def test_record_type_is_session(self, tmp_path):
        db = make_drift_db(tmp_path)
        r = load_sessions(db)[0]
        assert r.record_type == "session"

    def test_title_is_label(self, tmp_path):
        db = make_drift_db(tmp_path)
        r = load_sessions(db)[0]
        assert r.title == "control_set"

    def test_alpha_populated(self, tmp_path):
        db = make_drift_db(tmp_path)
        r = load_sessions(db)[0]
        assert abs(r.alpha - 0.318) < 0.001

    def test_policy_action_populated(self, tmp_path):
        db = make_drift_db(tmp_path)
        r = load_sessions(db)[0]
        assert r.policy_action == "CONTINUE"

    def test_summary_contains_alpha_and_action(self, tmp_path):
        db = make_drift_db(tmp_path)
        r = load_sessions(db)[0]
        assert "alpha=" in r.summary
        assert "action=" in r.summary

    def test_source_is_live(self, tmp_path):
        db = make_drift_db(tmp_path)
        r = load_sessions(db)[0]
        assert r.source == "live"

    def test_turn_count_populated(self, tmp_path):
        db = make_drift_db(tmp_path)
        r = load_sessions(db)[0]
        assert r.turn_count == 1

    def test_no_mock_label(self, tmp_path):
        db = make_drift_db(tmp_path)
        r = load_sessions(db)[0]
        assert r.source != "mock"
        assert r.source != "static"


# ---------------------------------------------------------------------------
# load_candidates
# ---------------------------------------------------------------------------

class TestLoadCandidates:

    def test_returns_list(self, tmp_path):
        assert isinstance(load_candidates(tmp_path / "empty"), list)

    def test_empty_if_dir_missing(self, tmp_path):
        assert load_candidates(tmp_path / "missing") == []

    def test_loads_candidate_file(self, tmp_path):
        cdir = tmp_path / "candidates"
        make_candidate_file(cdir, "ses001", "test_label")
        records = load_candidates(cdir)
        assert len(records) == 1
        assert records[0].record_type == "candidate"
        assert records[0].record_id   == "ses001"

    def test_skips_degraded_files(self, tmp_path):
        cdir = tmp_path / "candidates"
        make_candidate_file(cdir, "ses001")
        make_clamp_file(cdir, "ses002")
        records = load_candidates(cdir)
        assert len(records) == 1
        assert records[0].record_id == "ses001"

    def test_source_is_file(self, tmp_path):
        cdir = tmp_path / "candidates"
        make_candidate_file(cdir, "ses001")
        r = load_candidates(cdir)[0]
        assert r.source == "file"


# ---------------------------------------------------------------------------
# load_clamps
# ---------------------------------------------------------------------------

class TestLoadClamps:

    def test_returns_list(self, tmp_path):
        assert isinstance(load_clamps(tmp_path / "empty"), list)

    def test_empty_if_dir_missing(self, tmp_path):
        assert load_clamps(tmp_path / "missing") == []

    def test_loads_clamp_file(self, tmp_path):
        cdir = tmp_path / "candidates"
        make_clamp_file(cdir, "ses001", exit_code=0)
        records = load_clamps(cdir)
        assert len(records) == 1
        assert records[0].record_type == "clamp"
        assert records[0].record_id   == "ses001"

    def test_skips_candidate_files(self, tmp_path):
        cdir = tmp_path / "candidates"
        make_candidate_file(cdir, "ses001")
        make_clamp_file(cdir, "ses002")
        records = load_clamps(cdir)
        assert len(records) == 1
        assert records[0].record_id == "ses002"

    def test_exit_code_in_metadata(self, tmp_path):
        cdir = tmp_path / "candidates"
        make_clamp_file(cdir, "ses001", exit_code=7)
        r = load_clamps(cdir)[0]
        assert r.metadata["exit_code"] == 7

    def test_source_is_file(self, tmp_path):
        cdir = tmp_path / "candidates"
        make_clamp_file(cdir, "ses001")
        r = load_clamps(cdir)[0]
        assert r.source == "file"


# ---------------------------------------------------------------------------
# load_all_records
# ---------------------------------------------------------------------------

class TestLoadAllRecords:

    def test_returns_list(self, tmp_path):
        db = make_drift_db(tmp_path)
        assert isinstance(load_all_records(db), list)

    def test_includes_sessions(self, tmp_path):
        db = make_drift_db(tmp_path)
        records = load_all_records(db)
        types = {r.record_type for r in records}
        assert "session" in types

    def test_includes_candidates_when_present(self, tmp_path):
        db = make_drift_db(tmp_path)
        cdir = tmp_path / "candidates"
        make_candidate_file(cdir, "ses001")
        records = load_all_records(db, cdir)
        types = [r.record_type for r in records]
        assert "candidate" in types

    def test_includes_clamps_when_present(self, tmp_path):
        db = make_drift_db(tmp_path)
        cdir = tmp_path / "candidates"
        make_clamp_file(cdir, "ses001")
        records = load_all_records(db, cdir)
        types = [r.record_type for r in records]
        assert "clamp" in types

    def test_sessions_come_first(self, tmp_path):
        db = make_drift_db(tmp_path)
        cdir = tmp_path / "candidates"
        make_candidate_file(cdir, "ses001")
        records = load_all_records(db, cdir)
        assert records[0].record_type == "session"

    def test_no_textual_import_needed(self):
        import sys
        textual_modules = [m for m in sys.modules if "textual" in m]
        assert not textual_modules, (
            "datasource imported Textual — this violates the boundary contract"
        )
