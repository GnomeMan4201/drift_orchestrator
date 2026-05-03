#!/usr/bin/env python3
"""
tests/test_controlplane_cli_smoke.py

End-to-end smoke tests for `python3 -m controlplane.cli smoke`.
Verifies the full control-plane pipeline without launching Textual:
    journal write → invariant evaluation → JSONL export → Markdown report

Run with:
    pytest tests/test_controlplane_cli_smoke.py -v
"""

from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

import pytest


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

CLI = [sys.executable, "-m", "controlplane.cli"]


def run_smoke(tmp_path: Path) -> subprocess.CompletedProcess:
    journal = tmp_path / "journal.db"
    exports = tmp_path / "exports"
    return subprocess.run(
        CLI + ["--journal", str(journal), "--exports", str(exports), "smoke"],
        capture_output=True,
        text=True,
    )


def smoke_session_id(stdout: str) -> str:
    """Extract the smoke session id from stdout."""
    for line in stdout.splitlines():
        if line.startswith("smoke session:"):
            return line.split(":", 1)[1].strip()
    return ""


# ---------------------------------------------------------------------------
# Basic exit / structure
# ---------------------------------------------------------------------------

class TestSmokeBasic:

    def test_smoke_exits_zero(self, tmp_path):
        result = run_smoke(tmp_path)
        assert result.returncode == 0, result.stderr

    def test_smoke_help_exits_zero(self):
        result = subprocess.run(CLI + ["smoke", "--help"],
                                capture_output=True, text=True)
        assert result.returncode == 0

    def test_smoke_produces_output(self, tmp_path):
        result = run_smoke(tmp_path)
        assert len(result.stdout.strip()) > 0

    def test_smoke_no_stderr(self, tmp_path):
        result = run_smoke(tmp_path)
        assert result.stderr == "", "unexpected stderr: " + result.stderr


# ---------------------------------------------------------------------------
# Session identity
# ---------------------------------------------------------------------------

class TestSmokeSessionId:

    def test_stdout_contains_smoke_prefix(self, tmp_path):
        result = run_smoke(tmp_path)
        assert "smoke_" in result.stdout

    def test_session_id_has_timestamp_format(self, tmp_path):
        result = run_smoke(tmp_path)
        sid = smoke_session_id(result.stdout)
        assert sid.startswith("smoke_"), f"unexpected session id: {sid}"
        # smoke_YYYYMMDD_HHMMSS — 6 digit date, underscore, 6 digit time
        parts = sid[len("smoke_"):].split("_")
        assert len(parts) == 2
        assert parts[0].isdigit() and len(parts[0]) == 8
        assert parts[1].isdigit() and len(parts[1]) == 6

    def test_session_id_in_stdout(self, tmp_path):
        result = run_smoke(tmp_path)
        sid = smoke_session_id(result.stdout)
        assert sid != "", "could not extract session id from stdout"
        # session id should appear more than once (in paths too)
        assert result.stdout.count(sid) >= 2


# ---------------------------------------------------------------------------
# Status output
# ---------------------------------------------------------------------------

class TestSmokeStatus:

    def test_stdout_contains_status(self, tmp_path):
        result = run_smoke(tmp_path)
        assert "STATUS:" in result.stdout

    def test_smoke_session_is_clean_pass(self, tmp_path):
        result = run_smoke(tmp_path)
        assert "STATUS: PASS" in result.stdout

    def test_stdout_contains_pass_confirmation(self, tmp_path):
        result = run_smoke(tmp_path)
        assert "smoke PASS" in result.stdout

    def test_stdout_mentions_events_written(self, tmp_path):
        result = run_smoke(tmp_path)
        assert "events written:" in result.stdout

    def test_stdout_mentions_events_loaded(self, tmp_path):
        result = run_smoke(tmp_path)
        assert "events loaded:" in result.stdout

    def test_four_events_written_and_loaded(self, tmp_path):
        result = run_smoke(tmp_path)
        assert "events written:  4" in result.stdout or "events written: 4" in result.stdout
        assert "events loaded:   4" in result.stdout or "events loaded:  4" in result.stdout


# ---------------------------------------------------------------------------
# JSONL export
# ---------------------------------------------------------------------------

class TestSmokeJsonlExport:

    def test_jsonl_file_exists(self, tmp_path):
        result = run_smoke(tmp_path)
        sid = smoke_session_id(result.stdout)
        exports = tmp_path / "exports"
        out = exports / ("action_log_" + sid + ".jsonl")
        assert out.exists(), f"JSONL not found at {out}"

    def test_jsonl_path_in_stdout(self, tmp_path):
        result = run_smoke(tmp_path)
        assert "action_log_" in result.stdout
        assert ".jsonl" in result.stdout

    def test_jsonl_line_count(self, tmp_path):
        result = run_smoke(tmp_path)
        sid = smoke_session_id(result.stdout)
        exports = tmp_path / "exports"
        out = exports / ("action_log_" + sid + ".jsonl")
        lines = out.read_text(encoding="utf-8").strip().splitlines()
        assert len(lines) == 4

    def test_jsonl_lines_are_valid_json(self, tmp_path):
        result = run_smoke(tmp_path)
        sid = smoke_session_id(result.stdout)
        exports = tmp_path / "exports"
        out = exports / ("action_log_" + sid + ".jsonl")
        for line in out.read_text(encoding="utf-8").strip().splitlines():
            obj = json.loads(line)
            assert "action" in obj
            assert "ts" in obj
            assert "session_id" in obj

    def test_jsonl_session_ids_match(self, tmp_path):
        result = run_smoke(tmp_path)
        sid = smoke_session_id(result.stdout)
        exports = tmp_path / "exports"
        out = exports / ("action_log_" + sid + ".jsonl")
        for line in out.read_text(encoding="utf-8").strip().splitlines():
            obj = json.loads(line)
            assert obj["session_id"] == sid

    def test_jsonl_contains_analyze_action(self, tmp_path):
        result = run_smoke(tmp_path)
        sid = smoke_session_id(result.stdout)
        exports = tmp_path / "exports"
        out = exports / ("action_log_" + sid + ".jsonl")
        actions = [json.loads(l)["action"] for l in
                   out.read_text().strip().splitlines()]
        assert "analyze" in actions

    def test_jsonl_contains_promote_candidate(self, tmp_path):
        result = run_smoke(tmp_path)
        sid = smoke_session_id(result.stdout)
        exports = tmp_path / "exports"
        out = exports / ("action_log_" + sid + ".jsonl")
        actions = [json.loads(l)["action"] for l in
                   out.read_text().strip().splitlines()]
        assert "promote_candidate" in actions

    def test_jsonl_contains_export_action(self, tmp_path):
        result = run_smoke(tmp_path)
        sid = smoke_session_id(result.stdout)
        exports = tmp_path / "exports"
        out = exports / ("action_log_" + sid + ".jsonl")
        actions = [json.loads(l)["action"] for l in
                   out.read_text().strip().splitlines()]
        assert "export" in actions

    def test_jsonl_is_chronological(self, tmp_path):
        result = run_smoke(tmp_path)
        sid = smoke_session_id(result.stdout)
        exports = tmp_path / "exports"
        out = exports / ("action_log_" + sid + ".jsonl")
        actions = [json.loads(l)["action"] for l in
                   out.read_text().strip().splitlines()]
        assert actions[0] == "analyze"
        assert actions[-1] == "export"


# ---------------------------------------------------------------------------
# Markdown report
# ---------------------------------------------------------------------------

class TestSmokeMarkdownReport:

    def test_report_file_exists(self, tmp_path):
        result = run_smoke(tmp_path)
        sid = smoke_session_id(result.stdout)
        exports = tmp_path / "exports"
        report = exports / ("session_" + sid + "_report.md")
        assert report.exists(), f"report not found at {report}"

    def test_report_path_in_stdout(self, tmp_path):
        result = run_smoke(tmp_path)
        assert "_report.md" in result.stdout

    def test_report_contains_session_id(self, tmp_path):
        result = run_smoke(tmp_path)
        sid = smoke_session_id(result.stdout)
        exports = tmp_path / "exports"
        report = exports / ("session_" + sid + "_report.md")
        content = report.read_text(encoding="utf-8")
        assert sid in content

    def test_report_is_valid_markdown(self, tmp_path):
        result = run_smoke(tmp_path)
        sid = smoke_session_id(result.stdout)
        exports = tmp_path / "exports"
        report = exports / ("session_" + sid + "_report.md")
        content = report.read_text(encoding="utf-8")
        assert "# Operator Session Report" in content
        assert "## Metadata" in content
        assert "## Timeline" in content
        assert "## Invariant Findings" in content

    def test_report_shows_pass(self, tmp_path):
        result = run_smoke(tmp_path)
        sid = smoke_session_id(result.stdout)
        exports = tmp_path / "exports"
        report = exports / ("session_" + sid + "_report.md")
        content = report.read_text(encoding="utf-8")
        assert "PASS" in content

    def test_report_contains_all_actions(self, tmp_path):
        result = run_smoke(tmp_path)
        sid = smoke_session_id(result.stdout)
        exports = tmp_path / "exports"
        report = exports / ("session_" + sid + "_report.md")
        content = report.read_text(encoding="utf-8")
        for action in ("analyze", "confirm_yes", "promote_candidate", "export"):
            assert action in content, f"action '{action}' missing from report"


# ---------------------------------------------------------------------------
# Textual boundary
# ---------------------------------------------------------------------------

class TestSmokeTextualBoundary:

    def test_smoke_does_not_import_textual(self, tmp_path):
        # Run smoke in a subprocess and inspect which modules were imported
        journal = tmp_path / "journal.db"
        exports = tmp_path / "exports"
        script = (
            "import sys; "
            "import runpy; "
            "runpy.run_module('controlplane.cli', run_name='__main__', "
            "alter_sys=True); "
        )
        result = subprocess.run(
            [sys.executable, "-c",
             "import sys; from controlplane import cli; "
             "cli.main(['--journal', sys.argv[1], '--exports', sys.argv[2], 'smoke']); "
             "textual_mods = [k for k in sys.modules if 'textual' in k]; "
             "print('TEXTUAL_MODS:' + str(textual_mods))",
             str(journal), str(exports)],
            capture_output=True, text=True,
        )
        assert result.returncode == 0, result.stderr
        assert "TEXTUAL_MODS:[]" in result.stdout, (
            "Textual was imported during smoke: " + result.stdout
        )

    def test_cli_source_has_no_textual_import(self):
        src = Path(__file__).parent.parent / "controlplane" / "cli.py"
        import_lines = [
            l for l in src.read_text().splitlines()
            if "import" in l and "textual" in l.lower()
        ]
        assert not import_lines, "cli.py imports Textual: " + str(import_lines)


# ---------------------------------------------------------------------------
# Idempotence — two smoke runs do not interfere
# ---------------------------------------------------------------------------

class TestSmokeIdempotence:

    def test_two_smoke_runs_produce_distinct_session_ids(self, tmp_path):
        import time
        r1 = run_smoke(tmp_path)
        time.sleep(1)      # ensure timestamp differs
        r2 = run_smoke(tmp_path)
        sid1 = smoke_session_id(r1.stdout)
        sid2 = smoke_session_id(r2.stdout)
        assert sid1 != sid2, "two smoke runs produced identical session ids"

    def test_two_smoke_runs_both_exit_zero(self, tmp_path):
        import time
        r1 = run_smoke(tmp_path)
        time.sleep(1)
        r2 = run_smoke(tmp_path)
        assert r1.returncode == 0
        assert r2.returncode == 0

    def test_second_smoke_run_writes_new_files(self, tmp_path):
        import time
        run_smoke(tmp_path)
        time.sleep(1)
        r2 = run_smoke(tmp_path)
        sid2 = smoke_session_id(r2.stdout)
        exports = tmp_path / "exports"
        jsonl = exports / ("action_log_" + sid2 + ".jsonl")
        report = exports / ("session_" + sid2 + "_report.md")
        assert jsonl.exists()
        assert report.exists()
