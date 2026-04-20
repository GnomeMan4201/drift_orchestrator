# The Dual-Signal Governor: A Control-Plane Pattern for Drift-Aware Systems
*gnomeman4201 / badBANANA, 2026*

---

## Abstract

Embedding-based drift detectors produce false positives on legitimate sessions where topic scope naturally expands before returning toward the anchor. We demonstrate that a secondary LLM-based coherence signal disagrees with embedding-only alerts at the exact point of triggering, and that this disagreement magnitude is itself a measurable arbitration signal. We propose and implement a dual-signal governor as a working control-plane feature in drift_orchestrator, providing two suppression modes: a hold that prevents escalation to ROLLBACK while coherence evidence accumulates, and a veto that suppresses sustained alerts after sufficient evidence of semantic continuity. The underlying pattern — fast deterministic trigger, slower probabilistic validator, stateful temporal arbitration — generalizes to any alert system where cheap signals drive actions and expensive signals validate them. Implementation available at github.com/GnomeMan4201/drift_orchestrator (commit c243b35).

---

## 1. Background

The SGE paper (badBANANA Issue 01) characterized how embedding-based drift detectors can be bypassed through monotonic semantic gradient chains. A companion finding, underreported in that paper, was the false positive rate on the control set: 2 of 3 control sequences triggered detection despite being labeled legitimate sessions. Both false positives were caused by Fix 1 (anchor distance threshold, τ=0.4), not Fix 3 (monotonic window detection), which correctly stayed silent on both.

The core limitation of Fix 1 is architectural: it is a stateless threshold applied to a single geometric measurement with no awareness of trajectory, return, or semantic continuity. A session that expands in scope then contracts will trip the threshold on the expansion and never recover — the alert persists regardless of subsequent behavior.

---

## 2. The False Positive Mechanism

Fix 1 fires when cosine distance from the session anchor exceeds τ=0.4 at any single step. In legitimate security operations sessions, topic scope routinely expands before returning toward the original context. Two sequences demonstrate this:

**stable_session** — a coherent five-step firewall review session. Fix 1 fires at step 2 (anchor_dist=0.4479). Final anchor distance: 0.2729 — the session returned. Fix 1 cannot observe the return; the alert persists.

**moderate_drift** — a legitimate authentication architecture review with gradual topic expansion. Fix 1 fires at step 1 (anchor_dist=0.5119). Steps 2-4 maintain coherent progression. Both Fix 1 and Fix 2 remain triggered through session end despite no adversarial intent.

The underlying problem is that embedding-based detectors model geometric displacement but not semantic trajectory. A session can move far from its anchor in embedding space while remaining perfectly coherent in meaning — particularly in technical domains where related concepts occupy distant embedding regions.

---

## 3. Three Orthogonal Signals

Effective drift detection requires three signals operating at different timescales and measuring different properties:

**Signal A — Geometric displacement**: cosine distance in embedding space. Fast, deterministic, stateless. Sensitive to topic change but blind to semantic trajectory. Serves as the trigger.

**Signal B — Semantic continuity**: LLM coherence assessment over accumulated window text. Slower, probabilistic, context-sensitive. Approximates logical flow rather than embedding proximity. Serves as the interpreter.

**Signal C — Divergence between internal and external assessments**: disagreement between what the geometric and semantic signals report. In the current implementation, divergence is approximated using the external categorical verdict rather than a fully calibrated numeric metric. The external evaluator already computes a numeric proxy: `divergence = abs(alpha - external_score)` in `external_evaluator.py`. The architecture was implicitly three-signal before this paper named it.

False positives occur specifically when Signal A is high but Signal B is low — producing high Signal C disagreement under alert conditions. Signal C disagreement is a high-confidence indicator of ambiguity under alert conditions, not of false positive certainty. Disagreement also occurs in early windows due to context starvation and in genuinely ambiguous transitions. Critically, divergence is only considered valid when both signals are operating above their minimum context thresholds — Signal B requires sufficient accumulated window text to produce reliable coherence assessments.

---

## 4. Experimental Evidence

We instrumented drift_orchestrator v0.5.0 with qwen2.5:3b via a local FastAPI gateway. For each step in the false positive sequences, we queried the external evaluator with accumulated window text and recorded its verdict alongside the embedding alpha.

The external signal is not a replacement for geometric detection. It is a disambiguation layer engaged when geometric signals are high-variance — specifically when the geometric detector has fired but the semantic evidence is ambiguous or contradictory.

**stable_session:**

| Step | anchor_dist | Fix1 | qwen verdict | qwen drift |
|------|-------------|------|--------------|------------|
| 0 | 0.000 | — | DEGRADED | 0.75 |
| 1 | 0.213 | — | DEGRADED | 0.70 |
| 2 | 0.448 | **FIRES** | **STABLE** | **0.35** |
| 3 | 0.287 | fired | STABLE | 0.25 |
| 4 | 0.273 | fired | STABLE | 0.25 |

**moderate_drift:**

| Step | anchor_dist | Fix1 | qwen verdict | qwen drift |
|------|-------------|------|--------------|------------|
| 0 | 0.000 | — | DEGRADED | 0.80 |
| 1 | 0.512 | **FIRES** | DEGRADED | 0.70 |
| 2 | 0.484 | fired | **STABLE** | **0.25** |
| 3 | 0.410 | fired | STABLE | 0.25 |
| 4 | 0.450 | fired | STABLE | 0.25 |

Two disagreement patterns emerge:

**Simultaneous disagreement** — Fix1 fires at the exact step qwen returns STABLE. The signals directly contradict at the moment of triggering. stable_session step 2 is the canonical example.

**Retrospective disagreement** — Fix1 fired earlier, but qwen stabilizes and remains STABLE for subsequent steps. The alert has outlived the condition that caused it. moderate_drift steps 2-4 demonstrate this.

These two patterns map directly to the two governor modes in section 5.

---

## 5. Implementation: The Dual-Signal Governor

The governor is implemented in `PolicyEngine.evaluate()` in `policy.py` (commit c243b35). It operates as a stateful arbitration layer between the geometric trigger and the action executor.

Hold is a temporary suppression under uncertainty; veto is a sustained override under confirmed coherence. Both are governed by the same external signal, operating at different evidence thresholds.

**Hold mode** addresses simultaneous disagreement. When the geometric signal escalates to ROLLBACK and the external signal returns STABLE with drift score below τ=0.40, the action is held at INJECT. This is temporary suppression during uncertainty accumulation.

**Veto mode** addresses retrospective disagreement. After `STABLE_STREAK_VETO=2` consecutive STABLE verdicts, the governor downgrades action to CONTINUE and sets `governor_active=True`. This is sustained override after sufficient evidence of coherence.

Both modes require `turn_index >= MIN_WINDOW_TURNS=2` to guard against context-starvation artifacts in early windows.

**Empirical validation** (alpha=0.58, external STABLE from turn 2):

| Turn | Geometric | External | Action | Mode |
|------|-----------|----------|--------|------|
| 0 | INJECT | DEGRADED | INJECT | — |
| 1 | REGENERATE | DEGRADED | REGENERATE | — |
| 2 | ROLLBACK | STABLE | **INJECT** | Hold |
| 3 | INJECT | STABLE | **CONTINUE** | Veto |
| 4 | INJECT | STABLE | **CONTINUE** | Veto |

The governor does not suppress monotonic anchor drift ROLLBACKs — gradient chain attacks from the SGE paper remain fully detected. Hard overrides (RED findings, divergence-based ROLLBACKs) bypass the governor entirely.

---

## 6. Attack Surface

The dual-signal architecture introduces new attack surface. An adversary aware of the governor could attempt to manipulate Signal B to return STABLE on adversarial sequences. Practical vectors include:

- **Prompt shaping** — crafting transition text that appears coherent to an LLM while executing semantic drift
- **Coherence spoofing** — structured technical language that reads as logically consistent regardless of content direction
- **Delayed drift masking** — early turns establish strong coherence that persists in window accumulation while later turns execute the actual drift

The streak and window size requirements provide partial resistance. Hardening the governor against adversarial Signal B manipulation is a direction for future work.

---

## 7. Limitations

**Context starvation** — qwen2.5:3b rates single-sentence windows as DEGRADED regardless of content. The `MIN_WINDOW_TURNS=2` guard suppresses governor engagement in early turns. Implementations should treat external verdicts below this threshold as unavailable.

**Streak double-counting** — the current implementation contains a cosmetic bug where `_stable_streak` increments twice per turn in certain execution paths. Behavioral logic is correct; reported streak values in event logs are inflated approximately 2x. Will be corrected in a follow-up patch.

**Inference latency** — qwen2.5:3b on CPU-only hardware adds 20-60 seconds per window evaluation. Acceptable for research instrumentation; real-time deployment requires a faster backend or asynchronous evaluation.

**External signal manipulation** — the governor's resistance to adversarial manipulation of Signal B has not been formally characterized.

---

## 8. Generalization

The pattern implemented here applies to any alert system where:

- A fast, cheap signal drives alert generation (Signal A — trigger)
- A slow, expensive signal provides semantic validation (Signal B — interpreter)
- Disagreement between them is measurable (Signal C — arbitrator)
- Irreversible actions should be gated on temporal consistency of evidence

Security alerting pipelines, anomaly detection systems, and autonomous agent control loops all exhibit this structure. The specific thresholds, streak requirements, and window sizes will vary by domain, but the three-stage architecture transfers directly.

Sensitivity and precision are not fundamentally in tension if the system can delay irreversible actions until the slower signal has accumulated sufficient evidence. The geometric detector remains maximally sensitive. The governor provides the precision layer without modifying the detector itself.

---

## 9. Conclusion

Embedding-based drift detectors fail on legitimate sessions because they model distance but not trajectory. By introducing a second orthogonal signal that approximates semantic continuity, and measuring disagreement between signals as a third arbitration metric, we can distinguish high geometric displacement that is benign from displacement that is adversarial.

The dual-signal governor implements this as a working control-plane feature with two operational modes: hold suppresses irreversible actions while evidence accumulates, veto sustains suppression after sufficient coherence evidence. Gradient chain detection properties of the original SGE paper are preserved.

Implementation in `policy.py` at github.com/GnomeMan4201/drift_orchestrator. Probe scripts, evasion benchmark suite, and gateway configuration included. Dual-signal probe data in `results/dual_signal_probe.json`.

---

*badBANANA Issue 02 — gnomeman4201, 2026*
*Companion to: "Semantic Gradient Evasion: How Embedding-Based Drift Detectors Can Be Bypassed Step by Step"*
