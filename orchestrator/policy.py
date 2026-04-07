from __future__ import annotations
from orchestrator.contracts import (
    AuditResult, AuditStatus, FailureClass,
    MAX_RETRY_ATTEMPTS, ModelRole, RetryAction, RouterTicket,
)
from orchestrator.registry import registry
from analysis.trace_logger import log_retry, log_block


class PolicyDecision:
    def __init__(
        self,
        action: RetryAction,
        next_model_name: str | None,
        should_replan: bool,
        fail_closed: bool,
        reason: str,
    ) -> None:
        self.action = action
        self.next_model_name = next_model_name
        self.should_replan = should_replan
        self.fail_closed = fail_closed
        self.reason = reason

    def __repr__(self) -> str:
        return (
            "PolicyDecision(action=" + self.action.value
            + " next_model=" + str(self.next_model_name)
            + " replan=" + str(self.should_replan)
            + " fail_closed=" + str(self.fail_closed) + ")"
        )


def decide(
    ticket: RouterTicket,
    audit_result: AuditResult,
    current_model_name: str,
    attempt: int,
) -> PolicyDecision:
    if audit_result.audit_status == AuditStatus.PASS:
        return PolicyDecision(
            action=RetryAction.PASS,
            next_model_name=current_model_name,
            should_replan=False,
            fail_closed=False,
            reason="audit passed",
        )

    if audit_result.failure_class == FailureClass.RISK_INJECTION:
        log_block(
            request_id=ticket.request_id,
            reason="risk_injection detected",
            failure_class=FailureClass.RISK_INJECTION.value,
            attempts=attempt,
        )
        return PolicyDecision(
            action=RetryAction.FAIL_CLOSED,
            next_model_name=None,
            should_replan=False,
            fail_closed=True,
            reason="risk_injection: immediate fail-closed",
        )

    if attempt >= MAX_RETRY_ATTEMPTS:
        log_block(
            request_id=ticket.request_id,
            reason="retry budget exhausted",
            failure_class=(
                audit_result.failure_class.value
                if audit_result.failure_class else "unknown"
            ),
            attempts=attempt,
        )
        return PolicyDecision(
            action=RetryAction.FAIL_CLOSED,
            next_model_name=None,
            should_replan=False,
            fail_closed=True,
            reason="retry budget exhausted after " + str(attempt) + " attempts",
        )

    action = audit_result.next_action
    failure_class = audit_result.failure_class

    if action == RetryAction.REPLAN_AND_RECODE:
        next_model = registry.next_model(ModelRole.CODER, current_model_name)
        next_name = next_model.name if next_model else current_model_name
        log_retry(
            request_id=ticket.request_id,
            attempt=attempt,
            action=action.value,
            from_model=current_model_name,
            to_model=next_name,
            failure_class=failure_class.value if failure_class else "unknown",
        )
        return PolicyDecision(
            action=action,
            next_model_name=next_name,
            should_replan=True,
            fail_closed=False,
            reason="planner_violation: re-plan and re-code",
        )

    if action == RetryAction.RETRY_ALTERNATE_MODEL:
        next_model = registry.next_model(ModelRole.CODER, current_model_name)
        if next_model is None:
            log_block(
                request_id=ticket.request_id,
                reason="no alternate model available",
                failure_class=failure_class.value if failure_class else "unknown",
                attempts=attempt,
            )
            return PolicyDecision(
                action=RetryAction.FAIL_CLOSED,
                next_model_name=None,
                should_replan=False,
                fail_closed=True,
                reason="no alternate coder model available",
            )
        log_retry(
            request_id=ticket.request_id,
            attempt=attempt,
            action=action.value,
            from_model=current_model_name,
            to_model=next_model.name,
            failure_class=failure_class.value if failure_class else "unknown",
        )
        return PolicyDecision(
            action=action,
            next_model_name=next_model.name,
            should_replan=False,
            fail_closed=False,
            reason="switching to alternate coder: " + next_model.name,
        )

    if action == RetryAction.RETRY_SAME_ROLE_STRICT:
        log_retry(
            request_id=ticket.request_id,
            attempt=attempt,
            action=action.value,
            from_model=current_model_name,
            to_model=current_model_name,
            failure_class=failure_class.value if failure_class else "unknown",
        )
        return PolicyDecision(
            action=action,
            next_model_name=current_model_name,
            should_replan=False,
            fail_closed=False,
            reason="retry same role with stricter constraints",
        )

    log_block(
        request_id=ticket.request_id,
        reason="unknown retry action: " + action.value,
        failure_class=failure_class.value if failure_class else "unknown",
        attempts=attempt,
    )
    return PolicyDecision(
        action=RetryAction.FAIL_CLOSED,
        next_model_name=None,
        should_replan=False,
        fail_closed=True,
        reason="unhandled retry action: " + action.value,
    )
