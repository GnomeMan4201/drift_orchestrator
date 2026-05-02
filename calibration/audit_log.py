"""
ACFC-Safe Calibration Suite — audit_log.py

Typed append-only audit event writers.
"""

from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

_AUDIT_LOG = Path(__file__).parent.parent / "storage" / "audit_log.jsonl"


def _utc_now() -> str:
    return datetime.now(timezone.utc).isoformat()


def write_audit_event(event: dict[str, Any], audit_log: Path | None = None) -> Path:
    """
    Append one minified JSON object to the audit log.

    Existing content is never truncated or overwritten.
    The caller's event dict is not mutated.
    """
    log_path = audit_log or _AUDIT_LOG
    log_path.parent.mkdir(parents=True, exist_ok=True)

    payload = {"timestamp": _utc_now(), **event} if "timestamp" not in event else dict(event)

    with log_path.open("a", encoding="utf-8") as fh:
        fh.write(json.dumps(payload, separators=(",", ":")) + "\n")

    return log_path


def audit_snapshot_frozen(
    *,
    session_id: str,
    checkpoint_id: str,
    snapshot_path: str,
    audit_log: Path | None = None,
) -> Path:
    return write_audit_event(
        {
            "event_type": "SNAPSHOT_FROZEN",
            "session_id": session_id,
            "checkpoint_id": checkpoint_id,
            "snapshot_path": snapshot_path,
        },
        audit_log=audit_log,
    )


def audit_trigger_fired(
    *,
    session_id: str,
    checkpoint_id: str,
    hit_count: int,
    window_size: int,
    audit_log: Path | None = None,
) -> Path:
    return write_audit_event(
        {
            "event_type": "TRIGGER_FIRED",
            "session_id": session_id,
            "checkpoint_id": checkpoint_id,
            "hit_count": hit_count,
            "window_size": window_size,
        },
        audit_log=audit_log,
    )


def audit_invariant_violation(
    *,
    session_id: str,
    violation_detail: str,
    audit_log: Path | None = None,
) -> Path:
    return write_audit_event(
        {
            "event_type": "INVARIANT_VIOLATION",
            "session_id": session_id,
            "violation_detail": violation_detail,
        },
        audit_log=audit_log,
    )
