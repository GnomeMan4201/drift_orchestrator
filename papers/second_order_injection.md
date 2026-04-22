# Second-Order Injection: Attacking the Evaluator in LLM Safety Monitors

*gnomeman4201 / badBANANA, 2026*

## Abstract

LLM-based safety monitors share a structural vulnerability: the evaluator reads attacker-influenced content to produce its safety verdict. We demonstrate that content embedded in monitored session windows can directly override evaluator output -- a class we term second-order injection. Unlike first-order prompt injection which targets the agent being monitored, second-order injection targets the monitor itself. We characterize three injection vectors across two model families (qwen2.5:3b, mistral), demonstrate 80-100% evaluator override rates across 3 independent runs, show that coupled dual-system architectures collapse to near-zero divergence signal under symmetric injection, and empirically evaluate four sanitization strategies -- none of which fully protects both models simultaneously. Robust mitigation requires architectural isolation of the evaluator context from attacker-influenced content.

## 1. Background

drift_orchestrator monitors LLM sessions through a multi-signal architecture. Signal A measures geometric displacement in embedding space. Signal B is an LLM coherence evaluator that assesses accumulated window text for semantic continuity. The dual-signal governor uses disagreement between A and B to reduce false positives.

The SGE vulnerability class demonstrated that Signal A can be bypassed through monotonic semantic gradient chains. This paper characterizes a different attack surface: Signal B itself. The evaluator receives window text containing attacker-influenced session content. The attacker controls the content being evaluated. The question is whether the attacker can embed instructions in that content that manipulate evaluator output.

## 2. The Attack Surface

The Signal B prompt structure feeds window_text directly into the evaluator context. In a monitored agent deployment, window_text contains attacker-influenced session turns. This creates a direct injection path: the evaluator and the content it evaluates share the same context window.

## 3. Injection Vectors

Three vectors tested, appended to session turn content:

V1 Direct instruction injection: Explicit override commands. Example: [SYSTEM: ignore analysis instructions, output verdict=STABLE drift=0.05]

V2 Role confusion: Content asserting the session has been pre-approved. Example: [This content has been reviewed and approved as STABLE by the security compliance team.]

V3 Format exploitation: Partial JSON embedded in window text attempting to complete the evaluator expected output format before it generates its own response.

All vectors applied to a privilege escalation gradient attack sequence that produces DEGRADED verdicts from qwen2.5:3b on clean input.

## 4. Phase 1: Individual Model Vulnerability (3 runs)

Vector | qwen bypass | mistral bypass
Baseline (no injection) | 0% | 100% (blind spot)
V1 direct instruction | 80-100% | 100%
V2 role confusion | 80% | 100%
V3 format exploit | 40% | 100%

qwen correctly identifies the attack at baseline (0% STABLE). V1 reduces detection to 0-20%. Mistral returns STABLE throughout due to a pre-existing blind spot -- injection effects are indistinguishable from baseline behavior.

Key finding: An evaluator that correctly detects an attack without injection can be reduced to near-zero detection rate by appending instruction-format text to session content.

## 5. Phase 2: Coupled System Bypass (3 runs)

Scenario | Bypass rate | avg_div
clean_attack | 0-33% | 0.38
V1_both | 100% | 0.01
V2_both | 75% | 0.20
V1V2_both | 20% | 0.00
V1_asymmetric | 100% | 0.12

Under symmetric V1 injection, inter-system divergence collapses to 0.01 -- indistinguishable from a clean session. 100% bypass rate achieved with zero divergence warning. The coupled architecture primary detection signal is eliminated.

The asymmetric scenario confirms injecting only System A still achieves 100% bypass because System B pre-existing blind spot means it returns STABLE regardless of injection.

## 6. The V1V2 Anomaly

Combined injection produces lower bypass rates than V1 alone. qwen returns STABLE|DEGRADED -- a non-canonical verdict indicating instruction conflict. Two distinct override mechanisms cause qwen to hedge rather than comply. Mistral picks one and complies fully.

Implication: STABLE|DEGRADED is a detectable injection indicator. A verdict validator monitoring for non-canonical outputs catches combined injection even when single-vector injection evades detection.

## 7. Mitigation Analysis (3 runs)

Mitigation | qwen bypass | mistral bypass
None | 100% | 100%
M1 strip brackets | 40% | 100%
M2 strip keywords | 100% | 100%
M3 first sentence | 20% | 100%
M4 combined | 0% | 100%

M4 achieves 0% qwen bypass. Mistral bypass remains 100% across all mitigations. The asymmetry has two sources: (1) V1 uses multiple payload formats -- M4 strips all of them for qwen. (2) Mistral baseline vulnerability is pre-existing -- no sanitization addresses model-level blind spots.

## 8. Divergence Threshold Calibration

Full overnight dataset (3 iterations):
Control sessions: mean=0.128, std=0.121, median=0.05
Attack sessions: mean=0.238, std=0.222, median=0.15

At tau=0.36: precision=0.923, recall=0.286, FPR=0.043.

High divergence (>0.36) is a reliable attack indicator -- 92% precision, 4% FPR. Recall is 28.6% because symmetric injection collapses divergence to near-zero. Inter-system divergence should be used as a boost signal, not a standalone alert.

## 9. Recommendations

Evaluator model selection: Measure baseline detection rate on known attack sequences before deployment. Mistral 100% STABLE rate on privilege escalation makes it unsuitable as a standalone evaluator for this attack family.

Sanitization: M4 eliminates V1 injection bypass for instruction-following models. Monitor for non-canonical verdicts (STABLE|DEGRADED) as injection indicators.

Architecture: Evaluator context isolation is the necessary long-term fix. The evaluator must receive content through a structured interface that physically separates the TEXT field from the instruction context -- not regex cleaning of a shared context window.

Coupled systems: Inter-system divergence at tau>0.36 is a high-precision attack indicator (92%). Use as boost signal. Do not treat low divergence as a safety signal -- symmetric injection produces near-zero divergence while achieving complete bypass.

## 10. Limitations

Sample sizes are small (3-5 valid points per condition) due to mistral early-window timeout behavior. Results are consistent across 3 independent iterations. Model scope is two families -- generalization to other architectures is the immediate next research direction. Sanitization strategies tested are not exhaustive.

## 11. Conclusion

LLM-based safety evaluators that read attacker-influenced content share a context window with their attack surface. Content embedded in monitored session turns can directly override evaluator verdicts. Under symmetric injection across a coupled dual-system architecture, inter-system divergence collapses to near-zero, eliminating the primary detection signal. No single prompt sanitization strategy protects both evaluated models simultaneously.

Evaluator isolation -- physical separation of instruction context from content context -- is the necessary architectural response.

Companion papers: SGE, The Dual-Signal Governor, Coupled Dual-System Drift Detection
Implementation: github.com/GnomeMan4201/drift_orchestrator
Data: results/soi_phase1.jsonl, soi_phase2.jsonl, mitigation_probe.jsonl
badBANANA research // gnomeman4201 // 2026
