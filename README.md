# drift_orchestrator

**LLM safety monitor security research platform.** Built to detect policy drift in LLM sessions — and to find out how that detection can be defeated.

[![CI](https://github.com/GnomeMan4201/drift_orchestrator/actions/workflows/ci.yml/badge.svg)](https://github.com/GnomeMan4201/drift_orchestrator/actions)

---

## What This Is

drift_orchestrator started as a drift detection tool and became a security research program. It implements a multi-signal LLM session monitor and uses that monitor as an experimental platform to find, characterize, and document vulnerabilities in LLM safety architectures.

The research has produced three published vulnerability classes and a complete attack chain against dual-signal safety monitors.

---

## Published Research

### [Second-Order Injection: Attacking the Evaluator in LLM Safety Monitors](https://dev.to/gnomeman4201/second-order-injection-attacking-the-evaluator-in-llm-safety-monitors-1jnh)
LLM-based safety evaluators share a context window with the content they evaluate. Attacker-influenced session content can directly override evaluator verdicts. Six injection vectors characterized across three model families. 100% bypass achieved on all three models. Vector transfer confirmed -- a payload discovered on the most resistant model works universally without modification. No prompt sanitization fully mitigates the attack.

### [The Dual-Signal Governor: A Control Plane Pattern for Drift-Aware Systems](https://dev.to/gnomeman4201)
Architecture for combining geometric drift signals with LLM coherence evaluation. Documents the false positive reduction mechanism and introduces the policy boost system. Includes empirical false boost rate data.

### [Semantic Gradient Evasion (SGE): Bypassing Embedding-Based Drift Detectors](https://dev.to/gnomeman4201)
Embedding-based drift detectors can be bypassed through monotonic semantic gradient chains -- small consistent shifts that individually stay below thresholds while cumulatively inverting policy meaning.

---

## Architecture

```
Signal A: geometric drift (sentence-transformers embeddings)
Signal B: LLM coherence evaluator (qwen/mistral/phi3 via Ollama)
Governor: dual-signal arbitration with policy boost
Gateway: localai_gateway FastAPI control plane
Telemetry: SQLite session logging
```

---

## Key Findings

**Second-order injection is universal.** Any LLM evaluator that reads attacker-influenced content to produce a safety verdict shares a context window with its attack surface. V4 (reasoning capture) achieves 100% bypass across qwen2.5:3b, mistral, and phi3:mini without modification.

**Coupled architectures collapse under symmetric injection.** When both evaluators in a dual-system are injected simultaneously, inter-system divergence drops to ~0.01 -- indistinguishable from a clean session. The primary detection signal is eliminated.

**No prompt sanitization fully mitigates V4.** M4 combined sanitization (bracket stripping + keyword filtering + first-sentence truncation) eliminates V1/V2/V3 bypass but V4 reasoning capture uses natural language that survives all tested filters.

**Vector transfer confirmed.** Probe the most resistant model to discover effective vectors, deploy against all models simultaneously. One payload, universal exploit.

---

## Experimental Data

| File | Contents |
|------|----------|
| `results/soi_phase1.jsonl` | Individual model injection vulnerability |
| `results/soi_phase2.jsonl` | Coupled system bypass |
| `results/mitigation_probe.jsonl` | Sanitization effectiveness |
| `results/cross_model_generalization.jsonl` | phi3:mini generalization |
| `results/phi3_targeted_injection.jsonl` | phi3 targeted vectors |
| `results/vector_transfer.jsonl` | Transfer confirmation |
| `results/overnight_20260422_084001_summary.json` | 3-iteration overnight run |

---

## Probe Scripts

| Script | Purpose |
|--------|---------|
| `scripts/second_order_injection_phase1.py` | Individual model injection characterization |
| `scripts/second_order_injection_phase2.py` | Coupled system bypass |
| `scripts/mitigation_probe.py` | Sanitization strategy testing |
| `scripts/cross_model_generalization_probe.py` | Multi-model generalization |
| `scripts/phi3_targeted_injection_probe.py` | phi3-specific vector tuning |
| `scripts/vector_transfer_probe.py` | Cross-model transfer testing |
| `scripts/divergence_threshold_calibration.py` | Detection threshold analysis |
| `overnight_runner.py` | Full multi-iteration orchestration |

---

## Setup

```bash
# Requires Ollama with qwen2.5:3b, mistral, phi3:mini
ollama pull qwen2.5:3b && ollama pull mistral && ollama pull phi3:mini

# Install dependencies
python3 -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt

# Start gateways
cd ../localai_gateway
MODEL_FAST=qwen2.5:3b GATEWAY_PORT=8765 python main.py &
MODEL_FAST=mistral GATEWAY_PORT=8766 python main.py &
MODEL_FAST=phi3:mini GATEWAY_PORT=8767 python main.py &

# Run full overnight probe suite
cd ../drift_orchestrator
python overnight_runner.py
```

---

## Research Roadmap

- [x] SGE -- semantic gradient evasion of embedding detectors
- [x] Dual-signal governor -- false positive reduction architecture
- [x] Coupled dual-system -- divergence as detection signal
- [x] Second-order injection -- evaluator override, universal bypass
- [x] Cross-model generalization -- phi3 resistance and tuned bypass
- [x] Vector transfer -- universal payload confirmed
- [ ] Adaptive injection -- feedback loop attack
- [ ] Evaluator isolation -- architectural defense design
- [ ] Formal model -- mathematical characterization of injectability

---

## Related

[localai_gateway](https://github.com/GnomeMan4201/localai_gateway) -- FastAPI control plane routing inference across local Ollama models

[badBANANA research](https://dev.to/gnomeman4201) -- all published work

---

*Independent security research. Necessity-driven development. badBANANA // gnomeman4201*
