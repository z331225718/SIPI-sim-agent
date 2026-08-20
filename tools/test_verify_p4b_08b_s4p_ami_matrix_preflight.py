"""Tests for the P4B-08b S4P-to-AMI matrix preflight verifier."""

from __future__ import annotations

import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT / "tools") not in sys.path:
    sys.path.insert(0, str(ROOT / "tools"))

import verify_p4b_08b_s4p_ami_matrix_preflight as GATE


class MatrixPreflightTests(unittest.TestCase):
    def test_current_preflight_is_valid(self) -> None:
        result = GATE.validate(ROOT)
        self.assertTrue(result["valid"])

    def test_port_mapping_unverified(self) -> None:
        charter = GATE.load_yaml(GATE.CHARTER)
        self.assertEqual(charter["decision_surface"]["port_mapping"], "unverified_requires_netlist")
        self.assertEqual(charter["admission"]["ami_matrix_construction"], "prohibited_without_port_mapping")

    def test_ibis_facts_recorded(self) -> None:
        charter = GATE.load_yaml(GATE.CHARTER)
        self.assertEqual(charter["observed_facts"]["diff_pairs"], ["1-2", "3-4"])
        self.assertEqual(charter["observed_facts"]["models"], ["pcie_tx", "pcie_rx"])

    def test_plan_row_present(self) -> None:
        plan_text = GATE.PLAN.read_text(encoding="utf-8")
        self.assertIn("**P4B-08b", plan_text)

    def test_rejects_matrix_admission(self) -> None:
        import copy
        import tempfile
        import unittest.mock as mock
        charter = copy.deepcopy(GATE.load_yaml(GATE.CHARTER))
        charter["admission"]["ami_matrix_construction"] = "admitted"
        with tempfile.TemporaryDirectory() as tmp:
            tmp_path = Path(tmp) / "charter.yaml"
            tmp_path.write_text(GATE.yaml.safe_dump(charter, sort_keys=False), encoding="utf-8")
            with mock.patch.object(GATE, "CHARTER", tmp_path):
                with self.assertRaises(GATE.MatrixPreflightError):
                    GATE.validate(ROOT)


if __name__ == "__main__":
    unittest.main()
