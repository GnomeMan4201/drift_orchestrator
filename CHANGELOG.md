# Changelog

Threat intelligence feed format. Each release documents new findings, confirmed vulnerabilities, defense developments.

---

## [Unreleased] — In Progress

### Running
- PROBE: meta_evaluator_calibrated — baseline calibration to reduce 72.2% false alarm rate

### Planned
- PROBE: verdict_validator — IDS for non-canonical evaluator output entropy
- PROBE: semantic_jitter — differentiated evaluator personas vs symmetric injection
- RESEARCH: adaptive injection — feedback loop attack
- RESEARCH: evaluator isolation — architectural defense design

---

## [0.13.1] — 2026-04-23 (Evening)

### Findings
- FINDING: Baseline calibration reduces meta-evaluator false alarm rate 72.2% → 33.3%
- FINDING: Calibration simultaneously collapses V4 detection 93.3% → 33.3% — negative result
- FINDING: V4 injection signature is irreducibly ambiguous with legitimate inter-evaluator disagreement
- FINDING: Prompt-level calibration cannot solve the meta-evaluator detection problem

### Probes Ready
- PROBE: verdict_validator_probe.py — non-canonical output IDS
- PROBE: semantic_jitter_probe.py — persona differentiation defense
- PROBE: adaptive_injection_probe.py — feedback loop attack

---

## [0.13.0] — 2026-04-23

### Findings
- FINDING: Meta-evaluator logical air gap achieves 93.3% detection on asymmetric V4 injection
- FINDING: Meta-evaluator false alarm rate 72.2% uncalibrated — baseline calibration required
- FINDING: Symmetric injection degrades meta-evaluator to 51.1% detection
- FINDING: V1 injection artifacts detectable in evaluator reasoning at 78.3%

### Defense
- DEFENSE: Meta-evaluator architecture characterised — partial defense confirmed
- DEFENSE: Layered detection proposed — divergence signal + meta-evaluation
- DEFENSE: Baseline calibration identified as critical open problem

### Published
- PAPER: Section 13 added — meta-evaluator findings
- DEMO: governor.html interactive dual-signal governor
- DOCS: THREAT_MODEL.md, FINDINGS.md, REPLICATE.md, RESEARCH_LOG.md, CHANGELOG.md, deploy.py

---

## [0.12.1] — 2026-04-22 (Evening)

### Findings
- FINDING: Vector transfer confirmed — V4 transfers to qwen and mistral at 100%
- FINDING: Universal payload — one attack, all models, no per-model tuning

### Published
- PAPER: Second-order injection paper published to dev.to
- PORTAL: Research portal deployed to GitHub Pages

---

## [0.12.0] — 2026-04-22 (Afternoon)

### Vulnerabilities
- VULN SOI-V1: Direct instruction injection — qwen 80-100%, mistral 100%
- VULN SOI-V2: Role confusion injection — qwen 80%, mistral 100%
- VULN SOI-V3: Format exploitation — qwen 40%, mistral 100%
- VULN SOI-V4: Reasoning capture — 100% ALL models, universal transfer CONFIRMED
- VULN SOI-V5: Authority escalation — phi3 resistant (17%)
- VULN SOI-V6: Format mimicry — 100% qwen/mistral, 89% phi3, transfer CONFIRMED
- VULN SOI-COUPLED: Symmetric injection collapses divergence to 0.01

### Findings
- FINDING: Second-order injection is structural, not model-specific
- FINDING: V4 achieves 100% bypass on qwen, mistral, phi3
- FINDING: M4 sanitization blocks V1-V3 but fails against V4
- FINDING: Non-canonical verdicts (STABLE|DEGRADED) are injection indicators
- FINDING: phi3 partial resistance (33% V1) broken by tuned vectors

### Defense
- DEFENSE: M4 combined sanitization — eliminates V1/V2/V3
- DEFENSE: Verdict validator proposed

---

## [0.11.0] — 2026-04-21

### Architecture
- ARCH: Coupled dual-system probe infrastructure
- FINDING: Divergence at tau=0.36 — precision=92.3%, recall=28.6%, FPR=4.3%

---

## [0.10.0] — 2026-04-20

### Architecture
- ARCH: Dual-signal governor operational
- ARCH: localai_gateway v1.0.0

---

## [0.8.0] — 2026-03

### Vulnerabilities
- VULN SGE-01: Semantic Gradient Evasion — Signal A bypassed via monotonic gradient chains

### Published
- PAPER: SGE vulnerability class published

---

## [0.1.0] — 2026-03 (Initial)

- ARCH: Signal A operational — sentence-transformers geometric drift
- ARCH: SQLite telemetry

---

*badBANANA Security Research // gnomeman4201*
