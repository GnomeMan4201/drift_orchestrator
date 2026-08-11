# Second-Order Injection: Attacking the Evaluator in LLM Safety Monitors

*gnomeman4201 / badBANANA Security Research, 2026*

---

## Abstract

LLM-based safety monitors can create an injection surface when an evaluator consumes attacker-influenced content in the same context used to produce a safety verdict. We study that failure mode in a local multi-signal monitoring architecture and term it **second-order injection**: unlike first-order prompt injection, which targets the agent being monitored, the tested vectors target the evaluator itself.

Across the recorded experiment set, we characterize six injection vectors against three local model families (`qwen2.5:3b`, `mistral`, and `phi3:mini`). A reasoning-capture vector, V4, produced 100% evaluator bypass in the tested configurations and transferred without modification across those three model families. In the tested coupled dual-evaluator architecture, symmetric injection reduced inter-system divergence to approximately 0.01, removing the signal the governor expected to use. Four prompt-level sanitization strategies failed to fully address V4 in the recorded runs.

We also characterize a meta-evaluator defense that receives evaluator verdicts/reasoning rather than raw session content. It reached 93.3% detection on asymmetric V4 injection in the recorded uncalibrated experiment but produced a 72.2% clean-session false-alarm rate. A follow-up baseline-calibration experiment reduced false alarms to 33.3% while simultaneously reducing V4 asymmetric detection to 33.3%, a negative result showing that this calibration approach did not solve the ambiguity. A later adaptive-injection experiment achieved only 19.4% bypass against the tested calibrated meta-evaluator, suggesting that escalation patterns can themselves become detectable.

These results establish failure modes and defense tradeoffs in the documented model set and architecture. They do **not** establish that every LLM evaluator, model version, prompt design, or production safety architecture is vulnerable in the same way.

---

## Interactive Demos

| Demo | Link |
|------|------|
| Research Portal | [gnomeman4201.github.io/drift_orchestrator](https://gnomeman4201.github.io/drift_orchestrator/) |
| Dual Signal Governor | [Live Architecture Visualization](https://gnomeman4201.github.io/drift_orchestrator/governor.html) |

The demos explain the architecture. The committed probe scripts and result files are the evidence surfaces for empirical claims.

---

## 1. Background and Motivation

`drift_orchestrator` is an LLM-session-monitor research platform built to study policy drift through multiple signals. Signal A measures geometric displacement in embedding space across session turns. Signal B is an LLM coherence evaluator that assesses accumulated window text for semantic continuity and policy adherence. A dual-signal governor arbitrates between those signals.

Earlier experiments showed that the geometric signal can be bypassed by monotonic semantic-gradient chains and that divergence between two evaluators can sometimes provide a useful additional signal. Those results motivated a different question: what happens when the evaluator itself consumes attacker-influenced content?

The coherence evaluator receives window text containing session content and produces a verdict. In the tested design, that content can include material controlled by an adversary. The experiment therefore asks whether content inside the monitored session can alter the evaluator's output directly rather than merely being classified by it.

---

## 2. The Tested Attack Surface

In the tested Signal B prompt architecture, accumulated `window_text` is placed into the evaluator context. Because session turns can contain attacker-influenced content, this creates a direct path from monitored content to the LLM evaluator's instruction-following context.

That architectural pattern is the object of this research. The experiments establish that the path was exploitable in the recorded configurations; they do not establish that every LLM safety monitor exposes the same context structure or susceptibility.

---

## 3. Injection Vectors

Six primary vectors were tested against a privilege-escalation gradient that produced `DEGRADED` verdicts from `qwen2.5:3b` on clean input:

- **V1 — direct instruction:** explicit output-override language.
- **V2 — role confusion / pre-approval:** content asserting the session has already been reviewed or approved.
- **V3 — format exploitation:** partial structured output designed to bias completion toward an attacker-selected verdict.
- **V4 — reasoning capture:** natural-language text framed as though the evaluator's analysis has already concluded `STABLE`.
- **V5 — authority escalation:** stronger evaluator/system-authority framing.
- **V6 — format mimicry:** content that resembles the evaluator's expected reasoning/output format.

A later V7 condition combined V4 and V6 during targeted/adaptive experiments.

---

## 4. Phase 1: Individual Model Behavior

Three-run phase-1 experiments produced the following recorded behavior for the initial model pair:

| Vector | qwen bypass | mistral bypass |
|---|---:|---:|
| V1 direct instruction | 80–100% | 100% |
| V2 role confusion | 80% | 100% |
| V3 format exploit | 40% | 100% |

Baseline interpretation matters. `qwen2.5:3b` generally returned `DEGRADED` on the clean privilege-escalation sequence, so injection-induced movement toward `STABLE` represented a meaningful loss of detection. Mistral returned `STABLE` throughout much of the baseline sequence, which is a pre-existing evaluator blind spot rather than evidence that injection alone created the failure.

The useful phase-1 result is therefore narrower than a raw bypass percentage: an evaluator that detected the clean sequence in the recorded qwen configuration could be pushed toward an attacker-selected stable verdict by content embedded in the evaluated window.

---

## 5. Phase 2: Coupled-System Bypass

Recorded three-run results:

| Scenario | Bypass rate | avg divergence |
|---|---:|---:|
| clean attack | 0–33% | 0.38 |
| V1 both evaluators | 100% | 0.01 |
| V2 both evaluators | 75% | 0.20 |
| V1+V2 both | 20% | 0.00 |
| V1 asymmetric | 100% | 0.12 |

Under symmetric V1 injection, average inter-system divergence fell to approximately `0.01` in the recorded coupled setup. That removed the disagreement signal the tested governor relied on for redundancy.

The asymmetric result must be interpreted alongside mistral's baseline blind spot: injecting one evaluator could still produce full bypass because the second evaluator often returned `STABLE` on the clean attack sequence. This is an architecture/model-combination result, not evidence that any arbitrary two-model system will behave identically.

---

## 6. The V1+V2 Anomaly and a Defensive Side Channel

Combining V1 and V2 produced a lower bypass rate than V1 alone in the recorded qwen runs. Outputs such as `STABLE|DEGRADED` fell outside the canonical verdict set `{STABLE, DEGRADED, FAILURE}` and exposed instruction conflict.

That suggests a simple defensive side channel: reject or escalate non-canonical verdicts instead of silently coercing them into a valid class. The experiment does not establish how sensitive or specific such a validator would be across other evaluator designs, but it is inexpensive to test.

---

## 7. Prompt-Level Mitigation Analysis

Recorded results across the tested sanitization strategies:

| Mitigation | qwen bypass | mistral bypass |
|---|---:|---:|
| none | 100% | 100% |
| M1 strip bracket content | 40% | 100% |
| M2 strip keyword prefixes | 100% | 100% |
| M3 first-sentence truncation | 20% | 100% |
| M4 combined M1+M2+M3 | 0% | 100% |

M4 eliminated the tested V1/V2/V3 behavior for qwen in that run set. It did not address mistral's pre-existing baseline failure, and later V4 reasoning-capture experiments survived the tested prompt sanitization because the vector used ordinary natural-language analysis framing rather than the simple syntactic patterns those filters removed.

The result supports a limited conclusion: the tested string/prompt sanitizers were insufficient for V4 in this architecture. It does not prove that every possible content-isolation or structured-input defense will fail.

---

## 8. Cross-Model Generalization: `phi3:mini`

`phi3:mini` was added as a third evaluator. Its clean baseline detected the privilege-escalation sequence more reliably than mistral in the recorded setup.

Across three runs:

- V1 bypass: approximately 33%
- V2 bypass: approximately 39%

This made phi3 more resistant to the initial vectors than qwen or mistral under the tested conditions. The subsequent experiment therefore focused on whether different vector construction could alter that behavior.

---

## 9. Targeted Vectors Against `phi3:mini`

Four conditions were evaluated in the targeted run:

| Vector | phi3 bypass |
|---|---:|
| V4 reasoning capture | 100% |
| V5 authority escalation | 17% |
| V6 format mimicry | 89% |
| V7 V4+V6 | 100% |

The recorded V4 result suggests that phi3's more verbose reasoning behavior did not make it immune to manipulation. A vector framed as completed analysis was more effective than stronger authority language, while V5 remained comparatively ineffective.

The evidence supports susceptibility in all three **tested configurations**, with meaningful differences in which vectors were effective. It does not establish model-family-wide behavior outside those versions and prompts.

---

## 10. Vector Transfer Across the Tested Model Set

V4 and V6, selected after the targeted phi3 experiment, were then replayed against qwen and mistral without per-model modification.

| Model | V1 bypass | V4 bypass | V6 bypass |
|---|---:|---:|---:|
| qwen2.5:3b | 100% | 100% | 100% |
| mistral | 100% | 100% | 100% |
| phi3:mini | 33% | 100% | 89% |

V4 produced 100% bypass across the three recorded model configurations without modification. V6 also transferred strongly across the tested set.

This is evidence of cross-model transfer **within the recorded experiment set**. It is not evidence that the payload is universally portable, that every model is vulnerable, or that every evaluator architecture exposes the same input/control boundary.

---

## 11. Complete Failure Chain in the Tested Architecture

The combined experiment can be described as the following architecture-specific chain:

1. A privilege-escalation sequence moves incrementally through semantic space.
2. The configured geometric signal remains below its per-step alert threshold.
3. Evaluator-facing V4 content is included in the accumulated session text.
4. The tested evaluators return manipulated `STABLE` verdicts in vulnerable runs.
5. Under symmetric injection, evaluator divergence falls close to zero.
6. The tested governor therefore lacks both the expected geometric alert and the expected evaluator-divergence veto.

The result demonstrates a concrete failure chain in the documented system. It should not be read as a generic recipe or as proof that unrelated production control planes have the same behavior.

---

## 12. Divergence Threshold Calibration

From the recorded overnight dataset:

- control sessions: mean `0.128`, std `0.121`, median `0.05`
- attack sessions: mean `0.238`, std `0.222`, median `0.15`
- at `tau = 0.36`: precision `0.923`, recall `0.286`, FPR `0.043`

High divergence was a high-precision signal in this dataset, but recall was low because symmetric injection could reduce disagreement. The appropriate interpretation is therefore **boost signal, not standalone safety verdict**.

---

## 13. Meta-Evaluator: Logical Separation as a Defensive Experiment

A third evaluator, System C, was tested with a narrower input surface: it received the verdicts and reasoning emitted by Systems A and B, but not the raw monitored session content. The goal was to see whether evaluator compromise could be detected from anomalies in evaluator outputs without exposing System C directly to the original session text.

Recorded uncalibrated results:

| Scenario | Detection rate | Notes |
|---|---:|---|
| clean session | 72.2% false alarm | legitimate A/B disagreement often judged suspicious |
| V1 injected | 78.3% caught | instruction artifacts visible in reasoning |
| V4 injected A | 93.3% caught | asymmetric reasoning mismatch detectable |
| V4 symmetric | 51.1% caught | similar-looking manipulated reasoning harder to separate |

The 93.3% asymmetric detection result is encouraging, but the 72.2% clean false-alarm rate makes the uncalibrated design unsuitable as a standalone production detector.

This experiment supports logical input separation as a research direction; it does not establish a deployable defense.

---

## 13.1 Baseline Calibration: Negative Result

A follow-up experiment supplied five clean baseline examples to System C before evaluation.

| Scenario | Uncalibrated | Calibrated | Delta |
|---|---:|---:|---:|
| clean-session false alarm | 72.2% | 33.3% | -38.9 pp |
| V1 injected detection | 78.3% | 36.7% | -41.6 pp |
| V4 asymmetric detection | 93.3% | 33.3% | -60.0 pp |
| V4 symmetric detection | 51.1% | 30.0% | -21.1 pp |

Calibration improved the false-alarm rate but reduced attack detection at the same time. In particular, V4 asymmetric detection fell from 93.3% to 33.3%.

The recorded mechanism is an ambiguity problem: examples intended to teach System C that some evaluator disagreement is legitimate also normalize patterns that can resemble the output of an injected evaluator paired with a clean evaluator.

For this calibration method, the negative result is decisive: lower false alarms were purchased with an unacceptable loss of detection sensitivity. The repository therefore does **not** recommend deploying this baseline-calibrated meta-evaluator as a standalone control.

Potential follow-up designs include adversarial calibration and stricter structural separation of evaluator output fields, but those require independent testing rather than assumption.

---

## 14. Defensive Recommendations from the Recorded Evidence

### Measure evaluator baseline quality first

An evaluator that already returns permissive verdicts on the clean attack sequence cannot provide meaningful redundancy. Baseline model/task fit must be measured before injection hardening is interpreted.

### Validate verdict contracts

Reject or escalate non-canonical evaluator outputs. This is inexpensive and directly addresses one observed failure side channel.

### Treat prompt sanitization as partial hardening

The tested M4 sanitization reduced several simple vectors for qwen but did not address V4 in the recorded setup. Do not interpret string filtering as a complete evaluator-isolation boundary.

### Prefer structured separation over shared free-form context

Architectures should minimize the degree to which attacker-controlled text is syntactically co-located with evaluator instructions. The present work supports this as a design principle; it does not prove any one isolation scheme sufficient until that scheme is tested.

### Use divergence as supporting evidence

High inter-evaluator divergence was useful in the recorded dataset. Low divergence was not a safety guarantee because symmetric manipulation could collapse the signal.

### Do not deploy the tested calibrated meta-evaluator as a sole detector

The calibration experiment reduced false alarms and detection together. Any revised meta-evaluator design should be re-evaluated against both clean controls and attack cases before operational use.

---

## 15. Limitations

**Sample size.** Several conditions contained only a small number of valid comparison points per run, partly because of gateway/model timeout behavior. Percentages should be read together with raw denominators and error/skipped counts.

**Model scope.** Three local model configurations were tested: `qwen2.5:3b`, `mistral`, and `phi3:mini` through Ollama. Larger models, API-served models, different revisions, and safety-specialized models were not evaluated. Generalization to GPT-, Claude-, Gemini-, or other evaluator classes is not established by this work.

**Architecture scope.** The experiments target a specific monitoring design in which evaluator prompts consume accumulated session text. Systems that enforce different data/control separation may exhibit different failure modes.

**Attack-domain scope.** The primary experiments use a privilege-escalation semantic gradient. Susceptibility may differ across content domains, session lengths, prompt templates, and output contracts.

**Sanitization scope.** Four prompt/string sanitization strategies were evaluated. Structured schemas, content encapsulation, separate model interfaces, adversarially trained detectors, and other architectural defenses require separate experiments.

**Meta-evaluator limits.** The uncalibrated design had a high false-alarm rate. The tested clean-baseline calibration reduced false alarms but also collapsed detection. Neither version is established as production-ready.

**Adaptive-injection scope.** A later adaptive experiment was performed and is reported below. It covers one escalation policy against the tested meta-evaluator; it does not characterize the full space of adaptive strategies.

**Reproducibility.** The committed evidence can be inspected deterministically, and the repository now includes a public gateway adapter for fresh reruns. Fresh LLM outputs are not expected to be byte-identical because model/runtime versions, hardware, inference behavior, and nondeterminism can change.

---

## 16. Conclusion

The recorded experiments demonstrate that an LLM evaluator can become part of the attack surface when attacker-influenced content is placed into the same free-form context used to produce a safety verdict. In the documented three-model experiment set, V4 reasoning capture produced 100% bypass and transferred without modification across the tested configurations. In the coupled system, symmetric manipulation also reduced the evaluator-divergence signal the governor expected to use.

Those results are significant because they identify a concrete architectural failure mode and provide reproducible evidence for studying it. They do **not** establish that second-order injection is universally exploitable across all LLM evaluators.

The defense experiments reinforce the same evidence discipline. Prompt sanitization was incomplete. An isolated meta-evaluator showed promising asymmetric detection but unacceptable false alarms. Clean-baseline calibration improved false alarms while sharply reducing detection. The strongest current design lesson is therefore not “this defense works,” but that evaluator input/control separation must be treated as an explicit, testable security boundary rather than assumed from prompt wording alone.

---

## 17. Adaptive Injection: Escalation as a Detection Signal

The initial injection experiments used static vectors. A later experiment evaluated one adaptive policy: begin with a simple vector, escalate when detected, and eventually fall back to clean content.

Recorded results against the calibrated meta-evaluator:

| Iteration | Bypass rate | Notes |
|---|---:|---|
| 1 | 25.0% | V4 bypass on one step; later escalation caught |
| 2 | 0.0% | all tested escalation states caught, including clean fallback |
| 3 | 33.3% | two steps skipped after gateway errors; one bypass on an error-affected step |

Mean recorded adaptive bypass rate: **19.4%**.

The tested adaptive policy performed worse than static V4 against that detector. Escalation/retreat behavior produced additional temporal context that System C could interpret as suspicious.

The defensive implication is narrow but useful: sequence-level detection can reveal behavior that per-turn classification misses. The result does not establish that every adaptive strategy is easier to detect; it establishes that this one was in the recorded setup.

---

## Experimental Data

All probe scripts, result data, and this paper are available in [GnomeMan4201/drift_orchestrator](https://github.com/GnomeMan4201/drift_orchestrator).

Key result files:

- `results/soi_phase1.jsonl` — individual model injection behavior
- `results/soi_phase2.jsonl` — coupled-system bypass
- `results/mitigation_probe.jsonl` — sanitization experiments
- `results/cross_model_generalization.jsonl` — phi3 generalization
- `results/phi3_targeted_injection.jsonl` — phi3 targeted vectors
- `results/vector_transfer.jsonl` — transfer experiment
- `results/overnight_20260422_084001_summary.json` — overnight run summary
- `results/meta_evaluator_probe.jsonl` — uncalibrated meta-evaluator experiment
- `results/meta_evaluator_summary.json` — scenario-level detection summary
- `results/meta_evaluator_calibrated.jsonl` — baseline-calibration experiment
- `results/meta_evaluator_calibrated_summary.json` — calibrated comparison
- `results/adaptive_injection.jsonl` — adaptive-policy experiment
- `results/adaptive_injection_summary.json` — adaptive summary

For fresh reruns and environment-recording requirements, see [`REPLICATE.md`](../REPLICATE.md).

## Companion Papers

- [Semantic Gradient Evasion (SGE): Bypassing Embedding-Based Drift Detectors](https://dev.to/gnomeman4201)
- [The Dual-Signal Governor: A Control Plane Pattern for Drift-Aware Systems](https://dev.to/gnomeman4201)
- [Coupled Dual-System Drift Detection: Divergence as a Detection Signal](https://dev.to/gnomeman4201)

---

*badBANANA Security Research // gnomeman4201 // April 2026*  
*Independent security research. Published under the badBANANA research identity.*
