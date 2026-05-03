#!/usr/bin/env python3
"""
tests/test_controlplane_status_formatting.py

Pure unit tests for select_highest_severity_finding and format_invariant_status.
No DB.  No TUI.  No side effects.

Run with:
    pytest tests/test_controlplane_status_formatting.py -v
"""

from __future__ import annotations

import pytest

from controlplane.invariants import (
    Finding,
    _PASS,
    format_invariant_status,
    select_highest_severity_finding,
)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def f(severity: str, code: str = "test_code", message: str = "test message") -> Finding:
    return Finding(severity=severity, code=code, message=message)


# ---------------------------------------------------------------------------
# select_highest_severity_finding
# ---------------------------------------------------------------------------

class TestSelectHighestSeverityFinding:

    def test_empty_list_returns_pass(self):
        result = select_highest_severity_finding([])
        assert result.severity == "pass"

    def test_single_pass_returns_it(self):
        p = f("pass", "clean_session")
        assert select_highest_severity_finding([p]) is p

    def test_single_warn_returns_it(self):
        w = f("warn", "rollback_present")
        assert select_highest_severity_finding([w]) is w

    def test_single_fail_returns_it(self):
        fail = f("fail", "critical_error")
        assert select_highest_severity_finding([fail]) is fail

    def test_warn_beats_pass(self):
        p = f("pass")
        w = f("warn")
        result = select_highest_severity_finding([p, w])
        assert result.severity == "warn"

    def test_fail_beats_warn(self):
        w = f("warn")
        fail = f("fail")
        result = select_highest_severity_finding([w, fail])
        assert result.severity == "fail"

    def test_fail_beats_all(self):
        findings = [f("pass"), f("warn"), f("fail"), f("warn"), f("pass")]
        result = select_highest_severity_finding(findings)
        assert result.severity == "fail"

    def test_all_pass_returns_pass(self):
        findings = [f("pass"), f("pass"), f("pass")]
        result = select_highest_severity_finding(findings)
        assert result.severity == "pass"

    def test_all_warn_returns_first_warn(self):
        w1 = f("warn", "rule_a")
        w2 = f("warn", "rule_b")
        result = select_highest_severity_finding([w1, w2])
        assert result.severity == "warn"
        # max is stable on equal keys — first occurrence wins
        assert result.code == "rule_a"

    def test_returns_finding_object_not_string(self):
        result = select_highest_severity_finding([f("warn")])
        assert isinstance(result, Finding)

    def test_canonical_pass_returned_for_empty(self):
        result = select_highest_severity_finding([])
        assert result is _PASS

    def test_preserves_all_finding_fields(self):
        target = Finding(
            severity="warn",
            code="rollback_present",
            message="A rollback occurred.",
            action="rollback",
            target_id="abc123",
            metadata={"k": "v"},
        )
        other = f("pass")
        result = select_highest_severity_finding([other, target])
        assert result is target
        assert result.action == "rollback"
        assert result.target_id == "abc123"
        assert result.metadata == {"k": "v"}

    def test_severity_order_fail_gt_warn_gt_pass(self):
        from controlplane.invariants import _SEVERITY_ORDER
        assert _SEVERITY_ORDER["fail"] > _SEVERITY_ORDER["warn"]
        assert _SEVERITY_ORDER["warn"] > _SEVERITY_ORDER["pass"]

    def test_mixed_order_in_list(self):
        # fail at position 0, warn at position 2
        findings = [f("fail", "f1"), f("pass", "p1"), f("warn", "w1")]
        result = select_highest_severity_finding(findings)
        assert result.severity == "fail"
        assert result.code == "f1"


# ---------------------------------------------------------------------------
# format_invariant_status
# ---------------------------------------------------------------------------

class TestFormatInvariantStatus:

    def test_returns_string(self):
        assert isinstance(format_invariant_status(f("pass")), str)

    def test_pass_contains_PASS(self):
        result = format_invariant_status(f("pass"))
        assert "PASS" in result

    def test_pass_contains_session_evaluated(self):
        result = format_invariant_status(f("pass"))
        assert "session_evaluated" in result

    def test_warn_contains_WARN(self):
        result = format_invariant_status(f("warn", "rollback_present"))
        assert "WARN" in result

    def test_warn_contains_code(self):
        result = format_invariant_status(f("warn", "rollback_present", "msg"))
        assert "rollback_present" in result

    def test_warn_contains_message(self):
        msg = "A rollback action was recorded."
        result = format_invariant_status(f("warn", "rollback_present", msg))
        assert msg in result

    def test_fail_contains_FAIL(self):
        result = format_invariant_status(f("fail", "critical"))
        assert "FAIL" in result

    def test_fail_contains_code(self):
        result = format_invariant_status(f("fail", "critical_error", "msg"))
        assert "critical_error" in result

    def test_warn_uses_yellow_markup(self):
        result = format_invariant_status(f("warn", "rollback_present"))
        assert "yellow" in result

    def test_fail_uses_red_markup(self):
        result = format_invariant_status(f("fail", "critical"))
        assert "red" in result

    def test_pass_does_not_use_yellow_or_red(self):
        result = format_invariant_status(f("pass"))
        assert "yellow" not in result
        assert "red" not in result

    def test_pass_uses_dim_markup(self):
        result = format_invariant_status(f("pass"))
        assert "[dim]" in result

    def test_no_newlines_in_output(self):
        for sev in ("pass", "warn", "fail"):
            result = format_invariant_status(f(sev, "code", "message"))
            assert "\n" not in result, f"Newline found for severity={sev}"

    def test_canonical_pass_finding_formats_cleanly(self):
        result = format_invariant_status(_PASS)
        assert "PASS" in result
        assert "session_evaluated" in result

    def test_real_rollback_finding_formats(self):
        finding = Finding(
            severity="warn",
            code="rollback_present",
            message="A rollback action was recorded in this session.",
            action="rollback",
            target_id="abc12345",
        )
        result = format_invariant_status(finding)
        assert "WARN" in result
        assert "rollback_present" in result
        assert "A rollback action was recorded in this session." in result

    def test_real_approve_then_fail_finding_formats(self):
        finding = Finding(
            severity="warn",
            code="approve_then_fail_same_target",
            message="confirm_yes was followed by result=error on the same target (t1).",
        )
        result = format_invariant_status(finding)
        assert "WARN" in result
        assert "approve_then_fail_same_target" in result

    def test_starts_with_whitespace_for_padding(self):
        # status bar looks better with leading space
        result = format_invariant_status(f("pass"))
        assert result.startswith("  ")

    def test_format_is_single_line_rich_markup(self):
        # must not contain bare unmatched brackets that would break Rich
        result = format_invariant_status(f("warn", "test_code", "test message"))
        # basic bracket balance check
        opens  = result.count("[")
        closes = result.count("]")
        assert opens == closes
