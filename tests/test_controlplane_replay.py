#!/usr/bin/env python3
"""
tests/test_controlplane_replay.py

Run with:
    pytest tests/test_controlplane_replay.py -v
"""

from __future__ import annotations

import json
import time
from pathlib import Path

import pytest

from controlplane.journal import append_event, init_db
from controlplane.replay import (
    load_events,
    render_markdown_report,
    render_timeline,
    summarize_events,
    write_markdown_report,
)


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

@pytest.fixture
def db(tmp_path):
    p = tmp_path / "journal.db"
    init_db(p)
    return p


def _ev(db, session_id="op_A", action="analyze", target_id=None,
        target_type=None, result="ok", metadata=None):
    """Convenience wrapper: append one event and return its id."""
    return append_event(
        session_id=session_id,
        action=action,
        target_type=target_type,
        target_id=target_id,
        result=result,
        metadata=metadata,
        db_path=db,
    )


# ---------------------------------------------------------------------------
# load_events
# ---------------------------------------------------------------------------

class TestLoadEvents:

    def test_returns_list(self, db):
        assert isinstance(load_events(db_path=db), list)

    def test_empty_db_returns_empty(self, db):
        assert load_events(db_path=db) == []

    def test_chronological_order(self, db):
        _ev(db, action="analyze")
        _ev(db, action="findings")
        _ev(db, action="open_raw")
        events = load_events(db_path=db)
        assert [e["action"] for e in events] == ["analyze", "findings", "open_raw"]

    def test_filter_by_session_id(self, db):
        _ev(db, session_id="op_A", action="analyze")
        _ev(db, session_id="op_B", action="findings")
        _ev(db, session_id="op_A", action="open_raw")
        events = load_events(session_id="op_A", db_path=db)
        assert len(events) == 2
        assert all(e["session_id"] == "op_A" for e in events)

    def test_filter_returns_chronological(self, db):
        _ev(db, session_id="op_A", action="analyze")
        _ev(db, session_id="op_B", action="noise")
        _ev(db, session_id="op_A", action="findings")
        events = load_events(session_id="op_A", db_path=db)
        assert events[0]["action"] == "analyze"
        assert events[1]["action"] == "findings"

    def test_no_filter_returns_all(self, db):
        _ev(db, session_id="op_A", action="analyze")
        _ev(db, session_id="op_B", action="findings")
        assert len(load_events(db_path=db)) == 2


# ---------------------------------------------------------------------------
# summarize_events
# ---------------------------------------------------------------------------

class TestSummarizeEvents:

    def test_empty_events_returns_zeros(self):
        s = summarize_events([])
        assert s["event_count"] == 0
        assert s["started_at"] is None
        assert s["ended_at"] is None
        assert s["warning_flags"] == []

    def test_event_count(self, db):
        for i in range(5):
            _ev(db, action="analyze")
        events = load_events(db_path=db)
        s = summarize_events(events)
        assert s["event_count"] == 5

    def test_action_counts(self, db):
        _ev(db, action="analyze")
        _ev(db, action="analyze")
        _ev(db, action="findings")
        events = load_events(db_path=db)
        s = summarize_events(events)
        assert s["action_counts"]["analyze"] == 2
        assert s["action_counts"]["findings"] == 1

    def test_result_counts(self, db):
        _ev(db, action="analyze", result="ok")
        _ev(db, action="clamp",   result="error")
        _ev(db, action="replay",  result="ok")
        events = load_events(db_path=db)
        s = summarize_events(events)
        assert s["result_counts"]["ok"] == 2
        assert s["result_counts"]["error"] == 1

    def test_target_counts(self, db):
        _ev(db, action="analyze",  target_id="abc")
        _ev(db, action="findings", target_id="abc")
        _ev(db, action="analyze",  target_id="xyz")
        events = load_events(db_path=db)
        s = summarize_events(events)
        assert s["target_counts"]["abc"] == 2
        assert s["target_counts"]["xyz"] == 1

    def test_rollback_count(self, db):
        _ev(db, action="analyze")
        _ev(db, action="rollback")
        _ev(db, action="rollback")
        events = load_events(db_path=db)
        s = summarize_events(events)
        assert s["rollback_count"] == 2

    def test_promotion_count(self, db):
        _ev(db, action="promote_candidate")
        _ev(db, action="promote_candidate_pending", result="pending")
        events = load_events(db_path=db)
        s = summarize_events(events)
        # pending promotion should NOT count
        assert s["promotion_count"] == 1

    def test_export_count(self, db):
        _ev(db, action="analyze")
        _ev(db, action="export")
        events = load_events(db_path=db)
        s = summarize_events(events)
        assert s["export_count"] == 1

    def test_started_at_and_ended_at(self, db):
        _ev(db, action="analyze")
        _ev(db, action="findings")
        events = load_events(db_path=db)
        s = summarize_events(events)
        assert s["started_at"] == events[0]["ts"]
        assert s["ended_at"]   == events[-1]["ts"]


# ---------------------------------------------------------------------------
# Warning flags
# ---------------------------------------------------------------------------

class TestWarningFlags:

    def test_clean_session_no_warnings(self, db):
        _ev(db, action="analyze", target_id="t1")
        _ev(db, action="findings", target_id="t1")
        events = load_events(db_path=db)
        s = summarize_events(events)
        assert s["warning_flags"] == []

    def test_rollback_present(self, db):
        _ev(db, action="analyze")
        _ev(db, action="rollback")
        events = load_events(db_path=db)
        s = summarize_events(events)
        assert "rollback_present" in s["warning_flags"]

    def test_fail_present(self, db):
        _ev(db, action="analyze", result="error")
        events = load_events(db_path=db)
        s = summarize_events(events)
        assert "fail_present" in s["warning_flags"]

    def test_approve_then_fail_same_target(self, db):
        _ev(db, action="confirm_yes", target_id="t1", result="ok")
        _ev(db, action="clamp",       target_id="t1", result="error")
        events = load_events(db_path=db)
        s = summarize_events(events)
        flags = s["warning_flags"]
        assert any("approve_then_fail_same_target" in f for f in flags)

    def test_approve_then_fail_different_targets_no_flag(self, db):
        _ev(db, action="confirm_yes", target_id="t1", result="ok")
        _ev(db, action="clamp",       target_id="t2", result="error")
        events = load_events(db_path=db)
        s = summarize_events(events)
        flags = s["warning_flags"]
        assert not any("approve_then_fail_same_target" in f for f in flags)

    def test_approve_before_fail_order_matters(self, db):
        # error before confirm_yes should NOT trigger the flag
        _ev(db, action="clamp",       target_id="t1", result="error")
        _ev(db, action="confirm_yes", target_id="t1", result="ok")
        events = load_events(db_path=db)
        s = summarize_events(events)
        flags = s["warning_flags"]
        assert not any("approve_then_fail_same_target" in f for f in flags)

    def test_repeated_action_same_target_triggers_at_three(self, db):
        for _ in range(3):
            _ev(db, action="analyze", target_id="t1")
        events = load_events(db_path=db)
        s = summarize_events(events)
        flags = s["warning_flags"]
        assert any("repeated_action_same_target" in f for f in flags)

    def test_repeated_action_below_threshold_no_flag(self, db):
        for _ in range(2):
            _ev(db, action="analyze", target_id="t1")
        events = load_events(db_path=db)
        s = summarize_events(events)
        flags = s["warning_flags"]
        assert not any("repeated_action_same_target" in f for f in flags)

    def test_export_not_final_when_actions_follow(self, db):
        _ev(db, action="analyze")
        _ev(db, action="export")
        _ev(db, action="analyze")    # action after export
        events = load_events(db_path=db)
        s = summarize_events(events)
        assert "export_not_final" in s["warning_flags"]

    def test_export_final_no_flag(self, db):
        _ev(db, action="analyze")
        _ev(db, action="export")     # export is last
        events = load_events(db_path=db)
        s = summarize_events(events)
        assert "export_not_final" not in s["warning_flags"]

    def test_no_export_no_export_flag(self, db):
        _ev(db, action="analyze")
        events = load_events(db_path=db)
        s = summarize_events(events)
        assert "export_not_final" not in s["warning_flags"]


# ---------------------------------------------------------------------------
# render_timeline
# ---------------------------------------------------------------------------

class TestRenderTimeline:

    def test_empty_returns_placeholder(self):
        assert render_timeline([]) == "(no events)"

    def test_output_is_string(self, db):
        _ev(db, action="analyze")
        events = load_events(db_path=db)
        assert isinstance(render_timeline(events), str)

    def test_chronological_order_in_output(self, db):
        _ev(db, action="analyze")
        _ev(db, action="findings")
        _ev(db, action="export")
        events = load_events(db_path=db)
        lines = render_timeline(events).splitlines()
        assert len(lines) == 3
        assert "analyze"  in lines[0]
        assert "findings" in lines[1]
        assert "export"   in lines[2]

    def test_each_line_contains_action_and_result(self, db):
        _ev(db, action="promote_candidate", target_id="abc", result="ok")
        events = load_events(db_path=db)
        line = render_timeline(events)
        assert "promote_candidate" in line
        assert "result=ok" in line

    def test_target_formatted_as_type_colon_id(self, db):
        _ev(db, action="analyze", target_type="session", target_id="abc123")
        events = load_events(db_path=db)
        line = render_timeline(events)
        assert "session:abc123" in line

    def test_missing_target_renders_dash(self, db):
        _ev(db, action="analyze")
        events = load_events(db_path=db)
        line = render_timeline(events)
        assert "target=-" in line

    def test_one_line_per_event(self, db):
        for i in range(7):
            _ev(db, action="a" + str(i))
        events = load_events(db_path=db)
        lines = render_timeline(events).splitlines()
        assert len(lines) == 7


# ---------------------------------------------------------------------------
# render_markdown_report
# ---------------------------------------------------------------------------

class TestRenderMarkdownReport:

    def test_returns_string(self, db):
        _ev(db, action="analyze")
        events = load_events(db_path=db)
        assert isinstance(render_markdown_report(events, "op_test"), str)

    def test_contains_session_id(self, db):
        _ev(db, action="analyze")
        events = load_events(db_path=db)
        report = render_markdown_report(events, "session_20260503_120000")
        assert "session_20260503_120000" in report

    def test_contains_metadata_section(self, db):
        _ev(db, action="analyze")
        events = load_events(db_path=db)
        report = render_markdown_report(events, "op_test")
        assert "## Metadata" in report

    def test_contains_timeline_section(self, db):
        _ev(db, action="analyze")
        events = load_events(db_path=db)
        report = render_markdown_report(events, "op_test")
        assert "## Timeline" in report

    def test_contains_summary_section(self, db):
        _ev(db, action="analyze")
        events = load_events(db_path=db)
        report = render_markdown_report(events, "op_test")
        assert "## Summary" in report

    def test_contains_invariant_findings_section(self, db):
        _ev(db, action="analyze")
        events = load_events(db_path=db)
        report = render_markdown_report(events, "op_test")
        assert "## Invariant Findings" in report

    def test_clean_session_shows_pass(self, db):
        _ev(db, action="analyze", target_id="t1")
        events = load_events(db_path=db)
        report = render_markdown_report(events, "op_test")
        assert "PASS no warnings" in report

    def test_warning_shows_warn_prefix(self, db):
        _ev(db, action="analyze")
        _ev(db, action="rollback")
        events = load_events(db_path=db)
        report = render_markdown_report(events, "op_test")
        assert "WARN rollback_present" in report

    def test_action_appears_in_timeline_table(self, db):
        _ev(db, action="promote_candidate", target_id="abc")
        events = load_events(db_path=db)
        report = render_markdown_report(events, "op_test")
        assert "promote_candidate" in report

    def test_empty_events_renders_without_error(self):
        report = render_markdown_report([], "op_test")
        assert "## Metadata" in report
        assert "op_test" in report

    def test_approve_then_fail_appears_in_report(self, db):
        _ev(db, action="confirm_yes", target_id="t1", result="ok")
        _ev(db, action="clamp",       target_id="t1", result="error")
        events = load_events(db_path=db)
        report = render_markdown_report(events, "op_test")
        assert "approve_then_fail_same_target" in report

    def test_export_not_final_appears_in_report(self, db):
        _ev(db, action="export")
        _ev(db, action="analyze")
        events = load_events(db_path=db)
        report = render_markdown_report(events, "op_test")
        assert "export_not_final" in report


# ---------------------------------------------------------------------------
# write_markdown_report
# ---------------------------------------------------------------------------

class TestWriteMarkdownReport:

    def test_creates_file(self, db, tmp_path):
        _ev(db, action="analyze")
        events = load_events(db_path=db)
        out = write_markdown_report(events, "op_test", tmp_path)
        assert out.exists()

    def test_filename_format(self, db, tmp_path):
        _ev(db, action="analyze")
        events = load_events(db_path=db)
        out = write_markdown_report(events, "op_test", tmp_path)
        assert out.name == "session_op_test_report.md"

    def test_creates_exports_dir_if_missing(self, tmp_path):
        exports = tmp_path / "deep" / "exports"
        assert not exports.exists()
        out = write_markdown_report([], "op_test", exports)
        assert exports.exists()

    def test_file_content_is_valid_markdown(self, db, tmp_path):
        _ev(db, action="analyze")
        events = load_events(db_path=db)
        out = write_markdown_report(events, "op_test", tmp_path)
        content = out.read_text(encoding="utf-8")
        assert content.startswith("# Operator Session Report")
        assert "## Metadata" in content

    def test_returns_path_object(self, db, tmp_path):
        _ev(db, action="analyze")
        events = load_events(db_path=db)
        out = write_markdown_report(events, "op_test", tmp_path)
        assert isinstance(out, Path)
