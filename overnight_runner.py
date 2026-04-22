#!/usr/bin/env python3
"""
overnight_runner.py
====================
Runs all probes 3+ times each with retries, logging, and a final
summary report. Designed to run unattended overnight.

Run order per iteration:
  1. coupled_dual_system_probe      (baseline divergence data)
  2. control_expansion_probe        (balance the dataset)
  3. adversarial_shaping_probe      (shaping attack characterization)
  4. symmetric_spoof_probe          (symmetric bypass attempt)
  5. second_order_injection_phase1  (individual model injection)
  6. second_order_injection_phase2  (coupled system bypass)
  7. mitigation_probe               (sanitization effectiveness)
  8. divergence_threshold_calibration (analysis only, no model calls)

3 full iterations. ~45-90 min per iteration depending on model speed.
Total estimated runtime: 3-5 hours.

Logs: results/overnight_TIMESTAMP.log
Summary: results/overnight_summary.json
"""
import subprocess, sys, os, json, time
from datetime import datetime, timezone
from pathlib import Path

RESULTS_DIR = Path(__file__).parent / "results"
RESULTS_DIR.mkdir(exist_ok=True)

GATEWAY_A = "http://127.0.0.1:8765"
GATEWAY_B = "http://127.0.0.1:8766"
PYTHON    = str(Path(__file__).parent / ".venv/bin/python")
SCRIPTS   = Path(__file__).parent / "scripts"

PROBES = [
    "coupled_dual_system_probe.py",
    "control_expansion_probe.py",
    "adversarial_shaping_probe.py",
    "symmetric_spoof_probe.py",
    "second_order_injection_phase1.py",
    "second_order_injection_phase2.py",
    "mitigation_probe.py",
    "divergence_threshold_calibration.py",
]

N_ITERATIONS = 3
COOLDOWN_BETWEEN_PROBES = 30      # seconds between probes
COOLDOWN_BETWEEN_ITERATIONS = 120 # seconds between full iterations

def ts():
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%S")

def run_probe(script, iteration, log_fh):
    script_path = SCRIPTS / script
    if not script_path.exists():
        msg = f"[{ts()}] SKIP {script} — file not found"
        print(msg); log_fh.write(msg + "\n"); log_fh.flush()
        return {"script": script, "iteration": iteration, "status": "skipped", "elapsed": 0}

    msg = f"[{ts()}] START {script} (iteration {iteration})"
    print(msg); log_fh.write(msg + "\n"); log_fh.flush()

    env = os.environ.copy()
    env["GATEWAY_A_URL"] = GATEWAY_A
    env["GATEWAY_B_URL"] = GATEWAY_B

    t0 = time.time()
    try:
        result = subprocess.run(
            [PYTHON, str(script_path)],
            env=env,
            capture_output=True,
            text=True,
            timeout=3600,
        )
        elapsed = round(time.time() - t0, 1)
        status = "ok" if result.returncode == 0 else "error"

        # Write stdout to log
        for line in result.stdout.splitlines():
            log_fh.write(f"  {line}\n")
        if result.stderr:
            for line in result.stderr.splitlines():
                if "INFO:" in line or "WARNING:" in line:
                    continue  # skip uvicorn noise
                log_fh.write(f"  ERR: {line}\n")
        log_fh.flush()

        msg = f"[{ts()}] END {script} — {status} ({elapsed}s)"
        print(msg); log_fh.write(msg + "\n"); log_fh.flush()
        return {"script": script, "iteration": iteration, "status": status, "elapsed": elapsed}

    except subprocess.TimeoutExpired:
        elapsed = round(time.time() - t0, 1)
        msg = f"[{ts()}] TIMEOUT {script} after {elapsed}s"
        print(msg); log_fh.write(msg + "\n"); log_fh.flush()
        return {"script": script, "iteration": iteration, "status": "timeout", "elapsed": elapsed}
    except Exception as e:
        elapsed = round(time.time() - t0, 1)
        msg = f"[{ts()}] EXCEPTION {script}: {e}"
        print(msg); log_fh.write(msg + "\n"); log_fh.flush()
        return {"script": script, "iteration": iteration, "status": "exception", "elapsed": elapsed}

def check_gateways(log_fh):
    import urllib.request
    for url, label in [(GATEWAY_A, "A"), (GATEWAY_B, "B")]:
        try:
            r = urllib.request.urlopen(f"{url}/health", timeout=5)
            data = json.loads(r.read())
            msg = f"[{ts()}] Gateway {label} ({url}): {data}"
        except Exception as e:
            msg = f"[{ts()}] Gateway {label} ({url}): DOWN — {e}"
        print(msg); log_fh.write(msg + "\n"); log_fh.flush()

run_ts = datetime.now(timezone.utc).strftime("%Y%m%d_%H%M%S")
log_path = RESULTS_DIR / f"overnight_{run_ts}.log"
summary_path = RESULTS_DIR / f"overnight_{run_ts}_summary.json"

all_results = []

with open(log_path, "w") as log_fh:
    msg = f"[{ts()}] OVERNIGHT RUNNER START — {N_ITERATIONS} iterations, {len(PROBES)} probes each"
    print(msg); log_fh.write(msg + "\n\n"); log_fh.flush()

    check_gateways(log_fh)
    log_fh.write("\n"); log_fh.flush()

    for iteration in range(1, N_ITERATIONS + 1):
        msg = f"\n[{ts()}] ===== ITERATION {iteration}/{N_ITERATIONS} ====="
        print(msg); log_fh.write(msg + "\n"); log_fh.flush()

        for script in PROBES:
            result = run_probe(script, iteration, log_fh)
            all_results.append(result)

            if script != PROBES[-1]:
                msg = f"[{ts()}] cooling down {COOLDOWN_BETWEEN_PROBES}s..."
                print(msg); log_fh.write(msg + "\n"); log_fh.flush()
                time.sleep(COOLDOWN_BETWEEN_PROBES)

        if iteration < N_ITERATIONS:
            msg = f"[{ts()}] iteration {iteration} complete — cooling down {COOLDOWN_BETWEEN_ITERATIONS}s before next..."
            print(msg); log_fh.write(msg + "\n"); log_fh.flush()
            time.sleep(COOLDOWN_BETWEEN_ITERATIONS)

    msg = f"\n[{ts()}] ===== ALL ITERATIONS COMPLETE ====="
    print(msg); log_fh.write(msg + "\n"); log_fh.flush()

    # Summary
    log_fh.write("\nSUMMARY:\n")
    ok = [r for r in all_results if r["status"] == "ok"]
    err = [r for r in all_results if r["status"] == "error"]
    skip = [r for r in all_results if r["status"] == "skipped"]
    timeout = [r for r in all_results if r["status"] == "timeout"]

    log_fh.write(f"  total runs : {len(all_results)}\n")
    log_fh.write(f"  ok         : {len(ok)}\n")
    log_fh.write(f"  errors     : {len(err)}\n")
    log_fh.write(f"  timeouts   : {len(timeout)}\n")
    log_fh.write(f"  skipped    : {len(skip)}\n")

    if err:
        log_fh.write("  FAILED:\n")
        for r in err:
            log_fh.write(f"    iter={r['iteration']} {r['script']}\n")

    print(f"  ok={len(ok)} err={len(err)} timeout={len(timeout)} skip={len(skip)}")

summary = {
    "run_ts": run_ts,
    "iterations": N_ITERATIONS,
    "probes": PROBES,
    "results": all_results,
    "ok": len(ok),
    "errors": len(err),
    "timeouts": len(timeout),
    "skipped": len(skip),
}
with open(summary_path, "w") as f:
    json.dump(summary, f, indent=2)

print(f"\nLog:     {log_path}")
print(f"Summary: {summary_path}")
