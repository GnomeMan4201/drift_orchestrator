# Replicate

Reproduction and verification instructions for the second-order-injection experiment set.

Tested reference environment: Pop!_OS 22.04, Python 3.11, Ollama.

## Public reproducibility status

There are two different reproducibility surfaces in this project and they should not be conflated:

1. **Public checkout verification** — clone this repository, install its dependencies, run its automated tests, inspect committed scripts/results, and validate the analysis code. This path is fully available from the public repository.
2. **Fresh model-experiment reruns** — the historical probe scripts in this document expect three HTTP gateway instances compatible with the `GATEWAY_A_URL`, `GATEWAY_B_URL`, and `GATEWAY_C_URL` interface. The sibling `localai_gateway` implementation used for the published runs is currently private, so the exact historical gateway environment is **not publicly reproducible from this repository alone**.

Do not report the second path as publicly self-contained unless that gateway implementation is made public or replaced by an equivalent public adapter with validated behavior.

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
pip install -r requirements.txt
```

### 3. Run the repository tests

```bash
python -m pytest -q
```

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

This verifies the committed implementation/evidence package. It does not create an independent fresh rerun of the model experiments.

---

## B. Fresh experiment reruns

### Prerequisites

Install Ollama and pull the reference model families:

```bash
ollama pull qwen2.5:3b
ollama pull mistral
ollama pull phi3:mini
```

The repository also contains an OpenAI-compatible/Ollama backend implementation for other project paths, but the historical second-order-injection scripts below are wired to the three gateway URL variables and should not be silently treated as equivalent without validation.

### Gateway requirement

Provide three compatible local HTTP gateways on ports 8765–8767, configured for the corresponding models. The implementation used for the original runs was `localai_gateway`, which is not currently public.

Once compatible gateways are available, verify them before starting a probe:

```bash
curl -fsS http://127.0.0.1:8765/health | python3 -m json.tool
curl -fsS http://127.0.0.1:8766/health | python3 -m json.tool
curl -fsS http://127.0.0.1:8767/health | python3 -m json.tool
```

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

Record model hashes/versions, gateway implementation, parameters, timestamps, hardware, and all errors for a meaningful rerun.

---

## Known run behavior

Historical runs observed intermittent gateway errors, especially on slower Mistral windows. Probe summaries calculate metrics over valid responses according to each script's recorded logic. Review ERROR/skipped counts rather than comparing percentages without their denominators.

LLM inference is nondeterministic. A useful replication report should include raw result files and environment details, not only headline percentages.

---

*badBANANA Security Research // GnomeMan4201*
