from __future__ import annotations
from firewall.sensation.schemas import StateVector, OperationalPosture

def derive_posture(state: StateVector) -> OperationalPosture:
    s = state.normalized()

    severity = max(
        s.host_risk,
        s.anomaly_level,
        s.network_restrictiveness,
        1.0 - s.tool_trust,
    )

    if severity >= 0.85:
        return OperationalPosture(
            name="LOCKDOWN",
            max_drift=0.05,
            sanitization_level="strict",
            tool_access="none",
            local_only=True,
            notes="High-risk posture. Minimize capability and prefer rollback.",
        )

    if severity >= 0.60:
        return OperationalPosture(
            name="HIGH_RESTRICTION",
            max_drift=0.12,
            sanitization_level="high",
            tool_access="local_only",
            local_only=True,
            notes="Elevated caution. Restrict tools and tighten drift budget.",
        )

    if severity >= 0.35:
        return OperationalPosture(
            name="CAUTIOUS",
            max_drift=0.22,
            sanitization_level="medium",
            tool_access="limited",
            local_only=False,
            notes="Moderate caution. Allow execution with tighter guardrails.",
        )

    return OperationalPosture(
        name="NORMAL",
        max_drift=0.30,
        sanitization_level="standard",
        tool_access="standard",
        local_only=False,
        notes="Normal operating posture.",
    )
