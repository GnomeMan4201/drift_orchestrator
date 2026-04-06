from __future__ import annotations

import json
from collections import Counter
from pathlib import Path
from typing import Any

from fastapi import FastAPI
from fastapi.responses import HTMLResponse

APP = FastAPI()
MASTER = Path.home() / "research_hub" / "repos" / "drift_orchestrator" / "runtime_signals" / "ai_sec_master.jsonl"

def load_rows() -> list[dict[str, Any]]:
    if not MASTER.exists():
        return []
    rows: list[dict[str, Any]] = []
    for line in MASTER.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line:
            continue
        try:
            rows.append(json.loads(line))
        except Exception:
            continue
    return rows

@APP.get("/api/summary")
def summary() -> dict[str, Any]:
    rows = load_rows()
    verdicts = Counter(r.get("final_verdict", "unknown") for r in rows)
    alphas = [float(r.get("alpha", 0.0)) for r in rows]
    top_issues = Counter()

    for r in rows:
        for issue in r.get("signals", {}).get("issues", []):
            top_issues[issue] += 1

    return {
        "runs": len(rows),
        "verdicts": dict(verdicts),
        "avg_alpha": round(sum(alphas) / len(alphas), 4) if alphas else 0.0,
        "latest_alpha": alphas[-1] if alphas else 0.0,
        "top_issues": top_issues.most_common(12),
    }

@APP.get("/api/timeseries")
def timeseries() -> dict[str, Any]:
    rows = load_rows()
    return {
        "points": [
            {
                "timestamp": r.get("timestamp"),
                "alpha": r.get("alpha", 0.0),
                "stability": r.get("stability", 1.0),
                "score": r.get("signals", {}).get("score", 0),
                "verdict": r.get("final_verdict", "unknown"),
                "best_phase": r.get("best_phase", "unknown"),
            }
            for r in rows
        ]
    }

@APP.get("/", response_class=HTMLResponse)
def index() -> str:
    return """
<!doctype html>
<html>
<head>
  <meta charset="utf-8">
  <title>ai-sec drift dashboard</title>
  <script src="https://cdn.jsdelivr.net/npm/chart.js"></script>
  <style>
    body { font-family: sans-serif; background: #0d1117; color: #e6edf3; margin: 24px; }
    .grid { display: grid; grid-template-columns: repeat(3, 1fr); gap: 16px; }
    .card { background: #161b22; padding: 16px; border-radius: 12px; }
    canvas { background: #161b22; border-radius: 12px; padding: 12px; }
    pre { white-space: pre-wrap; }
  </style>
</head>
<body>
  <h1>ai-sec drift dashboard</h1>
  <div class="grid">
    <div class="card"><h3>Runs</h3><div id="runs">0</div></div>
    <div class="card"><h3>Average α</h3><div id="avg_alpha">0</div></div>
    <div class="card"><h3>Latest α</h3><div id="latest_alpha">0</div></div>
  </div>
  <br>
  <canvas id="alphaChart" height="120"></canvas>
  <br>
  <div class="card">
    <h3>Top issues</h3>
    <pre id="issues"></pre>
  </div>

<script>
async function load() {
  const summary = await fetch('/api/summary').then(r => r.json());
  const timeseries = await fetch('/api/timeseries').then(r => r.json());

  document.getElementById('runs').textContent = summary.runs;
  document.getElementById('avg_alpha').textContent = summary.avg_alpha;
  document.getElementById('latest_alpha').textContent = summary.latest_alpha;
  document.getElementById('issues').textContent =
    summary.top_issues.map(x => `${x[0]}: ${x[1]}`).join('\\n');

  const labels = timeseries.points.map(p => p.timestamp);
  const alpha = timeseries.points.map(p => p.alpha);

  new Chart(document.getElementById('alphaChart'), {
    type: 'line',
    data: {
      labels,
      datasets: [{ label: 'α drift', data: alpha }]
    },
    options: {
      responsive: true,
      scales: { y: { min: 0, max: 1 } }
    }
  });
}
load();
</script>
</body>
</html>
"""

app = APP
