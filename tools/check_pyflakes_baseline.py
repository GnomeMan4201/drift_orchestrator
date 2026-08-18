#!/usr/bin/env python3
"""Enforce an exact, monotonic Pyflakes debt baseline."""

from __future__ import annotations

import argparse
import json
import pathlib
import re
import subprocess
import sys
from collections import Counter
from typing import Iterable

DIAGNOSTIC_RE = re.compile(r"^(.*?):\d+:\d+: (.*)$")
EXCLUDED_PARTS = {".git", ".venv", "venv", "__pycache__"}
FORMAT_VERSION = 1


def python_files(root: pathlib.Path = pathlib.Path(".")) -> list[pathlib.Path]:
    return sorted(
        path
        for path in root.rglob("*.py")
        if not any(part in EXCLUDED_PARTS for part in path.parts)
    )


def normalize_diagnostics(lines: Iterable[str]) -> Counter[str]:
    """Collapse location churn while preserving file/message multiplicity."""
    counts: Counter[str] = Counter()
    for raw in lines:
        line = raw.strip()
        if not line:
            continue
        match = DIAGNOSTIC_RE.match(line)
        if match:
            path, message = match.groups()
            key = f"{path}: {message}"
        else:
            key = f"<unparsed>: {line}"
        counts[key] += 1
    return counts


def collect_pyflakes(files: list[pathlib.Path]) -> Counter[str]:
    if not files:
        raise RuntimeError("no Python files found")
    proc = subprocess.run(
        [sys.executable, "-m", "pyflakes", *map(str, files)],
        capture_output=True,
        text=True,
        check=False,
    )
    if proc.returncode not in (0, 1):
        raise RuntimeError(
            f"pyflakes execution failed with exit code {proc.returncode}: "
            f"{(proc.stderr or proc.stdout).strip()}"
        )
    return normalize_diagnostics((proc.stdout + proc.stderr).splitlines())


def load_baseline(path: pathlib.Path) -> Counter[str]:
    data = json.loads(path.read_text(encoding="utf-8"))
    if data.get("format_version") != FORMAT_VERSION:
        raise RuntimeError(f"unsupported baseline format: {data.get('format_version')}")
    diagnostics = data.get("diagnostics")
    if not isinstance(diagnostics, dict):
        raise RuntimeError("baseline diagnostics must be an object")
    return Counter({str(key): int(value) for key, value in diagnostics.items()})


def write_baseline(path: pathlib.Path, diagnostics: Counter[str]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    payload = {
        "format_version": FORMAT_VERSION,
        "diagnostics": dict(sorted(diagnostics.items())),
    }
    path.write_text(json.dumps(payload, indent=2) + "\n", encoding="utf-8")


def regressions(current: Counter[str], baseline: Counter[str]) -> dict[str, tuple[int, int]]:
    return {
        key: (baseline.get(key, 0), count)
        for key, count in current.items()
        if count > baseline.get(key, 0)
    }


def reductions(current: Counter[str], baseline: Counter[str]) -> dict[str, tuple[int, int]]:
    """Return baseline allowances that can now be tightened."""
    return {
        key: (allowed, current.get(key, 0))
        for key, allowed in baseline.items()
        if current.get(key, 0) < allowed
    }


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--baseline",
        type=pathlib.Path,
        default=pathlib.Path(".github/pyflakes-baseline.json"),
    )
    parser.add_argument("--write-baseline", action="store_true")
    args = parser.parse_args()

    current = collect_pyflakes(python_files())
    if args.write_baseline:
        write_baseline(args.baseline, current)
        print(
            f"Wrote Pyflakes baseline: {sum(current.values())} diagnostics "
            f"across {len(current)} normalized classes"
        )
        return 0

    if not args.baseline.is_file():
        print(f"Pyflakes baseline missing: {args.baseline}", file=sys.stderr)
        return 2

    baseline = load_baseline(args.baseline)
    increased = regressions(current, baseline)
    if increased:
        print("Pyflakes debt regression detected:")
        for key, (allowed, observed) in sorted(increased.items()):
            print(f"  {allowed} -> {observed}: {key}")
        print("Fix the new diagnostic; do not expand the baseline in routine PRs.")
        return 1

    reduced = reductions(current, baseline)
    if reduced:
        print("Pyflakes debt was reduced, but the committed baseline is now stale:")
        for key, (allowed, observed) in sorted(reduced.items()):
            print(f"  {allowed} -> {observed}: {key}")
        print("Tighten the baseline in this PR so removed debt cannot be reintroduced later.")
        return 1

    print(
        f"Pyflakes ratchet passed exactly: {sum(current.values())} diagnostics "
        f"across {len(current)} normalized classes."
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
