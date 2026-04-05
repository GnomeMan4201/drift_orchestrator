# drift_orchestrator

Runtime control system for LLM sessions. Detects reasoning drift, fires policy decisions, rolls back to checkpoints, and continues execution — without stopping the agent.

---

## Demo
```bash
![drift_orchestrator demo](demo_recordings/demo.gif)

To record your own:
```bash
---

## What it does

Wraps an LLM session with a scoring and recovery layer:

1. Each turn is scored for **alpha** (internal coherence) and **divergence** (embedding distance from the prior state)
2. A **policy engine** evaluates both signals and returns `CONTINUE`, `WARN`, or `ROLLBACK`
3. On `ROLLBACK`, the session restores the last known-good checkpoint and resumes
4. The entire session is written to SQLite and available for review

---

## Why this exists

LLM agents fail gradually. A reasoning chain that starts coherent can drift across 10-15 turns without triggering any hard error. By the time the output is visibly wrong, the chain is unsalvageable.

This system puts a control plane around the session. It catches degradation before it compounds.

---

## Core Concepts

| Concept | What it means |
|---|---|
| **Alpha** | Per-turn coherence score (0-1). Computed internally from response structure. |
| **Divergence** | Cosine distance between the current turn embedding and the session centroid. Computed externally via sentence-transformers. |
| **Policy** | Hysteresis-gated decision layer. Evaluates both signals, fires CONTINUE / WARN / ROLLBACK. Avoids thrashing on borderline turns. |
| **Recovery** | On ROLLBACK, the session manager restores the last checkpoint and replays context. Execution continues from that point. |

Alpha and divergence are **independent signals**. Either can trigger rollback. The dual-signal design catches failures that a single internal monitor is blind to.

---

## Example Output
---

## Architecture
---

## What this is not

- Not a guardrail or output filter
- Not a fine-tuning or alignment tool
- Not production-hardened (alpha research)

## What this is

A runtime observability and control layer for LLM sessions. The closest analogy is a circuit breaker for agent reasoning chains: monitors, decides, and recovers without manual intervention.

---

## Requirements
```bash
pip install -r requirements.txt
```

---

## License

MIT. See LICENSE.
