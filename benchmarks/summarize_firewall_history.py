#!/usr/bin/env python3
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

results_dir = ROOT / "results"
files = sorted(results_dir.glob("firewall_benchmark_*.json"))
if not files:
    raise SystemExit("no benchmark json files found")

rows = []
for f in files:
    data = json.loads(f.read_text(encoding="utf-8"))
    rows.append({
        "timestamp": data["timestamp"],
        "total": data["total"],
        "passed": data["passed"],
        "failed": data["failed"],
        "pass_rate": data["pass_rate"],
        "duration_sec": data["duration_sec"],
    })

out = results_dir / "firewall_benchmark_history.json"
out.write_text(json.dumps(rows, indent=2), encoding="utf-8")
print(out)
print(json.dumps(rows, indent=2))
