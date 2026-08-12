"""Negative tests for the narrow P3C ADS source-edge amendment."""

from __future__ import annotations

import copy
import importlib.util
from pathlib import Path
import unittest
from unittest import mock

import yaml


ROOT = Path(__file__).resolve().parents[1]
SPEC = importlib.util.spec_from_file_location("p3c_prbs9_v2", ROOT / "tools/verify_p3c_prbs9_waveform_jitter_contract_v2.py")
assert SPEC and SPEC.loader
GATE = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(GATE)


class Prbs9WaveformJitterContractV2Tests(unittest.TestCase):
    def setUp(self) -> None:
        self.document = yaml.safe_load((ROOT / "docs/baselines/p3c-prbs9-waveform-jitter-contract.v2.yaml").read_text(encoding="utf-8"))

    def test_current_amendment_is_narrow_and_not_accepted(self) -> None:
        report = GATE.verify_document(self.document)
        self.assertEqual(report["source_edge_seconds"], 1.0e-16)
        self.assertFalse(report["acceptance_ready"])
        self.assertFalse(report["external_reference_observed"])

    def test_edge_and_existing_metric_semantics_drift_are_rejected(self) -> None:
        document = copy.deepcopy(self.document)
        document["stimulus"]["transition"]["rise_time_seconds"] = 0.0
        with self.assertRaisesRegex(GATE.ContractV2Error, "contract_v2_drift"):
            GATE.verify_document(document)
        document = copy.deepcopy(self.document)
        document["stimulus"]["transition"]["edge_shape_code"] = 1
        with self.assertRaisesRegex(GATE.ContractV2Error, "contract_v2_drift"):
            GATE.verify_document(document)
        document = copy.deepcopy(self.document)
        document["waveform_compare"]["relative_rms_error_limit"] = 0.02
        with self.assertRaisesRegex(GATE.ContractV2Error, "contract_v2_drift"):
            GATE.verify_document(document)
        with mock.patch.object(GATE, "digest", return_value=GATE.POLICY_SHA256):
            with self.assertRaisesRegex(GATE.ContractV2Error, "unauthorized_semantic_diff"):
                GATE.verify_document(document)

    def test_superseded_contract_and_external_promotion_are_rejected(self) -> None:
        document = copy.deepcopy(self.document)
        document["admission"]["external_reference_observed"] = True
        with self.assertRaisesRegex(GATE.ContractV2Error, "contract_v2_drift"):
            GATE.verify_document(document)
        with mock.patch.object(GATE, "sha256_file", return_value="0" * 64):
            with self.assertRaisesRegex(GATE.ContractV2Error, "superseded_contract_source_drift"):
                GATE.verify_document(self.document)

    def test_p4b_and_release_gate_drift_are_rejected(self) -> None:
        original = GATE.load_yaml

        def p4b_drift(path: Path):
            if path.name == GATE.P4B.name:
                return {"status": "admitted"}
            return original(path)

        with mock.patch.object(GATE, "load_yaml", side_effect=p4b_drift):
            with self.assertRaisesRegex(GATE.ContractV2Error, "p4b_runtime_admission_drift"):
                GATE.verify_document(self.document)
        with mock.patch.object(GATE.json, "loads", return_value={"rows": [{"id": "compare", "acceptance_state": "accepted", "blockers": []}]}):
            with self.assertRaisesRegex(GATE.ContractV2Error, "release_compare_metric_gate_drift"):
                GATE.verify_document(self.document)


if __name__ == "__main__":
    unittest.main()
