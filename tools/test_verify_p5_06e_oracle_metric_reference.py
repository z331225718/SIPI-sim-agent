# -*- coding: utf-8 -*-
"""Tests for the P5-06e COM oracle metric reference binding verifier."""

from __future__ import annotations

import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT / "tools") not in sys.path:
    sys.path.insert(0, str(ROOT / "tools"))

import verify_p5_06e_oracle_metric_reference as GATE


class OracleReferenceTests(unittest.TestCase):
    def test_current_reference_is_valid(self) -> None:
        result = GATE.validate(ROOT)
        self.assertTrue(result["valid"])

    def test_evidence_aggregate_matches_bound(self) -> None:
        reference = GATE.load_yaml(GATE.REFERENCE)
        evidence = GATE.load_yaml(GATE.EVIDENCE)
        aggregate, _cases = GATE.extract_from_evidence(evidence)
        bound = reference["aggregate_reference"]
        for k in GATE.C4_METRICS:
            self.assertEqual(bound[k], aggregate[k], k)

    def test_recomputed_digest_matches_bound(self) -> None:
        reference = GATE.load_yaml(GATE.REFERENCE)
        evidence = GATE.load_yaml(GATE.EVIDENCE)
        aggregate, _cases = GATE.extract_from_evidence(evidence)
        self.assertEqual(GATE.reference_digest(aggregate), reference["aggregate_reference_digest"])

    def test_c4_values_are_finite_positive(self) -> None:
        reference = GATE.load_yaml(GATE.REFERENCE)
        for k in GATE.C4_METRICS:
            v = reference["aggregate_reference"][k]
            self.assertTrue(v > 0 and v == v, k)

    def test_case_references_recorded(self) -> None:
        reference = GATE.load_yaml(GATE.REFERENCE)
        cases = reference["case_references"]
        self.assertGreaterEqual(len(cases), 2)
        for case in cases:
            for k in GATE.C4_METRICS:
                self.assertIn(k, case, f"case {case['case_index']} missing {k}")

    def test_plan_row_present(self) -> None:
        self.assertIn("**P5-06e", GATE.PLAN.read_text(encoding="utf-8"))

    def test_rejects_digest_drift(self) -> None:
        import copy
        import tempfile
        import unittest.mock as mock
        reference = copy.deepcopy(GATE.load_yaml(GATE.REFERENCE))
        reference["aggregate_reference_digest"] = "0" * 64
        with tempfile.TemporaryDirectory() as tmp:
            tmp_path = Path(tmp) / "ref.yaml"
            tmp_path.write_text(GATE.yaml.safe_dump(reference, sort_keys=False), encoding="utf-8")
            with mock.patch.object(GATE, "REFERENCE", tmp_path):
                with self.assertRaises(GATE.OracleReferenceError):
                    GATE.validate(ROOT)


if __name__ == "__main__":
    unittest.main()
