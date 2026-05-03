#!/usr/bin/env python3
"""
controlplane/cli.py

Headless CLI operator surface for the drift_orchestrator control plane.
No Textual dependency.  All output goes to stdout/stderr.

Usage
-----
    python3 -m controlplane.cli --help
    python3 -m controlplane.cli list [--db PATH]
    python3 -m controlplane.cli replay   --session SESSION_ID
    python3 -m controlplane.cli report   --session SESSION_ID [--exports DIR]
    python3 -m controlplane.cli invariants --session SESSION_ID
    python3 -m controlplane.cli export   --session SESSION_ID [--exports DIR]

Global options
    --db PATH        path to drift_orchestrator drift.db
                     (default: ~/research_hub/repos/drift_orchestrator/data/drift.db)
    --journal PATH   path to control-plane journal.db
                     (default: ~/.drift_controlplane/journal.db)
    --exports DIR    output directory for reports and JSONL files
                     (default: ./exports)

Exit codes
    0   success or empty result (not an error)
    1   session not found / bad arguments
    2   unexpected runtime error
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

# ---------------------------------------------------------------------------
# Default paths (mirrors drifttop.py and journal.py defaults)
# ---------------------------------------------------------------------------

DB_DEFAULT      = Path.home() / "research_hub" / "repos" / "drift_orchestrator" / "data" / "drift.db"
JOURNAL_DEFAULT = Path.home() / ".drift_controlplane" / "journal.db"
EXPORTS_DEFAULT = Path("exports")

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _short(s: str, n: int = 16) -> str:
    return s[:n] if s else ""


def _cell(s: str, width: int) -> str:
    s = str(s)
    if len(s) > width:
        return s[:width - 1] + "~"
    return s.ljust(width)


def _print_table(headers: list[str], widths: list[int], rows: list[list[str]]) -> None:
    header_line = "  ".join(_cell(h, w) for h, w in zip(headers, widths))
    sep_line    = "  ".join("-" * w for w in widths)
    print(header_line)
    print(sep_line)
    for row in rows:
        print("  ".join(_cell(str(v), w) for v, w in zip(row, widths)))


# ---------------------------------------------------------------------------
# Command implementations
# ---------------------------------------------------------------------------

def cmd_list(args: argparse.Namespace) -> int:
    """List sessions from drift.db via datasource."""
    from controlplane.datasource import load_sessions

    db = args.db
    if not db.exists():
        print("drift.db not found: " + str(db))
        print("Use --db /path/to/drift.db")
        return 0   # not an error — DB may not exist yet

    sessions = load_sessions(db)
    if not sessions:
        print("no sessions found in " + str(db))
        return 0

    _print_table(
        ["SESSION",  "LABEL",           "ALPHA",  "ACTION",  "TURNS", "STARTED"],
        [16,          18,                 7,        12,         6,       16],
        [
            [
                _short(r.record_id, 16),
                r.title[:18],
                "{:.4f}".format(r.alpha),
                r.policy_action[:12],
                str(r.turn_count),
                r.created_at[:16].replace("T", " "),
            ]
            for r in sessions
        ],
    )
    print("\n" + str(len(sessions)) + " session(s)")
    return 0


def cmd_replay(args: argparse.Namespace) -> int:
    """Print chronological action timeline for a session."""
    from controlplane.replay import load_events, render_timeline

    events = load_events(session_id=args.session, db_path=args.journal)
    if not events:
        print("no events found for session: " + args.session)
        return 1

    print(render_timeline(events))
    print("\n" + str(len(events)) + " event(s)  session=" + args.session)
    return 0


def cmd_report(args: argparse.Namespace) -> int:
    """Write a Markdown report for a session to exports/."""
    from controlplane.replay import load_events, write_markdown_report

    events = load_events(session_id=args.session, db_path=args.journal)
    if not events:
        print("no events found for session: " + args.session)
        return 1

    exports = args.exports
    out = write_markdown_report(events, args.session, exports)
    print("report written: " + str(out))
    return 0


def cmd_invariants(args: argparse.Namespace) -> int:
    """Evaluate and print invariant findings for a session."""
    from controlplane import invariants
    from controlplane.replay import load_events

    events = load_events(session_id=args.session, db_path=args.journal)
    if not events:
        print("no events found for session: " + args.session)
        print("STATUS: PASS  (empty session — no violations possible)")
        return 0

    findings = invariants.check(events)
    violations = [f for f in findings if f.severity in ("warn", "fail")]

    print("session:   " + args.session)
    print("events:    " + str(len(events)))
    print("findings:  " + str(len(findings)))
    print("")

    if not violations:
        print("PASS  clean_session")
        print("  " + findings[0].message)
    else:
        for f in findings:
            if f.severity in ("warn", "fail"):
                prefix = "WARN" if f.severity == "warn" else "FAIL"
                target = (" target=" + str(f.target_id)) if f.target_id else ""
                print(prefix + "  " + f.code + target)
                print("  " + f.message)

    return 0


def cmd_export(args: argparse.Namespace) -> int:
    """Write JSONL action log for a session to exports/."""
    from controlplane.journal import export_jsonl

    session_id = args.session
    exports    = args.exports
    out_name   = "action_log_" + session_id + ".jsonl"
    out_path   = exports / out_name

    count = export_jsonl(out_path, session_id=session_id, db_path=args.journal)
    if count == 0:
        print("no events found for session: " + session_id)
        return 1

    print("exported: " + str(out_path) + "  (" + str(count) + " events)")
    return 0


# ---------------------------------------------------------------------------
# Argument parser
# ---------------------------------------------------------------------------

def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="python3 -m controlplane.cli",
        description="drift_orchestrator control-plane CLI  (no Textual required)",
    )
    parser.add_argument(
        "--db",
        type=Path,
        default=DB_DEFAULT,
        metavar="PATH",
        help="path to drift.db (default: %(default)s)",
    )
    parser.add_argument(
        "--journal",
        type=Path,
        default=JOURNAL_DEFAULT,
        metavar="PATH",
        help="path to journal.db (default: %(default)s)",
    )
    parser.add_argument(
        "--exports",
        type=Path,
        default=EXPORTS_DEFAULT,
        metavar="DIR",
        help="exports output directory (default: %(default)s)",
    )

    sub = parser.add_subparsers(dest="command", metavar="COMMAND")
    sub.required = True

    # list
    sub.add_parser(
        "list",
        help="list sessions from drift.db",
    )

    # replay
    p_replay = sub.add_parser(
        "replay",
        help="print action timeline for a session",
    )
    p_replay.add_argument("--session", required=True, metavar="SESSION_ID")

    # report
    p_report = sub.add_parser(
        "report",
        help="write Markdown report for a session",
    )
    p_report.add_argument("--session", required=True, metavar="SESSION_ID")

    # invariants
    p_inv = sub.add_parser(
        "invariants",
        help="evaluate and print invariant findings for a session",
    )
    p_inv.add_argument("--session", required=True, metavar="SESSION_ID")

    # export
    p_exp = sub.add_parser(
        "export",
        help="write JSONL action log for a session",
    )
    p_exp.add_argument("--session", required=True, metavar="SESSION_ID")

    sub.add_parser("smoke", help="end-to-end pipeline smoke test")

    return parser


# ---------------------------------------------------------------------------
# Entry point
# ---------------------------------------------------------------------------


def cmd_smoke(args):
    """End-to-end pipeline smoke test — no Textual required."""
    import datetime as _dt
    from controlplane import invariants
    from controlplane.journal import append_event, export_jsonl, init_db
    from controlplane.replay import load_events, write_markdown_report

    ts = _dt.datetime.now().strftime("%Y%m%d_%H%M%S")
    session_id = "smoke_" + ts
    journal_path = args.journal
    exports = args.exports

    print("smoke session:  " + session_id)
    print("journal:        " + str(journal_path))
    print("exports:        " + str(exports))
    print("")

    init_db(journal_path)

    events_to_write = [
        dict(action="analyze", target_type="session",
             target_id="smoke_target_001",
             target_summary="smoke_label alpha=0.3180 action=CONTINUE",
             result="ok"),
        dict(action="confirm_yes", result="ok",
             metadata={"confirmed_action": "promote",
                       "session_id": "smoke_target_001"}),
        dict(action="promote_candidate", target_type="session",
             target_id="smoke_target_001",
             target_summary="smoke_label alpha=0.3180 action=CONTINUE",
             result="ok",
             metadata={"candidate_path": "candidates/smoke_target_001.json",
                       "session_id": "smoke_target_001"}),
        dict(action="export", result="ok",
             metadata={"path": str(exports / ("action_log_" + session_id + ".jsonl")),
                       "event_count": 4}),
    ]
    for ev in events_to_write:
        append_event(session_id=session_id, db_path=journal_path, **ev)
    print("events written: " + str(len(events_to_write)))

    events = load_events(session_id=session_id, db_path=journal_path)
    print("events loaded:  " + str(len(events)))
    print("")

    findings = invariants.check(events)
    top = invariants.select_highest_severity_finding(findings)
    print("STATUS: " + top.severity.upper() + "  " + top.code + "  " + top.message)
    print("")

    jsonl_path = exports / ("action_log_" + session_id + ".jsonl")
    count = export_jsonl(jsonl_path, session_id=session_id, db_path=journal_path)
    print("JSONL export:   " + str(jsonl_path) + "  (" + str(count) + " events)")

    report_path = write_markdown_report(events, session_id, exports)
    print("report:         " + str(report_path))
    print("")
    print("smoke PASS  — full pipeline exercised")
    return 0


_COMMANDS = {
    "list":       cmd_list,
    "replay":     cmd_replay,
    "report":     cmd_report,
    "invariants": cmd_invariants,
    "export":     cmd_export,
    "smoke":      cmd_smoke,
}


def main(argv: list[str] | None = None) -> int:
    parser = build_parser()
    args   = parser.parse_args(argv)
    try:
        return _COMMANDS[args.command](args)
    except Exception as exc:
        print("ERROR: " + str(exc), file=sys.stderr)
        return 2


if __name__ == "__main__":
    sys.exit(main())
