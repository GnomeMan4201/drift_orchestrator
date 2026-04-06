from __future__ import annotations
from firewall.sensation.schemas import OperationalPosture, StateVector

def build_policy_header(posture: OperationalPosture, state: StateVector) -> str:
    s = state.normalized()
    return (
        f"[POSTURE:{posture.name}] "
        f"[MAX_DRIFT:{posture.max_drift:.2f}] "
        f"[SANITIZATION:{posture.sanitization_level}] "
        f"[TOOL_ACCESS:{posture.tool_access}] "
        f"[LOCAL_ONLY:{str(posture.local_only).lower()}] "
        f"[HOST_RISK:{s.host_risk:.2f}] "
        f"[NET_RESTRICT:{s.network_restrictiveness:.2f}] "
        f"[TOOL_TRUST:{s.tool_trust:.2f}] "
        f"[ANOMALY:{s.anomaly_level:.2f}]"
    )

def inject_context(prompt: str, posture: OperationalPosture, state: StateVector) -> str:
    header = build_policy_header(posture, state)
    return f"{header}\n[TASK] {prompt}"
