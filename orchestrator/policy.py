"""
drift_orchestrator — orchestrator/policy.py
Translates AuditResult into a PolicyDecision: what to do next.
"""
from __future__ import annotations

from dataclasses import dataclass, field

from .contracts import (
    AuditResult,
    AuditStatus,
    FailureClass,
    MAX_RETRY_ATTEMPTS,
    RetryAction,
    RouterTicket,
)

# Ordered model rotation pool used by RETRY_ALTERNATE_MODEL
_MODEL_POOL: list[str] = [
    "mistral:latest",
    "llama3.1:latest",
    "phi3:latest",
]

# Dual-signal divergence threshold: if BOTH internal and external
# scores meet or exceed this value, fail closed immediately.
_DUAL_SIGNAL_THRESHOLD: float = 0.75


@dataclass
class PolicyDecision:
    action:          RetryAction
    fail_closed:     bool  = False
    should_replan:   bool  = False
    next_model_name: str | None = None
    reason:          str   = ""


def decide(
    ticket: RouterTicket,
    audit: AuditResult,
    current_model: str,
    attempt: int,
) -> PolicyDecision:
    """
    Produce a PolicyDecision given the current audit result and attempt context.

    Decision priority:
      1. Risk injection              → immediate fail_closed
      2. Dual-signal divergence      → immediate fail_closed
      3. Retry budget exhausted      → fail_closed
      4. PASS                        → PASS decision
      5. REPLAN_AND_RECODE           → should_replan=True
      6. RETRY_SAME_ROLE_STRICT      → same model, no replan
      7. RETRY_ALTERNATE_MODEL       → next model in pool, or fail_closed
      8. FAIL_CLOSED (other)         → fail_closed
    """

    # 1 — Risk injection always fails closed immediately
    if audit.failure_class == FailureClass.RISK_INJECTION:
        return PolicyDecision(
            action=RetryAction.FAIL_CLOSED,
            fail_closed=True,
            reason="risk injection detected",
        )

    # 2 — Dual-signal divergence
    if (
        audit.drift_score >= _DUAL_SIGNAL_THRESHOLD
        and audit.external_score >= _DUAL_SIGNAL_THRESHOLD
    ):
        return PolicyDecision(
            action=RetryAction.FAIL_CLOSED,
            fail_closed=True,
            reason=(
                f"dual-signal divergence: drift={audit.drift_score}, "
                f"external={audit.external_score}"
            ),
        )

    # 3 — Budget exhausted
    if attempt >= MAX_RETRY_ATTEMPTS:
        return PolicyDecision(
            action=RetryAction.FAIL_CLOSED,
            fail_closed=True,
            reason=f"retry budget exhausted at attempt {attempt}",
        )

    # 4 — Pass
    if audit.audit_status == AuditStatus.PASS:
        return PolicyDecision(
            action=RetryAction.PASS,
            fail_closed=False,
            next_model_name=current_model,
        )

    # 5 — Replan
    if audit.next_action == RetryAction.REPLAN_AND_RECODE:
        return PolicyDecision(
            action=RetryAction.REPLAN_AND_RECODE,
            should_replan=True,
            next_model_name=current_model,
            reason="planner spec violated; replan required",
        )

    # 6 — Retry same role strict (keep model)
    if audit.next_action == RetryAction.RETRY_SAME_ROLE_STRICT:
        return PolicyDecision(
            action=RetryAction.RETRY_SAME_ROLE_STRICT,
            next_model_name=current_model,
            reason="strict retry on same role",
        )

    # 7 — Alternate model rotation
    if audit.next_action == RetryAction.RETRY_ALTERNATE_MODEL:
        try:
            idx = _MODEL_POOL.index(current_model)
        except ValueError:
            idx = -1

        next_idx = idx + 1
        if next_idx >= len(_MODEL_POOL):
            return PolicyDecision(
                action=RetryAction.FAIL_CLOSED,
                fail_closed=True,
                reason=f"no alternate models remaining after {current_model}",
            )

        return PolicyDecision(
            action=RetryAction.RETRY_ALTERNATE_MODEL,
            next_model_name=_MODEL_POOL[next_idx],
            reason=f"switching from {current_model} to {_MODEL_POOL[next_idx]}",
        )

    # 8 — Any remaining FAIL_CLOSED
    return PolicyDecision(
        action=RetryAction.FAIL_CLOSED,
        fail_closed=True,
        reason=str(audit.audit_status),
    )
