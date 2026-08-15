"""Tests for current-candidate fixed TRAN external evidence."""

from __future__ import annotations

import copy
import importlib.util
import sys
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "tools"))
def load_gate(name: str, filename: str):
    spec = importlib.util.spec_from_file_location(name, ROOT / "tools" / filename)
    assert spec and spec.loader
    gate = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(gate)
    return gate


GATE_V1 = load_gate("current_tran_evidence_v1", "verify_tran_rc_pulse_current_external_compare_evidence.py")
GATE_V2 = load_gate("current_tran_evidence_v2", "verify_tran_rc_pulse_current_external_compare_evidence_v2.py")
GATE_V3 = load_gate("current_tran_evidence_v3", "verify_tran_rc_pulse_current_external_compare_evidence_v3.py")


class CurrentTranEvidenceTests(unittest.TestCase):
    def document(self, gate) -> dict:
        return copy.deepcopy(gate._load(gate.EVIDENCE))

    def test_prior_current_evidence_remains_drifted(self) -> None:
        with self.assertRaisesRegex(GATE_V1.EvidenceError, "evidence_product_source_drift"):
            GATE_V1.verify_document(self.document(GATE_V1))

    def test_v2_current_candidate_evidence_is_historical_after_lock_drift(self) -> None:
        with self.assertRaisesRegex(GATE_V2.EvidenceError, "evidence_product_source_drift"):
            GATE_V2.verify_document(self.document(GATE_V2))

    def test_rejects_historical_schema_and_product_drift(self) -> None:
        wrong_schema = self.document(GATE_V2)
        wrong_schema["schema"] = GATE_V2.HISTORICAL_SCHEMA
        with self.assertRaises(GATE_V2.EvidenceError):
            GATE_V2.verify_document(wrong_schema)
        drift = self.document(GATE_V2)
        drift["product"]["source_trees"]["sipi-tran"] = "0" * 40
        with self.assertRaises(GATE_V2.EvidenceError):
            GATE_V2.verify_document(drift)

    def test_v3_current_candidate_evidence_is_valid(self) -> None:
        self.assertTrue(GATE_V3.verify_document(self.document(GATE_V3))["valid"])

    def test_v3_rejects_historical_schema_and_product_drift(self) -> None:
        wrong_schema = self.document(GATE_V3)
        wrong_schema["schema"] = GATE_V3.HISTORICAL_SCHEMA
        with self.assertRaises(GATE_V3.EvidenceError):
            GATE_V3.verify_document(wrong_schema)
        drift = self.document(GATE_V3)
        drift["product"]["cargo_lock_blob"] = "0" * 40
        with self.assertRaises(GATE_V3.EvidenceError):
            GATE_V3.verify_document(drift)


if __name__ == "__main__":
    unittest.main()
