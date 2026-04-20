#!/usr/bin/env python3
"""
Minimal labeling CLI for Signal C dataset collection.

Session labels (coarse):
  control_set       — known legitimate sequences
  probe_run         — dual_signal_control_probe runs
  live_manual       — manual live sessions
  benchmark_attack  — gradient chain / jitter attack runs

Turn/window labels (fine-grained):
  legit             — legitimate turn, should not trigger
  false_positive    — triggered but should not have
  true_positive     — triggered correctly
  ambiguous         — unclear ground truth
  unlabeled         — default

Usage:
  python3 scripts/label_session.py --list
  python3 scripts/label_session.py --session <session_id_prefix> --label control_set
  python3 scripts/label_session.py --session <session_id_prefix> --turn-label legit
  python3 scripts/label_session.py --session <session_id_prefix> --window <n> --turn-label false_positive
"""

import argparse
import sqlite3
import sys

DB_PATH = "data/drift.db"

SESSION_LABELS = {"control_set", "probe_run", "live_manual", "benchmark_attack"}
TURN_LABELS = {"legit", "false_positive", "true_positive", "ambiguous", "unlabeled"}

def get_conn():
    return sqlite3.connect(DB_PATH)

def resolve_session(prefix):
    conn = get_conn()
    rows = conn.execute(
        "SELECT id, created_at, session_label FROM sessions WHERE id LIKE ?",
        (f"{prefix}%",)
    ).fetchall()
    conn.close()
    if not rows:
        print(f"No session matching prefix: {prefix}")
        sys.exit(1)
    if len(rows) > 1:
        print(f"Ambiguous prefix — matched {len(rows)} sessions:")
        for r in rows:
            print(f"  {r[0]}  created={r[1]}  label={r[2]}")
        sys.exit(1)
    return rows[0][0]

def list_sessions():
    conn = get_conn()
    rows = conn.execute(
        "SELECT id, created_at, session_label FROM sessions ORDER BY created_at DESC LIMIT 20"
    ).fetchall()
    conn.close()
    print(f"{'ID':<38} {'created_at':<28} {'label'}")
    print("-" * 80)
    for r in rows:
        print(f"{r[0]:<38} {r[1]:<28} {r[2] or 'unlabeled'}")

def label_session(session_id, label):
    if label not in SESSION_LABELS:
        print(f"Invalid session label: {label}. Valid: {SESSION_LABELS}")
        sys.exit(1)
    conn = get_conn()
    conn.execute("UPDATE sessions SET session_label=? WHERE id=?", (label, session_id))
    conn.commit()
    conn.close()
    print(f"Session {session_id[:8]}... labeled: {label}")

def label_turns(session_id, label, window_index=None):
    if label not in TURN_LABELS:
        print(f"Invalid turn label: {label}. Valid: {TURN_LABELS}")
        sys.exit(1)
    conn = get_conn()
    if window_index is not None:
        conn.execute(
            "UPDATE turn_metrics SET label=? WHERE session_id=? AND window_index=?",
            (label, session_id, window_index)
        )
        conn.execute(
            "UPDATE external_eval SET label=? WHERE session_id=? AND window_index=?",
            (label, session_id, window_index)
        )
        print(f"Window {window_index} in {session_id[:8]}... labeled: {label}")
    else:
        conn.execute(
            "UPDATE turn_metrics SET label=? WHERE session_id=?",
            (label, session_id)
        )
        conn.execute(
            "UPDATE external_eval SET label=? WHERE session_id=?",
            (label, session_id)
        )
        print(f"All turns in {session_id[:8]}... labeled: {label}")
    conn.commit()
    conn.close()

def main():
    parser = argparse.ArgumentParser(description="Label sessions and turns for Signal C dataset")
    parser.add_argument("--list", action="store_true", help="List recent sessions")
    parser.add_argument("--session", help="Session ID prefix to label")
    parser.add_argument("--label", help="Session-level label")
    parser.add_argument("--turn-label", help="Turn/window-level label")
    parser.add_argument("--window", type=int, help="Specific window index to label")
    args = parser.parse_args()

    if args.list:
        list_sessions()
        return

    if not args.session:
        parser.print_help()
        return

    session_id = resolve_session(args.session)

    if args.label:
        label_session(session_id, args.label)

    if args.turn_label:
        label_turns(session_id, args.turn_label, args.window)

if __name__ == "__main__":
    main()
