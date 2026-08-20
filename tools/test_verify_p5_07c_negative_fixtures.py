"""Tests for the P5-07c negative fixture evidence verifier."""

from __future__ import annotations

import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT / "tools") not in sys.path:
    sys.path.insert(0, str(ROOT / "tools"))

import verify_p5_07c_negative_fixtures as GATE


class NegativeTests(unittest.TestCase):
    def test_current_evidence_is_valid(self) -> None:
        result = GATE.validate(ROOT)
        self.assertTrue(result["valid"])
        self.assertEqual(result["cases"], 10)

    def test_all_cases_rejected(self) -> None:
        evidence = GATE.load_yaml(GATE.EVIDENCE)
        for result in evidence["results"]:
            self.assertTrue(result["rejected"], result["case"])

    def test_plan_row_present(self) -> None:
        plan_text = GATE.PLAN.read_text(encoding="utf-8")
        self.assertIn("**P5-07c", plan_text)

    def test_rejects_unrejected_case(self) -> None:
        import copy
        import tempfile
        import unittest.mock as mock
        evidence = copy.deepcopy(GATE.load_yaml(GATE.EVIDENCE))
        evidence["results"][0]["rejected"] = False
        with tempfile.TemporaryDirectory() as tmp:
            tmp_path = Path(tmp) / "evidence.yaml"
            tmp_path.write_text(GATE.yaml.safe_dump(evidence, sort_keys=False), encoding="utf-8")
            with mock.patch.object(GATE, "EVIDENCE", tmp_path):
                with self.assertRaises(GATE.NegativeError):
                    GATE.validate(ROOT)


if __name__ == "__main__":
    unittest.main()
