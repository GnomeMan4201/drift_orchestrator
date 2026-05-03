#!/usr/bin/env python3
"""
controlplane/datasource.py

Datasource boundary between drift_orchestrator runtime state and the
control-plane UI layer.

Responsibilities
----------------
- Read from drift_orchestrator SQLite (drift.db) and candidate/clamp files.
- Produce UIRecord / SessionRecord objects with stable, typed fields.
- Provide target_type / target_id / summary fields for journal event logging.
- Never import Textual, journal, invariants, or replay modules.

Public API
----------
UIRecord        frozen dataclass — generic display record
SessionRecord   frozen dataclass — session-specific display record
session_record(...)  -> SessionRecord            constructor helper
candidate_record(...)-> UIRecord                 constructor helper
clamp_record(...)    -> UIRecord                 constructor helper
load_sessions(db_path, limit) -> list[SessionRecord]
load_candidates(candidates_dir) -> list[UIRecord]
load_clamps(candidates_dir) -> list[UIRecord]
load_all_records(db_path, candidates_dir) -> list[UIRecord]
"""

from __future__ import annotations

import json
import sqlite3
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Optional

CANDIDATES_DEFAULT = Path("candidates")


# ---------------------------------------------------------------------------
# Record dataclasses
# ---------------------------------------------------------------------------

@dataclass(frozen=True)
class UIRecord:
    """
    Generic display record for the control-plane UI.

    Provides stable target fields for journal event logging:
        target_type  = record_type
        target_id    = record_id
        target_summary = summary
    """
    record_type: str                           # "session" | "candidate" | "clamp"
    record_id:   str                           # stable identifier
    title:       str                           # short display name
    summary:     str                           # one-line human-readable description
    status:      str           = "unknown"    # policy action or lifecycle status
    severity:    str           = "info"       # "low" | "medium" | "high" | "info"
    source:      str           = "unknown"    # "live" | "mock" | "static" | "file"
    metadata:    dict[str, Any] = field(default_factory=dict)


@dataclass(frozen=True)
class SessionRecord:
    """
    Session-specific display record.  Holds all UIRecord fields plus the
    numeric and display fields needed for the drifttop session table.

    Defined independently (not via inheritance) to avoid frozen dataclass
    default-field ordering constraints.
    """
    # --- UIRecord-compatible fields -----------------------------------------
    record_type: str                           # always "session"
    record_id:   str                           # drift session UUID
    title:       str                           # session_label or UUID[:8]
    summary:     str                           # "label alpha=X.XXXX action=Y"
    status:      str           = "unknown"    # latest policy action
    severity:    str           = "info"       # derived from alpha
    source:      str           = "live"
    metadata:    dict[str, Any] = field(default_factory=dict)
    # --- Session display fields ---------------------------------------------
    alpha:        float = 0.0
    policy_action: str  = "---"
    turn_count:   int   = 0
    total_tokens: int   = 0
    created_at:   str   = ""


# ---------------------------------------------------------------------------
# Constructor helpers
# ---------------------------------------------------------------------------

def _alpha_severity(alpha: float) -> str:
    if alpha >= 0.6:
        return "high"
    if alpha >= 0.35:
        return "medium"
    return "low"


def session_record(
    *,
    session_id: str,
    label: str,
    alpha: float,
    policy_action: str,
    turn_count: int,
    total_tokens: int,
    created_at: str,
    extra_metadata: Optional[dict] = None,
) -> SessionRecord:
    """Construct a SessionRecord with pre-computed summary and severity."""
    summary = (
        label
        + " alpha=" + "{:.4f}".format(alpha)
        + " action=" + policy_action
    )
    return SessionRecord(
        record_type   = "session",
        record_id     = session_id,
        title         = label,
        summary       = summary,
        status        = policy_action,
        severity      = _alpha_severity(alpha),
        source        = "live",
        metadata      = extra_metadata or {},
        alpha         = alpha,
        policy_action = policy_action,
        turn_count    = turn_count,
        total_tokens  = total_tokens,
        created_at    = created_at,
    )


def candidate_record(
    *,
    session_id: str,
    label: str = "",
    alpha: float = 0.0,
    path: Optional[Path] = None,
) -> UIRecord:
    """Construct a UIRecord for a promote-candidate JSON file."""
    title   = label or session_id[:8]
    summary = "candidate " + title + " alpha=" + "{:.4f}".format(alpha)
    meta: dict[str, Any] = {}
    if path is not None:
        meta["candidate_path"] = str(path)
    return UIRecord(
        record_type = "candidate",
        record_id   = session_id,
        title       = title,
        summary     = summary,
        status      = "CANDIDATE_REVIEW",
        severity    = _alpha_severity(alpha),
        source      = "file",
        metadata    = meta,
    )


def clamp_record(
    *,
    session_id: str,
    path: Optional[Path] = None,
    exit_code: int = 0,
) -> UIRecord:
    """Construct a UIRecord for a degraded-annotation (clamp) JSON file."""
    result  = "ok" if exit_code == 0 else "error"
    summary = "clamp " + session_id[:8] + " control_exit=" + str(exit_code)
    meta: dict[str, Any] = {"exit_code": exit_code}
    if path is not None:
        meta["annotation_path"] = str(path)
    return UIRecord(
        record_type = "clamp",
        record_id   = session_id,
        title       = session_id[:8],
        summary     = summary,
        status      = result,
        severity    = "high" if result == "error" else "info",
        source      = "file",
        metadata    = meta,
    )


# ---------------------------------------------------------------------------
# Loaders
# ---------------------------------------------------------------------------

def load_sessions(
    db_path: Path,
    limit: int = 30,
) -> list[SessionRecord]:
    """
    Load the most recent sessions from drift_orchestrator SQLite.

    Returns an empty list if the database does not exist.
    The caller (drifttop) is responsible for sorting.
    """
    if not db_path.exists():
        return []

    conn = sqlite3.connect(str(db_path))
    conn.row_factory = sqlite3.Row

    rows = conn.execute("""
        SELECT
            s.id,
            COALESCE(s.session_label, '') AS label,
            s.created_at,
            (SELECT tm.alpha FROM turn_metrics tm
             WHERE tm.session_id = s.id
             ORDER BY tm.created_at DESC LIMIT 1) AS alpha,
            (SELECT pe.action FROM policy_events pe
             WHERE pe.session_id = s.id
             ORDER BY pe.created_at DESC LIMIT 1) AS policy_action,
            (SELECT COUNT(*) FROM turns t
             WHERE t.session_id = s.id) AS turn_count,
            (SELECT COALESCE(SUM(t.token_count), 0) FROM turns t
             WHERE t.session_id = s.id) AS total_tokens
        FROM sessions s
        ORDER BY s.created_at DESC
        LIMIT ?
    """, (limit,)).fetchall()
    conn.close()

    records: list[SessionRecord] = []
    for r in rows:
        alpha  = float(r["alpha"] or 0)
        action = r["policy_action"] or "---"
        label  = r["label"] or r["id"][:8]
        records.append(session_record(
            session_id    = r["id"],
            label         = label,
            alpha         = alpha,
            policy_action = action,
            turn_count    = r["turn_count"] or 0,
            total_tokens  = r["total_tokens"] or 0,
            created_at    = r["created_at"] or "",
        ))
    return records


def load_candidates(
    candidates_dir: Path = CANDIDATES_DEFAULT,
) -> list[UIRecord]:
    """
    Load candidate JSON files written by the promote-candidate workflow.

    Files matching ``<session_id>.json`` (not ending in ``_degraded.json``).
    Returns an empty list if the directory does not exist.
    """
    if not candidates_dir.exists():
        return []
    records: list[UIRecord] = []
    for p in sorted(candidates_dir.glob("*.json")):
        if p.name.endswith("_degraded.json"):
            continue
        try:
            data = json.loads(p.read_text(encoding="utf-8"))
            sid  = data.get("session_id", p.stem)
            sess = data.get("session", {})
            lbl  = sess.get("session_label", "") or sid[:8]
            # alpha not stored in candidate file; use 0.0 as placeholder
            records.append(candidate_record(
                session_id = sid,
                label      = lbl,
                alpha      = 0.0,
                path       = p,
            ))
        except Exception:
            continue
    return records


def load_clamps(
    candidates_dir: Path = CANDIDATES_DEFAULT,
) -> list[UIRecord]:
    """
    Load degraded-annotation (clamp) JSON files.

    Files matching ``<session_id>_degraded.json``.
    Returns an empty list if the directory does not exist.
    """
    if not candidates_dir.exists():
        return []
    records: list[UIRecord] = []
    for p in sorted(candidates_dir.glob("*_degraded.json")):
        try:
            data = json.loads(p.read_text(encoding="utf-8"))
            sid  = data.get("session_id", p.stem.replace("_degraded", ""))
            code = int(data.get("control_exit", 0))
            records.append(clamp_record(session_id=sid, path=p, exit_code=code))
        except Exception:
            continue
    return records


def load_all_records(
    db_path: Path,
    candidates_dir: Path = CANDIDATES_DEFAULT,
) -> list[UIRecord]:
    """
    Combine live sessions, candidates, and clamps into a single list.

    Sessions are returned first (as UIRecord-compatible SessionRecord objects),
    followed by candidates, then clamps.
    """
    sessions: list[UIRecord] = list(load_sessions(db_path))   # type: ignore[arg-type]
    return sessions + load_candidates(candidates_dir) + load_clamps(candidates_dir)
