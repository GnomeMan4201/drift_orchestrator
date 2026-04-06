from __future__ import annotations

import json
from pathlib import Path
from typing import Any

MASTER = Path.home() / "research_hub" / "repos" / "drift_orchestrator" / "runtime_signals" / "ai_sec_master.jsonl"

def latest_ai_sec_signal() -> dict[str, Any] | None:
    if not MASTER.exists():
        return None
    lines = [line for line in MASTER.read_text(encoding="utf-8").splitlines() if line.strip()]
    if not lines:
        return None
    try:
        return json.loads(lines[-1])
    except Exception:
        return None

def ai_sec_alpha() -> float | None:
    row = latest_ai_sec_signal()
    if not row:
        return None
    try:
        return float(row.get("alpha"))
    except Exception:
        return None

def ai_sec_summary() -> dict[str, Any]:
    row = latest_ai_sec_signal()
    if not row:
        return {"available": False}
    return {
        "available": True,
        "alpha": row.get("alpha"),
        "stability": row.get("stability"),
        "final_verdict": row.get("final_verdict"),
        "best_phase": row.get("best_phase"),
        "issues": row.get("signals", {}).get("issues", []),
        "score": row.get("signals", {}).get("score"),
    }
