"""
drift_orchestrator — orchestrator/audit.py
Audits CoderOutput against RouterTicket and optional PlannerSpec.
"""
from __future__ import annotations

import ast
import json
import re

from .contracts import (
    AuditResult,
    AuditStatus,
    CoderOutput,
    FailureClass,
    PlannerSpec,
    RetryAction,
    RouterTicket,
    make_request_id,
)

# Patterns that indicate prompt/instruction injection attempts
_INJECTION_SIGNALS: list[str] = [
    r"ignore\s+(previous|prior|all)\s+instructions",
    r"forget\s+(previous|prior|all)\s+instructions",
    r"new\s+instructions",
    r"disregard\s+(previous|prior|all)",
    r"override\s+(previous|prior|all)",
    r"you\s+are\s+now\s+a",
    r"act\s+as\s+if",
    r"pretend\s+you\s+are",
    r"system\s*:\s*",
]


def _check_risk_injection(text: str) -> list[str]:
    """Return a list of matched injection signal descriptions."""
    hits = []
    lower = text.lower()
    for pattern in _INJECTION_SIGNALS:
        if re.search(pattern, lower):
            hits.append(pattern)
    return hits


def _check_generic_fallback(text: str, forbidden_patterns: list[str]) -> list[str]:
    """Return forbidden pattern strings found in text."""
    hits = []
    for pattern in forbidden_patterns:
        if pattern.lower() in text.lower():
            hits.append(pattern)
    return hits


def _check_planner_spec_compliance(text: str, spec: PlannerSpec) -> list[str]:
    """
    Check code against PlannerSpec validation_targets and forbidden_patterns.

    validation_targets use prefix conventions:
      "contains X"     — X must appear in code
      "does not use X" — X must NOT appear in code
    """
    violations = []

    # Forbidden patterns
    for pattern in spec.forbidden_patterns:
        if pattern.lower() in text.lower():
            violations.append(f"forbidden pattern present: {pattern!r}")

    # Validation targets
    for target in spec.validation_targets:
        t = target.strip()
        if t.startswith("contains "):
            keyword = t[len("contains "):].strip()
            if keyword.lower() not in text.lower():
                violations.append(f"validation target not met: {target!r}")
        elif t.startswith("does not use "):
            keyword = t[len("does not use "):].strip()
            if keyword.lower() in text.lower():
                violations.append(f"validation target violated: {target!r}")

    return violations


def _try_compile_python(code: str) -> str | None:
    """Return a SyntaxError description string, or None if code compiles cleanly."""
    try:
        ast.parse(code)
        return None
    except SyntaxError as exc:
        return f"SyntaxError: {exc}"


def _try_parse_json(text: str) -> str | None:
    """Return a parse error description string, or None if text is valid JSON."""
    try:
        json.loads(text)
        return None
    except json.JSONDecodeError as exc:
        return f"JSONDecodeError: {exc}"


def run(
    ticket: RouterTicket,
    coder_output: CoderOutput,
    spec: PlannerSpec | None = None,
) -> AuditResult:
    """
    Full audit pipeline. Returns AuditResult with pass/fail verdict and retry guidance.

    Priority order:
      1. Risk injection      → FAIL_CLOSED immediately
      2. Empty output        → RETRY_ALTERNATE_MODEL
      3. Compile failure     → RETRY_ALTERNATE_MODEL
      4. JSON parse failure  → RETRY_SAME_ROLE_STRICT
      5. Generic fallback    → FAIL (GENERIC_FALLBACK)
      6. Planner violation   → REPLAN_AND_RECODE
      7. PASS
    """
    code = coder_output.cleaned_output or coder_output.raw_output
    reasons: list[str] = []

    # 1 — Risk injection (highest priority, fail hard)
    injection_hits = _check_risk_injection(code)
    if injection_hits:
        return AuditResult(
            request_id=ticket.request_id,
            audit_status=AuditStatus.FAIL_CLOSED,
            passed=False,
            failure_class=FailureClass.RISK_INJECTION,
            drift_score=1.0,
            verification_passed=False,
            reasons=[f"injection signal: {h}" for h in injection_hits],
            next_action=RetryAction.FAIL_CLOSED,
            next_model_role=None,
            generic_hits=[],
            spec_violations=[],
        )

    # 2 — Empty output
    if not code.strip():
        return AuditResult(
            request_id=ticket.request_id,
            audit_status=AuditStatus.RETRY_ALTERNATE_MODEL,
            passed=False,
            failure_class=FailureClass.EMPTY_OUTPUT,
            drift_score=0.5,
            verification_passed=False,
            reasons=["output is empty"],
            next_action=RetryAction.RETRY_ALTERNATE_MODEL,
            next_model_role=coder_output.model_role,
        )

    # 3 — Compile check (Python code only)
    if coder_output.output_mode == "code":
        compile_err = _try_compile_python(code)
        if compile_err:
            return AuditResult(
                request_id=ticket.request_id,
                audit_status=AuditStatus.RETRY_ALTERNATE_MODEL,
                passed=False,
                failure_class=FailureClass.COMPILE_FAILURE,
                drift_score=0.6,
                verification_passed=False,
                reasons=[compile_err],
                next_action=RetryAction.RETRY_ALTERNATE_MODEL,
                next_model_role=coder_output.model_role,
                compile_error=compile_err,
            )

    # 4 — JSON parse check
    if coder_output.output_mode == "json":
        json_err = _try_parse_json(code)
        if json_err:
            return AuditResult(
                request_id=ticket.request_id,
                audit_status=AuditStatus.RETRY_SAME_ROLE_STRICT,
                passed=False,
                failure_class=FailureClass.SCHEMA_FAILURE,
                drift_score=0.4,
                verification_passed=False,
                reasons=[json_err],
                next_action=RetryAction.RETRY_SAME_ROLE_STRICT,
                next_model_role=coder_output.model_role,
            )

    # 5 — Generic fallback (ticket-level forbidden patterns)
    ticket_forbidden = ticket.forbidden_patterns or []
    generic_hits = _check_generic_fallback(code, ticket_forbidden)
    if generic_hits:
        return AuditResult(
            request_id=ticket.request_id,
            audit_status=AuditStatus.RETRY_ALTERNATE_MODEL,
            passed=False,
            failure_class=FailureClass.GENERIC_FALLBACK,
            drift_score=0.5,
            verification_passed=False,
            reasons=[f"generic fallback: {h}" for h in generic_hits],
            next_action=RetryAction.RETRY_ALTERNATE_MODEL,
            next_model_role=coder_output.model_role,
            generic_hits=generic_hits,
        )

    # 6 — Planner spec compliance
    if spec is not None:
        spec_violations = _check_planner_spec_compliance(code, spec)
        if spec_violations:
            return AuditResult(
                request_id=ticket.request_id,
                audit_status=AuditStatus.REPLAN_AND_RECODE,
                passed=False,
                failure_class=FailureClass.PLANNER_VIOLATION,
                drift_score=0.5,
                verification_passed=False,
                reasons=spec_violations,
                next_action=RetryAction.REPLAN_AND_RECODE,
                next_model_role=None,
                spec_violations=spec_violations,
            )

    # 7 — PASS
    return AuditResult(
        request_id=ticket.request_id,
        audit_status=AuditStatus.PASS,
        passed=True,
        failure_class=None,
        drift_score=0.0,
        verification_passed=True,
        reasons=[],
        next_action=RetryAction.PASS,
        next_model_role=None,
    )
