#!/usr/bin/env python3
"""Fail-closed verifier for the committed Second-Order Injection claim ledger."""

from __future__ import annotations

import argparse
import json
import math
import sys
from pathlib import Path
from typing import Any

MISSING = object()
FLOAT_TOLERANCE = 1e-4
VALID_KINDS = {"binary_rate", "numeric_mean"}
VALID_OPS = {"eq", "not_in", "is_number"}


class VerificationError(Exception):
    """Raised when evidence or a claim contract cannot be verified."""


def read_json(path: Path) -> Any:
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except FileNotFoundError as exc:
        raise VerificationError(f"missing file: {path}") from exc
    except (UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise VerificationError(f"invalid JSON in {path}: {exc}") from exc


def read_jsonl(path: Path) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    try:
        with path.open("r", encoding="utf-8") as handle:
            for line_number, line in enumerate(handle, start=1):
                if not line.strip():
                    continue
                try:
                    row = json.loads(line)
                except json.JSONDecodeError as exc:
                    raise VerificationError(
                        f"invalid JSONL in {path}:{line_number}: {exc}"
                    ) from exc
                if not isinstance(row, dict):
                    raise VerificationError(
                        f"non-object JSONL row in {path}:{line_number}"
                    )
                rows.append(row)
    except FileNotFoundError as exc:
        raise VerificationError(f"missing evidence file: {path}") from exc
    except UnicodeDecodeError as exc:
        raise VerificationError(f"invalid UTF-8 in {path}: {exc}") from exc

    if not rows:
        raise VerificationError(f"evidence file has no rows: {path}")
    return rows


def get_path(value: Any, dotted_path: str) -> Any:
    current = value
    for part in dotted_path.split("."):
        if not isinstance(current, dict) or part not in current:
            return MISSING
        current = current[part]
    return current


def predicate_matches(row: dict[str, Any], predicate: dict[str, Any]) -> bool:
    path = predicate.get("path")
    op = predicate.get("op")
    if not isinstance(path, str) or not path:
        raise VerificationError(f"invalid predicate path: {predicate!r}")
    if op not in VALID_OPS:
        raise VerificationError(f"unsupported predicate operator: {op!r}")

    actual = get_path(row, path)
    if op == "eq":
        if "value" not in predicate:
            raise VerificationError(f"eq predicate missing value: {predicate!r}")
        return actual is not MISSING and actual == predicate["value"]
    if op == "not_in":
        values = predicate.get("value")
        if not isinstance(values, list):
            raise VerificationError(f"not_in value must be a list: {predicate!r}")
        return actual is not MISSING and actual not in values
    if op == "is_number":
        return isinstance(actual, (int, float)) and not isinstance(actual, bool)
    raise AssertionError("unreachable")


def all_match(row: dict[str, Any], predicates: list[dict[str, Any]]) -> bool:
    return all(predicate_matches(row, predicate) for predicate in predicates)


def any_match(row: dict[str, Any], predicates: list[dict[str, Any]]) -> bool:
    return any(predicate_matches(row, predicate) for predicate in predicates)


def safe_source(root: Path, source: Any) -> Path:
    if not isinstance(source, str) or not source.startswith("results/"):
        raise VerificationError(f"source must be under results/: {source!r}")
    if not source.endswith(".jsonl"):
        raise VerificationError(f"source must be JSONL: {source!r}")

    root = root.resolve()
    path = (root / source).resolve()
    try:
        path.relative_to(root)
    except ValueError as exc:
        raise VerificationError(f"source escapes repository root: {source!r}") from exc
    return path


def wilson_interval(successes: int, trials: int, z: float = 1.959963984540054) -> list[float] | None:
    if trials == 0:
        return None
    p = successes / trials
    denominator = 1 + (z * z / trials)
    center = (p + z * z / (2 * trials)) / denominator
    margin = (
        z
        * math.sqrt((p * (1 - p) + z * z / (4 * trials)) / trials)
        / denominator
    )
    return [round(max(0.0, center - margin), 4), round(min(1.0, center + margin), 4)]


def assert_expected(
    derivation_id: str,
    observed: dict[str, Any],
    expected: dict[str, Any],
) -> list[str]:
    failures: list[str] = []
    for key, expected_value in expected.items():
        if key not in observed:
            failures.append(f"{derivation_id}: observed value missing {key}")
            continue
        actual = observed[key]
        if isinstance(expected_value, float):
            if not isinstance(actual, (int, float)) or abs(actual - expected_value) > FLOAT_TOLERANCE:
                failures.append(
                    f"{derivation_id}: {key} expected {expected_value}, observed {actual}"
                )
        elif actual != expected_value:
            failures.append(
                f"{derivation_id}: {key} expected {expected_value}, observed {actual}"
            )
    return failures


def derive(root: Path, derivation: dict[str, Any]) -> dict[str, Any]:
    derivation_id = derivation.get("derivation_id")
    kind = derivation.get("kind")
    if not isinstance(derivation_id, str) or not derivation_id:
        raise VerificationError("derivation_id must be a non-empty string")
    if kind not in VALID_KINDS:
        raise VerificationError(f"{derivation_id}: unsupported kind {kind!r}")

    filters = derivation.get("filters")
    valid_when = derivation.get("valid_when")
    error_when = derivation.get("error_when")
    expected = derivation.get("expected")
    if not isinstance(filters, list):
        raise VerificationError(f"{derivation_id}: filters must be a list")
    if not isinstance(valid_when, list) or not valid_when:
        raise VerificationError(f"{derivation_id}: valid_when must be non-empty")
    if not isinstance(error_when, list):
        raise VerificationError(f"{derivation_id}: error_when must be a list")
    if not isinstance(expected, dict):
        raise VerificationError(f"{derivation_id}: expected must be an object")

    source_path = safe_source(root, derivation.get("source"))
    source_rows = read_jsonl(source_path)
    rows = [row for row in source_rows if all_match(row, filters)]
    if not rows:
        raise VerificationError(f"{derivation_id}: filters selected zero rows")

    valid_rows = [row for row in rows if all_match(row, valid_when)]
    invalid_rows = [row for row in rows if not all_match(row, valid_when)]
    error_n = sum(1 for row in invalid_rows if any_match(row, error_when))
    skipped_n = len(invalid_rows) - error_n

    observed: dict[str, Any] = {
        "total_n": len(rows),
        "valid_n": len(valid_rows),
        "error_n": error_n,
        "skipped_n": skipped_n,
    }

    if kind == "binary_rate":
        success_when = derivation.get("success_when")
        if not isinstance(success_when, list) or not success_when:
            raise VerificationError(f"{derivation_id}: success_when must be non-empty")
        success_n = sum(1 for row in valid_rows if all_match(row, success_when))
        observed["success_n"] = success_n
        observed["rate"] = round(success_n / len(valid_rows), 4) if valid_rows else None
        observed["wilson_95"] = wilson_interval(success_n, len(valid_rows))
    else:
        value_path = derivation.get("value_path")
        if not isinstance(value_path, str) or not value_path:
            raise VerificationError(f"{derivation_id}: value_path must be non-empty")
        values = [get_path(row, value_path) for row in valid_rows]
        if any(
            not isinstance(value, (int, float)) or isinstance(value, bool)
            for value in values
        ):
            raise VerificationError(
                f"{derivation_id}: valid row has non-numeric {value_path}"
            )
        observed["mean"] = (
            round(sum(float(value) for value in values) / len(values), 4)
            if values
            else None
        )

    observed["derivation_id"] = derivation_id
    observed["source"] = str(source_path.relative_to(root.resolve()))
    observed["verified"] = not assert_expected(derivation_id, observed, expected)
    return observed


def verify(root: Path, ledger_path: Path) -> dict[str, Any]:
    ledger = read_json(ledger_path)
    if not isinstance(ledger, dict) or ledger.get("schema_version") != "claims.v1":
        raise VerificationError("claim ledger schema_version must be claims.v1")
    claims = ledger.get("claims")
    if not isinstance(claims, list) or not claims:
        raise VerificationError("claim ledger must contain claims")

    seen_claims: set[str] = set()
    seen_derivations: set[str] = set()
    output_claims: list[dict[str, Any]] = []
    failures: list[str] = []

    for claim in claims:
        if not isinstance(claim, dict):
            raise VerificationError("claim entries must be objects")
        claim_id = claim.get("claim_id")
        if not isinstance(claim_id, str) or not claim_id:
            raise VerificationError("claim_id must be a non-empty string")
        if claim_id in seen_claims:
            raise VerificationError(f"duplicate claim_id: {claim_id}")
        seen_claims.add(claim_id)

        derivations = claim.get("derivations")
        if not isinstance(derivations, list) or not derivations:
            raise VerificationError(f"{claim_id}: no derivations")

        claim_results = []
        for derivation in derivations:
            if not isinstance(derivation, dict):
                raise VerificationError(f"{claim_id}: derivation must be an object")
            derivation_id = derivation.get("derivation_id")
            if derivation_id in seen_derivations:
                raise VerificationError(f"duplicate derivation_id: {derivation_id}")
            seen_derivations.add(derivation_id)

            result = derive(root, derivation)
            expected = derivation["expected"]
            failures.extend(assert_expected(derivation_id, result, expected))
            claim_results.append(result)

        output_claims.append(
            {
                "claim_id": claim_id,
                "status": claim.get("status"),
                "verified": all(result["verified"] for result in claim_results),
                "derivations": claim_results,
            }
        )

    return {
        "schema_version": "claim-verification.v1",
        "verified": not failures,
        "claims": output_claims,
        "failures": failures,
    }


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--root",
        type=Path,
        default=Path(__file__).resolve().parents[1],
        help="repository root",
    )
    parser.add_argument(
        "--claims",
        type=Path,
        default=Path("research/claims.v1.json"),
        help="claim ledger path relative to root",
    )
    parser.add_argument("--json", action="store_true", help="emit JSON")
    args = parser.parse_args()

    root = args.root.resolve()
    ledger_path = args.claims if args.claims.is_absolute() else root / args.claims

    try:
        result = verify(root, ledger_path)
    except VerificationError as exc:
        print(f"CLAIM VERIFICATION ERROR: {exc}", file=sys.stderr)
        return 2

    if args.json:
        print(json.dumps(result, indent=2, sort_keys=True))
    else:
        for claim in result["claims"]:
            marker = "PASS" if claim["verified"] else "FAIL"
            print(f"[{marker}] {claim['claim_id']}")
            for item in claim["derivations"]:
                details = [
                    f"valid={item['valid_n']}/{item['total_n']}",
                    f"errors={item['error_n']}",
                    f"skipped={item['skipped_n']}",
                ]
                if "rate" in item:
                    details.append(f"success={item['success_n']}")
                    details.append(f"rate={item['rate']}")
                    details.append(f"wilson95={item['wilson_95']}")
                if "mean" in item:
                    details.append(f"mean={item['mean']}")
                print(f"  {item['derivation_id']}: " + " ".join(details))
        for failure in result["failures"]:
            print(f"FAIL: {failure}", file=sys.stderr)

    return 0 if result["verified"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
