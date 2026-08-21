from __future__ import annotations

import copy
import sys
import tempfile
import unittest
from pathlib import Path
from unittest import mock

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT / "tools") not in sys.path:
    sys.path.insert(0, str(ROOT / "tools"))

import verify_p3c_03_current_semantics_gap as GATE


class P3C03GapTests(unittest.TestCase):
    def test_current_gap_is_valid(self) -> None:
        result = GATE.validate(ROOT)
        self.assertTrue(result["valid"])
        self.assertEqual(result["current_c4_metric_count"], 3)
        self.assertEqual(result["required_metric_count"], 3)
        self.assertFalse(result["td_iln_substitution_allowed"])
        self.assertEqual(result["acceptance_state"], "specified")

    def test_c4_and_required_metric_surfaces_are_distinct(self) -> None:
        document = GATE._load(GATE.EVIDENCE)
        current = [entry["name"] for entry in document["current_c4_surface"]["metrics"]]
        required = [entry["id"] for entry in document["required_contract"]["required_metrics"]]
        self.assertEqual(current, ["COM_dB", "ICN_mV", "ERL"])
        self.assertEqual(required, ["com_db", "erl_db", "td_iln_db"])
        self.assertNotIn("ICN_mV", required)

    def test_rejects_icn_substitution(self) -> None:
        document = copy.deepcopy(GATE._load(GATE.EVIDENCE))
        document["required_contract"]["c4_substitution_guard"]["substitution_allowed"] = True
        with tempfile.TemporaryDirectory() as temporary:
            path = Path(temporary) / "evidence.yaml"
            path.write_text(GATE.yaml.safe_dump(document, sort_keys=False), encoding="utf-8")
            with mock.patch.object(GATE, "EVIDENCE", path):
                with self.assertRaises(GATE.P3C03GapError):
                    GATE.validate(ROOT)

    def test_rejects_release_promotion(self) -> None:
        document = copy.deepcopy(GATE._load(GATE.EVIDENCE))
        document["publication_boundary"]["external_oracle"] = True
        with tempfile.TemporaryDirectory() as temporary:
            path = Path(temporary) / "evidence.yaml"
            path.write_text(GATE.yaml.safe_dump(document, sort_keys=False), encoding="utf-8")
            with mock.patch.object(GATE, "EVIDENCE", path):
                with self.assertRaises(GATE.P3C03GapError):
                    GATE.validate(ROOT)

    def test_rejects_reference_inventory_mutation(self) -> None:
        document = copy.deepcopy(GATE._load(GATE.EVIDENCE))
        document["references"][0]["sha256"] = "0" * 64
        with tempfile.TemporaryDirectory() as temporary:
            path = Path(temporary) / "evidence.yaml"
            path.write_text(GATE.yaml.safe_dump(document, sort_keys=False), encoding="utf-8")
            with mock.patch.object(GATE, "EVIDENCE", path):
                with self.assertRaises(GATE.P3C03GapError):
                    GATE.validate(ROOT)

    def test_requires_unknown_candidate_guard(self) -> None:
        source = GATE.COMPARE_SOURCE.read_text(encoding="utf-8")
        self.assertIn("UnknownCandidateMetric", source)
        self.assertIn("contains_key", source)


if __name__ == "__main__":
    unittest.main()
