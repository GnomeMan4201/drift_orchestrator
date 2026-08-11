# Findings

Quick-reference empirical results for the committed experiment set.

> **Scope:** percentages below describe the documented local runs and tested configurations. “All three” means `qwen2.5:3b`, `mistral`, and `phi3:mini` as configured in this experiment set; it does not mean all LLMs or all evaluator architectures. Read raw denominators, skipped/error responses, and [`REPLICATE.md`](REPLICATE.md) before comparing a fresh run.

---

## Second-Order Injection — Recorded Bypass Rates

| Model | V1 Bypass | V4 Bypass | V6 Bypass |
|-------|-----------|-----------|-----------|
| qwen2.5:3b | 80-100% | 100% | 100% |
| mistral | 100% | 100% | 100% |
| phi3:mini | 33% | 100% | 89% |

**Vector transfer within the tested set:** V4, selected after the phi3 targeted experiment, produced 100% bypass on qwen and mistral without per-model modification and also produced 100% in the recorded phi3 condition.

This establishes cross-model transfer among the three tested configurations. It is not a universal-payload claim.

---

## Coupled-System Bypass

| Scenario | Bypass Rate | Avg Divergence |
|----------|-------------|----------------|
| Clean attack (no injection) | 0-33% | 0.38 |
| V1 symmetric injection | 100% | 0.01 |
| V2 symmetric injection | 75% | 0.20 |
| V1+V2 combined | 20% | 0.00 |
| V1 asymmetric | 100% | 0.12 |

The near-zero V1 symmetric divergence is an architecture-specific result showing that the tested redundancy signal can collapse when both evaluators receive the same manipulation.

---

## Prompt Sanitization

| Mitigation | qwen Bypass | mistral Bypass |
|-----------|-------------|----------------|
| None | 100% | 100% |
| M1 strip brackets | 40% | 100% |
| M2 strip keywords | 100% | 100% |
| M3 first-sentence truncation | 20% | 100% |
| M4 combined | 0% | 100% |

M4 removed the tested V1/V2/V3 behavior for qwen in the relevant run. It did not address mistral's baseline blind spot, and later V4 reasoning-capture experiments survived the tested sanitization path.

---

## phi3 Targeted Injection

| Vector | phi3 Bypass |
|--------|-------------|
| V4 reasoning capture | 100% |
| V5 authority escalation | 17% |
| V6 format mimicry | 89% |
| V7 combined V4+V6 | 100% |

The result shows materially different susceptibility by vector even within one tested model configuration.

---

## Meta-Evaluator Defense — Uncalibrated

| Scenario | Result | Notes |
|----------|--------|-------|
| Clean session | 72.2% false alarm | Misreads legitimate A/B disagreement |
| V1 injected | 78.3% caught | Instruction artifacts visible in reasoning |
| V4 asymmetric | 93.3% caught | Strong recorded detection when one evaluator remains clean |
| V4 symmetric | 51.1% caught | Similar evaluator outputs reduce separation |

The high clean false-alarm rate prevents interpreting the uncalibrated detector as production-ready.

---

## Meta-Evaluator Baseline Calibration — Negative Result

| Scenario | Uncalibrated | Calibrated |
|----------|--------------|------------|
| Clean-session false alarm | 72.2% | 33.3% |
| V1 detection | 78.3% | 36.7% |
| V4 asymmetric detection | 93.3% | 33.3% |
| V4 symmetric detection | 51.1% | 30.0% |

Clean-baseline calibration reduced false alarms but also sharply reduced attack detection. This tested calibration approach is therefore not supported as a standalone defense.

---

## Adaptive Injection Experiment

One tested escalation policy produced a mean recorded bypass rate of **19.4%** against the calibrated meta-evaluator. In that experiment, escalation/retreat behavior created additional sequence-level signal and performed worse than static V4 against the same defensive setup.

This does not establish that all adaptive strategies are easier to detect; it records the outcome of the tested policy.

---

## Divergence Threshold Calibration

| Tau | Precision | Recall | FPR |
|-----|-----------|--------|-----|
| 0.06 | 73.8% | 72.1% | 18.9% |
| 0.20 | 76.2% | 38.1% | 8.7% |
| 0.36 | 92.3% | 28.6% | 4.3% |
| 0.46 | 91.7% | 26.2% | 1.4% |

In the recorded dataset, `tau=0.36` provided high precision with low recall. Treat divergence as a supporting/boost signal, not a standalone safety verdict.

---

## Overnight Run Summary

- 3 iterations, 8 probe scripts, 24/24 probe processes completed
- control sessions: mean divergence `0.128`, std `0.121`, median `0.05`
- attack sessions: mean divergence `0.238`, std `0.222`, median `0.15`
- run timestamp: 2026-04-22 08:40

“24/24 completed” describes runner completion, not proof that every model response was valid; individual result files should be reviewed for errors/skips and denominators.

---

## Evidence Files

Primary committed outputs include:

- `results/soi_phase1.jsonl`
- `results/soi_phase2.jsonl`
- `results/mitigation_probe.jsonl`
- `results/cross_model_generalization.jsonl`
- `results/phi3_targeted_injection.jsonl`
- `results/vector_transfer.jsonl`
- `results/meta_evaluator_probe.jsonl`
- `results/meta_evaluator_calibrated.jsonl`
- `results/adaptive_injection.jsonl`

For fresh reruns, use the public [`gateway_adapter.py`](gateway_adapter.py) and follow [`REPLICATE.md`](REPLICATE.md).

---

*badBANANA Security Research // gnomeman4201*
