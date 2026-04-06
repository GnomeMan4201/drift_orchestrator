#!/usr/bin/env python3
from __future__ import annotations

import sqlite3
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
DB = ROOT / "data" / "drift.db"

conn = sqlite3.connect(DB)
conn.row_factory = sqlite3.Row

def fetch_one(q, params=()):
    cur = conn.execute(q, params)
    row = cur.fetchone()
    return dict(row) if row else None

def table_exists(name: str) -> bool:
    row = conn.execute(
        "SELECT 1 FROM sqlite_master WHERE type='table' AND name=?",
        (name,),
    ).fetchone()
    return row is not None

print("# drift inspect")

# Latest scored turn (global)
turn = None
if table_exists("turn_metrics"):
    for q in (
        "SELECT * FROM turn_metrics ORDER BY created_at DESC LIMIT 1",
        "SELECT * FROM turn_metrics ORDER BY id DESC LIMIT 1",
    ):
        turn = fetch_one(q)
        if turn:
            break

if not turn:
    print("# no turn_metrics data")
    conn.close()
    raise SystemExit(0)

sid = turn.get("session_id")
print("# session:", sid)

# Core signals
for k in ("alpha", "rho_density", "d_goal", "d_anchor", "risk_verify", "repetition_score"):
    if k in turn:
        print(f"# {k}:", turn.get(k))

if "created_at" in turn:
    print("# turn_created_at:", turn["created_at"])

# Policy for same session
policy = None
if table_exists("policy_events"):
    for q in (
        "SELECT * FROM policy_events WHERE session_id=? ORDER BY created_at DESC LIMIT 1",
        "SELECT * FROM policy_events WHERE session_id=? ORDER BY id DESC LIMIT 1",
    ):
        try:
            policy = fetch_one(q, (sid,))
            if policy:
                break
        except sqlite3.OperationalError:
            pass

if policy:
    event = policy.get("event_type") or policy.get("action") or policy.get("policy_decision")
    print("# policy:", event)
    if "created_at" in policy:
        print("# policy_created_at:", policy["created_at"])
else:
    print("# policy: none")

# Optional raw_scores (compact)
raw = turn.get("raw_scores")
if raw:
    print("# raw_scores:", raw)

conn.close()
