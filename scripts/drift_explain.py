#!/usr/bin/env python3
from __future__ import annotations

import sqlite3
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
DB = ROOT / "data" / "drift.db"

# --- fallback thresholds (override if found in policy/config) ---
THRESHOLDS = {
    "alpha": 0.30,
    "rho_density": 0.40,
    "d_goal": 0.20,
    "d_anchor": 0.20,
    "repetition_score": 0.30,
    "divergence": 0.60,
}

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

def cmp(v, t):
    if v is None:
        return "NA"
    return "ABOVE" if v >= t else "BELOW"

print("# drift explain")

# latest scored turn
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

# signals
alpha = turn.get("alpha")
rho = turn.get("rho_density")
d_goal = turn.get("d_goal")
d_anchor = turn.get("d_anchor")
rep = turn.get("repetition_score")

# comparisons
print("# signals_vs_thresholds")

def show(name, value):
    t = THRESHOLDS[name]
    print(f"# {name}: {value} (threshold: {t}) → {cmp(value, t)}")

show("alpha", alpha)
show("rho_density", rho)
show("d_goal", d_goal)
show("d_anchor", d_anchor)
show("repetition_score", rep)

# policy
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

event = None
if policy:
    event = policy.get("event_type") or policy.get("action") or policy.get("policy_decision")

print("# policy:", event)

# reasoning
reasons = []

if alpha is not None and alpha < THRESHOLDS["alpha"]:
    reasons.append("alpha below threshold")

if rho is not None and rho >= THRESHOLDS["rho_density"]:
    reasons.append("structure maintained")

if rep is not None and rep < THRESHOLDS["repetition_score"]:
    reasons.append("repetition low")

if not reasons:
    reasons.append("no dominant trigger")

print("# reasoning:")
for r in reasons:
    print(f"# - {r}")

conn.close()
