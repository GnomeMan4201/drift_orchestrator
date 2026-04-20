#!/usr/bin/env python3
"""
Export labeled external_eval rows to JSONL for Signal C dataset.
Run after labeling sessions to snapshot current dataset state.
Output: data/signal_c_dataset.jsonl
"""

import sqlite3
import json
from datetime import datetime

conn = sqlite3.connect("data/drift.db")
conn.row_factory = sqlite3.Row

rows = conn.execute("""
    SELECT
        e.id,
        e.session_id,
        s.session_label,
        e.label as turn_label,
        e.window_index,
        e.turn_index,
        e.alpha,
        e.external_score,
        e.divergence,
        e.verdict,
        e.created_at
    FROM external_eval e
    JOIN sessions s ON e.session_id = s.id
    WHERE e.label IS NOT NULL
    ORDER BY e.created_at
""").fetchall()

out_path = "data/signal_c_dataset.jsonl"
with open(out_path, "w") as f:
    for r in rows:
        f.write(json.dumps(dict(r)) + "\n")

print(f"Exported {len(rows)} labeled rows to {out_path}")

# Summary
summary = conn.execute("""
    SELECT s.session_label, e.label, COUNT(*) as n,
           ROUND(AVG(e.divergence),4) as avg_div
    FROM external_eval e
    JOIN sessions s ON e.session_id = s.id
    WHERE e.label IS NOT NULL
    GROUP BY s.session_label, e.label
""").fetchall()

print("\nSummary:")
for r in summary:
    print(f"  {r[0]:<20} {r[1]:<16} n={r[2]:>4}  avg_div={r[3]}")

conn.close()
