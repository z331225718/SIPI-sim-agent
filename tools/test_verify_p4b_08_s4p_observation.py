"""Tests for the P4B-08a S4P observation verifier."""

from __future__ import annotations

import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT / "tools") not in sys.path:
    sys.path.insert(0, str(ROOT / "tools"))

import verify_p4b_08_s4p_observation as GATE


class S4PObservationTests(unittest.TestCase):
    def test_current_observation_is_valid(self) -> None:
        result = GATE.validate(ROOT)
        self.assertTrue(result["valid"])
        self.assertEqual(result["files"], 6)

    def test_record_counts_match_axis(self) -> None:
        evidence = GATE.load_yaml(GATE.EVIDENCE)
        for entry in evidence["files"]:
            if entry["material_id"].startswith("ads-pcie-gen5-s4p-tx"):
                self.assertEqual(entry["record_count"], 10003)
                self.assertEqual(float(entry["last_frequency_hz"]), 1e11)
            else:
                self.assertEqual(entry["record_count"], 8003)
                self.assertEqual(float(entry["last_frequency_hz"]), 8e10)

    def test_hashes_match_registry(self) -> None:
        evidence = GATE.load_yaml(GATE.EVIDENCE)
        registry = GATE.load_yaml(GATE.REGISTRY)
        registered = {m["id"]: m for m in registry["materials"]}
        for entry in evidence["files"]:
            self.assertEqual(entry["sha256"], registered[entry["material_id"]]["sha256"].lower())

    def test_plan_row_present(self) -> None:
        plan_text = GATE.PLAN.read_text(encoding="utf-8")
        self.assertIn("**P4B-08a", plan_text)

    def test_rejects_record_drift(self) -> None:
        import copy
        import tempfile
        import unittest.mock as mock
        evidence = copy.deepcopy(GATE.load_yaml(GATE.EVIDENCE))
        evidence["files"][0]["record_count"] = 1
        with tempfile.TemporaryDirectory() as tmp:
            tmp_path = Path(tmp) / "evidence.yaml"
            tmp_path.write_text(GATE.yaml.safe_dump(evidence, sort_keys=False), encoding="utf-8")
            with mock.patch.object(GATE, "EVIDENCE", tmp_path):
                with self.assertRaises(GATE.S4PObservationError):
                    GATE.validate(ROOT)


if __name__ == "__main__":
    unittest.main()
