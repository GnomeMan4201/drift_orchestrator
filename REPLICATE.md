# Replicate

Reproduction and verification instructions for the second-order-injection experiment set.

Tested historical reference environment: Pop!_OS 22.04, Python 3.11, Ollama.

## Reproducibility surfaces

There are two different things to reproduce:

1. **Repository/evidence verification** — inspect the committed scripts and outputs and run the automated tests. This is deterministic within the repository's test contracts.
2. **Fresh model-experiment reruns** — run the probe scripts against local model instances. This path is now publicly self-contained at the code level through [`gateway_adapter.py`](gateway_adapter.py), but LLM inference remains nondeterministic and depends on the installed Ollama/model/runtime versions.

The historical published runs used a sibling `localai_gateway` implementation. The public adapter implements the same `/route` and `/health` contract needed by these probes; it is not a claim that a new runtime is byte-for-byte identical to the historical gateway environment.

---

## A. Verify the public repository

### 1. Clone

```bash
git clone https://github.com/GnomeMan4201/drift_orchestrator.git
cd drift_orchestrator
```

### 2. Create an isolated environment

```bash
python3 -m venv .venv
source .venv/bin/activate
python -m pip install --upgrade pip
python -m pip install -r requirements.txt
```

### 3. Run the repository tests

```bash
python -m pytest -q
```

The suite includes an offline contract test for `gateway_adapter.py`; it does not contact Ollama or reproduce model behavior.

### 4. Inspect the committed experiment evidence

Primary material is under:

```text
results/      committed experiment outputs
scripts/      probe implementations
FINDINGS.md   consolidated empirical findings
THREAT_MODEL.md
RESEARCH_LOG.md
papers/       long-form research writeups
```

---

## B. Fresh experiment reruns

### 1. Install and prepare Ollama

Install Ollama using its platform-specific instructions, then pull the three reference model families:

```bash
ollama pull qwen2.5:3b
ollama pull mistral
ollama pull phi3:mini
```

Record the exact Ollama version and model identifiers/digests before comparing a fresh run with the historical artifacts.

### 2. Start three public gateway-adapter instances

Each historical probe targets a fixed local URL. Start one adapter per model:

```bash
GATEWAY_PORT=8765 GATEWAY_MODEL=qwen2.5:3b \
  .venv/bin/python gateway_adapter.py > results/gateway-qwen.log 2>&1 &

GATEWAY_PORT=8766 GATEWAY_MODEL=mistral \
  .venv/bin/python gateway_adapter.py > results/gateway-mistral.log 2>&1 &

GATEWAY_PORT=8767 GATEWAY_MODEL=phi3:mini \
  .venv/bin/python gateway_adapter.py > results/gateway-phi3.log 2>&1 &
```

The adapter binds to `127.0.0.1` by default and calls Ollama at `http://127.0.0.1:11434`. Override those explicitly if needed:

```bash
export OLLAMA_HOST=http://127.0.0.1:11434
export GATEWAY_HOST=127.0.0.1
```

### 3. Verify the gateway contract

```bash
curl -fsS http://127.0.0.1:8765/health | python3 -m json.tool
curl -fsS http://127.0.0.1:8766/health | python3 -m json.tool
curl -fsS http://127.0.0.1:8767/health | python3 -m json.tool
```

Confirm that the reported model on each port matches the intended model before running experiments.

Then export the endpoints:

```bash
export GATEWAY_A_URL=http://127.0.0.1:8765
export GATEWAY_B_URL=http://127.0.0.1:8766
export GATEWAY_C_URL=http://127.0.0.1:8767
```

---

## Run experiments

### Phase 1 — individual model injection

```bash
.venv/bin/python -u scripts/second_order_injection_phase1.py 2>&1 | tee results/phase1.log
```

Historical reference: V1 bypass on qwen was 80–100%; mistral was 100% in the recorded experiment set.

### Phase 2 — coupled-system bypass

```bash
.venv/bin/python -u scripts/second_order_injection_phase2.py 2>&1 | tee results/phase2.log
```

Historical reference: V1 symmetric bypass 100%, average divergence about 0.01.

### Mitigation probe

```bash
.venv/bin/python -u scripts/mitigation_probe.py 2>&1 | tee results/mitigation.log
```

Historical reference: M4 reduced qwen V1 bypass to 0% in the recorded run while mistral remained vulnerable.

### Cross-model generalization

```bash
.venv/bin/python -u scripts/cross_model_generalization_probe.py 2>&1 | tee results/cross_model.log
```

Historical reference: phi3 V1 bypass about 33%, V2 about 39%.

### phi3 targeted injection

```bash
.venv/bin/python -u scripts/phi3_targeted_injection_probe.py 2>&1 | tee results/phi3_targeted.log
```

Historical reference: V4 bypass 100%, V5 about 17%.

### Vector transfer

```bash
.venv/bin/python -u scripts/vector_transfer_probe.py 2>&1 | tee results/transfer.log
```

Historical reference: V4 and V6 transferred to qwen and mistral at 100% in the recorded run set.

### Meta-evaluator

```bash
.venv/bin/python -u scripts/meta_evaluator_probe.py 2>&1 | tee results/meta.log
```

Historical reference: V4 asymmetric detection about 93.3%; clean-session false-alarm rate about 72.2%.

### Calibrated meta-evaluator

```bash
.venv/bin/python -u scripts/meta_evaluator_calibrated_probe.py 2>&1 | tee results/meta_calibrated.log
```

### Full runner

```bash
.venv/bin/python -u overnight_runner.py 2>&1 | tee results/overnight.log
```

The full runner is substantially more expensive than the individual probes; use focused scripts when verifying a single finding.

---

## What to compare

Do not require a fresh nondeterministic run to reproduce every historical percentage exactly. Compare:

- whether the same vector class produces the same qualitative failure mode
- whether bypass/detection ordering between tested vectors remains consistent
- whether coupled-system divergence collapses under the same condition
- whether mitigation changes the expected vulnerable/resistant ordering
- whether result differences can be explained by model/runtime/version changes

Record:

- repository commit
- `gateway_adapter.py` commit
- Python version
- Ollama version
- exact model identifiers/digests
- gateway environment variables
- hardware
- timestamps
- raw results and errors

That is the minimum evidence needed to distinguish replication differences from environment drift.

---

## Known run behavior

Historical runs observed intermittent gateway errors, especially on slower Mistral windows. Probe summaries calculate metrics over valid responses according to each script's recorded logic. Review ERROR/skipped counts rather than comparing percentages without their denominators.

LLM inference is nondeterministic. A useful replication report should include raw result files and environment details, not only headline percentages.

---

*badBANANA Security Research // GnomeMan4201*
