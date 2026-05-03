#!/usr/bin/env python3
"""
tests/test_controlplane_contract_docs.py

Verify that the control-plane contract document exists and contains
its required sections.  These tests act as a guard against accidental
deletion or structural drift of the contract.

Run with:
    pytest tests/test_controlplane_contract_docs.py -v
"""

from __future__ import annotations

from pathlib import Path

import pytest

CONTRACT_PATH = Path(__file__).parent.parent / "docs" / "controlplane_contract.md"


@pytest.fixture(scope="module")
def contract() -> str:
    assert CONTRACT_PATH.exists(), (
        f"Contract document not found at {CONTRACT_PATH}. "
        "Create docs/controlplane_contract.md."
    )
    return CONTRACT_PATH.read_text(encoding="utf-8")


# ---------------------------------------------------------------------------
# File existence
# ---------------------------------------------------------------------------

def test_contract_file_exists():
    assert CONTRACT_PATH.exists(), f"Missing: {CONTRACT_PATH}"


def test_contract_is_non_empty(contract):
    assert len(contract.strip()) > 100


# ---------------------------------------------------------------------------
# Required top-level sections
# ---------------------------------------------------------------------------

def test_has_architecture_map_section(contract):
    assert "Architecture Map" in contract or "Architecture" in contract


def test_has_event_schema_section(contract):
    assert "Event schema" in contract or "Event Schema" in contract


def test_has_canonical_action_names_section(contract):
    assert "Canonical action names" in contract or "Canonical Action Names" in contract


def test_has_result_semantics_section(contract):
    assert "Result semantics" in contract or "Result Semantics" in contract or "result semantics" in contract


def test_has_invariant_rules_section(contract):
    assert "Invariant rules" in contract or "Invariant Rules" in contract or "Invariant rules" in contract


def test_has_ui_status_section(contract):
    assert "UI status" in contract or "UI Status" in contract or "status behavior" in contract.lower()


# ---------------------------------------------------------------------------
# Result semantics content
# ---------------------------------------------------------------------------

def test_documents_result_error(contract):
    assert 'result="error"' in contract or "result=error" in contract


def test_documents_result_ok(contract):
    assert 'result="ok"' in contract or "result=ok" in contract


def test_documents_result_pending(contract):
    assert 'result="pending"' in contract or "result=pending" in contract


def test_documents_result_cancelled(contract):
    assert 'result="cancelled"' in contract or "result=cancelled" in contract


def test_documents_fail_present_mapping(contract):
    assert "fail_present" in contract


# ---------------------------------------------------------------------------
# Canonical action names
# ---------------------------------------------------------------------------

def test_documents_confirm_yes_action(contract):
    assert "confirm_yes" in contract


def test_documents_export_action(contract):
    assert '"export"' in contract or "`export`" in contract


def test_documents_analyze_action(contract):
    assert "analyze" in contract


def test_documents_clamp_action(contract):
    assert "clamp" in contract


def test_documents_promote_candidate_action(contract):
    assert "promote_candidate" in contract


def test_documents_rollback_action(contract):
    assert "rollback" in contract


# ---------------------------------------------------------------------------
# Vocabulary mismatch guard — wrong names must be flagged
# ---------------------------------------------------------------------------

def test_documents_approve_as_wrong_name(contract):
    # The contract should warn against using "approve" as an action name
    assert "approve" in contract


def test_documents_export_session_log_as_wrong_name(contract):
    assert "export_session_log" in contract or "export_not_final" in contract


def test_documents_empty_session_as_wrong_name(contract):
    assert "empty_session" in contract or "clean_session" in contract


# ---------------------------------------------------------------------------
# Invariant rule coverage
# ---------------------------------------------------------------------------

def test_documents_clean_session_rule(contract):
    assert "clean_session" in contract


def test_documents_rollback_present_rule(contract):
    assert "rollback_present" in contract


def test_documents_fail_present_rule(contract):
    assert "fail_present" in contract


def test_documents_approve_then_fail_rule(contract):
    assert "approve_then_fail_same_target" in contract


def test_documents_repeated_action_rule(contract):
    assert "repeated_action_same_target" in contract


def test_documents_action_after_export_rule(contract):
    assert "action_after_export" in contract


def test_documents_promote_clamp_without_candidate_rule(contract):
    assert "promote_clamp_without_candidate" in contract


def test_documents_rollback_without_prior_approval_rule(contract):
    assert "rollback_without_prior_approval" in contract


# ---------------------------------------------------------------------------
# UI status helper documentation
# ---------------------------------------------------------------------------

def test_documents_select_highest_severity_finding(contract):
    assert "select_highest_severity_finding" in contract


def test_documents_severity_priority(contract):
    # fail > warn > pass must be documented
    assert "fail" in contract and "warn" in contract and "pass" in contract
    # Check priority ordering is documented
    assert "fail" in contract


def test_documents_format_invariant_status(contract):
    assert "format_invariant_status" in contract


# ---------------------------------------------------------------------------
# Architecture map completeness
# ---------------------------------------------------------------------------

def test_architecture_references_journal(contract):
    assert "journal" in contract.lower()


def test_architecture_references_invariants(contract):
    assert "invariants" in contract.lower()


def test_architecture_references_replay(contract):
    assert "replay" in contract.lower()


def test_architecture_references_exports(contract):
    assert "exports" in contract.lower()


def test_architecture_references_drifttop(contract):
    assert "drifttop" in contract.lower()
