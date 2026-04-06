#!/usr/bin/env python3
import json
import time
from pathlib import Path

LOG = Path("results/trace_log.jsonl")
STATE = Path("results/alerts_state.json")
ALERTS = Path("results/alerts.log")
ALERTS.parent.mkdir(parents=True, exist_ok=True)

def load_state():
    if STATE.exists():
        try:
            return json.loads(STATE.read_text(encoding="utf-8"))
        except Exception:
            pass
    return {"last_line_count": 0}

def save_state(state):
    STATE.write_text(json.dumps(state, indent=2), encoding="utf-8")

def append_alert(msg):
    line = f"[{time.strftime('%Y-%m-%d %H:%M:%S')}] {msg}"
    with ALERTS.open("a", encoding="utf-8") as f:
        f.write(line + "\n")
    print(line)

def main():
    state = load_state()
    if not LOG.exists():
        print("trace log not found")
        return

    lines = LOG.read_text(encoding="utf-8").splitlines()
    new_lines = lines[state["last_line_count"]:]
    state["last_line_count"] = len(lines)

    for line in new_lines:
        if not line.strip():
            continue
        try:
            e = json.loads(line)
        except Exception:
            continue

        drift = float(e.get("drift_score", 0.0) or 0.0)
        inj = float(e.get("inj_score", 0.0) or 0.0)
        blocked = bool(e.get("blocked", False))
        reason = str(e.get("reason", "") or "")
        agent = str(e.get("agent", "unknown"))

        if inj >= 0.4:
            append_alert(f"INJECTION agent={agent} inj={inj} blocked={blocked} reason={reason}")
        if drift >= 0.3:
            append_alert(f"DRIFT agent={agent} drift={drift} blocked={blocked} reason={reason}")
        if "http_error" in reason:
            append_alert(f"GATEWAY agent={agent} reason={reason}")

    save_state(state)

if __name__ == "__main__":
    main()
