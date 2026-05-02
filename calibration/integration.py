"""
ACFC-Safe Calibration Suite — integration.py

Wires the full forensic pipeline into a single atomic sequence:

    1. Trigger detects persistent directional blindness.
    2. CalibrationReason is derived from current-window blindness pairs.
    3. MemorySnapshot is constructed and schema-validated.
    4. MemorySnapshot is frozen to a unique file on disk.
    5. Audit events are appended referencing the frozen path.
    6. A ResetToken is issued only after freeze + audit succeed.
    7. Caller presents the ResetToken to reset evaluator state.
"""

from __future__ import annotations

import uuid
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from .audit_log import audit_invariant_violation, audit_snapshot_frozen, audit_trigger_fired
from .memory_snapshot import (
    build_calibration_reason_from_pairs,
    build_memory_snapshot,
    freeze_snapshot,
)
from .schemas import (
    FactualSummaryEntry,
    MemorySnapshot,
    RiskMarker,
    ToneShiftMetadata,
    ValidatorStatus,
)
from .trigger import CalibrationTrigger


@dataclass(frozen=True)
class ResetToken:
    token_id: str
    snapshot_path: Path
    session_id: str
    checkpoint_id: str
    trigger_instance_id: str
    issued_at: datetime


@dataclass(frozen=True)
class CalibrationEvent:
    snapshot: MemorySnapshot
    snapshot_path: Path
    reset_token: ResetToken
    sequence_id: str = field(default_factory=lambda: uuid.uuid4().hex)
    completed_at: datetime = field(default_factory=lambda: datetime.now(timezone.utc))


class GuardedTrigger:
    def __init__(
        self,
        trigger: CalibrationTrigger | None = None,
        *,
        window_size: int = 5,
        required_hits: int = 3,
    ) -> None:
        self._trigger = trigger or CalibrationTrigger(
            window_size=window_size,
            required_hits=required_hits,
        )
        self._instance_id = uuid.uuid4().hex
        self._pending_token: ResetToken | None = None

    def process_turn(self, pair) -> bool:
        return self._trigger.process_turn(pair)

    def reset_with_token(self, token: ResetToken) -> None:
        if token is None:
            raise RuntimeError(
                "GuardedTrigger.reset_with_token: reset requires a ResetToken. "
                "Call process_calibration_event() to obtain one."
            )

        if token.trigger_instance_id != self._instance_id:
            raise RuntimeError(
                "GuardedTrigger.reset_with_token: token was issued for a different "
                "trigger instance."
            )

        if not token.snapshot_path.exists():
            raise RuntimeError(
                f"GuardedTrigger.reset_with_token: snapshot file does not exist at "
                f"{token.snapshot_path}. Refusing reset."
            )

        if self._pending_token is None or token.token_id != self._pending_token.token_id:
            raise RuntimeError(
                "GuardedTrigger.reset_with_token: token does not match the pending "
                "token for this trigger instance. Tokens are single-use."
            )

        self._pending_token = None
        self._trigger.reset()

    def _accept_token(self, token: ResetToken) -> None:
        self._pending_token = token

    @property
    def inner(self) -> CalibrationTrigger:
        return self._trigger

    @property
    def instance_id(self) -> str:
        return self._instance_id


def process_calibration_event(
    *,
    trigger: GuardedTrigger,
    session_id: str,
    checkpoint_id: str,
    tone_kernel_id: str,
    preserved_original_refs: dict[str, Any],
    evidence_refs: list[str],
    snapshot_dir: Path | None = None,
    audit_log: Path | None = None,
    factual_summary: list[FactualSummaryEntry] | None = None,
    risk_markers: list[RiskMarker] | None = None,
    tone_shift_metadata: list[ToneShiftMetadata] | None = None,
    validator_status: list[ValidatorStatus] | None = None,
    reason_code: str = "DIRECTIONAL_BLINDNESS",
    rule: str = "3_of_5_blindness_hits",
    description: str = "Calibration triggered by persistent directional evaluator blindness.",
) -> CalibrationEvent:
    pairs = list(trigger.inner.history)

    if not trigger.inner.is_armed:
        raise RuntimeError(
            f"process_calibration_event: trigger for session '{session_id}' is not armed. "
            f"Need at least {trigger.inner.window_size} turns before calibration can proceed."
        )

    if trigger.inner.hit_count < trigger.inner.required_hits:
        raise RuntimeError(
            f"process_calibration_event: trigger for session '{session_id}' has only "
            f"{trigger.inner.hit_count}/{trigger.inner.window_size} blindness hits in "
            f"the current window; requires {trigger.inner.required_hits}."
        )

    window_blind_pairs = [
        p for p in trigger.inner.current_window if p.is_blindness_detected
    ]

    calibration_reason = build_calibration_reason_from_pairs(
        window_blind_pairs,
        reason_code=reason_code,
        rule=rule,
        description=description,
        evidence_refs=evidence_refs,
    )

    snapshot = build_memory_snapshot(
        session_id=session_id,
        checkpoint_id=checkpoint_id,
        tone_kernel_id=tone_kernel_id,
        pairs=pairs,
        preserved_original_refs=preserved_original_refs,
        factual_summary=factual_summary,
        risk_markers=risk_markers,
        tone_shift_metadata=tone_shift_metadata,
        calibration_reason=calibration_reason,
        validator_status=validator_status,
    )

    snapshot_path = freeze_snapshot(snapshot, snapshot_dir=snapshot_dir)

    try:
        audit_snapshot_frozen(
            session_id=session_id,
            checkpoint_id=checkpoint_id,
            snapshot_path=str(snapshot_path),
            audit_log=audit_log,
        )
        audit_trigger_fired(
            session_id=session_id,
            checkpoint_id=checkpoint_id,
            hit_count=trigger.inner.hit_count,
            window_size=trigger.inner.window_size,
            audit_log=audit_log,
        )
    except Exception as exc:
        try:
            audit_invariant_violation(
                session_id=session_id,
                violation_detail=f"Audit log write failed after successful freeze: {exc}",
                audit_log=audit_log,
            )
        except Exception:
            pass
        raise

    token = ResetToken(
        token_id=uuid.uuid4().hex,
        snapshot_path=snapshot_path,
        session_id=session_id,
        checkpoint_id=checkpoint_id,
        trigger_instance_id=trigger.instance_id,
        issued_at=datetime.now(timezone.utc),
    )
    trigger._accept_token(token)

    return CalibrationEvent(
        snapshot=snapshot,
        snapshot_path=snapshot_path,
        reset_token=token,
    )
