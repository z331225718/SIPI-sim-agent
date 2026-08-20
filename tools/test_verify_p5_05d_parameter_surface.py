"""Tests for the P5-05d parameter surface stage verifier."""

from __future__ import annotations

import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT / "tools") not in sys.path:
    sys.path.insert(0, str(ROOT / "tools"))

import verify_p5_05d_parameter_surface as GATE


class SurfaceStageTests(unittest.TestCase):
    def test_current_charter_is_valid(self) -> None:
        result = GATE.validate(ROOT)
        self.assertTrue(result["valid"])

    def test_source_map_has_three_mappings(self) -> None:
        source_map = GATE.load_yaml(GATE.SOURCE_MAP)
        self.assertEqual(len(source_map["mapping"]), 3)
        self.assertIn("value consumption / default resolution (P5-02 consumption surface)", source_map["not_ported"])

    def test_policy_present_in_source(self) -> None:
        self.assertIn(GATE.POLICY, GATE.SOURCE.read_text(encoding="utf-8"))

    def test_plan_row_present(self) -> None:
        self.assertIn("**P5-05d", GATE.PLAN.read_text(encoding="utf-8"))

    def test_evidence_surface_counts(self) -> None:
        evidence = GATE.load_yaml(GATE.EVIDENCE)
        xlsx = next(entry for entry in evidence["entries"] if entry["id"] == "xlsx_authorized_config")
        self.assertEqual(xlsx["pairs"], 137)
        self.assertEqual(xlsx["consumed"], 82)
        self.assertEqual(evidence["canonical"]["key_count"], 214)

    def test_rejects_consumption_admission(self) -> None:
        import copy
        import tempfile
        import unittest.mock as mock
        charter = copy.deepcopy(GATE.load_yaml(GATE.CHARTER))
        charter["admission"]["value_consumption"] = True
        with tempfile.TemporaryDirectory() as tmp:
            tmp_path = Path(tmp) / "charter.yaml"
            tmp_path.write_text(GATE.yaml.safe_dump(charter, sort_keys=False), encoding="utf-8")
            with mock.patch.object(GATE, "CHARTER", tmp_path):
                with self.assertRaises(GATE.SurfaceStageError):
                    GATE.validate(ROOT)


if __name__ == "__main__":
    unittest.main()
