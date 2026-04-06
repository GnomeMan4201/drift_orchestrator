#!/usr/bin/env python3
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

import json
import time
from pathlib import Path
from typing import Any

from firewall.gateway_wrapper import guarded_call

ROOT = Path(__file__).resolve().parent.parent
CASES_PATH = ROOT / "benchmarks" / "firewall_cases.json"
OUTDIR = ROOT / "results"
OUTDIR.mkdir(parents=True, exist_ok=True)

def contains_all(text: str, items: list[str]) -> bool:
    return all(x.lower() in text.lower() for x in items)

def contains_any(text: str, items: list[str]) -> bool:
    return any(x.lower() in text.lower() for x in items)

def evaluate(case: dict[str, Any], result: dict[str, Any]) -> dict[str, Any]:
    output = result.get("response", "")
    blocked = bool(result.get("blocked", False))
    reason = str(result.get("reason", "") or "")

    passed = True
    failures = []

    if "expect_blocked" in case and blocked != case["expect_blocked"]:
        passed = False
        failures.append(f"blocked expected {case['expect_blocked']} got {blocked}")

    if "expect_exact" in case and output.strip() != case["expect_exact"].strip():
        passed = False
        failures.append("exact output mismatch")

    if "expect_contains" in case and not contains_all(output, case["expect_contains"]):
        passed = False
        failures.append(f"missing expected substrings: {case['expect_contains']}")

    if "expect_not_contains" in case and contains_any(output, case["expect_not_contains"]):
        passed = False
        failures.append(f"found forbidden substrings: {case['expect_not_contains']}")

    if "expect_reason_contains" in case and case["expect_reason_contains"].lower() not in reason.lower():
        passed = False
        failures.append(f"reason missing substring: {case['expect_reason_contains']}")

    return {
        "id": case["id"],
        "passed": passed,
        "failures": failures,
        "prompt": case["prompt"],
        "drift_score": case.get("drift_score", 0.0),
        "response": output,
        "inj_score": result.get("inj_score"),
        "blocked": blocked,
        "reason": reason,
    }

def main() -> None:
    cases = json.loads(CASES_PATH.read_text(encoding="utf-8"))
    ts = time.strftime("%Y%m%d_%H%M%S")
    results = []
    started = time.time()

    for case in cases:
        result = guarded_call(
            case["prompt"],
            drift_score=float(case.get("drift_score", 0.0)),
            use_rollback=True,
        )
        results.append(evaluate(case, result))

    duration = round(time.time() - started, 3)
    passed = sum(1 for r in results if r["passed"])
    failed = len(results) - passed
    pass_rate = round((passed / len(results)) * 100.0, 2) if results else 0.0

    summary = {
        "timestamp": ts,
        "total": len(results),
        "passed": passed,
        "failed": failed,
        "pass_rate": pass_rate,
        "duration_sec": duration,
        "results": results,
    }

    json_path = OUTDIR / f"firewall_benchmark_{ts}.json"
    md_path = OUTDIR / f"firewall_benchmark_{ts}.md"

    json_path.write_text(json.dumps(summary, indent=2), encoding="utf-8")

    lines = []
    lines.append(f"# Firewall Benchmark Report ({ts})")
    lines.append("")
    lines.append(f"- Total: {summary['total']}")
    lines.append(f"- Passed: {summary['passed']}")
    lines.append(f"- Failed: {summary['failed']}")
    lines.append(f"- Pass rate: {summary['pass_rate']}%")
    lines.append(f"- Duration: {summary['duration_sec']}s")
    lines.append("")
    lines.append("| id | passed | blocked | inj_score | drift_score | reason |")
    lines.append("|---|---:|---:|---:|---:|---|")

    for r in results:
        lines.append(
            f"| {r['id']} | {'yes' if r['passed'] else 'no'} | "
            f"{'yes' if r['blocked'] else 'no'} | {r['inj_score']} | {r['drift_score']} | {r['reason']} |"
        )

    lines.append("")
    lines.append("## Failures")
    lines.append("")
    for r in results:
        if not r["passed"]:
            lines.append(f"### {r['id']}")
            lines.append("")
            lines.append(f"- Failures: {', '.join(r['failures'])}")
            lines.append(f"- Response: {r['response']}")
            lines.append("")

    md_path.write_text("\n".join(lines), encoding="utf-8")

    print(f"WROTE_JSON {json_path}")
    print(f"WROTE_MD {md_path}")
    print(f"TOTAL {summary['total']}")
    print(f"PASSED {summary['passed']}")
    print(f"FAILED {summary['failed']}")
    print(f"PASS_RATE {summary['pass_rate']}")

if __name__ == "__main__":
    main()
