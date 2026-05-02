"""
ACFC-Safe Calibration Suite — memory_snapshot.py
Builds, freezes, and audits MemorySnapshot instances.
"""

from __future__ import annotations

import json
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from .metrics import RiskPair
from .schemas import (
    CalibrationReason,
    DisagreementEntry,
    FactualSummaryEntry,
    MemorySnapshot,
    RiskMarker,
    ToneShiftMetadata,
    TurnRange,
    ValidatorStatus,
)

_SNAPSHOT_DIR = Path(__file__).parent.parent / "storage" / "snapshots"
_AUDIT_LOG = Path(__file__).parent.parent / "storage" / "audit_log.jsonl"


def build_calibration_reason_from_pairs(
    pairs: list[RiskPair],
    *,
    reason_code: str = "DIRECTIONAL_BLINDNESS",
    rule: str = "3_of_5_blindness_hits",
    description: str = "Calibration triggered by persistent directional evaluator blindness.",
    evidence_refs: list[str],
) -> CalibrationReason:
    blind_turns = [p.turn for p in pairs if p.is_blindness_detected]

    if not blind_turns:
        raise ValueError(
            "build_calibration_reason_from_pairs: no blindness events in supplied pairs."
        )

    return CalibrationReason(
        reason_code=reason_code,
        description=description,
        trigger_turns=blind_turns,
        evidence_refs=evidence_refs,
        rule=rule,
    )


def build_memory_snapshot(
    *,
    session_id: str,
    checkpoint_id: str,
    tone_kernel_id: str,
    pairs: list[RiskPair],
    preserved_original_refs: dict[str, Any],
    factual_summary: list[FactualSummaryEntry] | None = None,
    risk_markers: list[RiskMarker] | None = None,
    tone_shift_metadata: list[ToneShiftMetadata] | None = None,
    calibration_reason: CalibrationReason | None = None,
    validator_status: list[ValidatorStatus] | None = None,
) -> MemorySnapshot:
    if not pairs:
        raise ValueError("build_memory_snapshot requires at least one RiskPair.")

    if preserved_original_refs is None:
        raise ValueError(
            "build_memory_snapshot: preserved_original_refs must not be None. "
            "Pass an empty dict explicitly if there are no refs."
        )

    turns = [p.turn for p in pairs]
    turn_range = TurnRange(start=min(turns), end=max(turns))

    disagreements = [
        DisagreementEntry(
            turn=p.turn,
            live_score=p.live_risk,
            shadow_score=p.shadow_risk,
            classification_decay=p.classification_decay,
            blindness_flag=p.is_blindness_detected,
        )
        for p in pairs
    ]

    return MemorySnapshot(
        session_id=session_id,
        checkpoint_id=checkpoint_id,
        tone_kernel_id=tone_kernel_id,
        turn_range=turn_range,
        factual_summary=factual_summary or [],
        risk_markers=risk_markers or [],
        tone_shift_metadata=tone_shift_metadata or [],
        live_shadow_disagreement_history=disagreements,
        preserved_original_refs=preserved_original_refs,
        rewrite_used=False,
        calibration_reason=calibration_reason,
        validator_status=validator_status or [],
    )


def freeze_snapshot(snapshot: MemorySnapshot, snapshot_dir: Path | None = None) -> Path:
    out_dir = snapshot_dir or _SNAPSHOT_DIR
    out_dir.mkdir(parents=True, exist_ok=True)

    frozen_at = datetime.now(timezone.utc).isoformat()
    ts_tag = snapshot.timestamp.strftime("%Y%m%dT%H%M%S")
    uid = uuid.uuid4().hex[:8]
    filename = f"snapshot_{snapshot.session_id}_{ts_tag}_{uid}.json"
    out_path = out_dir / filename

    if out_path.exists():
        raise FileExistsError(
            f"freeze_snapshot: target already exists and will not be overwritten: {out_path}"
        )

    model_data = json.loads(snapshot.model_dump_json())

    payload = {
        "_metadata": {
            "frozen_at": frozen_at,
            "snapshot_path": str(out_path),
            "acfc_safe_version": snapshot.snapshot_version,
        },
        **model_data,
    }

    out_path.write_text(json.dumps(payload, indent=2), encoding="utf-8")
    return out_path


def append_audit_event(event: dict[str, Any], audit_log: Path | None = None) -> Path:
    log_path = audit_log or _AUDIT_LOG
    log_path.parent.mkdir(parents=True, exist_ok=True)

    if "timestamp" not in event:
        payload = {"timestamp": datetime.now(timezone.utc).isoformat(), **event}
    else:
        payload = dict(event)

    with log_path.open("a", encoding="utf-8") as fh:
        fh.write(json.dumps(payload, separators=(",", ":")) + "\n")

    return log_path
