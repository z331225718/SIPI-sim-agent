"""Tests for the P5-04h noise-PDF build stage verifier."""

from __future__ import annotations

import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT / "tools") not in sys.path:
    sys.path.insert(0, str(ROOT / "tools"))

import verify_p5_04h_build_noise_pdf as GATE


class NoisePdfStageTests(unittest.TestCase):
    def test_current_charter_is_valid(self) -> None:
        result = GATE.validate(ROOT)
        self.assertTrue(result["valid"])

    def test_source_map_has_four_mappings(self) -> None:
        source_map = GATE.load_yaml(GATE.SOURCE_MAP)
        self.assertEqual(len(source_map["mapping"]), 4)
        self.assertIn("search_r480_mmse / MMSE path", source_map["not_ported"])

    def test_policies_present_in_sources(self) -> None:
        self.assertIn(GATE.POLICY, GATE.SOURCE.read_text(encoding="utf-8"))
        self.assertIn(GATE.ERF_POLICY, GATE.ERF_SOURCE.read_text(encoding="utf-8"))

    def test_plan_row_present(self) -> None:
        self.assertIn("**P5-04h", GATE.PLAN.read_text(encoding="utf-8"))

    def test_evidence_four_cases_ber_q_matched(self) -> None:
        evidence = GATE.load_yaml(GATE.EVIDENCE)
        self.assertEqual(len(evidence["entries"]), 4)
        for entry in evidence["entries"]:
            self.assertTrue(entry["matched"])
            self.assertLess(abs(entry["ber_q_product"] - entry["ber_q_oracle"]), 1e-11)

    def test_rejects_mmse_admission(self) -> None:
        import copy
        import tempfile
        import unittest.mock as mock
        charter = copy.deepcopy(GATE.load_yaml(GATE.CHARTER))
        charter["admission"]["mmse_path"] = True
        with tempfile.TemporaryDirectory() as tmp:
            tmp_path = Path(tmp) / "charter.yaml"
            tmp_path.write_text(GATE.yaml.safe_dump(charter, sort_keys=False), encoding="utf-8")
            with mock.patch.object(GATE, "CHARTER", tmp_path):
                with self.assertRaises(GATE.NoisePdfStageError):
                    GATE.validate(ROOT)


if __name__ == "__main__":
    unittest.main()
