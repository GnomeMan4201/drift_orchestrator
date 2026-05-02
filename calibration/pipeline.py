"""
calibration/pipeline.py
=======================
Session-keyed calibration registry for the live drift pipeline.

Bridges evaluator.py's per-window (alpha, embed_score) observations into
the ACFC-Safe CalibrationTrigger/GuardedTrigger machinery.

Design:
  - One GuardedTrigger per session_id, lazily created.
  - observe() is called once per evaluated window, after the policy decision.
  - Returns CalibrationEvent if the trigger fires and a snapshot is frozen,
    None otherwise.
  - Calibration is forensic — it never blocks or alters the policy action.
  - embed_score is the shadow evaluator. If None (embedding unavailable),
    the observation is skipped silently.
"""

from __future__ import annotations

import logging
from pathlib import Path
from typing import Any

from .integration import CalibrationEvent, GuardedTrigger, process_calibration_event
from .metrics import RiskPair
from .audit_log import write_audit_event

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Module-level session registry
# ---------------------------------------------------------------------------

_registry: dict[str, GuardedTrigger] = {}

_SNAPSHOT_DIR = Path(__file__).parent.parent / "storage" / "snapshots"
_AUDIT_LOG    = Path(__file__).parent.parent / "storage" / "audit_log.jsonl"


def _get_trigger(session_id: str) -> GuardedTrigger:
    """Return existing GuardedTrigger for session, or create one."""
    if session_id not in _registry:
        _registry[session_id] = GuardedTrigger(window_size=5, required_hits=3)
        logger.debug("calibration.pipeline: new trigger for session %s", session_id[:8])
    return _registry[session_id]


def drop_session(session_id: str) -> None:
    """Remove a session's trigger from the registry (call on session teardown)."""
    _registry.pop(session_id, None)


# ---------------------------------------------------------------------------
# Main integration point
# ---------------------------------------------------------------------------

def observe(
    turn: int,
    live_risk: float,
    shadow_risk: float | None,
    *,
    session_id: str,
    window_text: str = "",
    action: str = "",
    snapshot_dir: Path | None = None,
    audit_log: Path | None = None,
) -> CalibrationEvent | None:
    """
    Record one observation for a session. Call once per evaluated window
    after the PolicyEngine has already made its decision.

    Parameters
    ----------
    turn        : last_turn_index from evaluator.py
    live_risk   : alpha (composite internal drift score)
    shadow_risk : embed_score (independent embedding evaluator score)
                  If None, the observation is skipped.
    session_id  : session identifier
    window_text : verbatim window text, stored as preserved evidence
    action      : policy action string, for audit context only
    snapshot_dir: override for snapshot storage path (useful in tests)
    audit_log   : override for audit log path (useful in tests)

    Returns
    -------
    CalibrationEvent if trigger fired and snapshot was frozen, else None.
    """
    if shadow_risk is None:
        logger.debug(
            "calibration.pipeline: skipping turn %d (shadow_risk unavailable)", turn
        )
        return None

    trigger = _get_trigger(session_id)
    pair = RiskPair(turn=turn, live_risk=live_risk, shadow_risk=shadow_risk)
    armed = trigger.process_turn(pair)

    if not armed:
        return None

    # Trigger is armed — build evidence refs from window text
    ref_key = f"window_turn_{turn}"
    preserved_refs: dict[str, Any] = {ref_key: window_text} if window_text else {ref_key: ""}

    try:
        event = process_calibration_event(
            trigger=trigger,
            session_id=session_id,
            checkpoint_id=f"auto_{turn}",
            tone_kernel_id="live_pipeline",
            preserved_original_refs=preserved_refs,
            evidence_refs=[ref_key],
            snapshot_dir=snapshot_dir or _SNAPSHOT_DIR,
            audit_log=audit_log or _AUDIT_LOG,
            reason_code="DIRECTIONAL_BLINDNESS",
            rule="3_of_5_blindness_hits",
            description=(
                f"Live pipeline calibration triggered at turn {turn}. "
                f"Policy action was {action!r}. "
                f"live_risk={live_risk:.4f}, shadow_risk={shadow_risk:.4f}."
            ),
        )
        trigger.reset_with_token(event.reset_token)
        logger.info(
            "calibration.pipeline: snapshot frozen for session %s at turn %d -> %s",
            session_id[:8], turn, event.snapshot_path,
        )
        return event

    except RuntimeError as exc:
        # Trigger armed but invariants not met (e.g. not enough blindness hits
        # in current window after full-history build) — log and continue.
        logger.warning(
            "calibration.pipeline: trigger armed but event failed for session %s "
            "turn %d: %s", session_id[:8], turn, exc
        )
        return None

    except Exception as exc:
        # Snapshot/audit IO failure — never crash the evaluator
        logger.error(
            "calibration.pipeline: unexpected error for session %s turn %d: %s",
            session_id[:8], turn, exc, exc_info=True,
        )
        write_audit_event(
            {
                "event_type": "PIPELINE_ERROR",
                "session_id": session_id,
                "turn": turn,
                "error": str(exc),
            },
            audit_log=audit_log or _AUDIT_LOG,
        )
        return None
