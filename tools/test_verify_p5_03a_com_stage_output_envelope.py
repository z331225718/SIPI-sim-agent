"""Tests for the P5-03a stage-output envelope verifier."""

from __future__ import annotations

import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT / "tools") not in sys.path:
    sys.path.insert(0, str(ROOT / "tools"))

import verify_p5_03a_com_stage_output_envelope as GATE


class EnvelopeTests(unittest.TestCase):
    def test_current_charter_is_valid(self) -> None:
        result = GATE.validate(ROOT)
        self.assertTrue(result["valid"])

    def test_envelope_matches_observed_surface(self) -> None:
        charter = GATE.load_yaml(GATE.CHARTER)
        self.assertEqual(charter["envelope"]["output_metrics"], "fourteen_observed_keys")
        self.assertEqual(charter["envelope"]["network_roles"], ["THRU", "FEXT1", "NEXT1"])

    def test_source_exists_with_policy(self) -> None:
        self.assertTrue(GATE.SOURCE.is_file())
        self.assertIn(GATE.POLICY, GATE.SOURCE.read_text(encoding="utf-8"))

    def test_plan_row_present(self) -> None:
        plan_text = GATE.PLAN.read_text(encoding="utf-8")
        self.assertIn("**P5-03a", plan_text)

    def test_rejects_computation_admission(self) -> None:
        import copy
        import tempfile
        import unittest.mock as mock
        charter = copy.deepcopy(GATE.load_yaml(GATE.CHARTER))
        charter["admission"]["computation"] = True
        with tempfile.TemporaryDirectory() as tmp:
            tmp_path = Path(tmp) / "charter.yaml"
            tmp_path.write_text(GATE.yaml.safe_dump(charter, sort_keys=False), encoding="utf-8")
            with mock.patch.object(GATE, "CHARTER", tmp_path):
                with self.assertRaises(GATE.EnvelopeError):
                    GATE.validate(ROOT)


if __name__ == "__main__":
    unittest.main()
