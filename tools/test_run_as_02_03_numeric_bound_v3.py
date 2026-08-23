from __future__ import annotations

import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from tools import run_as_02_03_numeric_bound_v3 as runner


class RunnerBootstrapTests(unittest.TestCase):
    def test_candidate_identity_is_explicit_not_self_referential(self):
        source = Path(runner.__file__).read_text(encoding="utf-8")
        self.assertNotIn("CANDIDATE_COMMIT =", source)
        self.assertIn("--candidate-commit", source)
        self.assertIn("candidate commit/tree binding mismatch", source)
        self.assertIn("candidate archive SHA binding mismatch", source)

    def test_wrapper_policy_is_fail_closed(self):
        self.assertTrue(runner.WRAPPER_POLICY["clear_inherited_rustc_wrapper"])
        self.assertTrue(runner.WRAPPER_POLICY["clear_inherited_rustc_workspace_wrapper"])
        self.assertEqual(runner.WRAPPER_POLICY["rustc_wrapper"], "unset")
        self.assertEqual(runner.WRAPPER_POLICY["rustc_workspace_wrapper"], "unset")


if __name__ == "__main__":
    unittest.main()
