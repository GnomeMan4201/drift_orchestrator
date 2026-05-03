#!/usr/bin/env python3
"""
controlplane/journal.py

Persistent action journal for drifttop control-plane events.
Owns all SQLite access. Usable independently of the TUI.

Schema
------
action_events:
    id              INTEGER PRIMARY KEY AUTOINCREMENT
    ts              TEXT NOT NULL        -- ISO-8601 UTC
    session_id      TEXT NOT NULL        -- operator UI session (session_YYYYMMDD_HHMMSS)
    action          TEXT NOT NULL        -- e.g. "analyze", "promote_candidate"
    target_type     TEXT                 -- "session" | "db" | None
    target_id       TEXT                 -- drift session UUID or None
    target_summary  TEXT                 -- human-readable one-liner
    result          TEXT                 -- "ok" | "error" | "cancelled" | "timeout"
    metadata_json   TEXT                 -- arbitrary JSON blob
"""

from __future__ import annotations

import json
import sqlite3
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional

JOURNAL_DEFAULT = Path.home() / ".drift_controlplane" / "journal.db"


# ---------------------------------------------------------------------------
# Internal helpers
# ---------------------------------------------------------------------------

def _connect(db_path: Path) -> sqlite3.Connection:
    db_path.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(str(db_path))
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA journal_mode=WAL")
    return conn


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------

def init_db(db_path: Path = JOURNAL_DEFAULT) -> None:
    """Create the action_events table if it does not exist."""
    conn = _connect(db_path)
    conn.execute("""
        CREATE TABLE IF NOT EXISTS action_events (
            id              INTEGER PRIMARY KEY AUTOINCREMENT,
            ts              TEXT NOT NULL,
            session_id      TEXT NOT NULL,
            action          TEXT NOT NULL,
            target_type     TEXT,
            target_id       TEXT,
            target_summary  TEXT,
            result          TEXT,
            metadata_json   TEXT
        )
    """)
    conn.execute(
        "CREATE INDEX IF NOT EXISTS idx_ae_session ON action_events (session_id)"
    )
    conn.commit()
    conn.close()


def append_event(
    *,
    session_id: str,
    action: str,
    target_type: Optional[str] = None,
    target_id: Optional[str] = None,
    target_summary: Optional[str] = None,
    result: str = "ok",
    metadata: Optional[dict] = None,
    db_path: Path = JOURNAL_DEFAULT,
) -> int:
    """
    Append one event to the journal.

    Returns the new row id.
    Thread-safe: each call opens and closes its own connection.
    """
    ts = datetime.now(timezone.utc).isoformat()
    meta_json = json.dumps(metadata, default=str) if metadata is not None else None
    conn = _connect(db_path)
    cur = conn.execute(
        """
        INSERT INTO action_events
            (ts, session_id, action, target_type, target_id,
             target_summary, result, metadata_json)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?)
        """,
        (ts, session_id, action, target_type, target_id,
         target_summary, result, meta_json),
    )
    conn.commit()
    row_id = cur.lastrowid
    conn.close()
    return row_id


def recent_events(
    limit: int = 50,
    session_id: Optional[str] = None,
    db_path: Path = JOURNAL_DEFAULT,
) -> list[dict]:
    """
    Return the most recent events, newest first.

    If session_id is given, filter to that operator session.
    """
    conn = _connect(db_path)
    if session_id:
        rows = conn.execute(
            """
            SELECT * FROM action_events
            WHERE session_id = ?
            ORDER BY id DESC
            LIMIT ?
            """,
            (session_id, limit),
        ).fetchall()
    else:
        rows = conn.execute(
            "SELECT * FROM action_events ORDER BY id DESC LIMIT ?",
            (limit,),
        ).fetchall()
    conn.close()
    return [dict(r) for r in rows]


def export_jsonl(
    output_path: Path,
    session_id: Optional[str] = None,
    db_path: Path = JOURNAL_DEFAULT,
) -> int:
    """
    Write all matching events to output_path as newline-delimited JSON.

    Events are written oldest-first (chronological order).
    Returns the number of lines written.
    """
    events = recent_events(limit=100_000, session_id=session_id, db_path=db_path)
    output_path.parent.mkdir(parents=True, exist_ok=True)
    with output_path.open("w", encoding="utf-8") as fh:
        for ev in reversed(events):   # recent_events returns newest-first
            fh.write(json.dumps(ev, default=str) + "\n")
    return len(events)
