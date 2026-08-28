import json
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[1]
VERIFIER = REPO_ROOT / "tools" / "verify_research_claims.py"


def make_ledger(source="results/sample.jsonl", expected_successes=1):
    return {
        "schema_version": "claims.v1",
        "claims": [
            {
                "claim_id": "TEST-CLAIM-001",
                "status": "supported",
                "statement": "Test statement.",
                "scope": "Synthetic verifier fixture.",
                "limitations": ["Not empirical evidence."],
                "derivations": [
                    {
                        "derivation_id": "test-binary-rate",
                        "kind": "binary_rate",
                        "source": source,
                        "filters": [{"path": "kind", "op": "eq", "value": "target"}],
                        "valid_when": [
                            {
                                "path": "verdict",
                                "op": "not_in",
                                "value": ["ERROR", "PARSE_ERROR", "?"],
                            }
                        ],
                        "success_when": [
                            {"path": "bypass", "op": "eq", "value": True}
                        ],
                        "error_when": [
                            {"path": "verdict", "op": "eq", "value": "ERROR"}
                        ],
                        "expected": {
                            "total_n": 2,
                            "valid_n": 1,
                            "success_n": expected_successes,
                            "error_n": 1,
                            "skipped_n": 0,
                            "rate": float(expected_successes),
                        },
                    }
                ],
            }
        ],
    }


class ResearchClaimVerifierTests(unittest.TestCase):
    def run_verifier(self, root, ledger_path):
        return subprocess.run(
            [
                sys.executable,
                str(VERIFIER),
                "--root",
                str(root),
                "--claims",
                str(ledger_path),
                "--json",
            ],
            capture_output=True,
            text=True,
            check=False,
        )

    def fixture(self, directory, ledger=None):
        root = Path(directory)
        results = root / "results"
        results.mkdir()
        rows = [
            {"kind": "target", "verdict": "STABLE", "bypass": True},
            {"kind": "target", "verdict": "ERROR", "bypass": False},
        ]
        (results / "sample.jsonl").write_text(
            "".join(json.dumps(row) + "\n" for row in rows),
            encoding="utf-8",
        )
        ledger_path = root / "claims.json"
        ledger_path.write_text(
            json.dumps(ledger if ledger is not None else make_ledger()),
            encoding="utf-8",
        )
        return root, ledger_path

    def test_matching_evidence_passes(self):
        with tempfile.TemporaryDirectory() as directory:
            root, ledger_path = self.fixture(directory)
            result = self.run_verifier(root, ledger_path)

        self.assertEqual(result.returncode, 0, result.stderr)
        output = json.loads(result.stdout)
        self.assertTrue(output["verified"])
        observed = output["claims"][0]["derivations"][0]
        self.assertEqual(observed["success_n"], 1)
        self.assertEqual(observed["error_n"], 1)
        self.assertEqual(observed["wilson_95"], [0.2065, 1.0])

    def test_changed_evidence_fails_expected_value(self):
        with tempfile.TemporaryDirectory() as directory:
            root, ledger_path = self.fixture(
                directory,
                ledger=make_ledger(expected_successes=0),
            )
            result = self.run_verifier(root, ledger_path)

        self.assertEqual(result.returncode, 1)
        output = json.loads(result.stdout)
        self.assertFalse(output["verified"])
        self.assertTrue(
            any("success_n expected 0, observed 1" in item for item in output["failures"])
        )

    def test_unknown_claim_field_fails_closed(self):
        ledger = make_ledger()
        ledger["claims"][0]["undeclared"] = True
        with tempfile.TemporaryDirectory() as directory:
            root, ledger_path = self.fixture(directory, ledger=ledger)
            result = self.run_verifier(root, ledger_path)

        self.assertEqual(result.returncode, 2)
        self.assertIn("unknown fields", result.stderr)

    def test_source_outside_results_fails_closed(self):
        ledger = make_ledger(source="../outside.jsonl")
        with tempfile.TemporaryDirectory() as directory:
            root, ledger_path = self.fixture(directory, ledger=ledger)
            result = self.run_verifier(root, ledger_path)

        self.assertEqual(result.returncode, 2)
        self.assertIn("source must be under results/", result.stderr)


if __name__ == "__main__":
    unittest.main()
