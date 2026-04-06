from __future__ import annotations
from dataclasses import dataclass, asdict

def clamp01(x: float) -> float:
    return max(0.0, min(1.0, float(x)))

@dataclass
class StateVector:
    host_risk: float = 0.0
    network_restrictiveness: float = 0.0
    tool_trust: float = 1.0
    anomaly_level: float = 0.0

    def normalized(self) -> "StateVector":
        return StateVector(
            host_risk=clamp01(self.host_risk),
            network_restrictiveness=clamp01(self.network_restrictiveness),
            tool_trust=clamp01(self.tool_trust),
            anomaly_level=clamp01(self.anomaly_level),
        )

    def to_dict(self) -> dict:
        return asdict(self.normalized())

@dataclass
class OperationalPosture:
    name: str
    max_drift: float
    sanitization_level: str
    tool_access: str
    local_only: bool
    notes: str = ""

    def to_dict(self) -> dict:
        return asdict(self)
