from controlplane.invariants import check as evaluate_invariants


def event(
    action,
    target_type="candidate",
    target_id="1",
    result="ok",
    event_id=None,
    ts="2026-05-03T00:00:00",
):
    return {
        "id": event_id,
        "ts": ts,
        "session_id": "session_test",
        "action": action,
        "target_type": target_type,
        "target_id": target_id,
        "target_summary": None,
        "result": result,
        "metadata": {},
    }


def codes(findings):
    return {f.code for f in findings}


def severities(findings):
    return {f.severity for f in findings}


def test_clean_session_returns_no_warnings_or_failures():
    findings = evaluate_invariants([
        event("approve", event_id=1),
        event("promote_candidate", event_id=2),
        event("export", target_type=None, target_id=None, event_id=3),
    ])

    assert "warn" not in severities(findings)
    assert "fail" not in severities(findings)


def test_rollback_present_emits_warning():
    findings = evaluate_invariants([event("rollback")])
    assert "rollback_present" in codes(findings)


def test_fail_present_emits_warning():
    findings = evaluate_invariants([event("clamp", result="error")])
    assert "fail_present" in codes(findings)


def test_approve_then_fail_same_target_emits_warning():
    findings = evaluate_invariants([
        event("confirm_yes", target_id="7", event_id=1),
        event("clamp",   target_id="7", result="error", event_id=2),
    ])
    assert "approve_then_fail_same_target" in codes(findings)


def test_approve_then_fail_different_target_does_not_warn():
    findings = evaluate_invariants([
        event("confirm_yes", target_id="7", event_id=1),
        event("fail", target_id="8", event_id=2),
    ])
    assert "approve_then_fail_same_target" not in codes(findings)


def test_repeated_action_same_target_threshold_works():
    findings = evaluate_invariants([
            event("analyze", target_id="7", event_id=1),
            event("analyze", target_id="7", event_id=2),
            event("analyze", target_id="7", event_id=3),
        ])
    assert "repeated_action_same_target" in codes(findings)


def test_repeated_action_below_threshold_does_not_warn():
    findings = evaluate_invariants([
        event("confirm_yes", target_id="7", event_id=1),
        event("approve", target_id="7", event_id=2),
    ])
    assert "repeated_action_same_target" not in codes(findings)


def test_export_not_final_emits_warning():
    findings = evaluate_invariants([
        event("export", target_type=None, target_id=None, event_id=1),
        event("approve", event_id=2),
    ])
    assert "action_after_export" in codes(findings)


def test_action_after_export_emits_warning():
    findings = evaluate_invariants([
        event("export", target_type=None, target_id=None, event_id=1),
        event("approve", event_id=2),
    ])
    assert "action_after_export" in codes(findings)


def test_promote_clamp_without_candidate_emits_warning():
    findings = evaluate_invariants([
        event("promote_clamp", target_type="clamp", target_id="9", event_id=1),
    ])
    assert "promote_clamp_without_candidate" in codes(findings)


def test_promote_clamp_after_candidate_does_not_warn():
    findings = evaluate_invariants([
        event("promote_candidate", target_type="candidate", target_id="9", event_id=1),
        event("promote_clamp", target_type="clamp", target_id="9", event_id=2),
    ])
    assert "promote_clamp_without_candidate" not in codes(findings)


def test_rollback_without_prior_approval_emits_warning():
    findings = evaluate_invariants([
        event("rollback", target_type="candidate", target_id="2", event_id=1),
    ])
    assert "rollback_without_prior_approval" in codes(findings)


def test_rollback_after_prior_approval_does_not_warn():
    findings = evaluate_invariants([
        event("confirm_yes", target_type="candidate", target_id="2", event_id=1),
        event("rollback", target_type="candidate", target_id="2", event_id=2),
    ])
    assert "rollback_without_prior_approval" not in codes(findings)


def test_empty_session_returns_structured_pass_finding():
    findings = evaluate_invariants([])
    assert findings
    assert "clean_session" in codes(findings)
    assert "pass" in severities(findings)


def test_findings_are_structured_dicts():
    findings = evaluate_invariants([event("fail", event_id=42)])
    assert findings
    finding = findings[0]

    for key in [
        "severity",
        "code",
        "message",
        "action",
        "target_type",
        "target_id",
        "event_id",
        "metadata",
    ]:
        assert hasattr(finding, key)
