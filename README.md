# drift_orchestrator

Runtime control system for LLM sessions. Detects reasoning drift, fires
policy decisions, rolls back to checkpoints, and continues execution
without stopping the agent.

---

## Demo

    git clone https://github.com/GnomeMan4201/drift_orchestrator.git
    cd drift_orchestrator
    pip install -r requirements.txt
    ./scripts/demo.sh

![drift_orchestrator demo](demo_recordings/demo.gif)

    ./scripts/record_demo.sh   # to record your own

---

## What it does

1. Each turn is scored for **alpha** (internal coherence) and **divergence**
   (embedding distance from prior session state)
2. A **policy engine** evaluates both and returns CONTINUE, WARN, or ROLLBACK
3. On ROLLBACK, the session restores the last checkpoint and resumes
4. Everything is written to SQLite for post-session review

---

## Why this exists

LLM agents fail gradually. A reasoning chain that starts coherent can
drift across 10-15 turns without triggering any hard error. By the time
output is visibly wrong, the chain is unsalvageable.

This system catches degradation before it compounds.

---

## Core Concepts

| Concept    | What it means                                                  |
|------------|----------------------------------------------------------------|
| Alpha      | Per-turn coherence score (0-1). Internal signal.               |
| Divergence | Cosine distance from session centroid. External embedding signal. |
| Policy     | Hysteresis-gated engine. Fires CONTINUE / WARN / ROLLBACK.    |
| Recovery   | Restores last checkpoint, replays context, resumes execution.  |

Alpha and divergence are independent signals. Either can trigger rollback.
The dual-signal design catches failures a single monitor is blind to.

---

## Example Output

    [demo-abc123]  turn=1   alpha=0.91  div=0.08  -> CONTINUE
    [demo-abc123]  turn=2   alpha=0.87  div=0.12  -> CONTINUE
    [demo-abc123]  turn=3   alpha=0.81  div=0.19  -> CONTINUE
    [demo-abc123]  turn=4   alpha=0.61  div=0.39  -> WARN
    [demo-abc123]  turn=5   alpha=0.36  div=0.54  -> ROLLBACK
      restoring checkpoint @ turn=3
      replaying context (3 turns)
      recovery complete - resuming
    [demo-abc123]  turn=6   alpha=0.89  div=0.11  -> CONTINUE
    [demo-abc123]  turn=7   alpha=0.92  div=0.07  -> CONTINUE
    [demo-abc123]  turn=8   alpha=0.94  div=0.05  -> CONTINUE

---

## Architecture

    agent_runtime.py
        |
        v
    evaluator.py         <- alpha + divergence scoring
        |
        v
    policy.py            <- CONTINUE / WARN / ROLLBACK
        |              |
        v              v
    session_manager  recovery.py     <- restore + replay
        |
        v
    sqlite_store.py      <- full flight record

---

## What this is not

- Not a guardrail or output filter
- Not a fine-tuning or alignment tool
- Not production-hardened (alpha research)

## What this is

A circuit breaker for LLM agent reasoning chains. Monitors turn-by-turn
coherence, fires policy decisions, orchestrates checkpoint restore and
replay — without stopping or restarting the session.

---

## Requirements

    pip install -r requirements.txt

---

## License

MIT. See LICENSE.
