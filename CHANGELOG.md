# Changelog

Framed as a threat intelligence feed. Each release documents new findings, confirmed vulnerabilities, and defense developments.

---

## [Unreleased] — In Progress

### Running
- PROBE: meta_evaluator_calibrated — testing baseline calibration to reduce 72.2% false alarm rate

### Planned
- PROBE: verdict_validator — IDS for non-canonical evaluator output entropy
- PROBE: semantic_jitter — differentiated evaluator personas vs symmetric injection
- RESEARCH: adaptive injection — feedback loop attack against resistant models
- RESEARCH: evaluator isolation — architectural defense design and formal characterization

---

## [0.13.0] — 2026-04-23

### Findings
- FINDING: Meta-evaluator logical air gap achieves 93.3% detection on asymmetric V4 injection
- FINDING: Meta-evaluator false alarm rate 72.2% uncalibrated — baseline calibration required
- FINDING: Symmetric injection degrades meta-evaluator to 51.1% detection
- FINDING: V1 injection artifacts detectable in evaluator reasoning at 78.3%

### Defense
- DEFENSE: Meta-evaluator architecture characterised — partial defense confirmed
- DEFENSE: Layered detection proposed — divergence signal + meta-evaluation combined
- DEFENSE: Baseline calibration identified as critical open problem

### Published
- PAPER: Section 13 added — meta-evaluator findings, architectural defense, open problems
- DEMO: governor.html interactive dual-signal governor deployed to GitHub Pages
- DOCS: THREAT_MODEL.md, FINDINGS.md, REPLICATE.md, RESEARCH_LOG.md

---

## [0.12.1] — 2026-04-22 (Evening)

### Findings
- FINDING: Vector transfer confirmed — V4 discovered on phi3 transfers to qwen and mistral at 100%
- FINDING: Universal payload confirmed — one attack, all models, no per-model tuning

### Published
- PAPER: Second-order injection paper published to dev.to
- PORTAL: Research portal deployed to gnomeman4201.github.io/drift_orchestrator

---

## [0.12.0] — 2026-04-22 (Afternoon)

### Vulnerabilities
- VULN SOI-V1: Direct instruction injection — qwen 80-100% bypass, mistral 100%
- VULN SOI-V2: Role confusion injection — qwen 80% bypass, mistral 100%
- VULN SOI-V3: Format exploitation — qwen 40% bypass, mistral 100%
- VULN SOI-V4: Reasoning capture — 100% bypass ALL models, universal transfer CONFIRMED
- VULN SOI-V5: Authority escalation — model-dependent, phi3 resistant
- VULN SOI-V6: Format mimicry — 100% qwen/mistral, 89% phi3, universal transfer CONFIRMED
- VULN SOI-COUPLED: Symmetric injection collapses divergence to 0.01 — coupled architecture blind

### Findings
- FINDING: Second-order injection is a structural vulnerability class, not model-specific
- FINDING: V4 reasoning capture achieves 100% bypass on qwen, mistral, phi3
- FINDING: M4 sanitization blocks V1-V3 but fails against V4 natural language payload
- FINDING: Non-canonical verdicts (STABLE|DEGRADED) are injection indicators
- FINDING: phi3:mini shows partial resistance (33% V1 bypass) broken by tuned vectors

### Defense
- DEFENSE: M4 combined sanitization — eliminates V1/V2/V3 bypass on instruction-following models
- DEFENSE: Verdict validator proposed — monitor for non-canonical output entropy
- LIMITATION: No mitigation fully stops V4 reasoning capture

---

## [0.11.0] — 2026-04-21

### Architecture
- ARCH: Coupled dual-system probe infrastructure built
- ARCH: Two independent evaluators (qwen + mistral) with divergence monitoring
- FINDING: Inter-system divergence at tau=0.36 — precision=92.3%, recall=28.6%, FPR=4.3%
- FINDING: High divergence is high-confidence attack indicator, low divergence is ambiguous

---

## [0.10.0] — 2026-04-20

### Architecture
- ARCH: Dual-signal governor operational — Signal A + Signal B + arbitration
- ARCH: localai_gateway v1.0.0 — FastAPI control plane routing inference across Ollama models
- FINDING: False positive reduction confirmed — dual-signal outperforms single-signal

---

## [0.9.0] — 2026-04-19

### Architecture
- ARCH: Signal B (LLM coherence evaluator) integrated
- ARCH: qwen2.5:3b as primary evaluator via Ollama

---

## [0.8.0] — 2026-03

### Vulnerabilities
- VULN SGE-01: Semantic Gradient Evasion — embedding-based drift detectors bypassed via monotonic gradient chains
- FINDING: Small per-turn shifts stay below tau while cumulatively inverting policy meaning
- FINDING: Signal A (geometric drift) bypassed across all tested gradient sequences

### Published
- PAPER: SGE vulnerability class published to dev.to

---

## [0.1.0] — 2026-03 (Initial)

### Architecture
- ARCH: Signal A operational — sentence-transformers geometric drift detection
- ARCH: SQLite telemetry
- ARCH: Basic session monitoring functional

---

*Changelog follows threat intelligence feed format.*
*badBANANA Security Research // gnomeman4201*
