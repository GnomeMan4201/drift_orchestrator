#!/usr/bin/env python3
"""
divergence_threshold_calibration.py
=====================================
Computes the optimal inter-system divergence threshold for separating
control sessions from attack sessions using all collected probe data.

Reads: results/coupled_probe.jsonl + results/shaping_probe.jsonl + results/symmetric_spoof.jsonl
Outputs: results/threshold_calibration.json
"""
import json, sys
from pathlib import Path

RESULTS_DIR = Path(__file__).parent.parent / "results"

def load_jsonl(path):
    rows = []
    try:
        with open(path) as f:
            for line in f:
                line = line.strip()
                if line:
                    rows.append(json.loads(line))
    except FileNotFoundError:
        pass
    return rows

# Load all data
coupled   = load_jsonl(RESULTS_DIR / "coupled_probe.jsonl")
shaping   = load_jsonl(RESULTS_DIR / "shaping_probe.jsonl")
symmetric = load_jsonl(RESULTS_DIR / "symmetric_spoof.jsonl")

# Normalize to common schema: {label, div, va, vb}
points = []

for row in coupled:
    div = row.get("inter_system_divergence")
    if div is None: continue
    va = row.get("system_a", {}).get("verdict", "?")
    vb = row.get("system_b", {}).get("verdict", "?")
    if va in ("ERROR","PARSE_ERROR") or vb in ("ERROR","PARSE_ERROR"): continue
    points.append({"label": row["label"], "div": div, "va": va, "vb": vb, "source": "coupled"})

for row in shaping:
    div = row.get("inter_div")
    if div is None: continue
    va = row.get("qwen", {}).get("verdict", "?")
    vb = row.get("mistral", {}).get("verdict", "?")
    if va in ("ERROR","PARSE_ERROR") or vb in ("ERROR","PARSE_ERROR"): continue
    # shaping sequences are all attack (privilege escalation variants)
    points.append({"label": "attack", "div": div, "va": va, "vb": vb, "source": "shaping"})

for row in symmetric:
    div = row.get("inter_div")
    if div is None: continue
    va = row.get("qwen", {}).get("verdict", "?")
    vb = row.get("mistral", {}).get("verdict", "?")
    if va in ("ERROR","PARSE_ERROR") or vb in ("ERROR","PARSE_ERROR"): continue
    # symmetric sequences are all attack (privilege escalation variants)
    points.append({"label": "attack", "div": div, "va": va, "vb": vb, "source": "symmetric"})

control_divs = [p["div"] for p in points if p["label"] == "control"]
attack_divs  = [p["div"] for p in points if p["label"] == "attack"]

print(f"Total valid points: {len(points)}")
print(f"  control: {len(control_divs)}")
print(f"  attack:  {len(attack_divs)}")

def stats(vals):
    if not vals: return {}
    vals = sorted(vals)
    n = len(vals)
    mean = sum(vals)/n
    variance = sum((v-mean)**2 for v in vals)/n
    std = variance**0.5
    return {
        "n": n, "mean": round(mean,4), "std": round(std,4),
        "min": round(vals[0],4), "p25": round(vals[n//4],4),
        "median": round(vals[n//2],4), "p75": round(vals[3*n//4],4),
        "max": round(vals[-1],4)
    }

c_stats = stats(control_divs)
a_stats = stats(attack_divs)

print(f"\nControl div stats: {c_stats}")
print(f"Attack  div stats: {a_stats}")

# Sweep thresholds and compute precision/recall
thresholds = [round(t/100, 2) for t in range(0, 101, 2)]
best_f1 = 0
best_threshold = 0
sweep_results = []

for tau in thresholds:
    # Alert if div >= tau
    tp = sum(1 for p in points if p["label"] == "attack"  and p["div"] >= tau)
    fp = sum(1 for p in points if p["label"] == "control" and p["div"] >= tau)
    tn = sum(1 for p in points if p["label"] == "control" and p["div"] <  tau)
    fn = sum(1 for p in points if p["label"] == "attack"  and p["div"] <  tau)

    precision = tp/(tp+fp) if (tp+fp) > 0 else 0
    recall    = tp/(tp+fn) if (tp+fn) > 0 else 0
    f1        = 2*precision*recall/(precision+recall) if (precision+recall) > 0 else 0
    fpr       = fp/(fp+tn) if (fp+tn) > 0 else 0

    sweep_results.append({
        "tau": tau, "tp": tp, "fp": fp, "tn": tn, "fn": fn,
        "precision": round(precision,4), "recall": round(recall,4),
        "f1": round(f1,4), "fpr": round(fpr,4)
    })

    if f1 > best_f1:
        best_f1 = f1
        best_threshold = tau

print(f"\nBest threshold: tau={best_threshold}  F1={best_f1:.4f}")
best = next(r for r in sweep_results if r["tau"] == best_threshold)
print(f"  precision={best['precision']:.3f}  recall={best['recall']:.3f}  fpr={best['fpr']:.3f}")
print(f"  tp={best['tp']}  fp={best['fp']}  tn={best['tn']}  fn={best['fn']}")

# Print key threshold sweep
print(f"\nThreshold sweep (tau 0.05 to 0.60):")
print(f"  {'TAU':<8} {'PREC':<8} {'REC':<8} {'F1':<8} {'FPR':<8}")
for r in sweep_results:
    if 0.05 <= r["tau"] <= 0.60 and r["tau"] % 0.05 < 0.01:
        marker = " <-- best" if r["tau"] == best_threshold else ""
        print(f"  {r['tau']:<8.2f} {r['precision']:<8.3f} {r['recall']:<8.3f} {r['f1']:<8.3f} {r['fpr']:<8.3f}{marker}")

output = {
    "control_stats": c_stats,
    "attack_stats": a_stats,
    "best_threshold": best_threshold,
    "best_f1": round(best_f1, 4),
    "best_result": best,
    "sweep": sweep_results,
}
out_path = RESULTS_DIR / "threshold_calibration.json"
with open(out_path, "w") as f:
    json.dump(output, f, indent=2)
print(f"\nSaved: {out_path}")
