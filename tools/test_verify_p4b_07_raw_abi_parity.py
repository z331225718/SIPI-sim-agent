"""Tests for the P4B-07b raw ABI parity verifier."""

from __future__ import annotations

import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT / "tools") not in sys.path:
    sys.path.insert(0, str(ROOT / "tools"))

import verify_p4b_07_raw_abi_parity as GATE


class ParityTests(unittest.TestCase):
    def test_current_parity_is_valid(self) -> None:
        result = GATE.validate(ROOT)
        self.assertTrue(result["valid"])
        self.assertEqual(result["probes"], 4)

    def test_all_probes_parity_in_both_custodies(self) -> None:
        evidence = GATE.load_yaml(GATE.EVIDENCE)
        self.assertTrue(all(evidence["custody_0_parity"].values()))
        self.assertTrue(all(evidence["custody_1_parity"].values()))
        self.assertEqual(set(evidence["custody_0_parity"]), {"init", "single-1024", "single-4096", "multi-1024"})

    def test_observer_is_external_only(self) -> None:
        charter = GATE.load_yaml(GATE.CHARTER)
        self.assertFalse(charter["observer"]["product_code"])
        self.assertEqual(charter["observer"]["kind"], "ctypes_external_only")

    def test_plan_row_present(self) -> None:
        plan_text = GATE.PLAN.read_text(encoding="utf-8")
        self.assertIn("**P4B-07b", plan_text)

    def test_rejects_parity_drift(self) -> None:
        import copy
        import tempfile
        import unittest.mock as mock
        evidence = copy.deepcopy(GATE.load_yaml(GATE.EVIDENCE))
        evidence["custody_0_parity"]["init"] = False
        with tempfile.TemporaryDirectory() as tmp:
            tmp_path = Path(tmp) / "evidence.yaml"
            tmp_path.write_text(GATE.yaml.safe_dump(evidence, sort_keys=False), encoding="utf-8")
            with mock.patch.object(GATE, "EVIDENCE", tmp_path):
                with self.assertRaises(GATE.ParityError):
                    GATE.validate(ROOT)


if __name__ == "__main__":
    unittest.main()
