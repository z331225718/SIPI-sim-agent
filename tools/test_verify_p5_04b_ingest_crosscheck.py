"""Tests for the P5-04b ingest cross-check verifier."""

from __future__ import annotations

import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT / "tools") not in sys.path:
    sys.path.insert(0, str(ROOT / "tools"))

import verify_p5_04b_ingest_crosscheck as GATE


class CrosscheckTests(unittest.TestCase):
    def test_current_evidence_is_valid(self) -> None:
        result = GATE.validate(ROOT)
        self.assertTrue(result["valid"])
        self.assertEqual(result["entries"], 3)

    def test_all_deltas_within_tolerance(self) -> None:
        evidence = GATE.load_yaml(GATE.EVIDENCE)
        for entry in evidence["entries"]:
            self.assertLessEqual(abs(entry["delta_db"]), GATE.TOLERANCE_DB, entry["material_id"])

    def test_oracle_values_match_fixture_names(self) -> None:
        evidence = GATE.load_yaml(GATE.EVIDENCE)
        by_id = {e["material_id"]: e for e in evidence["entries"]}
        self.assertEqual(by_id["com-synthetic-thru"]["oracle_sdd21_db"], -10.0)
        self.assertEqual(by_id["com-synthetic-fext"]["oracle_sdd21_db"], -40.0)
        self.assertEqual(by_id["com-synthetic-next"]["oracle_sdd21_db"], -40.0)

    def test_plan_row_present(self) -> None:
        plan_text = GATE.PLAN.read_text(encoding="utf-8")
        self.assertIn("**P5-04b", plan_text)

    def test_rejects_delta_drift(self) -> None:
        import copy
        import tempfile
        import unittest.mock as mock
        evidence = copy.deepcopy(GATE.load_yaml(GATE.EVIDENCE))
        evidence["entries"][0]["delta_db"] = 5.0
        with tempfile.TemporaryDirectory() as tmp:
            tmp_path = Path(tmp) / "evidence.yaml"
            tmp_path.write_text(GATE.yaml.safe_dump(evidence, sort_keys=False), encoding="utf-8")
            with mock.patch.object(GATE, "EVIDENCE", tmp_path):
                with self.assertRaises(GATE.CrosscheckError):
                    GATE.validate(ROOT)


if __name__ == "__main__":
    unittest.main()
