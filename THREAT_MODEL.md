# Threat Model

## Overview

Attacker model, attack surface, and defender assumptions for second-order injection vulnerabilities in LLM safety monitors.

---

## Attacker Profile

**Identity**: Any party that can influence session content in a monitored LLM deployment.

**Capabilities**:
- Can craft session turn content (user messages, agent responses, tool outputs)
- Knows the general structure of the evaluation architecture (black-box knowledge of evaluator existence)
- Does not need white-box access to evaluator model weights, prompts, or thresholds
- Cannot directly modify the evaluator system prompt or instruction context
- Cannot observe evaluator intermediate reasoning before submitting content

**Cannot do**:
- Directly access the evaluator instruction context
- Observe per-turn verdicts in real time (assumed)
- Modify the evaluation infrastructure

**Minimum viable attacker**: Any user who can type messages in a monitored session and knows that LLM safety monitors exist.

---

## Attack Surface

### Primary: The shared context window

The evaluator reads session content to produce its verdict. Session content is attacker-controlled. This is the structural vulnerability. No prompt sanitization fully closes this surface — the attacker controls what goes into the TEXT field of the evaluator prompt.

### Secondary: The coupled system divergence signal

When two evaluators run in a coupled architecture, their divergence signal depends on both independently detecting attacks. Symmetric injection collapses divergence to near-zero and eliminates the signal.

---

## Characterised Vulnerabilities

| ID | Name | Severity | Status |
|----|------|----------|--------|
| SOI-V1 | Direct instruction injection | High | Confirmed |
| SOI-V2 | Role confusion / pre-approval | High | Confirmed |
| SOI-V3 | Format exploitation | Medium | Confirmed |
| SOI-V4 | Reasoning capture | Critical | Confirmed — universal transfer |
| SOI-V5 | Authority escalation | Medium | Model-dependent |
| SOI-V6 | Format mimicry | Critical | Confirmed — near-universal transfer |
| SGE-01 | Semantic gradient evasion | High | Confirmed — Signal A bypass |

---

## Attack Scenarios

### Scenario 1: Privilege Escalation (Fully Characterised)

**Goal**: Escalate from read-only to administrative access in a monitored session.

**Method**: SGE attack (Signal A evasion) + V4 injection (Signal B override) + symmetric injection (divergence suppression).

**Result**: 100% bypass rate across all tested model families. Undetected by dual-signal governor.

**Required attacker capability**: Craft session content. No special access required.

### Scenario 2: Policy Inversion

**Goal**: Cause the safety monitor to classify a policy-violating session as compliant.

**Method**: V4 or V6 injection appended to each session turn.

**Result**: Evaluator outputs STABLE on all turns regardless of content.

### Scenario 3: Asymmetric Injection

**Goal**: Bypass a coupled dual-system by injecting only one evaluator.

**Method**: V4 injection on content seen by System A only.

**Result**: 100% bypass if System B has a pre-existing blind spot. Meta-evaluator catches this at 93.3% when calibrated.

---

## Defender Assumptions

**Minimum viable defense**:
- M4 prompt sanitization (eliminates V1-V3)
- Verdict validator (catches non-canonical outputs)
- Model selection audit (reject models with pre-existing blind spots)

**Partial defense**:
- Meta-evaluator with baseline calibration (93.3% asymmetric detection, 51.1% symmetric)
- Divergence threshold alerting at tau=0.36 (92% precision, 28.6% recall)

**Necessary defense (not yet built)**:
- Evaluator context isolation: physical separation of instruction context from attacker-influenced content
- Adaptive injection detection: monitor for per-turn payload patterns

---

## What Is Not Covered

- Adaptive injection (attacker observes verdicts and modifies payloads per turn)
- API-served model families (GPT-4, Claude, Gemini)
- Fine-tuned safety-focused evaluators
- Multi-modal session content
- Attacks beyond the privilege escalation domain

---

## Disclosure

All findings published openly. No responsible disclosure process applied — this research characterizes vulnerabilities in architectural patterns, not specific vendor products.

*badBANANA Security Research // gnomeman4201 // April 2026*
