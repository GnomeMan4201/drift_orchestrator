from __future__ import annotations
import ast
import json
import py_compile
import tempfile
import os
from typing import Optional

from orchestrator.contracts import (
    AuditResult, AuditStatus, CoderOutput, FailureClass,
    ModelRole, PlannerSpec, RetryAction, RouterTicket, TaskType,
    validate_audit_result,
)
from analysis.trace_logger import log_stage

_GENERIC_FALLBACK_SIGNATURES = [
    "beautifulsoup",
    "from bs4",
    "soup.find",
    "requests.get(url)",
    "urllib.request.urlopen(url)",
    "response.text",
    "html.parser",
    "lxml",
    "scrape",
    "grep(",
    "re.findall",
]

_RISK_INJECTION_SIGNATURES = [
    "ignore previous instructions",
    "disregard your",
    "override system",
    "new persona",
    "pretend you are",
    "act as if you have no",
    "jailbreak",
]

_CODE_TASK_TYPES = {
    TaskType.CODE_GENERATION, TaskType.CODE_PATCH,
    TaskType.TOOL_CLONE, TaskType.SECURITY_ANALYSIS,
}


def _check_risk_injection(output: str) -> list[str]:
    low = output.lower()
    hits = [sig for sig in _RISK_INJECTION_SIGNATURES if sig in low]
    return hits


def _check_generic_fallback(output: str, forbidden: list[str]) -> list[str]:
    low = output.lower()
    hits = []
    for sig in _GENERIC_FALLBACK_SIGNATURES:
        if sig in low:
            hits.append(sig)
    for pat in forbidden:
        if pat.lower() in low:
            hits.append(pat)
    return hits


def _check_planner_spec_compliance(
    output: str, spec: PlannerSpec
) -> list[str]:
    low = output.lower()
    violations: list[str] = []
    for target in spec.validation_targets:
        key = target.lower()
        present = False
        if key.startswith("contains "):
            needle = key[len("contains "):]
            present = needle in low
        elif key.startswith("does not "):
            needle = key[len("does not "):]
            present = needle not in low
        elif key.startswith("absence of "):
            needle = key[len("absence of "):]
            present = needle not in low
        elif key.startswith("presence of "):
            needle = key[len("presence of "):]
            present = needle in low
        else:
            # direct substring check first
            if key in low:
                present = True
            else:
                # fuzzy: all significant words (>4 chars) present in output
                words = [w for w in key.split() if len(w) > 4]
                present = bool(words) and sum(1 for w in words if w in low) >= max(1, len(words) // 2)
        if not present:
            violations.append("validation_target not satisfied: " + target)
    for pat in spec.forbidden_patterns:
        if pat.lower() in low:
            violations.append("forbidden_pattern present: " + pat)
    return violations


def _try_compile_python(code: str) -> Optional[str]:
    try:
        ast.parse(code)
        return None
    except SyntaxError as e:
        return "SyntaxError: " + str(e)


def _try_parse_json(text: str) -> Optional[str]:
    try:
        json.loads(text)
        return None
    except json.JSONDecodeError as e:
        return "JSONDecodeError: " + str(e)


def _drift_score(
    generic_hits: list[str],
    spec_violations: list[str],
    compile_error: Optional[str],
) -> float:
    score = 0.0
    score += min(len(generic_hits) * 0.15, 0.45)
    score += min(len(spec_violations) * 0.20, 0.40)
    if compile_error:
        score += 0.20
    return min(round(score, 3), 1.0)


def run(
    ticket: RouterTicket,
    coder_output: CoderOutput,
    planner_spec: Optional[PlannerSpec] = None,
    attempt: int = 1,
) -> AuditResult:
    output = coder_output.cleaned_output
    reasons: list[str] = []
    failure_class: Optional[FailureClass] = None
    compile_error: Optional[str] = None
    generic_hits: list[str] = []
    spec_violations: list[str] = []

    injection_hits = _check_risk_injection(output)
    if injection_hits:
        result = AuditResult(
            request_id=ticket.request_id,
            audit_status=AuditStatus.FAIL_CLOSED,
            passed=False,
            failure_class=FailureClass.RISK_INJECTION,
            drift_score=1.0,
            verification_passed=False,
            reasons=["risk_injection detected: " + ", ".join(injection_hits)],
            next_action=RetryAction.FAIL_CLOSED,
            next_model_role=None,
        )
        validate_audit_result(result)
        log_stage(
            request_id=ticket.request_id,
            stage="audit",
            model="audit",
            attempt=attempt,
            status="FAIL_CLOSED",
            failure_class=FailureClass.RISK_INJECTION.value,
            drift_score=1.0,
            detail="injection: " + ", ".join(injection_hits),
        )
        return result

    if not output.strip():
        result = AuditResult(
            request_id=ticket.request_id,
            audit_status=AuditStatus.RETRY_ALTERNATE_MODEL,
            passed=False,
            failure_class=FailureClass.UNKNOWN_FAILURE,
            drift_score=1.0,
            verification_passed=False,
            reasons=["empty output from coder"],
            next_action=RetryAction.RETRY_ALTERNATE_MODEL,
            next_model_role=ModelRole.CODER,
        )
        validate_audit_result(result)
        log_stage(
            request_id=ticket.request_id,
            stage="audit",
            model="audit",
            attempt=attempt,
            status="RETRY_ALTERNATE_MODEL",
            failure_class=FailureClass.UNKNOWN_FAILURE.value,
            drift_score=1.0,
            detail="empty output",
        )
        return result

    forbidden = planner_spec.forbidden_patterns if planner_spec else ticket.forbidden_patterns
    generic_hits = _check_generic_fallback(output, forbidden)
    if generic_hits:
        reasons.append("generic_fallback detected: " + ", ".join(generic_hits[:3]))
        failure_class = FailureClass.GENERIC_FALLBACK

    if planner_spec is not None:
        spec_violations = _check_planner_spec_compliance(output, planner_spec)
        if spec_violations:
            reasons += spec_violations[:3]
            if failure_class is None:
                failure_class = FailureClass.PLANNER_VIOLATION
            else:
                failure_class = FailureClass.PLANNER_VIOLATION

    if coder_output.output_mode == "code" and ticket.task_type in _CODE_TASK_TYPES:
        compile_error = _try_compile_python(output)
        if compile_error:
            reasons.append(compile_error)
            failure_class = FailureClass.COMPILE_FAILURE

    if coder_output.output_mode == "json":
        json_error = _try_parse_json(output)
        if json_error:
            reasons.append(json_error)
            if failure_class is None:
                failure_class = FailureClass.SCHEMA_FAILURE

    drift = _drift_score(generic_hits, spec_violations, compile_error)

    if not reasons:
        result = AuditResult(
            request_id=ticket.request_id,
            audit_status=AuditStatus.PASS,
            passed=True,
            failure_class=None,
            drift_score=drift,
            verification_passed=True,
            reasons=[],
            next_action=RetryAction.PASS,
            next_model_role=None,
        )
        validate_audit_result(result)
        log_stage(
            request_id=ticket.request_id,
            stage="audit",
            model="audit",
            attempt=attempt,
            status="PASS",
            drift_score=drift,
        )
        return result

    if failure_class == FailureClass.COMPILE_FAILURE:
        next_action = RetryAction.RETRY_ALTERNATE_MODEL
        audit_status = AuditStatus.RETRY_ALTERNATE_MODEL
        next_role = ModelRole.CODER
    elif failure_class == FailureClass.PLANNER_VIOLATION:
        next_action = RetryAction.REPLAN_AND_RECODE
        audit_status = AuditStatus.REPLAN_AND_RECODE
        next_role = ModelRole.PLANNER
    elif failure_class == FailureClass.GENERIC_FALLBACK:
        next_action = RetryAction.RETRY_ALTERNATE_MODEL
        audit_status = AuditStatus.RETRY_ALTERNATE_MODEL
        next_role = ModelRole.CODER
    elif failure_class == FailureClass.SCHEMA_FAILURE:
        next_action = RetryAction.RETRY_SAME_ROLE_STRICT
        audit_status = AuditStatus.RETRY_SAME_ROLE_STRICT
        next_role = ModelRole.CODER
    else:
        next_action = RetryAction.RETRY_SAME_ROLE_STRICT
        audit_status = AuditStatus.RETRY_SAME_ROLE_STRICT
        next_role = ModelRole.CODER

    result = AuditResult(
        request_id=ticket.request_id,
        audit_status=audit_status,
        passed=False,
        failure_class=failure_class,
        drift_score=drift,
        verification_passed=False,
        reasons=reasons,
        next_action=next_action,
        next_model_role=next_role,
    )
    validate_audit_result(result)
    log_stage(
        request_id=ticket.request_id,
        stage="audit",
        model="audit",
        attempt=attempt,
        status=audit_status.value,
        failure_class=failure_class.value if failure_class else None,
        drift_score=drift,
        detail="; ".join(reasons[:2]),
    )
    return result
