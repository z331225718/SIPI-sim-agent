"""Tests for current-candidate fixed TRAN external evidence."""

from __future__ import annotations

import copy
import importlib.util
import sys
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "tools"))
SPEC = importlib.util.spec_from_file_location(
    "current_tran_evidence", ROOT / "tools" / "verify_tran_rc_pulse_current_external_compare_evidence.py"
)
assert SPEC and SPEC.loader
GATE = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(GATE)


class CurrentTranEvidenceTests(unittest.TestCase):
    def document(self) -> dict:
        return copy.deepcopy(GATE._load(GATE.EVIDENCE))

    def test_current_candidate_evidence_is_bound(self) -> None:
        result = GATE.verify_document(self.document())
        self.assertTrue(result["valid"])
        self.assertEqual(result["evidence_level"], "hash_only_attestation")

    def test_rejects_historical_schema_and_product_drift(self) -> None:
        wrong_schema = self.document()
        wrong_schema["schema"] = GATE.HISTORICAL_SCHEMA
        with self.assertRaises(GATE.EvidenceError):
            GATE.verify_document(wrong_schema)
        drift = self.document()
        drift["product"]["source_trees"]["sipi-tran"] = "0" * 40
        with self.assertRaises(GATE.EvidenceError):
            GATE.verify_document(drift)


if __name__ == "__main__":
    unittest.main()
