# Replicate

Exact reproduction instructions for all experiments in the second-order injection paper.

Tested on: Pop!_OS 22.04, Python 3.11, Ollama 0.1.x

---

## Prerequisites

### 1. Install Ollama
```bash
curl -fsSL https://ollama.ai/install.sh | sh
```

### 2. Pull required models
```bash
ollama pull qwen2.5:3b
ollama pull mistral
ollama pull phi3:mini
```

Verify:
```bash
ollama list
# Should show qwen2.5:3b, mistral, phi3:mini
```

### 3. Clone repositories
```bash
git clone git@github.com:GnomeMan4201/drift_orchestrator.git
git clone git@github.com:GnomeMan4201/localai_gateway.git
cd drift_orchestrator
```

### 4. Install dependencies
```bash
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
```

---

## Start Gateways

Three gateway instances required — one per model:

```bash
cd ../localai_gateway
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt

# Terminal 1
MODEL_FAST=qwen2.5:3b GATEWAY_PORT=8765 GATEWAY_DB=gateway.db python main.py &

# Terminal 2
MODEL_FAST=mistral GATEWAY_PORT=8766 GATEWAY_DB=gateway_b.db python main.py &

# Terminal 3
MODEL_FAST=phi3:mini GATEWAY_PORT=8767 GATEWAY_DB=gateway_c.db python main.py &

# Verify all three up
curl -s http://127.0.0.1:8765/health | python3 -m json.tool | grep status
curl -s http://127.0.0.1:8766/health | python3 -m json.tool | grep status
curl -s http://127.0.0.1:8767/health | python3 -m json.tool | grep status
```

Expected output: `"status": "ok"` for all three.

---

## Run Experiments

Set gateway URLs and run from the drift_orchestrator directory:

```bash
cd ../drift_orchestrator
export GATEWAY_A_URL=http://127.0.0.1:8765
export GATEWAY_B_URL=http://127.0.0.1:8766
export GATEWAY_C_URL=http://127.0.0.1:8767
```

### Phase 1 — Individual model injection
```bash
.venv/bin/python -u scripts/second_order_injection_phase1.py 2>&1 | tee results/phase1.log
```
Expected: V1 bypass on qwen 80-100%, mistral 100%

### Phase 2 — Coupled system bypass
```bash
.venv/bin/python -u scripts/second_order_injection_phase2.py 2>&1 | tee results/phase2.log
```
Expected: V1 symmetric bypass 100%, avg_div=0.01

### Mitigation probe
```bash
.venv/bin/python -u scripts/mitigation_probe.py 2>&1 | tee results/mitigation.log
```
Expected: M4 achieves 0% qwen bypass, mistral remains 100%

### Cross-model generalization
```bash
.venv/bin/python -u scripts/cross_model_generalization_probe.py 2>&1 | tee results/cross_model.log
```
Expected: phi3 V1 bypass ~33%, V2 ~39%

### phi3 targeted injection
```bash
.venv/bin/python -u scripts/phi3_targeted_injection_probe.py 2>&1 | tee results/phi3_targeted.log
```
Expected: V4 bypass 100%, V5 bypass ~17%

### Vector transfer
```bash
.venv/bin/python -u scripts/vector_transfer_probe.py 2>&1 | tee results/transfer.log
```
Expected: V4 and V6 transfer to qwen and mistral at 100%

### Meta-evaluator
```bash
.venv/bin/python -u scripts/meta_evaluator_probe.py 2>&1 | tee results/meta.log
```
Expected: V4 asymmetric detection 93.3%, clean session false alarm 72.2%

### Meta-evaluator calibrated
```bash
.venv/bin/python -u scripts/meta_evaluator_calibrated_probe.py 2>&1 | tee results/meta_calibrated.log
```
Expected: false alarm rate lower than uncalibrated, detection rate maintained

### Full overnight run
```bash
.venv/bin/python -u overnight_runner.py 2>&1 | tee results/overnight.log
```
Runs all probes across 3 iterations. Takes ~6 hours.

---

## Verify Results

Compare your output against the published result files:

```bash
# Check summary files
cat results/soi_phase2_summary.json | python3 -m json.tool
cat results/vector_transfer_summary.json | python3 -m json.tool
cat results/meta_evaluator_summary.json | python3 -m json.tool
```

Key numbers to verify:
- V1 symmetric bypass rate: ~100%
- V1 symmetric avg_div: ~0.01
- V4 transfer to qwen: 100%
- V4 transfer to mistral: 100%
- Meta-evaluator V4 asymmetric detection: ~93%

---

## Notes

**502 errors are normal.** Mistral has early-window timeout behavior on short inputs — the gateway returns 502 and the probe marks it as ERROR/skipped. This is expected and documented in the paper limitations. Results are computed over valid responses only.

**Results will vary slightly** across runs due to LLM non-determinism. The key findings (100% V4 transfer, divergence collapse, meta-evaluator detection rates) are consistent across 3-iteration runs.

**Hardware**: experiments run on consumer hardware (Pop!_OS, no GPU). Ollama CPU inference. Mistral is the slowest model — allow 90-120 minutes per full probe suite.

---

*Questions or reproduction issues: open an issue on GitHub.*
*badBANANA Security Research // gnomeman4201*
