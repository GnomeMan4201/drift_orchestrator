"""
ACFC-Safe Calibration Suite — schemas.py
Immutable evidence schema layer. All invariants are enforced at model-validation time.
Original evidence is never rewritten, paraphrased, sanitized, or replaced.
"""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Any, Literal

from pydantic import BaseModel, Field, model_validator


class TurnRange(BaseModel):
    """Inclusive turn span covered by a snapshot."""

    start: int = Field(..., ge=0)
    end: int = Field(..., ge=0)

    @model_validator(mode="after")
    def start_lte_end(self) -> "TurnRange":
        if self.start > self.end:
            raise ValueError(
                f"TurnRange invariant violated: start ({self.start}) > end ({self.end})"
            )
        return self


class FactualSummaryEntry(BaseModel):
    claim_id: str
    text: str
    source_turns: list[str] = Field(..., min_length=1)
    risk_bearing: Literal[False] = False

    model_config = {"frozen": True}


class RiskMarker(BaseModel):
    marker_id: str
    turn: int
    label: str
    confidence: float = Field(..., ge=0.0, le=1.0)
    evidence_ref: str

    model_config = {"frozen": True}


class ToneShiftMetadata(BaseModel):
    shift_id: str
    description: str
    source_turns: list[str] = Field(..., min_length=1)
    delta_score: float

    model_config = {"frozen": True}


class DisagreementEntry(BaseModel):
    turn: int
    live_score: float = Field(..., ge=0.0, le=1.0)
    shadow_score: float = Field(..., ge=0.0, le=1.0)
    classification_decay: float
    blindness_flag: bool

    model_config = {"frozen": True}


class CalibrationReason(BaseModel):
    reason_code: str
    description: str
    trigger_turns: list[int] = Field(..., min_length=1)
    evidence_refs: list[str] = Field(..., min_length=1)
    rule: str

    model_config = {"frozen": True}


class ValidatorStatus(BaseModel):
    validator_id: str
    passed: bool
    notes: str
    is_rewrite_accepted: Literal[False] = False

    model_config = {"frozen": True}


SHADOW_RISK_MIN: float = 0.75
LIVE_RISK_MAX: float = 0.40
DECAY_MIN: float = 0.35


class MemorySnapshot(BaseModel):
    snapshot_version: str = Field(default="acfc_safe_v0.1")
    session_id: str
    checkpoint_id: str
    tone_kernel_id: str

    timestamp: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
    turn_range: TurnRange

    factual_summary: list[FactualSummaryEntry]
    risk_markers: list[RiskMarker]
    tone_shift_metadata: list[ToneShiftMetadata]

    live_shadow_disagreement_history: list[DisagreementEntry]

    preserved_original_refs: dict[str, Any]

    rewrite_used: Literal[False] = False

    calibration_reason: CalibrationReason | None = None
    validator_status: list[ValidatorStatus] = Field(default_factory=list)

    model_config = {"frozen": True}

    @model_validator(mode="after")
    def enforce_invariants(self) -> "MemorySnapshot":
        ref_keys = set(self.preserved_original_refs.keys())
        disagreement_turns = {d.turn for d in self.live_shadow_disagreement_history}

        if self.rewrite_used is not False:
            raise ValueError("INVARIANT VIOLATED: rewrite_used must always be False.")

        for rm in self.risk_markers:
            if rm.evidence_ref not in ref_keys:
                raise ValueError(
                    f"INVARIANT VIOLATED: risk_marker '{rm.marker_id}' has evidence_ref "
                    f"'{rm.evidence_ref}' not found in preserved_original_refs."
                )
            if not (self.turn_range.start <= rm.turn <= self.turn_range.end):
                raise ValueError(
                    f"INVARIANT VIOLATED: risk_marker '{rm.marker_id}' at turn {rm.turn} "
                    f"falls outside turn_range [{self.turn_range.start}, {self.turn_range.end}]."
                )

        for fs in self.factual_summary:
            for st in fs.source_turns:
                if st not in ref_keys:
                    raise ValueError(
                        f"INVARIANT VIOLATED: factual_summary '{fs.claim_id}' has source_turn "
                        f"'{st}' not found in preserved_original_refs."
                    )

        for ts in self.tone_shift_metadata:
            for st in ts.source_turns:
                if st not in ref_keys:
                    raise ValueError(
                        f"INVARIANT VIOLATED: tone_shift '{ts.shift_id}' has source_turn "
                        f"'{st}' not found in preserved_original_refs."
                    )

        for d in self.live_shadow_disagreement_history:
            if not (self.turn_range.start <= d.turn <= self.turn_range.end):
                raise ValueError(
                    f"INVARIANT VIOLATED: disagreement at turn {d.turn} falls outside "
                    f"turn_range [{self.turn_range.start}, {self.turn_range.end}]."
                )

            expected_decay = round(d.shadow_score - d.live_score, 10)
            actual_decay = round(d.classification_decay, 10)
            if actual_decay != expected_decay:
                raise ValueError(
                    f"INVARIANT VIOLATED: disagreement at turn {d.turn} has "
                    f"classification_decay={d.classification_decay!r}, "
                    f"expected {expected_decay!r} (shadow_score - live_score)."
                )

            expected_blindness = (
                d.shadow_score >= SHADOW_RISK_MIN
                and d.live_score <= LIVE_RISK_MAX
                and d.classification_decay >= DECAY_MIN
            )
            if d.blindness_flag != expected_blindness:
                raise ValueError(
                    f"INVARIANT VIOLATED: disagreement at turn {d.turn} has "
                    f"blindness_flag={d.blindness_flag!r}, expected {expected_blindness!r} "
                    f"(shadow≥{SHADOW_RISK_MIN}, live≤{LIVE_RISK_MAX}, decay≥{DECAY_MIN})."
                )

        if self.calibration_reason is not None:
            missing_turns = [
                t for t in self.calibration_reason.trigger_turns
                if t not in disagreement_turns
            ]
            if missing_turns:
                raise ValueError(
                    f"INVARIANT VIOLATED: calibration_reason.trigger_turns {missing_turns} "
                    f"not present in live_shadow_disagreement_history turns: "
                    f"{sorted(disagreement_turns)}."
                )

            for ref in self.calibration_reason.evidence_refs:
                if ref not in ref_keys:
                    raise ValueError(
                        f"INVARIANT VIOLATED: calibration_reason evidence_ref '{ref}' "
                        f"not found in preserved_original_refs."
                    )

            disagreement_map = {d.turn: d for d in self.live_shadow_disagreement_history}
            for t in self.calibration_reason.trigger_turns:
                entry = disagreement_map.get(t)
                if entry is not None and not entry.blindness_flag:
                    raise ValueError(
                        f"INVARIANT VIOLATED: calibration_reason.trigger_turns includes "
                        f"turn {t} which has blindness_flag=False in disagreement history. "
                        f"Only turns where blindness was detected may be recorded as trigger causes."
                    )

        return self
