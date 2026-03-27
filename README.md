# drift_orchestrator

Runtime drift control and hallucination verification for LLM session analysis.

## What it does

Evaluates conversation JSONL files using a sliding window pipeline that computes:

- **ρ (rho)** — composite density score (entropy, TTR, sentence length, code density)
- **α (alpha)** — drift score: weighted composite of rho, semantic drift, anchor drift, verifier risk, hallucination risk, repetition
- **Policy** — hysteresis engine: CONTINUE / INJECT / REGENERATE / ROLLBACK
- **Hard override** — RED findings (invented APIs, ghost flags, fake imports) force immediate ROLLBACK regardless of alpha

## Structure
```
drift_orchestrator/
  evaluator.py          # main pipeline entry point
  session_manager.py    # session/branch/turn/checkpoint management
  sqlite_store.py       # SQLite flight recorder (7 tables)
  metrics.py            # CompositeDensityScorer, sliding windows, repetition
  embeddings.py         # hash-vector stub (replaceable with sentence-transformers)
  policy.py             # hysteresis engine with hard override
  report.py             # terminal Drift Map renderer
  utils.py              # shared helpers
  verifier/
    python_imports.py   # importlib validation, stdlib-gated
    python_signatures.py # AST signature extraction (code blocks only)
    cli_flags.py        # invented flag detection
    hallucination.py    # fabricated API / module / flag detection
    findings.py         # severity-graded finding emitter
```

## Usage
```bash
python3 evaluator.py sample.jsonl
python3 evaluator.py high_drift.jsonl
python3 evaluator.py hallucination_test.jsonl
bash run_eval.sh [optional_file.jsonl]
```

## Input format

JSONL with `role` and `content` fields:
```json
{"role": "user", "content": "..."}
{"role": "assistant", "content": "..."}
```

## Policy thresholds

| Threshold | Value | Action |
|-----------|-------|--------|
| tau_warn_low | 0.45 | sustained state |
| tau_warn_high | 0.55 | INJECT |
| tau_rb_low | 0.65 | sustained state |
| tau_rb_high | 0.75 | ROLLBACK |
| RED finding | any | hard ROLLBACK |

## Alpha weights

| Signal | Weight |
|--------|--------|
| rho_density | 0.15 |
| d_goal | 0.25 |
| d_anchor | 0.20 |
| risk_verify | 0.10 |
| hallucination | 0.20 |
| repetition | 0.10 |

## Verified against

- `sample.jsonl` — coherent Python tooling session → all CONTINUE
- `high_drift.jsonl` — topic-pivot stress test → INJECT/REGENERATE/ROLLBACK
- `hallucination_test.jsonl` — fabricated APIs + ghost flags → ROLLBACK every turn

## Part of LANimals / badBANANA research infrastructure
