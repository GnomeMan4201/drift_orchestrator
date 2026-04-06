#!/usr/bin/env python3
import json
import sys
import time
from collections import defaultdict
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from firewall.gateway_wrapper import guarded_call
from agents.multi_agent import Coordinator

SUITE_PATH = ROOT / "benchmarks" / "suites" / "formal_control_plane_benchmark.json"
OUTDIR = ROOT / "results" / "formal_bench"
OUTDIR.mkdir(parents=True, exist_ok=True)

def contains_all(text, items):
    return all(x.lower() in text.lower() for x in items)

def contains_any(text, items):
    return any(x.lower() in text.lower() for x in items)

def eval_single(case):
    result = guarded_call(
        case["prompt"],
        drift_score=float(case.get("drift_score", 0.0)),
        use_rollback=True,
    )
    output = result.get("response", "")
    blocked = bool(result.get("blocked", False))
    reason = str(result.get("reason", "") or "")

    passed = True
    failures = []
    expect = case["expect"]

    if "blocked" in expect and blocked != expect["blocked"]:
        passed = False
        failures.append(f"blocked expected {expect['blocked']} got {blocked}")

    if "exact" in expect and output.strip() != expect["exact"].strip():
        passed = False
        failures.append("exact output mismatch")

    if "contains" in expect and not contains_all(output, expect["contains"]):
        passed = False
        failures.append(f"missing expected substrings: {expect['contains']}")

    if "not_contains" in expect and contains_any(output, expect["not_contains"]):
        passed = False
        failures.append(f"found forbidden substrings: {expect['not_contains']}")

    if "reason_contains" in expect and expect["reason_contains"].lower() not in reason.lower():
        passed = False
        failures.append(f"reason missing substring: {expect['reason_contains']}")

    return {
        "id": case["id"],
        "kind": case["kind"],
        "category": case["category"],
        "passed": passed,
        "failures": failures,
        "blocked": blocked,
        "reason": reason,
        "response": output,
        "inj_score": result.get("inj_score"),
        "drift_score": result.get("drift_score"),
    }

def eval_multi(case):
    c = Coordinator()
    c.add_agent("researcher")
    c.add_agent("executor")

    trace = []
    final = None
    for agent, prompt, drift in case["steps"]:
        final = c.run(agent, prompt, drift)
        trace.append({
            "agent": agent,
            "prompt": prompt,
            "drift_score": drift,
            "output": final["output"],
            "blocked": final["blocked"],
            "reason": final["reason"],
        })

    output = final["output"]
    blocked = bool(final["blocked"])
    reason = str(final["reason"] or "")

    passed = True
    failures = []
    expect = case["expect"]

    if "final_agent" in expect and final["agent"] != expect["final_agent"]:
        passed = False
        failures.append(f"final_agent expected {expect['final_agent']} got {final['agent']}")

    if "final_blocked" in expect and blocked != expect["final_blocked"]:
        passed = False
        failures.append(f"final_blocked expected {expect['final_blocked']} got {blocked}")

    if "final_contains" in expect and not contains_all(output, expect["final_contains"]):
        passed = False
        failures.append(f"missing expected substrings: {expect['final_contains']}")

    if "final_not_contains" in expect and contains_any(output, expect["final_not_contains"]):
        passed = False
        failures.append(f"found forbidden substrings: {expect['final_not_contains']}")

    return {
        "id": case["id"],
        "kind": case["kind"],
        "category": case["category"],
        "passed": passed,
        "failures": failures,
        "blocked": blocked,
        "reason": reason,
        "response": output,
        "trace": trace,
    }

def main():
    suite = json.loads(SUITE_PATH.read_text(encoding="utf-8"))
    ts = time.strftime("%Y%m%d_%H%M%S")
    started = time.time()

    results = []
    by_category = defaultdict(lambda: {"total": 0, "passed": 0, "failed": 0})

    for case in suite["cases"]:
        if case["kind"] == "single":
            res = eval_single(case)
        elif case["kind"] == "multi":
            res = eval_multi(case)
        else:
            raise ValueError(f"unknown case kind: {case['kind']}")

        results.append(res)
        by_category[res["category"]]["total"] += 1
        if res["passed"]:
            by_category[res["category"]]["passed"] += 1
        else:
            by_category[res["category"]]["failed"] += 1

    duration = round(time.time() - started, 3)
    passed = sum(1 for r in results if r["passed"])
    failed = len(results) - passed
    pass_rate = round((passed / len(results)) * 100.0, 2) if results else 0.0

    summary = {
        "suite_name": suite["suite_name"],
        "version": suite["version"],
        "timestamp": ts,
        "total": len(results),
        "passed": passed,
        "failed": failed,
        "pass_rate": pass_rate,
        "duration_sec": duration,
        "by_category": dict(by_category),
        "results": results,
    }

    json_path = OUTDIR / f"formal_benchmark_{ts}.json"
    md_path = OUTDIR / f"formal_benchmark_{ts}.md"

    json_path.write_text(json.dumps(summary, indent=2), encoding="utf-8")

    lines = []
    lines.append(f"# Formal Control-Plane Benchmark ({ts})")
    lines.append("")
    lines.append(f"- Suite: {summary['suite_name']} v{summary['version']}")
    lines.append(f"- Total: {summary['total']}")
    lines.append(f"- Passed: {summary['passed']}")
    lines.append(f"- Failed: {summary['failed']}")
    lines.append(f"- Pass rate: {summary['pass_rate']}%")
    lines.append(f"- Duration: {summary['duration_sec']}s")
    lines.append("")
    lines.append("## Category summary")
    lines.append("")
    lines.append("| category | total | passed | failed |")
    lines.append("|---|---:|---:|---:|")
    for cat, vals in sorted(summary["by_category"].items()):
        lines.append(f"| {cat} | {vals['total']} | {vals['passed']} | {vals['failed']} |")

    lines.append("")
    lines.append("## Case summary")
    lines.append("")
    lines.append("| id | kind | category | passed | blocked | reason |")
    lines.append("|---|---|---|---:|---:|---|")
    for r in results:
        lines.append(
            f"| {r['id']} | {r['kind']} | {r['category']} | "
            f"{'yes' if r['passed'] else 'no'} | "
            f"{'yes' if r['blocked'] else 'no'} | {r['reason']} |"
        )

    lines.append("")
    lines.append("## Failures")
    lines.append("")
    had_fail = False
    for r in results:
        if not r["passed"]:
            had_fail = True
            lines.append(f"### {r['id']}")
            lines.append("")
            lines.append(f"- Category: {r['category']}")
            lines.append(f"- Failures: {', '.join(r['failures'])}")
            lines.append(f"- Response: {r['response']}")
            if r["kind"] == "multi":
                lines.append("- Trace:")
                for step in r.get("trace", []):
                    lines.append(f"  - {step}")
            lines.append("")
    if not had_fail:
        lines.append("None.")

    md_path.write_text("\n".join(lines), encoding="utf-8")

    print(f"WROTE_JSON {json_path}")
    print(f"WROTE_MD {md_path}")
    print(f"TOTAL {summary['total']}")
    print(f"PASSED {summary['passed']}")
    print(f"FAILED {summary['failed']}")
    print(f"PASS_RATE {summary['pass_rate']}")

if __name__ == "__main__":
    main()
