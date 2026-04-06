#!/usr/bin/env python3
import json
from pathlib import Path
from fastapi import FastAPI
from fastapi.responses import HTMLResponse, JSONResponse

app = FastAPI()
LOG = Path("results/trace_log.jsonl")

def load_events():
    if not LOG.exists():
        return []
    rows = []
    with LOG.open(encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if line:
                try:
                    rows.append(json.loads(line))
                except Exception:
                    pass
    return rows

def build_graph(events):
    nodes = []
    edges = []
    seen = set()

    def add_node(node):
        nid = node["id"]
        if nid not in seen:
            seen.add(nid)
            nodes.append(node)

    for i, e in enumerate(events):
        agent = str(e.get("agent", "unknown"))
        prompt = str(e.get("prompt", ""))[:80]
        output = str(e.get("output", ""))[:120]
        blocked = bool(e.get("blocked", False))
        reason = str(e.get("reason", "") or "")
        inj = float(e.get("inj_score", 0.0) or 0.0)
        drift = float(e.get("drift_score", 0.0) or 0.0)

        if blocked and "drift" in reason:
            color = "#ff8800"
        elif blocked and "http_error" in reason:
            color = "#ff3333"
        elif blocked:
            color = "#cc2222"
        else:
            color = "#33cc66"

        size = 10 + (inj * 25.0) + (drift * 35.0)

        a = f"agent:{agent}"
        p = f"prompt:{i}"
        s = f"state:{i}"

        add_node({
            "id": a,
            "label": agent,
            "kind": "agent",
            "color": "#cc0000",
            "size": 18,
            "meta": {"agent": agent},
        })
        add_node({
            "id": p,
            "label": f"prompt {i}",
            "kind": "prompt",
            "color": "#888888",
            "size": 10,
            "meta": {"prompt": prompt},
        })
        add_node({
            "id": s,
            "label": f"{'BLOCK' if blocked else 'OK'} {i}",
            "kind": "state",
            "color": color,
            "size": size,
            "meta": {
                "prompt": prompt,
                "output": output,
                "blocked": blocked,
                "reason": reason,
                "inj_score": inj,
                "drift_score": drift,
            },
        })

        edges.append({"source": a, "target": p, "kind": "issued"})
        edges.append({"source": p, "target": s, "kind": "produced"})

    return {"nodes": nodes, "edges": edges, "events": len(events)}

@app.get("/api/trace")
def api_trace():
    events = load_events()
    return JSONResponse(build_graph(events))

@app.get("/", response_class=HTMLResponse)
def home():
    return """
<!doctype html>
<html>
<head>
<meta charset="utf-8">
<title>LANimals Live Graph</title>
<style>
html, body {
  margin: 0;
  padding: 0;
  background: #0b0b0b;
  color: #e8e8e8;
  font-family: monospace;
  height: 100%;
}
#wrap {
  display: grid;
  grid-template-columns: 1fr 340px;
  height: 100vh;
}
#left {
  position: relative;
  overflow: hidden;
  border-right: 1px solid #2a2a2a;
}
#right {
  padding: 14px;
  overflow-y: auto;
}
#title {
  position: absolute;
  left: 14px;
  top: 10px;
  z-index: 10;
  color: #ff3b3b;
  font-weight: bold;
  font-size: 22px;
  letter-spacing: 1px;
  text-shadow: 0 0 8px rgba(255,0,0,0.4);
}
#subtitle {
  position: absolute;
  left: 16px;
  top: 40px;
  z-index: 10;
  color: #b0b0b0;
  font-size: 12px;
}
#stats {
  margin-bottom: 14px;
  padding: 10px;
  border: 1px solid #2f2f2f;
  border-radius: 10px;
  background: #111;
}
.card {
  margin-bottom: 12px;
  padding: 10px;
  border: 1px solid #2f2f2f;
  border-radius: 10px;
  background: #111;
}
.small { color: #aaa; font-size: 12px; }
canvas { display: block; width: 100%; height: 100%; }
.badge {
  display: inline-block;
  padding: 2px 8px;
  border-radius: 999px;
  margin-left: 6px;
  font-size: 11px;
}
.ok { background: #163a22; color: #7dffad; }
.blocked { background: #4a1515; color: #ffb0b0; }
.drift { background: #4a3312; color: #ffcb7a; }
.http { background: #4a1515; color: #ff8c8c; }
</style>
</head>
<body>
<div id="wrap">
  <div id="left">
    <div id="title">LANimals</div>
    <div id="subtitle">live execution graph / control-plane telemetry</div>
    <canvas id="graph"></canvas>
  </div>
  <div id="right">
    <div id="stats"></div>
    <div id="details" class="card">click a node</div>
  </div>
</div>

<script>
const canvas = document.getElementById("graph");
const ctx = canvas.getContext("2d");
const details = document.getElementById("details");
const stats = document.getElementById("stats");

let nodes = [];
let edges = [];
let byId = {};
let selected = null;
let W = 0, H = 0;

function resize() {
  const rect = canvas.parentElement.getBoundingClientRect();
  W = rect.width;
  H = rect.height;
  canvas.width = W * devicePixelRatio;
  canvas.height = H * devicePixelRatio;
  canvas.style.width = W + "px";
  canvas.style.height = H + "px";
  ctx.setTransform(devicePixelRatio, 0, 0, devicePixelRatio, 0, 0);
}
window.addEventListener("resize", resize);
resize();

function seedPositions(graphNodes) {
  const agents = graphNodes.filter(n => n.kind === "agent");
  const prompts = graphNodes.filter(n => n.kind === "prompt");
  const states = graphNodes.filter(n => n.kind === "state");

  agents.forEach((n, i) => {
    n.x = 120;
    n.y = 120 + i * 180;
    n.vx = 0; n.vy = 0;
  });

  prompts.forEach((n, i) => {
    n.x = W * 0.45 + (i % 2) * 20;
    n.y = 80 + i * 70;
    n.vx = 0; n.vy = 0;
  });

  states.forEach((n, i) => {
    n.x = W * 0.75 + (i % 3) * 15;
    n.y = 80 + i * 70;
    n.vx = 0; n.vy = 0;
  });
}

function updateGraph(data) {
  const old = byId;
  nodes = data.nodes.map(n => {
    const prev = old[n.id] || {};
    return {...n, x: prev.x ?? 100, y: prev.y ?? 100, vx: prev.vx ?? 0, vy: prev.vy ?? 0};
  });
  edges = data.edges;
  byId = {};
  nodes.forEach(n => byId[n.id] = n);

  if (nodes.every(n => n.x === 100 && n.y === 100)) {
    seedPositions(nodes);
  }

  const blocked = nodes.filter(n => n.kind === "state" && n.meta && n.meta.blocked).length;
  const drift = nodes.filter(n => n.kind === "state" && n.meta && String(n.meta.reason || "").includes("drift")).length;
  const http = nodes.filter(n => n.kind === "state" && n.meta && String(n.meta.reason || "").includes("http_error")).length;

  stats.innerHTML = `
    <b>events</b>: ${data.events}<br>
    <b>nodes</b>: ${nodes.length}<br>
    <b>blocked</b>: ${blocked}<br>
    <b>drift blocks</b>: ${drift}<br>
    <b>http errors</b>: ${http}
  `;
}

function simulate() {
  const kRepel = 6000;
  const kSpring = 0.012;
  const damp = 0.85;

  for (let i = 0; i < nodes.length; i++) {
    const a = nodes[i];
    for (let j = i + 1; j < nodes.length; j++) {
      const b = nodes[j];
      let dx = a.x - b.x;
      let dy = a.y - b.y;
      let d2 = dx*dx + dy*dy + 0.01;
      let f = kRepel / d2;
      let d = Math.sqrt(d2);
      dx /= d; dy /= d;
      a.vx += dx * f;
      a.vy += dy * f;
      b.vx -= dx * f;
      b.vy -= dy * f;
    }
  }

  edges.forEach(e => {
    const a = byId[e.source], b = byId[e.target];
    if (!a || !b) return;
    const dx = b.x - a.x;
    const dy = b.y - a.y;
    a.vx += dx * kSpring;
    a.vy += dy * kSpring;
    b.vx -= dx * kSpring;
    b.vy -= dy * kSpring;
  });

  nodes.forEach(n => {
    if (n.kind === "agent") n.x += (100 - n.x) * 0.08;
    if (n.kind === "prompt") n.x += (W * 0.45 - n.x) * 0.03;
    if (n.kind === "state") n.x += (W * 0.78 - n.x) * 0.03;

    n.vx *= damp;
    n.vy *= damp;
    n.x += n.vx * 0.01;
    n.y += n.vy * 0.01;

    n.x = Math.max(40, Math.min(W - 40, n.x));
    n.y = Math.max(40, Math.min(H - 40, n.y));
  });
}

function draw() {
  ctx.clearRect(0, 0, W, H);

  edges.forEach(e => {
    const a = byId[e.source], b = byId[e.target];
    if (!a || !b) return;
    ctx.strokeStyle = "#333";
    ctx.lineWidth = 1;
    ctx.beginPath();
    ctx.moveTo(a.x, a.y);
    ctx.lineTo(b.x, b.y);
    ctx.stroke();
  });

  nodes.forEach(n => {
    ctx.beginPath();
    ctx.fillStyle = n.color || "#888";
    ctx.arc(n.x, n.y, n.size || 8, 0, Math.PI * 2);
    ctx.fill();

    if (selected && selected.id === n.id) {
      ctx.strokeStyle = "#fff";
      ctx.lineWidth = 2;
      ctx.beginPath();
      ctx.arc(n.x, n.y, (n.size || 8) + 4, 0, Math.PI * 2);
      ctx.stroke();
    }

    ctx.fillStyle = "#ddd";
    ctx.font = "11px monospace";
    ctx.fillText(n.label || n.id, n.x + 10, n.y + 4);
  });
}

function animate() {
  simulate();
  draw();
  requestAnimationFrame(animate);
}

canvas.addEventListener("click", ev => {
  const rect = canvas.getBoundingClientRect();
  const x = ev.clientX - rect.left;
  const y = ev.clientY - rect.top;
  selected = null;
  for (const n of nodes) {
    const dx = x - n.x;
    const dy = y - n.y;
    if ((dx*dx + dy*dy) <= ((n.size || 8) + 6) ** 2) {
      selected = n;
      break;
    }
  }
  if (!selected) {
    details.innerHTML = "click a node";
    return;
  }

  const m = selected.meta || {};
  const reason = String(m.reason || "");
  const badge = m.blocked
    ? `<span class="badge ${reason.includes('drift') ? 'drift' : (reason.includes('http_error') ? 'http' : 'blocked')}">blocked</span>`
    : `<span class="badge ok">ok</span>`;

  details.innerHTML = `
    <div><b>${selected.label || selected.id}</b> ${badge}</div>
    <div class="small">kind=${selected.kind || ""}</div>
    <hr style="border-color:#222">
    <div><b>prompt</b><br>${String(m.prompt || selected.text || "").replace(/</g, "&lt;")}</div>
    <br>
    <div><b>output</b><br>${String(m.output || "").replace(/</g, "&lt;")}</div>
    <br>
    <div class="small">reason=${reason}</div>
    <div class="small">inj=${m.inj_score ?? m.inj ?? ""} drift=${m.drift_score ?? m.drift ?? ""}</div>
  `;
});

async function refresh() {
  try {
    const res = await fetch("/api/trace");
    const data = await res.json();
    updateGraph(data);
  } catch (e) {}
}
setInterval(refresh, 2000);
refresh();
animate();
</script>
</body>
</html>
"""

if __name__ == "__main__":
    import uvicorn
    uvicorn.run("ui.lanimals_live:app", host="127.0.0.1", port=8099, reload=False)
