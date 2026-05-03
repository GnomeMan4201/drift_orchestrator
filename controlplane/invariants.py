#!/usr/bin/env python3
"""
controlplane/invariants.py

First-class invariant rule layer for operator session analysis.
Owns all rule logic.  Returns structured Finding objects.
No TUI dependency.  No SQLite calls.  Usable standalone.

Public API
----------
check(events)           -> list[Finding]
has_violations(findings) -> bool
Finding                  dataclass (frozen)
"""

from __future__ import annotations

from collections import Counter, defaultdict
from dataclasses import dataclass
from typing import Optional


# ---------------------------------------------------------------------------
# Finding dataclass
# ---------------------------------------------------------------------------

@dataclass(frozen=True)
class Finding:
    severity:    str                   # "pass" | "warn" | "fail"
    code:        str                   # stable machine-readable identifier
    message:     str                   # human-readable explanation
    action:      Optional[str] = None
    target_type: Optional[str] = None
    target_id:   Optional[str] = None
    event_id:    Optional[int] = None
    metadata:    Optional[dict] = None


_PASS = Finding(
    severity="pass",
    code="clean_session",
    message="No invariant violations found.",
)


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------

def check(events: list[dict]) -> list[Finding]:
    """
    Run all invariant rules over a chronological event list.

    Returns a non-empty list of Findings.
    An empty or violation-free session returns [PASS finding].
    """
    if not events:
        return [_PASS]

    findings: list[Finding] = []
    findings.extend(_rollback_present(events))
    findings.extend(_fail_present(events))
    findings.extend(_approve_then_fail_same_target(events))
    findings.extend(_repeated_action_same_target(events))
    findings.extend(_action_after_export(events))
    findings.extend(_promote_clamp_without_candidate(events))
    findings.extend(_rollback_without_prior_approval(events))

    return findings if findings else [_PASS]


def has_violations(findings: list[Finding]) -> bool:
    """Return True if any finding carries severity warn or fail."""
    return any(f.severity in ("warn", "fail") for f in findings)


def violation_codes(findings: list[Finding]) -> list[str]:
    """Return a flat list of codes for all warn/fail findings."""
    return [f.code for f in findings if f.severity in ("warn", "fail")]


# ---------------------------------------------------------------------------
# Rules
# ---------------------------------------------------------------------------

def _rollback_present(events: list[dict]) -> list[Finding]:
    """One finding per rollback action recorded in the session."""
    return [
        Finding(
            severity="warn",
            code="rollback_present",
            message="A rollback action was recorded in this session.",
            action=e.get("action"),
            target_type=e.get("target_type"),
            target_id=e.get("target_id"),
            event_id=e.get("id"),
        )
        for e in events
        if "rollback" in (e.get("action") or "")
    ]


def _fail_present(events: list[dict]) -> list[Finding]:
    """One finding per action that completed with result=error."""
    return [
        Finding(
            severity="warn",
            code="fail_present",
            message="An action completed with result=error.",
            action=e.get("action"),
            target_type=e.get("target_type"),
            target_id=e.get("target_id"),
            event_id=e.get("id"),
        )
        for e in events
        if (e.get("result") or "") == "error"
    ]


def _approve_then_fail_same_target(events: list[dict]) -> list[Finding]:
    """
    Fires once per target where confirm_yes is later followed by result=error.
    confirm_yes before the error — not after.
    """
    by_target: dict[str, list[dict]] = defaultdict(list)
    for e in events:
        by_target[e.get("target_id") or "_global"].append(e)

    findings: list[Finding] = []
    for tid, evs in sorted(by_target.items()):
        confirm_idx = [i for i, e in enumerate(evs) if e.get("action") == "confirm_yes"]
        error_idx   = [i for i, e in enumerate(evs) if (e.get("result") or "") == "error"]
        if confirm_idx and error_idx:
            if any(ei > ci for ci in confirm_idx for ei in error_idx):
                label = tid if tid != "_global" else "global"
                findings.append(Finding(
                    severity="warn",
                    code="approve_then_fail_same_target",
                    message=(
                        "confirm_yes was followed by result=error on the same target "
                        "(" + label + ")."
                    ),
                    target_id=None if tid == "_global" else tid,
                    metadata={"target": label},
                ))
    return findings


def _repeated_action_same_target(
    events: list[dict],
    threshold: int = 3,
) -> list[Finding]:
    """
    Fires when the same (action, target_id) pair appears >= threshold times.
    """
    counts: Counter = Counter()
    for e in events:
        tid = e.get("target_id") or "_global"
        counts[(e.get("action") or "", tid)] += 1

    return [
        Finding(
            severity="warn",
            code="repeated_action_same_target",
            message=(
                "Action '" + action + "' repeated " + str(count)
                + " times on target '" + tid
                + "' (threshold=" + str(threshold) + ")."
            ),
            action=action,
            target_id=None if tid == "_global" else tid,
            metadata={"count": count, "threshold": threshold, "target": tid},
        )
        for (action, tid), count in sorted(counts.items())
        if count >= threshold
    ]


def _action_after_export(events: list[dict]) -> list[Finding]:
    """
    Fires if any export event is followed by further operator actions.
    The export should be the terminal action of a session.
    """
    export_indices = [i for i, e in enumerate(events) if (e.get("action") or "") == "export"]
    if not export_indices:
        return []
    last_export = max(export_indices)
    if last_export >= len(events) - 1:
        return []
    post = [e.get("action") for e in events[last_export + 1:]]
    return [
        Finding(
            severity="warn",
            code="action_after_export",
            message=(
                str(len(post)) + " action(s) recorded after the last export event."
            ),
            metadata={"post_export_actions": post},
        )
    ]


def _promote_clamp_without_candidate(events: list[dict]) -> list[Finding]:
    """
    Fires when a confirmed clamp action exists on a target that never had a
    prior promote_candidate on the same target.
    """
    candidate_targets: set[str] = {
        e.get("target_id") or "_global"
        for e in events
        if (e.get("action") or "") == "promote_candidate"
    }

    return [
        Finding(
            severity="warn",
            code="promote_clamp_without_candidate",
            message=(
                "A clamp action was performed without a prior promote_candidate "
                "on the same target."
            ),
            action=e.get("action"),
            target_type=e.get("target_type"),
            target_id=e.get("target_id"),
            event_id=e.get("id"),
        )
        for e in events
        if (e.get("action") or "") in ("clamp", "promote_clamp")
        and (e.get("target_id") or "_global") not in candidate_targets
    ]


def _rollback_without_prior_approval(events: list[dict]) -> list[Finding]:
    """
    Fires when a rollback action occurs on a target without any prior
    confirm_yes on the same target (scanning forward through the session).
    """
    approved: set[str] = set()
    findings: list[Finding] = []
    for e in events:
        tid = e.get("target_id") or "_global"
        if (e.get("action") or "") == "confirm_yes":
            approved.add(tid)
        if "rollback" in (e.get("action") or ""):
            if tid not in approved:
                findings.append(Finding(
                    severity="warn",
                    code="rollback_without_prior_approval",
                    message=(
                        "A rollback occurred without a prior confirm_yes on the same target."
                    ),
                    action=e.get("action"),
                    target_type=e.get("target_type"),
                    target_id=e.get("target_id"),
                    event_id=e.get("id"),
                ))
    return findings


# ---------------------------------------------------------------------------
# Status helpers (pure -- no DB, no TUI dependency)
# ---------------------------------------------------------------------------

_SEVERITY_ORDER: dict[str, int] = {"fail": 2, "warn": 1, "pass": 0}


def select_highest_severity_finding(findings):
    """
    Return the single highest-severity Finding from a list.
    Priority: fail > warn > pass. Empty list returns canonical PASS.
    """
    if not findings:
        return _PASS
    return max(findings, key=lambda f: _SEVERITY_ORDER.get(f.severity, 0))


def format_invariant_status(finding) -> str:
    """
    Format a single Finding as a one-line Rich markup status string.
    Pass:  "  STATUS: PASS  session_evaluated"
    Warn:  "  STATUS: WARN  <code>  <message>"
    Fail:  "  STATUS: FAIL  <code>  <message>"
    """
    if finding.severity == "pass":
        return "  [dim]STATUS: PASS  session_evaluated[/dim]"
    color = "red" if finding.severity == "fail" else "yellow"
    return (
        "  [bold " + color + "]STATUS: " + finding.severity.upper()
        + "[/bold " + color + "]"
        + "  [" + color + "]" + finding.code + "[/" + color + "]"
        + "  [dim]" + finding.message + "[/dim]"
    )
