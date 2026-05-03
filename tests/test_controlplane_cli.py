#!/usr/bin/env python3
"""
tests/test_controlplane_cli.py

Tests for controlplane.cli — the headless CLI operator surface.
Uses subprocess for black-box invocation and direct imports for unit tests.
No drift.db or Textual required.

Run with:
    pytest tests/test_controlplane_cli.py -v
"""

from __future__ import annotations

import json
import sqlite3
import subprocess
import sys
from pathlib import Path

import pytest

from controlplane import cli as cli_module
from controlplane.cli import (
    _cell,
    _print_table,
    _short,
    build_parser,
    cmd_export,
    cmd_invariants,
    cmd_list,
    cmd_replay,
    cmd_report,
    main,
)
from controlplane.journal import append_event, init_db


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

CLI_ARGV_PREFIX = [sys.executable, "-m", "controlplane.cli"]


def run_cli(*args: str, cwd: str | None = None) -> subprocess.CompletedProcess:
    """Run the CLI as a subprocess and return the result."""
    return subprocess.run(
        CLI_ARGV_PREFIX + list(args),
        capture_output=True,
        text=True,
        cwd=cwd,
    )


def make_journal(tmp_path: Path) -> Path:
    """Create a populated journal.db for testing."""
    db = tmp_path / "journal.db"
    init_db(db)
    append_event(
        session_id="session_20260503_181201",
        action="analyze",
        target_type="session",
        target_id="abc12345",
        target_summary="control_set alpha=0.3180 action=CONTINUE",
        result="ok",
        db_path=db,
    )
    append_event(
        session_id="session_20260503_181201",
        action="rollback",
        target_type="session",
        target_id="abc12345",
        result="ok",
        db_path=db,
    )
    append_event(
        session_id="session_20260503_181201",
        action="export",
        result="ok",
        db_path=db,
    )
    return db


def make_minimal_drift_db(tmp_path: Path) -> Path:
    """Create a minimal drift.db with one session for list command testing."""
    db = tmp_path / "drift.db"
    conn = sqlite3.connect(str(db))
    conn.executescript("""
        CREATE TABLE sessions (id TEXT PRIMARY KEY, session_label TEXT, created_at TEXT);
        CREATE TABLE turn_metrics (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            session_id TEXT, alpha REAL, d_anchor REAL, d_goal REAL,
            rho_density REAL, repetition_score REAL, created_at TEXT);
        CREATE TABLE policy_events (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            session_id TEXT, action TEXT, reason TEXT, created_at TEXT);
        CREATE TABLE turns (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            session_id TEXT, token_count INTEGER, created_at TEXT);
        CREATE TABLE findings (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            session_id TEXT, severity TEXT, finding_type TEXT,
            detail TEXT, created_at TEXT);
    """)
    conn.execute("INSERT INTO sessions VALUES (?, ?, ?)",
                 ("abc12345-test", "test_session", "2026-05-03T08:00:00"))
    conn.execute(
        "INSERT INTO turn_metrics (session_id, alpha, d_anchor, d_goal, rho_density, repetition_score, created_at) VALUES (?, ?, ?, ?, ?, ?, ?)",
        ("abc12345-test", 0.32, 0.46, 0.23, 0.55, 0.66, "2026-05-03T08:01:00"))
    conn.execute(
        "INSERT INTO policy_events (session_id, action, reason, created_at) VALUES (?, ?, ?, ?)",
        ("abc12345-test", "CONTINUE", "ok", "2026-05-03T08:01:01"))
    conn.execute("INSERT INTO turns VALUES (NULL, ?, ?, ?)",
                 ("abc12345-test", 72, "2026-05-03T08:01:00"))
    conn.commit()
    conn.close()
    return db


# ---------------------------------------------------------------------------
# Module-level checks
# ---------------------------------------------------------------------------

class TestModuleProperties:

    def test_module_imports_without_error(self):
        import controlplane.cli  # noqa: F401

    def test_no_textual_in_cli_module_source(self):
        src = Path(cli_module.__file__).read_text(encoding="utf-8")
        # Check for import statements only, not doc prose
        import_lines = [l for l in src.splitlines()
                        if "import" in l and "textual" in l.lower()]
        assert not import_lines, (
            "cli.py must not import Textual: " + str(import_lines)
        )

    def test_no_textual_imported_after_cli_import(self):
        textual_keys = [k for k in sys.modules if k.startswith("textual")]
        assert not textual_keys, (
            "Textual was imported as a side effect of importing controlplane.cli"
        )

    def test_cli_has_main_function(self):
        assert callable(cli_module.main)

    def test_cli_has_build_parser(self):
        assert callable(cli_module.build_parser)

    def test_all_commands_registered(self):
        assert set(cli_module._COMMANDS.keys()) == {
            "list", "replay", "report", "invariants", "export", "smoke"
        }


# ---------------------------------------------------------------------------
# Subprocess: --help
# ---------------------------------------------------------------------------

class TestHelp:

    def test_help_exits_zero(self):
        result = run_cli("--help")
        assert result.returncode == 0

    def test_help_mentions_commands(self):
        result = run_cli("--help")
        for cmd in ("list", "replay", "report", "invariants", "export", "smoke"):
            assert cmd in result.stdout

    def test_list_help_exits_zero(self):
        result = run_cli("list", "--help")
        assert result.returncode == 0

    def test_replay_help_exits_zero(self):
        result = run_cli("replay", "--help")
        assert result.returncode == 0

    def test_report_help_exits_zero(self):
        result = run_cli("report", "--help")
        assert result.returncode == 0

    def test_invariants_help_exits_zero(self):
        result = run_cli("invariants", "--help")
        assert result.returncode == 0

    def test_export_help_exits_zero(self):
        result = run_cli("export", "--help")
        assert result.returncode == 0


# ---------------------------------------------------------------------------
# Subprocess: list command
# ---------------------------------------------------------------------------

class TestListCommand:

    def test_list_missing_db_exits_zero(self, tmp_path):
        result = run_cli("--db", str(tmp_path / "missing.db"), "list")
        assert result.returncode == 0

    def test_list_missing_db_prints_message(self, tmp_path):
        result = run_cli("--db", str(tmp_path / "missing.db"), "list")
        assert "not found" in result.stdout or "no sessions" in result.stdout

    def test_list_with_sessions(self, tmp_path):
        db = make_minimal_drift_db(tmp_path)
        result = run_cli("--db", str(db), "list")
        assert result.returncode == 0
        assert "test_session" in result.stdout

    def test_list_shows_alpha(self, tmp_path):
        db = make_minimal_drift_db(tmp_path)
        result = run_cli("--db", str(db), "list")
        assert "0.32" in result.stdout

    def test_list_shows_action(self, tmp_path):
        db = make_minimal_drift_db(tmp_path)
        result = run_cli("--db", str(db), "list")
        assert "CONTINUE" in result.stdout

    def test_list_shows_session_count(self, tmp_path):
        db = make_minimal_drift_db(tmp_path)
        result = run_cli("--db", str(db), "list")
        assert "session" in result.stdout.lower()


# ---------------------------------------------------------------------------
# Subprocess: replay command
# ---------------------------------------------------------------------------

class TestReplayCommand:

    def test_replay_missing_session_exits_nonzero(self, tmp_path):
        journal_db = tmp_path / "j.db"
        init_db(journal_db)
        result = run_cli("--journal", str(journal_db), "replay", "--session", "session_missing")
        assert result.returncode != 0

    def test_replay_missing_session_prints_message(self, tmp_path):
        journal_db = tmp_path / "j.db"
        init_db(journal_db)
        result = run_cli("--journal", str(journal_db), "replay", "--session", "session_missing")
        assert "no events" in result.stdout

    def test_replay_with_events_exits_zero(self, tmp_path):
        journal_db = make_journal(tmp_path)
        result = run_cli("--journal", str(journal_db), "replay", "--session", "session_20260503_181201")
        assert result.returncode == 0

    def test_replay_shows_actions(self, tmp_path):
        journal_db = make_journal(tmp_path)
        result = run_cli("--journal", str(journal_db), "replay", "--session", "session_20260503_181201")
        assert "analyze" in result.stdout
        assert "rollback" in result.stdout
        assert "export" in result.stdout

    def test_replay_shows_event_count(self, tmp_path):
        journal_db = make_journal(tmp_path)
        result = run_cli("--journal", str(journal_db), "replay", "--session", "session_20260503_181201")
        assert "3" in result.stdout

    def test_replay_shows_target_ids(self, tmp_path):
        journal_db = make_journal(tmp_path)
        result = run_cli("--journal", str(journal_db), "replay", "--session", "session_20260503_181201")
        assert "abc12345" in result.stdout

    def test_replay_requires_session_flag(self):
        result = run_cli("replay")
        assert result.returncode != 0


# ---------------------------------------------------------------------------
# Subprocess: report command
# ---------------------------------------------------------------------------

class TestReportCommand:

    def test_report_missing_session_exits_nonzero(self, tmp_path):
        journal_db = tmp_path / "j.db"
        init_db(journal_db)
        result = run_cli("--journal", str(journal_db), "--exports", str(tmp_path / "exports"),
                "report", "--session", "session_missing")
        assert result.returncode != 0

    def test_report_writes_file(self, tmp_path):
        journal_db = make_journal(tmp_path)
        exports = tmp_path / "exports"
        result = run_cli("--journal", str(journal_db), "--exports", str(exports),
                "report", "--session", "session_20260503_181201")
        assert result.returncode == 0
        report_file = exports / "session_session_20260503_181201_report.md"
        assert report_file.exists()

    def test_report_output_mentions_path(self, tmp_path):
        journal_db = make_journal(tmp_path)
        exports = tmp_path / "exports"
        result = run_cli("--journal", str(journal_db), "--exports", str(exports),
                "report", "--session", "session_20260503_181201")
        assert "report written" in result.stdout

    def test_report_content_is_markdown(self, tmp_path):
        journal_db = make_journal(tmp_path)
        exports = tmp_path / "exports"
        run_cli("--journal", str(journal_db), "--exports", str(exports),
                "report", "--session", "session_20260503_181201")
        report_file = exports / "session_session_20260503_181201_report.md"
        content = report_file.read_text()
        assert "# Operator Session Report" in content
        assert "## Timeline" in content

    def test_report_requires_session_flag(self):
        result = run_cli("report")
        assert result.returncode != 0


# ---------------------------------------------------------------------------
# Subprocess: invariants command
# ---------------------------------------------------------------------------

class TestInvariantsCommand:

    def test_invariants_no_events_exits_zero(self, tmp_path):
        journal_db = tmp_path / "j.db"
        init_db(journal_db)
        result = run_cli("--journal", str(journal_db), "invariants", "--session", "session_missing")
        assert result.returncode == 0

    def test_invariants_no_events_prints_pass(self, tmp_path):
        journal_db = tmp_path / "j.db"
        init_db(journal_db)
        result = run_cli("--journal", str(journal_db), "invariants", "--session", "session_missing")
        assert "PASS" in result.stdout or "no events" in result.stdout

    def test_invariants_with_clean_session_shows_pass(self, tmp_path):
        journal_db = tmp_path / "j.db"
        init_db(journal_db)
        append_event(session_id="op_clean", action="analyze",
                     target_id="t1", result="ok", db_path=journal_db)
        append_event(session_id="op_clean", action="export",
                     result="ok", db_path=journal_db)
        result = run_cli("--journal", str(journal_db), "invariants", "--session", "op_clean")
        assert result.returncode == 0
        assert "PASS" in result.stdout

    def test_invariants_with_rollback_shows_warn(self, tmp_path):
        journal_db = make_journal(tmp_path)
        result = run_cli("--journal", str(journal_db), "invariants", "--session", "session_20260503_181201")
        assert result.returncode == 0
        assert "WARN" in result.stdout
        assert "rollback" in result.stdout.lower()

    def test_invariants_shows_session_id(self, tmp_path):
        journal_db = make_journal(tmp_path)
        result = run_cli("--journal", str(journal_db), "invariants", "--session", "session_20260503_181201")
        assert "session_20260503_181201" in result.stdout

    def test_invariants_shows_event_count(self, tmp_path):
        journal_db = make_journal(tmp_path)
        result = run_cli("--journal", str(journal_db), "invariants", "--session", "session_20260503_181201")
        assert "3" in result.stdout

    def test_invariants_requires_session_flag(self):
        result = run_cli("invariants")
        assert result.returncode != 0


# ---------------------------------------------------------------------------
# Subprocess: export command
# ---------------------------------------------------------------------------

class TestExportCommand:

    def test_export_missing_session_exits_nonzero(self, tmp_path):
        journal_db = tmp_path / "j.db"
        init_db(journal_db)
        result = run_cli("--journal", str(journal_db), "--exports", str(tmp_path / "exports"),
                "export", "--session", "session_missing")
        assert result.returncode != 0

    def test_export_with_events_exits_zero(self, tmp_path):
        journal_db = make_journal(tmp_path)
        exports = tmp_path / "exports"
        result = run_cli("--journal", str(journal_db), "--exports", str(exports),
                "export", "--session", "session_20260503_181201")
        assert result.returncode == 0

    def test_export_creates_jsonl_file(self, tmp_path):
        journal_db = make_journal(tmp_path)
        exports = tmp_path / "exports"
        run_cli("--journal", str(journal_db), "--exports", str(exports),
                "export", "--session", "session_20260503_181201")
        out = exports / "action_log_session_20260503_181201.jsonl"
        assert out.exists()

    def test_export_jsonl_is_valid(self, tmp_path):
        journal_db = make_journal(tmp_path)
        exports = tmp_path / "exports"
        run_cli("--journal", str(journal_db), "--exports", str(exports),
                "export", "--session", "session_20260503_181201")
        out = exports / "action_log_session_20260503_181201.jsonl"
        lines = out.read_text().strip().splitlines()
        assert len(lines) == 3
        for line in lines:
            obj = json.loads(line)
            assert "action" in obj
            assert "ts" in obj

    def test_export_shows_event_count(self, tmp_path):
        journal_db = make_journal(tmp_path)
        exports = tmp_path / "exports"
        result = run_cli("--journal", str(journal_db), "--exports", str(exports),
                "export", "--session", "session_20260503_181201")
        assert "3" in result.stdout

    def test_export_requires_session_flag(self):
        result = run_cli("export")
        assert result.returncode != 0


# ---------------------------------------------------------------------------
# Direct unit tests — main() function
# ---------------------------------------------------------------------------

class TestMainFunction:

    def test_main_returns_int(self, tmp_path):
        journal_db = tmp_path / "j.db"
        init_db(journal_db)
        rc = main(["--db", str(tmp_path / "missing.db"), "list"])
        assert isinstance(rc, int)

    def test_main_help_raises_systemexit_zero(self):
        with pytest.raises(SystemExit) as exc:
            main(["--help"])
        assert exc.value.code == 0

    def test_main_invalid_command_raises_systemexit(self):
        with pytest.raises(SystemExit):
            main(["doesnotexist"])

    def test_main_invariants_empty_session(self, tmp_path):
        journal_db = tmp_path / "j.db"
        init_db(journal_db)
        rc = main(["--journal", str(journal_db), "invariants", "--session", "missing"])
        assert rc == 0

    def test_main_replay_missing_exits_one(self, tmp_path):
        journal_db = tmp_path / "j.db"
        init_db(journal_db)
        rc = main(["--journal", str(journal_db), "replay", "--session", "missing"])
        assert rc == 1

    def test_main_export_missing_exits_one(self, tmp_path):
        journal_db = tmp_path / "j.db"
        init_db(journal_db)
        rc = main(["--journal", str(journal_db), "--exports", str(tmp_path / "exports"),
                   "export", "--session", "missing"])
        assert rc == 1


# ---------------------------------------------------------------------------
# Helper function unit tests
# ---------------------------------------------------------------------------

class TestHelperFunctions:

    def test_short_truncates(self):
        assert _short("abcdefghijklmnop", 8) == "abcdefgh"

    def test_short_handles_empty(self):
        assert _short("", 8) == ""

    def test_cell_pads_short_string(self):
        result = _cell("abc", 10)
        assert result == "abc       "
        assert len(result) == 10

    def test_cell_truncates_long_string_with_tilde(self):
        result = _cell("abcdefghij", 8)
        assert len(result) == 8
        assert result.endswith("~")

    def test_cell_exact_fit(self):
        result = _cell("abcde", 5)
        assert result == "abcde"
        assert len(result) == 5

    def test_print_table_runs_without_error(self, capsys):
        _print_table(
            ["A", "B"],
            [10, 10],
            [["hello", "world"], ["foo", "bar"]],
        )
        out = capsys.readouterr().out
        assert "hello" in out
        assert "world" in out
        assert "A" in out


# ---------------------------------------------------------------------------
# build_parser tests
# ---------------------------------------------------------------------------

class TestBuildParser:

    def test_returns_parser(self):
        p = build_parser()
        assert p is not None

    def test_list_subcommand_parses(self):
        p = build_parser()
        args = p.parse_args(["list"])
        assert args.command == "list"

    def test_replay_requires_session(self):
        p = build_parser()
        with pytest.raises(SystemExit):
            p.parse_args(["replay"])

    def test_replay_parses_session(self):
        p = build_parser()
        args = p.parse_args(["replay", "--session", "session_20260503_181201"])
        assert args.session == "session_20260503_181201"

    def test_report_parses_session(self):
        p = build_parser()
        args = p.parse_args(["report", "--session", "s1"])
        assert args.session == "s1"

    def test_invariants_parses_session(self):
        p = build_parser()
        args = p.parse_args(["invariants", "--session", "s1"])
        assert args.session == "s1"

    def test_export_parses_session(self):
        p = build_parser()
        args = p.parse_args(["export", "--session", "s1"])
        assert args.session == "s1"

    def test_db_default(self):
        p = build_parser()
        args = p.parse_args(["list"])
        assert isinstance(args.db, Path)

    def test_custom_db_path(self):
        p = build_parser()
        args = p.parse_args(["--db", "/tmp/test.db", "list"])
        assert args.db == Path("/tmp/test.db")

    def test_exports_default(self):
        p = build_parser()
        args = p.parse_args(["list"])
        assert isinstance(args.exports, Path)
