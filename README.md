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

## Example output
```bash
python3 evaluator.py examples/hallucination_test.jsonl
```
```
[TURN   3] Window 0:  rho=0.5704,  alpha=0.5889
  CLAIM:  Run nmap --ultra-scan --ghost-mode ...
  STATUS: YELLOW   POLICY: Level 3 ROLLBACK
  SCORES: hallucination_risk=1.0000, hallucination_count=5.0000

[TURN   5] Window 2:  rho=0.5972,  alpha=0.7114
  CLAIM:  import magiclib ...
  STATUS: RED   POLICY: Level 3 ROLLBACK

--- SESSION SUMMARY ---
  Turns evaluated : 11
  Avg alpha (drift): 0.6550
  Max alpha (drift): 0.7239
  Policy actions   : {'ROLLBACK': 11}
```

Findings logged to SQLite:
- 23x `invented_api` HIGH
- 12x `invented_cli_flag` HIGH
- 1x `invented_import` HIGH
- 1x `missing_import` HIGH

## Roadmap

- v0.2.0 — branch recovery: restore last green checkpoint, continue from stable state
- ~~v0.3.0 — sentence-transformers embeddings~~ ✓ shipped
- v0.4.0 — multi-session comparison + drift delta reporting
- v0.5.0 — live mode: stdin streaming eval with policy signals
