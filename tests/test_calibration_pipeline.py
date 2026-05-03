"""
tests/test_calibration_pipeline.py
===================================
Dedicated pytest suite for the ACFC-Safe calibration pipeline.

All RiskPair values are inert synthetic scores — no exploit strings,
no real payloads, no real session data.
"""
from __future__ import annotations

import json
import tempfile
from pathlib import Path

import pytest

from calibration.integration import (
    CalibrationEvent,
    GuardedTrigger,
    ResetToken,
    process_calibration_event,
)
from calibration.metrics import RiskPair
from calibration.pipeline import drop_session, observe
from calibration.schemas import (
    DECAY_MIN,
    LIVE_RISK_MAX,
    SHADOW_RISK_MIN,
    MemorySnapshot,
    TurnRange,
)
from replay_cli import verify_audit_log


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _blind_pair(turn: int) -> RiskPair:
    """A RiskPair that meets all blindness conditions."""
    return RiskPair(turn=turn, live_risk=0.20, shadow_risk=0.85)


def _sighted_pair(turn: int) -> RiskPair:
    """A RiskPair that does NOT trigger blindness."""
    return RiskPair(turn=turn, live_risk=0.80, shadow_risk=0.10)


def _make_trigger(window_size: int = 5, required_hits: int = 3) -> GuardedTrigger:
    return GuardedTrigger(window_size=window_size, required_hits=required_hits)


def _arm_trigger(trigger: GuardedTrigger, n_blind: int = 5) -> None:
    """Feed enough blind pairs to arm the trigger."""
    for i in range(1, n_blind + 1):
        trigger.process_turn(_blind_pair(i))


def _fire_event(
    trigger: GuardedTrigger,
    snap_dir: Path,
    audit_log: Path,
    session_id: str = "test-session",
) -> CalibrationEvent:
    return process_calibration_event(
        trigger=trigger,
        session_id=session_id,
        checkpoint_id="test-ckpt",
        tone_kernel_id="test-tk",
        preserved_original_refs={"ref_1": "synthetic evidence"},
        evidence_refs=["ref_1"],
        snapshot_dir=snap_dir,
        audit_log=audit_log,
    )


# ---------------------------------------------------------------------------
# Happy path
# ---------------------------------------------------------------------------

class TestHappyPath:
    def test_snapshot_frozen_and_exists(self, tmp_path):
        snap_dir = tmp_path / "snapshots"
        audit_log = tmp_path / "audit.jsonl"
        trigger = _make_trigger()
        _arm_trigger(trigger)

        event = _fire_event(trigger, snap_dir, audit_log)

        assert event.snapshot_path.exists()
        data = json.loads(event.snapshot_path.read_text())
        assert data["rewrite_used"] is False
        assert "_metadata" in data
        assert data["_metadata"]["snapshot_path"] == str(event.snapshot_path)

    def test_reset_token_issued(self, tmp_path):
        snap_dir = tmp_path / "snapshots"
        audit_log = tmp_path / "audit.jsonl"
        trigger = _make_trigger()
        _arm_trigger(trigger)

        event = _fire_event(trigger, snap_dir, audit_log)

        assert isinstance(event.reset_token, ResetToken)
        assert event.reset_token.trigger_instance_id == trigger.instance_id
        assert event.reset_token.snapshot_path.exists()

    def test_reset_succeeds_with_valid_token(self, tmp_path):
        snap_dir = tmp_path / "snapshots"
        audit_log = tmp_path / "audit.jsonl"
        trigger = _make_trigger()
        _arm_trigger(trigger)

        event = _fire_event(trigger, snap_dir, audit_log)
        trigger.reset_with_token(event.reset_token)

        assert trigger.inner.history == []

    def test_audit_log_contains_required_events(self, tmp_path):
        snap_dir = tmp_path / "snapshots"
        audit_log = tmp_path / "audit.jsonl"
        trigger = _make_trigger()
        _arm_trigger(trigger)

        event = _fire_event(trigger, snap_dir, audit_log)
        trigger.reset_with_token(event.reset_token)

        lines = [json.loads(l) for l in audit_log.read_text().strip().splitlines()]
        event_types = [l["event_type"] for l in lines]
        assert "SNAPSHOT_FROZEN" in event_types
        assert "TRIGGER_FIRED" in event_types

    def test_snapshot_frozen_before_trigger_fired_in_audit(self, tmp_path):
        """Audit ordering: SNAPSHOT_FROZEN must appear before TRIGGER_FIRED."""
        snap_dir = tmp_path / "snapshots"
        audit_log = tmp_path / "audit.jsonl"
        trigger = _make_trigger()
        _arm_trigger(trigger)

        event = _fire_event(trigger, snap_dir, audit_log)
        trigger.reset_with_token(event.reset_token)

        lines = [json.loads(l) for l in audit_log.read_text().strip().splitlines()]
        event_types = [l["event_type"] for l in lines]
        assert event_types.index("SNAPSHOT_FROZEN") < event_types.index("TRIGGER_FIRED")

    def test_full_risk_history_preserved_in_snapshot(self, tmp_path):
        snap_dir = tmp_path / "snapshots"
        audit_log = tmp_path / "audit.jsonl"
        trigger = _make_trigger(window_size=5, required_hits=3)
        # Feed 7 turns total — history should contain all 7
        for i in range(1, 8):
            trigger.process_turn(_blind_pair(i))

        event = _fire_event(trigger, snap_dir, audit_log, session_id="history-test")
        trigger.reset_with_token(event.reset_token)

        data = json.loads(event.snapshot_path.read_text())
        disagreements = data["live_shadow_disagreement_history"]
        assert len(disagreements) == 7

    def test_trigger_turns_derived_from_current_window_only(self, tmp_path):
        """trigger_turns should contain only turns from the current window's blind pairs."""
        snap_dir = tmp_path / "snapshots"
        audit_log = tmp_path / "audit.jsonl"
        trigger = _make_trigger(window_size=5, required_hits=3)

        # Turns 1-3: blind
        for i in range(1, 4):
            trigger.process_turn(_blind_pair(i))
        # Turns 4-5: sighted (not blind, window has 3 blind + 2 sighted = 3 hits, armed)
        trigger.process_turn(_sighted_pair(4))
        trigger.process_turn(_sighted_pair(5))

        assert trigger.inner.is_armed  # 3/5 blind hits

        event = _fire_event(trigger, snap_dir, audit_log, session_id="window-test")
        trigger.reset_with_token(event.reset_token)

        data = json.loads(event.snapshot_path.read_text())
        reason = data["calibration_reason"]
        # trigger_turns must be a subset of the window (turns 1-5), specifically the blind ones
        assert set(reason["trigger_turns"]).issubset({1, 2, 3, 4, 5})
        # Must not include sighted turns
        assert 4 not in reason["trigger_turns"]
        assert 5 not in reason["trigger_turns"]

    def test_replay_verifier_passes_on_valid_pair(self, tmp_path):
        snap_dir = tmp_path / "snapshots"
        audit_log = tmp_path / "audit.jsonl"
        trigger = _make_trigger()
        _arm_trigger(trigger)

        event = _fire_event(trigger, snap_dir, audit_log)
        trigger.reset_with_token(event.reset_token)

        result = verify_audit_log(audit_log, snap_dir)
        assert result.passed, result.violations
        assert result.snapshot_frozen_count == 1
        assert result.trigger_fired_count == 1


# ---------------------------------------------------------------------------
# Reset token safety
# ---------------------------------------------------------------------------

class TestResetTokenSafety:
    def test_reset_fails_with_no_token(self, tmp_path):
        snap_dir = tmp_path / "snapshots"
        audit_log = tmp_path / "audit.jsonl"
        trigger = _make_trigger()
        _arm_trigger(trigger)
        event = _fire_event(trigger, snap_dir, audit_log)

        with pytest.raises(RuntimeError, match="reset requires a ResetToken"):
            trigger.reset_with_token(None)

    def test_reset_fails_with_wrong_trigger_instance(self, tmp_path):
        snap_dir = tmp_path / "snapshots"
        audit_log = tmp_path / "audit.jsonl"

        trigger_a = _make_trigger()
        _arm_trigger(trigger_a)
        event_a = _fire_event(trigger_a, snap_dir, audit_log, session_id="sess-a")

        trigger_b = _make_trigger()
        _arm_trigger(trigger_b)
        event_b = _fire_event(trigger_b, snap_dir, audit_log, session_id="sess-b")

        with pytest.raises(RuntimeError, match="different trigger instance"):
            trigger_a.reset_with_token(event_b.reset_token)

    def test_reset_fails_if_snapshot_deleted(self, tmp_path):
        snap_dir = tmp_path / "snapshots"
        audit_log = tmp_path / "audit.jsonl"
        trigger = _make_trigger()
        _arm_trigger(trigger)
        event = _fire_event(trigger, snap_dir, audit_log)

        # Delete the snapshot after token issuance
        event.snapshot_path.unlink()

        with pytest.raises(RuntimeError, match="snapshot file does not exist"):
            trigger.reset_with_token(event.reset_token)

    def test_token_is_single_use(self, tmp_path):
        snap_dir = tmp_path / "snapshots"
        audit_log = tmp_path / "audit.jsonl"
        trigger = _make_trigger()
        _arm_trigger(trigger)
        event = _fire_event(trigger, snap_dir, audit_log)

        trigger.reset_with_token(event.reset_token)  # First use succeeds

        # Second use must fail — trigger is no longer armed and has no pending token
        with pytest.raises(RuntimeError):
            trigger.reset_with_token(event.reset_token)


# ---------------------------------------------------------------------------
# Trigger arming guards
# ---------------------------------------------------------------------------

class TestTriggerArmingGuards:
    def test_calibration_fails_if_trigger_not_armed(self, tmp_path):
        snap_dir = tmp_path / "snapshots"
        audit_log = tmp_path / "audit.jsonl"
        trigger = _make_trigger()
        # Only 2 turns — not armed
        trigger.process_turn(_blind_pair(1))
        trigger.process_turn(_blind_pair(2))

        with pytest.raises(RuntimeError, match="not armed"):
            _fire_event(trigger, snap_dir, audit_log)

    def test_calibration_fails_if_window_has_insufficient_hits(self, tmp_path):
        """Armed by count but window has fewer than required_hits blind pairs."""
        snap_dir = tmp_path / "snapshots"
        audit_log = tmp_path / "audit.jsonl"
        trigger = _make_trigger(window_size=5, required_hits=3)

        # Feed 5 turns: only 2 blind — not enough hits despite window full
        trigger.process_turn(_blind_pair(1))
        trigger.process_turn(_blind_pair(2))
        trigger.process_turn(_sighted_pair(3))
        trigger.process_turn(_sighted_pair(4))
        trigger.process_turn(_sighted_pair(5))

        assert not trigger.inner.is_armed  # 2/5 < required_hits=3

        with pytest.raises(RuntimeError):
            _fire_event(trigger, snap_dir, audit_log)


# ---------------------------------------------------------------------------
# Schema invariants
# ---------------------------------------------------------------------------

class TestSchemaInvariants:
    def test_snapshot_rewrite_used_is_always_false(self, tmp_path):
        snap_dir = tmp_path / "snapshots"
        audit_log = tmp_path / "audit.jsonl"
        trigger = _make_trigger()
        _arm_trigger(trigger)
        event = _fire_event(trigger, snap_dir, audit_log)
        trigger.reset_with_token(event.reset_token)

        data = json.loads(event.snapshot_path.read_text())
        assert data["rewrite_used"] is False

    def test_snapshot_version_is_acfc_safe(self, tmp_path):
        snap_dir = tmp_path / "snapshots"
        audit_log = tmp_path / "audit.jsonl"
        trigger = _make_trigger()
        _arm_trigger(trigger)
        event = _fire_event(trigger, snap_dir, audit_log)
        trigger.reset_with_token(event.reset_token)

        data = json.loads(event.snapshot_path.read_text())
        assert data["snapshot_version"] == "acfc_safe_v0.1"

    def test_blindness_flag_matches_threshold_logic(self, tmp_path):
        """Each DisagreementEntry.blindness_flag must match schema invariant."""
        snap_dir = tmp_path / "snapshots"
        audit_log = tmp_path / "audit.jsonl"
        trigger = _make_trigger()
        _arm_trigger(trigger)
        event = _fire_event(trigger, snap_dir, audit_log)
        trigger.reset_with_token(event.reset_token)

        data = json.loads(event.snapshot_path.read_text())
        for d in data["live_shadow_disagreement_history"]:
            expected = (
                d["shadow_score"] >= SHADOW_RISK_MIN
                and d["live_score"] <= LIVE_RISK_MAX
                and round(d["classification_decay"], 10) >= DECAY_MIN
            )
            assert d["blindness_flag"] == expected, (
                f"turn {d['turn']}: blindness_flag={d['blindness_flag']} "
                f"expected={expected}"
            )

    def test_classification_decay_equals_shadow_minus_live(self, tmp_path):
        snap_dir = tmp_path / "snapshots"
        audit_log = tmp_path / "audit.jsonl"
        trigger = _make_trigger()
        _arm_trigger(trigger)
        event = _fire_event(trigger, snap_dir, audit_log)
        trigger.reset_with_token(event.reset_token)

        data = json.loads(event.snapshot_path.read_text())
        for d in data["live_shadow_disagreement_history"]:
            expected = round(d["shadow_score"] - d["live_score"], 10)
            actual = round(d["classification_decay"], 10)
            assert actual == expected, (
                f"turn {d['turn']}: decay={actual} != shadow-live={expected}"
            )


# ---------------------------------------------------------------------------
# Pipeline observe() interface
# ---------------------------------------------------------------------------

class TestPipelineObserve:
    def test_observe_returns_none_before_window_full(self, tmp_path):
        session = "obs-test-1"
        for i in range(1, 5):
            result = observe(
                i, live_risk=0.20, shadow_risk=0.85,
                session_id=session, window_text=f"turn {i}",
                action="CONTINUE",
                snapshot_dir=tmp_path / "snap",
                audit_log=tmp_path / "audit.jsonl",
            )
            assert result is None
        drop_session(session)

    def test_observe_fires_on_fifth_blind_turn(self, tmp_path):
        session = "obs-test-2"
        result = None
        for i in range(1, 6):
            result = observe(
                i, live_risk=0.20, shadow_risk=0.85,
                session_id=session, window_text=f"turn {i}",
                action="INJECT",
                snapshot_dir=tmp_path / "snap",
                audit_log=tmp_path / "audit.jsonl",
            )
        assert result is not None
        assert result.snapshot_path.exists()
        drop_session(session)

    def test_observe_skips_silently_when_shadow_risk_none(self, tmp_path):
        session = "obs-test-3"
        result = observe(
            1, live_risk=0.20, shadow_risk=None,
            session_id=session, window_text="turn 1",
            action="CONTINUE",
            snapshot_dir=tmp_path / "snap",
            audit_log=tmp_path / "audit.jsonl",
        )
        assert result is None
        drop_session(session)

    def test_observe_sessions_are_isolated(self, tmp_path):
        """Two sessions accumulate history independently."""
        for i in range(1, 5):
            observe(i, live_risk=0.20, shadow_risk=0.85, session_id="iso-a",
                    snapshot_dir=tmp_path / "snap", audit_log=tmp_path / "a.jsonl")
            observe(i, live_risk=0.20, shadow_risk=0.85, session_id="iso-b",
                    snapshot_dir=tmp_path / "snap", audit_log=tmp_path / "b.jsonl")

        result_a = observe(5, live_risk=0.20, shadow_risk=0.85, session_id="iso-a",
                           snapshot_dir=tmp_path / "snap", audit_log=tmp_path / "a.jsonl")
        result_b = observe(5, live_risk=0.20, shadow_risk=0.85, session_id="iso-b",
                           snapshot_dir=tmp_path / "snap", audit_log=tmp_path / "b.jsonl")

        assert result_a is not None
        assert result_b is not None
        assert result_a.snapshot_path != result_b.snapshot_path
        drop_session("iso-a")
        drop_session("iso-b")


# ---------------------------------------------------------------------------
# Package contract
# ---------------------------------------------------------------------------

class TestPackageContract:
    def test_reset_token_not_in_calibration_all(self):
        import calibration
        assert "ResetToken" not in calibration.__all__
