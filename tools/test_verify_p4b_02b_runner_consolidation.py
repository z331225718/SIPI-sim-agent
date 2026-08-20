"""Mutation tests for the P4B-02b runner consolidation gate."""

from __future__ import annotations

import sys
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
if str(ROOT / "tools") not in sys.path:
    sys.path.insert(0, str(ROOT / "tools"))

import verify_p4b_02b_runner_consolidation as GATE


class RunnerConsolidationTests(unittest.TestCase):
    def test_current_inventory_is_valid(self) -> None:
        result = GATE.validate(ROOT)
        self.assertTrue(result["valid"])
        self.assertEqual(result["runner_sources"], 191)
        self.assertEqual(result["cargo_targets"], 1)
        self.assertEqual(result["execution_claim"], "not_executed_by_this_verifier")

    def test_rejects_reintroduced_cargo_test_target(self) -> None:
        text = GATE.CARGO.read_text(encoding="utf-8") + (
            '\n[[test]]\nname = "legacy"\nharness = false\n'
        )
        with self.assertRaisesRegex(GATE.RunnerConsolidationError, "external_test_targets"):
            GATE._validate_cargo(text)

    def test_rejects_missing_dispatcher_arm(self) -> None:
        stems = ["one", "two"]
        text = (
            '#[path = "../../tests/one.rs"]\nmod one;\n'
            '#[path = "../../tests/two.rs"]\nmod two;\n'
            'std::env::var("SIPI_P4B_RUNNER");\n'
            '"one" => one::main,\n_ => {}'
        )
        with self.assertRaisesRegex(GATE.RunnerConsolidationError, "two"):
            GATE._validate_dispatcher(text, stems)

    def test_rejects_legacy_script_test_build(self) -> None:
        text = (
            'os.environ["SIPI_P4B_RUNNER"] = "one"\n'
            'args = ["--test", "one", "--features", "p4b-self-crosscheck"]\n'
        )
        with self.assertRaises(GATE.RunnerConsolidationError):
            GATE._script_runner(text)


if __name__ == "__main__":
    unittest.main()
