"""Tests for the P5-06a MATLAB oracle first-run verifier."""

from __future__ import annotations

import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT / "tools") not in sys.path:
    sys.path.insert(0, str(ROOT / "tools"))

import verify_p5_06a_matlab_oracle_first_run as GATE


class OracleFirstRunTests(unittest.TestCase):
    def test_current_evidence_is_valid(self) -> None:
        result = GATE.validate(ROOT)
        self.assertTrue(result["valid"])

    def test_outputs_hash_bound(self) -> None:
        evidence = GATE.load_yaml(GATE.EVIDENCE)
        for name, digest in evidence["output_file_hashes"].items():
            self.assertEqual(len(digest), 64, name)

    def test_plan_row_present(self) -> None:
        plan_text = GATE.PLAN.read_text(encoding="utf-8")
        self.assertIn("**P5-06a", plan_text)

    def test_rejects_status_drift(self) -> None:
        import copy
        import tempfile
        import unittest.mock as mock
        evidence = copy.deepcopy(GATE.load_yaml(GATE.EVIDENCE))
        evidence["status"] = "failed"
        with tempfile.TemporaryDirectory() as tmp:
            tmp_path = Path(tmp) / "evidence.yaml"
            tmp_path.write_text(GATE.yaml.safe_dump(evidence, sort_keys=False), encoding="utf-8")
            with mock.patch.object(GATE, "EVIDENCE", tmp_path):
                with self.assertRaises(GATE.OracleFirstRunError):
                    GATE.validate(ROOT)


if __name__ == "__main__":
    unittest.main()
