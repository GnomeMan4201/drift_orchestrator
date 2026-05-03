#!/usr/bin/env python3
"""
controlplane/replay.py

Replay, summarize, and report on operator sessions from the action journal.
No TUI dependency. No direct SQLite calls - delegates entirely to journal.py.

Public API
----------
load_events(session_id, db_path)          -> list[dict]   chronological
summarize_events(events)                  -> dict
render_timeline(events)                   -> str
render_markdown_report(events, session_id) -> str
write_markdown_report(events, session_id, exports_dir) -> Path
"""

from __future__ import annotations

from collections import Counter, defaultdict
from pathlib import Path
from typing import Optional

from controlplane.journal import JOURNAL_DEFAULT, recent_events

EXPORTS_DEFAULT = Path("exports")


# ---------------------------------------------------------------------------
# Load
# ---------------------------------------------------------------------------

def load_events(
    session_id: Optional[str] = None,
    db_path: Path = JOURNAL_DEFAULT,
) -> list[dict]:
    """
    Return events in chronological order (oldest first).
    journal.recent_events returns newest-first; we reverse here so
    callers always get a natural timeline.
    """
    rows = recent_events(limit=100_000, session_id=session_id, db_path=db_path)
    return list(reversed(rows))


# ---------------------------------------------------------------------------
# Summarize
# ---------------------------------------------------------------------------

def summarize_events(events: list[dict]) -> dict:
    """
    Deterministic summary.  No AI.  No inference beyond raw counts.

    Returns
    -------
    dict with keys:
        event_count, started_at, ended_at,
        action_counts, target_counts, result_counts,
        rollback_count, promotion_count, export_count,
        warning_flags
    """
    if not events:
        return {
            "event_count":    0,
            "started_at":     None,
            "ended_at":       None,
            "action_counts":  {},
            "target_counts":  {},
            "result_counts":  {},
            "rollback_count": 0,
            "promotion_count": 0,
            "export_count":   0,
            "warning_flags":  [],
        }

    action_counts = Counter(e["action"] for e in events)
    target_counts = Counter(
        e["target_id"] for e in events if e.get("target_id")
    )
    result_counts = Counter((e.get("result") or "ok") for e in events)

    rollback_count = sum(
        1 for e in events if "rollback" in (e["action"] or "")
    )
    # count confirmed promotions (not pending / not cancelled)
    promotion_count = sum(
        1 for e in events
        if (e["action"] or "") in ("promote_candidate", "promote_clamp")
        or (
            "promote" in (e["action"] or "")
            and "pending" not in (e["action"] or "")
            and (e.get("result") or "ok") not in ("cancelled", "error")
        )
    )
    export_count = action_counts.get("export", 0)

    return {
        "event_count":    len(events),
        "started_at":     events[0]["ts"],
        "ended_at":       events[-1]["ts"],
        "action_counts":  dict(action_counts),
        "target_counts":  dict(target_counts),
        "result_counts":  dict(result_counts),
        "rollback_count": rollback_count,
        "promotion_count": promotion_count,
        "export_count":   export_count,
        "warning_flags":  _compute_warnings(events),
    }


def _compute_warnings(events: list[dict]) -> list[str]:
    """
    Deterministic invariant checks over a chronological event list.
    Returns a list of warning strings (empty = clean session).
    """
    warnings: list[str] = []

    # ---- build per-target sequences ----------------------------------------
    actions_by_target: dict[str, list[str]] = defaultdict(list)
    results_by_target: dict[str, list[str]] = defaultdict(list)
    for e in events:
        tid = e.get("target_id") or "_global"
        actions_by_target[tid].append(e.get("action") or "")
        results_by_target[tid].append(e.get("result") or "ok")

    # rollback_present
    if any("rollback" in (e.get("action") or "") for e in events):
        warnings.append("rollback_present")

    # fail_present
    if any((e.get("result") or "") == "error" for e in events):
        warnings.append("fail_present")

    # approve_then_fail_same_target
    # confirm_yes on a target followed later by result=error on the same target
    for tid, action_seq in actions_by_target.items():
        result_seq = results_by_target[tid]
        confirm_indices = [i for i, a in enumerate(action_seq) if a == "confirm_yes"]
        error_indices   = [i for i, r in enumerate(result_seq)  if r == "error"]
        if confirm_indices and error_indices:
            if any(ei > ci for ci in confirm_indices for ei in error_indices):
                label = tid if tid != "_global" else "global"
                warnings.append("approve_then_fail_same_target target=" + label)
                break   # one flag is enough

    # repeated_action_same_target (>= 3 identical (action, target_id) pairs)
    action_target: Counter = Counter()
    for e in events:
        tid = e.get("target_id") or "_global"
        action_target[(e.get("action") or "", tid)] += 1
    for (action, tid), count in sorted(action_target.items()):
        if count >= 3:
            warnings.append(
                "repeated_action_same_target"
                " action=" + action
                + " target=" + tid
                + " count=" + str(count)
            )

    # export_not_final: an export event exists but is not the last event
    if any((e.get("action") or "") == "export" for e in events):
        if (events[-1].get("action") or "") != "export":
            warnings.append("export_not_final")

    return warnings


# ---------------------------------------------------------------------------
# Render timeline
# ---------------------------------------------------------------------------

def render_timeline(events: list[dict]) -> str:
    """
    Return a human-readable timeline string.

    Format:
        [2026-05-03 18:12:01]  analyze               target=session:abc12345   result=ok
    """
    if not events:
        return "(no events)"

    lines: list[str] = []
    for e in events:
        ts          = (e.get("ts") or "")[:19].replace("T", " ")
        action      = (e.get("action") or "").ljust(28)
        target_id   = e.get("target_id") or ""
        target_type = e.get("target_type") or ""
        result      = e.get("result") or "ok"
        target_str  = (target_type + ":" + target_id) if target_id else "-"
        lines.append(
            "[" + ts + "]  "
            + action
            + "  target=" + target_str.ljust(28)
            + "  result=" + result
        )
    return "\n".join(lines)


# ---------------------------------------------------------------------------
# Markdown report
# ---------------------------------------------------------------------------

def render_markdown_report(events: list[dict], session_id: str) -> str:
    """Return a complete Markdown report string for a session."""
    s = summarize_events(events)

    lines: list[str] = [
        "# Operator Session Report",
        "",
        "## Metadata",
        "",
        "| Field | Value |",
        "|---|---|",
        "| Session ID | `" + session_id + "` |",
        "| Started | " + (s["started_at"] or "-") + " |",
        "| Ended | " + (s["ended_at"] or "-") + " |",
        "| Event count | " + str(s["event_count"]) + " |",
        "| Rollbacks | " + str(s["rollback_count"]) + " |",
        "| Promotions | " + str(s["promotion_count"]) + " |",
        "| Exports | " + str(s["export_count"]) + " |",
        "",
        "## Timeline",
        "",
        "| Time (UTC) | Action | Target | Result |",
        "|---|---|---|---|",
    ]

    for e in events:
        ts          = (e.get("ts") or "")[:19].replace("T", " ")
        action      = e.get("action") or ""
        target_id   = e.get("target_id") or ""
        target_type = e.get("target_type") or ""
        result      = e.get("result") or "ok"
        target_str  = (target_type + ":" + target_id) if target_id else "-"
        lines.append(
            "| " + ts
            + " | " + action
            + " | " + target_str
            + " | " + result + " |"
        )

    lines += [
        "",
        "## Summary",
        "",
        "### Action Counts",
        "",
    ]
    for action, count in sorted(s["action_counts"].items(), key=lambda x: -x[1]):
        lines.append("- " + action + ": " + str(count))

    lines += ["", "### Result Counts", ""]
    for result, count in sorted(s["result_counts"].items(), key=lambda x: -x[1]):
        lines.append("- " + result + ": " + str(count))

    if s["target_counts"]:
        most_active = max(s["target_counts"], key=lambda k: s["target_counts"][k])
        lines += [
            "",
            "### Most Active Target",
            "",
            "- " + most_active
            + " (" + str(s["target_counts"][most_active]) + " events)",
        ]

    lines += ["", "## Invariant Findings", ""]
    if s["warning_flags"]:
        for flag in s["warning_flags"]:
            lines.append("- WARN " + flag)
    else:
        lines.append("- PASS no warnings")

    return "\n".join(lines) + "\n"


def write_markdown_report(
    events: list[dict],
    session_id: str,
    exports_dir: Path = EXPORTS_DEFAULT,
) -> Path:
    """
    Write the Markdown report to:
        exports_dir/session_<session_id>_report.md

    Creates exports_dir if needed.  Returns the path written.
    """
    exports_dir.mkdir(parents=True, exist_ok=True)
    out_path = exports_dir / ("session_" + session_id + "_report.md")
    out_path.write_text(render_markdown_report(events, session_id), encoding="utf-8")
    return out_path
