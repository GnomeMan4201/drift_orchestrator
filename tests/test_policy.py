import sys
sys.path.insert(0, ".")

from orchestrator.contracts import (
    AuditResult, AuditStatus, CoderOutput, FailureClass,
    MAX_RETRY_ATTEMPTS, ModelRole, RetryAction,
    RouteDecision, RouterTicket, RiskPosture, TaskType,
    COMPLEXITY_HIGH, PRECISION_HIGH, make_request_id,
)
from orchestrator.policy import decide, PolicyDecision


def _ticket():
    return RouterTicket(
        request_id=make_request_id(),
        original_prompt="clone sherlock",
        normalized_prompt="Implement Sherlock-style username checker.",
        route_decision=RouteDecision.PLANNER,
        task_type=TaskType.TOOL_CLONE,
        complexity=COMPLEXITY_HIGH,
        precision=PRECISION_HIGH,
        risk_posture=RiskPosture.CAUTIOUS,
        needs_decomposition=True,
        needs_verification=True,
        needs_code_validation=True,
        preferred_model_role=ModelRole.PLANNER,
        secondary_model_role=ModelRole.CODER,
        routing_reason="test",
        routing_confidence=0.95,
        forbidden_patterns=[],
        required_outputs=[],
    )


def _audit(status, failure_class, next_action, next_role=ModelRole.CODER, drift=0.3):
    return AuditResult(
        request_id=make_request_id(),
        audit_status=status,
        passed=(status == AuditStatus.PASS),
        failure_class=failure_class,
        drift_score=drift,
        verification_passed=(status == AuditStatus.PASS),
        reasons=[] if status == AuditStatus.PASS else ["test reason"],
        next_action=next_action,
        next_model_role=next_role,
    )


def test_pass_returns_pass_decision():
    ticket = _ticket()
    audit = _audit(AuditStatus.PASS, None, RetryAction.PASS, None, 0.0)
    d = decide(ticket, audit, "mistral:latest", 1)
    assert d.action == RetryAction.PASS
    assert not d.fail_closed
    assert not d.should_replan
    print("[PASS] policy PASS -> PASS decision")


def test_injection_always_fails_closed():
    ticket = _ticket()
    audit = _audit(
        AuditStatus.FAIL_CLOSED,
        FailureClass.RISK_INJECTION,
        RetryAction.FAIL_CLOSED,
        None, 1.0,
    )
    d = decide(ticket, audit, "mistral:latest", 1)
    assert d.fail_closed is True
    assert d.action == RetryAction.FAIL_CLOSED
    print("[PASS] policy RISK_INJECTION -> immediate fail_closed")


def test_injection_fails_closed_even_at_attempt_1():
    ticket = _ticket()
    audit = _audit(
        AuditStatus.FAIL_CLOSED,
        FailureClass.RISK_INJECTION,
        RetryAction.FAIL_CLOSED,
        None, 1.0,
    )
    d = decide(ticket, audit, "mistral:latest", 1)
    assert d.fail_closed is True
    print("[PASS] policy injection fail_closed does not wait for budget")


def test_budget_exhausted_fails_closed():
    ticket = _ticket()
    audit = _audit(
        AuditStatus.RETRY_ALTERNATE_MODEL,
        FailureClass.COMPILE_FAILURE,
        RetryAction.RETRY_ALTERNATE_MODEL,
    )
    d = decide(ticket, audit, "mistral:latest", MAX_RETRY_ATTEMPTS)
    assert d.fail_closed is True
    print("[PASS] policy budget exhausted -> fail_closed")


def test_budget_not_exhausted_does_not_fail():
    ticket = _ticket()
    audit = _audit(
        AuditStatus.RETRY_ALTERNATE_MODEL,
        FailureClass.COMPILE_FAILURE,
        RetryAction.RETRY_ALTERNATE_MODEL,
    )
    d = decide(ticket, audit, "mistral:latest", 1)
    assert not d.fail_closed
    print("[PASS] policy attempt=1 does not fail_closed on compile_failure")


def test_alternate_model_switches_correctly():
    ticket = _ticket()
    audit = _audit(
        AuditStatus.RETRY_ALTERNATE_MODEL,
        FailureClass.GENERIC_FALLBACK,
        RetryAction.RETRY_ALTERNATE_MODEL,
    )
    d = decide(ticket, audit, "mistral:latest", 1)
    assert not d.fail_closed
    assert d.next_model_name == "llama3.1:latest"
    assert not d.should_replan
    print("[PASS] policy RETRY_ALTERNATE_MODEL switches to llama3.1:latest")


def test_alternate_model_second_switch():
    ticket = _ticket()
    audit = _audit(
        AuditStatus.RETRY_ALTERNATE_MODEL,
        FailureClass.GENERIC_FALLBACK,
        RetryAction.RETRY_ALTERNATE_MODEL,
    )
    d = decide(ticket, audit, "llama3.1:latest", 2)
    assert not d.fail_closed
    assert d.next_model_name == "phi3:latest"
    print("[PASS] policy second alternate switch -> phi3:latest")


def test_alternate_model_exhausted_fails_closed():
    ticket = _ticket()
    audit = _audit(
        AuditStatus.RETRY_ALTERNATE_MODEL,
        FailureClass.GENERIC_FALLBACK,
        RetryAction.RETRY_ALTERNATE_MODEL,
    )
    d = decide(ticket, audit, "phi3:latest", 2)
    assert d.fail_closed is True
    print("[PASS] policy no more alternates -> fail_closed")


def test_replan_sets_should_replan():
    ticket = _ticket()
    audit = _audit(
        AuditStatus.REPLAN_AND_RECODE,
        FailureClass.PLANNER_VIOLATION,
        RetryAction.REPLAN_AND_RECODE,
        ModelRole.PLANNER,
    )
    d = decide(ticket, audit, "mistral:latest", 1)
    assert d.should_replan is True
    assert not d.fail_closed
    print("[PASS] policy REPLAN_AND_RECODE sets should_replan=True")


def test_same_role_strict_keeps_model():
    ticket = _ticket()
    audit = _audit(
        AuditStatus.RETRY_SAME_ROLE_STRICT,
        FailureClass.SCHEMA_FAILURE,
        RetryAction.RETRY_SAME_ROLE_STRICT,
    )
    d = decide(ticket, audit, "mistral:latest", 1)
    assert not d.fail_closed
    assert not d.should_replan
    assert d.next_model_name == "mistral:latest"
    print("[PASS] policy RETRY_SAME_ROLE_STRICT keeps same model")


if __name__ == "__main__":
    tests = [(k, v) for k, v in sorted(globals().items()) if k.startswith("test_")]
    passed = 0
    failed = 0
    for name, fn in tests:
        try:
            fn()
            passed += 1
        except Exception as exc:
            print("[FAIL]", name, "->", str(exc))
            failed += 1
    print()
    print(str(passed) + " passed, " + str(failed) + " failed")
    if failed:
        sys.exit(1)
