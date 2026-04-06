#!/usr/bin/env python3
import json
from pathlib import Path
import networkx as nx

INPUT = Path("results/trace_log.jsonl")
OUT = Path("results/trace_graph.gexf")

G = nx.DiGraph()

def color(blocked, reason):
    if blocked and "drift" in reason:
        return "orange"
    if blocked and "http_error" in reason:
        return "red"
    if blocked:
        return "darkred"
    return "green"

with INPUT.open() as f:
    for i, line in enumerate(f):
        e = json.loads(line)

        agent = e["agent"]
        prompt = e["prompt"][:60]
        blocked = e["blocked"]
        reason = str(e.get("reason") or "")
        drift = float(e.get("drift_score", 0.0))
        inj = float(e.get("inj_score", 0.0))

        a = f"agent:{agent}"
        p = f"prompt:{i}"
        s = f"state:{i}"

        G.add_node(a, type="agent")
        G.add_node(p, type="prompt", text=prompt)
        G.add_node(
            s,
            type="state",
            blocked=blocked,
            reason=reason,
            drift=drift,
            inj=inj,
            viz_color=color(blocked, reason),
            viz_size=10 + drift * 30 + inj * 20,
        )

        G.add_edge(a, p)
        G.add_edge(p, s)

nx.write_gexf(G, OUT)
print("graph rebuilt")
