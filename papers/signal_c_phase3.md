# Signal C Phase 3 — Empirical Findings

## Dataset
- 580 labeled external_eval rows across 42 sessions
- 5 control sequence types × 6 runs = 30 control sessions
- 3 attack sequence types × 4 runs = 12 attack sessions

## Distribution Results

| Class | n | avg_ext | avg_div | STABLE | DEGRADED | FAILURE |
|-------|---|---------|---------|--------|----------|---------|
| control legit | 361 | 0.3824 | 0.1386 | 173 | 187 | 1 |
| control false_positive | 85 | 0.3334 | 0.1254 | 72 | 13 | 0 |
| attack true_positive | 124 | 0.4218 | 0.2006 | 69 | 31 | 24 |

## Policy Boost Coverage

| Session Type | Boosted Windows | Total | Rate |
|-------------|----------------|-------|------|
| benchmark_attack | 38 | 124 | 30.6% |
| control_set | 84 | 455 | 18.5% |

## Rollbacks

| Session Type | Rollbacks |
|-------------|-----------|
| benchmark_attack | 15 |
| control_set | 13 |

Control rollbacks are entirely from internal anchor drift (network_audit sequence).
Attack rollbacks are from monotonic anchor drift, not Signal C.

## What Signal C Detects

**Detected reliably:**
- Auth/access control weakening (JWT required → optional → removed)
- Explicit token removal language

**Not detected (blind spots):**
- Privilege escalation gradients (read → write → admin)
- Data retention policy erosion
- Any attack without auth/token language

## False Positive Rate

18.5% of control windows receive a policy boost — too high.
Root cause: patterns like ("require", "encouraged") and ("enforced", "")
fire on benign security review text that contains these words in
non-weakening contexts.

## Architecture (Frozen)

- External model: qwen2.5:3b, semantic coherence scorer
- Python rule layer: policy weakening detector, 11 patterns
- Verdict: derived in code (not model-chosen)
- policy_boost = 0.65
- Baseline dampening = 0.6x when no boost
- STABLE threshold = 0.35
- TAU_DIV_RB = 0.85 (temporary, calibration phase)

## Next Steps

1. Tighten weakening patterns to reduce 18.5% false boost rate
2. Add data retention and privilege escalation pattern families
3. Restore TAU_DIV_RB to 0.60 once patterns are tightened
4. Investigate network_audit anchor rollback as separate finding
