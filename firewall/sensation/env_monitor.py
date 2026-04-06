from __future__ import annotations
import json
from pathlib import Path
from firewall.sensation.schemas import StateVector

TRACE_PATH = Path("results/trace_log.jsonl")
LANIMALS_STATE_PATH = Path("results/lanimals_state.json")

def _read_json(path: Path) -> dict:
    if not path.exists():
        return {}
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        return {}

def _recent_trace_metrics() -> dict:
    if not TRACE_PATH.exists():
        return {"blocked_ratio": 0.0, "avg_inj": 0.0, "avg_drift": 0.0}

    rows = []
    for line in TRACE_PATH.read_text(encoding="utf-8").splitlines()[-25:]:
        line = line.strip()
        if not line:
            continue
        try:
            rows.append(json.loads(line))
        except Exception:
            continue

    if not rows:
        return {"blocked_ratio": 0.0, "avg_inj": 0.0, "avg_drift": 0.0}

    blocked_ratio = sum(1 for r in rows if r.get("blocked")) / len(rows)
    avg_inj = sum(float(r.get("inj_score", 0.0) or 0.0) for r in rows) / len(rows)
    avg_drift = sum(float(r.get("drift_score", 0.0) or 0.0) for r in rows) / len(rows)
    return {
        "blocked_ratio": blocked_ratio,
        "avg_inj": avg_inj,
        "avg_drift": avg_drift,
    }

def collect_state() -> StateVector:
    trace = _recent_trace_metrics()
    ext = _read_json(LANIMALS_STATE_PATH)

    host_risk = max(
        float(ext.get("host_risk", 0.0) or 0.0),
        float(ext.get("anomaly_level", 0.0) or 0.0) * 0.7,
        trace["blocked_ratio"] * 0.6,
    )

    network_restrictiveness = max(
        float(ext.get("network_restrictiveness", 0.0) or 0.0),
        0.8 if ext.get("local_only") else 0.0,
    )

    tool_trust = float(ext.get("tool_trust", 1.0) or 1.0)
    anomaly_level = max(
        float(ext.get("anomaly_level", 0.0) or 0.0),
        trace["avg_inj"],
        trace["avg_drift"],
    )

    return StateVector(
        host_risk=host_risk,
        network_restrictiveness=network_restrictiveness,
        tool_trust=tool_trust,
        anomaly_level=anomaly_level,
    ).normalized()
