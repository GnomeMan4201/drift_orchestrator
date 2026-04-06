#!/usr/bin/env python3
from __future__ import annotations

import sqlite3
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
DB = ROOT / "data" / "drift.db"

conn = sqlite3.connect(DB)
conn.row_factory = sqlite3.Row

def fetch_one(query: str, params: tuple = ()):
    cur = conn.execute(query, params)
    row = cur.fetchone()
    return dict(row) if row else None

def table_exists(name: str) -> bool:
    row = conn.execute(
        "SELECT 1 FROM sqlite_master WHERE type='table' AND name=?",
        (name,),
    ).fetchone()
    return row is not None

print("# latest snapshot")

latest_session = None
if table_exists("sessions"):
    for q in (
        "SELECT * FROM sessions ORDER BY created_at DESC LIMIT 1",
        "SELECT * FROM sessions ORDER BY id DESC LIMIT 1",
    ):
        latest_session = fetch_one(q)
        if latest_session:
            break

if not latest_session:
    print("# session: none")
    conn.close()
    raise SystemExit(0)

session_id = latest_session.get("id")
print("# session:", session_id)
if "created_at" in latest_session:
    print("# session_created_at:", latest_session["created_at"])
if "meta" in latest_session:
    print("# session_meta:", latest_session["meta"])

latest_turn = None
if table_exists("turn_metrics"):
    for q in (
        "SELECT * FROM turn_metrics WHERE session_id=? ORDER BY created_at DESC LIMIT 1",
        "SELECT * FROM turn_metrics WHERE session_id=? ORDER BY id DESC LIMIT 1",
    ):
        latest_turn = fetch_one(q, (session_id,))
        if latest_turn:
            break

if latest_turn:
    print("# alpha:", latest_turn.get("alpha"))
    print("# turn_index:", latest_turn.get("turn_index"))
    if "created_at" in latest_turn:
        print("# turn_created_at:", latest_turn["created_at"])
else:
    print("# alpha: none")
    print("# turn_index: none")

    fallback_turn = None
    if table_exists("turn_metrics"):
        for q in (
            "SELECT * FROM turn_metrics ORDER BY created_at DESC LIMIT 1",
            "SELECT * FROM turn_metrics ORDER BY id DESC LIMIT 1",
        ):
            fallback_turn = fetch_one(q)
            if fallback_turn:
                break

    if fallback_turn:
        print("# fallback_latest_scored_session:", fallback_turn.get("session_id"))
        print("# fallback_alpha:", fallback_turn.get("alpha"))
        print("# fallback_turn_index:", fallback_turn.get("turn_index"))
        if "created_at" in fallback_turn:
            print("# fallback_turn_created_at:", fallback_turn["created_at"])

latest_policy = None
if table_exists("policy_events"):
    for q in (
        "SELECT * FROM policy_events WHERE session_id=? ORDER BY created_at DESC LIMIT 1",
        "SELECT * FROM policy_events WHERE session_id=? ORDER BY id DESC LIMIT 1",
    ):
        try:
            latest_policy = fetch_one(q, (session_id,))
            if latest_policy:
                break
        except sqlite3.OperationalError:
            pass

if latest_policy:
    event = latest_policy.get("event_type") or latest_policy.get("action") or latest_policy.get("policy_decision")
    print("# policy:", event)
    if "created_at" in latest_policy:
        print("# policy_created_at:", latest_policy["created_at"])
else:
    print("# policy: none")

    fallback_policy = None
    if table_exists("policy_events"):
        for q in (
            "SELECT * FROM policy_events ORDER BY created_at DESC LIMIT 1",
            "SELECT * FROM policy_events ORDER BY id DESC LIMIT 1",
        ):
            try:
                fallback_policy = fetch_one(q)
                if fallback_policy:
                    break
            except sqlite3.OperationalError:
                pass

    if fallback_policy:
        event = fallback_policy.get("event_type") or fallback_policy.get("action") or fallback_policy.get("policy_decision")
        print("# fallback_policy_session:", fallback_policy.get("session_id"))
        print("# fallback_policy:", event)
        if "created_at" in fallback_policy:
            print("# fallback_policy_created_at:", fallback_policy["created_at"])

conn.close()
