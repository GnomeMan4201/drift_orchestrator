#!/usr/bin/env python3
import json
import math
from pathlib import Path
import networkx as nx

INPUT = Path("results/trace_log.jsonl")
OUT = Path("results/trace_graph.gexf")

G = nx.DiGraph()

def add_node(name, **attrs):
    if name not in G:
        G.add_node(name, **attrs)

def add_edge(a, b, **attrs):
    G.add_edge(a, b, **attrs)

if not INPUT.exists():
    raise SystemExit("trace_log.jsonl not found")

with INPUT.open(encoding="utf-8") as f:
    for i, line in enumerate(f):
        line = line.strip()
        if not line:
            continue
        e = json.loads(line)

        agent = e.get("agent", "unknown")
        prompt = str(e.get("prompt", ""))[:120]
        inj = float(e.get("inj_score", 0.0) or 0.0)
        drift = float(e.get("drift_score", 0.0) or 0.0)
        blocked = bool(e.get("blocked", False))
        reason = str(e.get("reason", "") or "")
        output = str(e.get("output", "") or "")[:120]

        vec = e.get("embedding") or e.get("vector") or None
        norm = None
        if isinstance(vec, list) and vec:
            try:
                norm = math.sqrt(sum(float(v) * float(v) for v in vec))
            except Exception:
                norm = None

        node_agent = f"agent:{agent}"
        node_prompt = f"prompt:{i}"
        node_state = f"state:{i}"

        add_node(node_agent, node_type="agent", label=agent)
        add_node(node_prompt, node_type="prompt", label=f"{agent}:{i}", text=prompt)
        add_node(
            node_state,
            node_type="state",
            label=f"state:{i}",
            inj=inj,
            drift=drift,
            blocked=blocked,
            reason=reason,
            output=output,
            norm=norm if norm is not None else -1.0,
        )

        add_edge(node_agent, node_prompt, edge_type="issued")
        add_edge(node_prompt, node_state, edge_type="produced")

nx.write_gexf(G, OUT)
print("wrote", OUT)
print("nodes", G.number_of_nodes())
print("edges", G.number_of_edges())
