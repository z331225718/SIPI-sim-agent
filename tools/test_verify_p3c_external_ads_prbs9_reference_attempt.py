"""Negative tests for the rejected external ADS PRBS9 reference trial."""

from __future__ import annotations

import copy
import importlib.util
from pathlib import Path
import unittest
from unittest import mock

import yaml


ROOT = Path(__file__).resolve().parents[1]
SPEC = importlib.util.spec_from_file_location("p3c_ads_attempt", ROOT / "tools/verify_p3c_external_ads_prbs9_reference_attempt.py")
assert SPEC and SPEC.loader
GATE = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(GATE)


class ExternalAdsPrbs9AttemptTests(unittest.TestCase):
    def setUp(self) -> None:
        self.document = yaml.safe_load((ROOT / "docs/baselines/p3c-external-ads-prbs9-reference-attempt.v1.yaml").read_text(encoding="utf-8"))

    def verify(self, document: dict) -> dict:
        return GATE.verify_document(document, hashes=set())

    def test_current_attempt_records_runtime_but_rejects_reference_promotion(self) -> None:
        report = self.verify(self.document)
        self.assertTrue(report["ads_runtime_observed"])
        self.assertFalse(report["reference_contract_match"])
        self.assertFalse(report["external_reference_observed"])
        self.assertFalse(report["release_promoted"])

    def test_source_port_stimulus_and_output_drift_are_rejected(self) -> None:
        document = copy.deepcopy(self.document)
        document["source"]["port_map"]["port_2"] = "rx_minus"
        with self.assertRaisesRegex(GATE.AttemptError, "source_identity_or_port_map_invalid"):
            self.verify(document)
        document = copy.deepcopy(self.document)
        document["stimulus"]["seed_hex"] = 1
        with self.assertRaisesRegex(GATE.AttemptError, "stimulus_invalid"):
            self.verify(document)
        document = copy.deepcopy(self.document)
        document["output"]["ads_samples_inclusive"] = 49056
        with self.assertRaisesRegex(GATE.AttemptError, "output_identity_invalid"):
            self.verify(document)

    def test_edge_floor_and_admission_promotion_are_rejected(self) -> None:
        document = copy.deepcopy(self.document)
        document["contract_result"]["reference_contract_match"] = True
        with self.assertRaisesRegex(GATE.AttemptError, "contract_rejection_invalid"):
            self.verify(document)
        document = copy.deepcopy(self.document)
        document["admission"]["p4b_ami_runtime_invoked"] = True
        with self.assertRaisesRegex(GATE.AttemptError, "admission_gate_drift"):
            self.verify(document)

    def test_external_hash_leak_and_global_gate_drift_are_rejected(self) -> None:
        with self.assertRaisesRegex(GATE.AttemptError, "external_custody_leak"):
            GATE.verify_document(self.document, hashes={self.document["source"]["sha256"]})
        original = GATE.load_yaml

        def drift_contract(path: Path) -> dict:
            if path.name == GATE.CONTRACT.name:
                return {"status": "accepted", "reference": {"external_observed": True}, "admission": {"ads_runtime_invoked": True}}
            return original(path)

        with mock.patch.object(GATE, "load_yaml", side_effect=drift_contract):
            with self.assertRaisesRegex(GATE.AttemptError, "p3c_contract_promotion_drift"):
                self.verify(self.document)

        def drift_p4b(path: Path) -> dict:
            if path.name == GATE.P4B.name:
                return {"status": "admitted"}
            return original(path)

        with mock.patch.object(GATE, "load_yaml", side_effect=drift_p4b):
            with self.assertRaisesRegex(GATE.AttemptError, "p4b_runtime_admission_drift"):
                self.verify(self.document)
        invalid_rows = [{"id": "compare", "acceptance_state": "accepted", "blockers": ["metric_profile_semantics_not_implemented"]}]
        with mock.patch.object(GATE.json, "loads", return_value={"rows": invalid_rows}):
            with self.assertRaisesRegex(GATE.AttemptError, "release_compare_metric_gate_drift"):
                self.verify(self.document)


if __name__ == "__main__":
    unittest.main()
