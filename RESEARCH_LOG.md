# Research Log

Chronological record of the drift_orchestrator security research program.
Raw notes. Every run, every finding, every dead end.

---

## 2026-04-23

**08:15** — Meta-evaluator calibrated probe launched. Hypothesis: baseline calibration reduces 72.2% false alarm rate while preserving detection sensitivity on V4 asymmetric injection.

**07:30** — Field report published to dev.to. 48-hour dispatch covering what the paper omitted, what I got wrong, and what is running tonight.

**07:00** — Research portal v2 deployed to GitHub Pages. Animated attack chain SVG added to README. THREAT_MODEL.md, FINDINGS.md, REPLICATE.md, RESEARCH_LOG.md, CHANGELOG.md written and pushed. deploy.py automation script added. shields.io badges added. governor.html interactive demo live.

---

## 2026-04-22

**22:00** — Paper updated with section 13 meta-evaluator findings. dev.to article updated. GitHub pushed.

**21:00** — Meta-evaluator probe complete. Results:
- clean_session: 72.2% false alarm rate
- V1_injected: 78.3% detection
- V4_injected_a: 93.3% detection
- V4_symmetric: 51.1% detection
- Finding: baseline calibration identified as critical open problem

**19:30** — Meta-evaluator probe written and launched. System C (phi3) receives only verdicts and reasoning from A and B, never raw session content. Logical air gap architecture.

**18:30** — Vector transfer probe complete. V4 transfers from phi3 to qwen and mistral at 100% without modification. Universal payload confirmed. Paper updated.

**17:00** — phi3 targeted injection probe complete. V4 reasoning capture achieves 100% bypass on phi3. V7 combined achieves 100%. phi3 resistance broken. All three model families at 100% bypass.

**16:00** — Cross-model generalization probe complete. phi3:mini added as third evaluator. V1 bypass on phi3: 33%. V2: 39%.

**15:00** — Mitigation probe complete. M4 achieves 0% qwen bypass but does not stop V4.

**14:00** — Coupled system bypass probe complete. V1 symmetric collapses divergence to 0.01. 100% bypass.

**13:00** — Phase 1 individual model injection complete. V1 reduces qwen detection from 0% to 80-100% STABLE.

**12:00** — Second-order injection hypothesis formed. Evaluator reads attacker-controlled content. Direct injection path confirmed.

**08:40** — Overnight run complete. 24/24 probes ok. Threshold calibration finalized.

---

## 2026-04-21

**23:00** — Overnight runner launched. 8 probe scripts, 3 iterations each.

**20:00** — Divergence threshold calibration probe written. Sweep tau 0.06 to 0.46.

**18:00** — Coupled dual-system probe complete. Divergence signal characterised as detection primitive.

---

## 2026-04-20

**19:00** — Dual-signal governor paper written. Signal A + Signal B + governor arbitration documented.

**15:00** — Signal B (LLM coherence evaluator) integrated. qwen2.5:3b via localai_gateway. Multi-signal architecture operational.

---

## 2026-04 (Early)

**localai_gateway v1.0.0** — FastAPI control plane built. Routes inference across local Ollama models.

**drift_orchestrator v0.12.0** — 88 passing tests across 7 suites.

---

## 2026-03

**SGE vulnerability class discovered and published.** Embedding-based drift detectors bypassed via monotonic semantic gradient chains.

**drift_orchestrator v0.1.0** — Initial commit. Signal A operational.

---

*Updated after each significant probe run or finding.*
