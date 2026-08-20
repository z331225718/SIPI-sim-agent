"""Tests for the P5-04n search support stage verifier."""

from __future__ import annotations

import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT / "tools") not in sys.path:
    sys.path.insert(0, str(ROOT / "tools"))

import verify_p5_04n_search_support as GATE


class SearchSupportStageTests(unittest.TestCase):
    def test_current_charter_is_valid(self) -> None:
        result = GATE.validate(ROOT)
        self.assertTrue(result["valid"])

    def test_source_map_has_seven_mappings(self) -> None:
        source_map = GATE.load_yaml(GATE.SOURCE_MAP)
        self.assertEqual(len(source_map["mapping"]), 7)
        self.assertIn("_receiver_noise (bessel/butterworth/raised-cosine chain)", source_map["not_ported"])

    def test_policy_present_in_source(self) -> None:
        self.assertIn(GATE.POLICY, GATE.SOURCE.read_text(encoding="utf-8"))

    def test_plan_row_present(self) -> None:
        self.assertIn("**P5-04n", GATE.PLAN.read_text(encoding="utf-8"))

    def test_evidence_nineteen_cases(self) -> None:
        evidence = GATE.load_yaml(GATE.EVIDENCE)
        self.assertEqual(len(evidence["entries"]), 19)
        self.assertTrue(all(entry["matched"] for entry in evidence["entries"]))

    def test_rejects_receiver_noise_admission(self) -> None:
        import copy
        import tempfile
        import unittest.mock as mock
        charter = copy.deepcopy(GATE.load_yaml(GATE.CHARTER))
        charter["admission"]["receiver_noise"] = True
        with tempfile.TemporaryDirectory() as tmp:
            tmp_path = Path(tmp) / "charter.yaml"
            tmp_path.write_text(GATE.yaml.safe_dump(charter, sort_keys=False), encoding="utf-8")
            with mock.patch.object(GATE, "CHARTER", tmp_path):
                with self.assertRaises(GATE.SearchSupportStageError):
                    GATE.validate(ROOT)


if __name__ == "__main__":
    unittest.main()
