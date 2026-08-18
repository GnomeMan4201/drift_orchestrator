from __future__ import annotations

import unittest
from collections import Counter

from tools.check_pyflakes_baseline import normalize_diagnostics, regressions


class PyflakesBaselineTests(unittest.TestCase):
    def test_normalization_ignores_line_and_column_churn(self) -> None:
        counts = normalize_diagnostics(
            [
                "agent.py:9:1: 'thing' imported but unused",
                "agent.py:99:7: 'thing' imported but unused",
            ]
        )
        self.assertEqual(
            counts,
            Counter({"agent.py: 'thing' imported but unused": 2}),
        )

    def test_new_diagnostic_class_is_regression(self) -> None:
        baseline = Counter({"agent.py: old warning": 1})
        current = Counter({"agent.py: old warning": 1, "agent.py: new warning": 1})
        self.assertEqual(
            regressions(current, baseline),
            {"agent.py: new warning": (0, 1)},
        )

    def test_increased_existing_diagnostic_count_is_regression(self) -> None:
        baseline = Counter({"agent.py: warning": 1})
        current = Counter({"agent.py: warning": 2})
        self.assertEqual(
            regressions(current, baseline),
            {"agent.py: warning": (1, 2)},
        )

    def test_debt_reduction_is_allowed(self) -> None:
        baseline = Counter({"agent.py: warning": 2})
        current = Counter({"agent.py: warning": 1})
        self.assertEqual(regressions(current, baseline), {})


if __name__ == "__main__":
    unittest.main()
