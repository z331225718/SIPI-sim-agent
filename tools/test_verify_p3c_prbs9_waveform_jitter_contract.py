"""Negative tests for the owner-confirmed PRBS9 metric contract."""

from __future__ import annotations

import copy
import importlib.util
from pathlib import Path
import unittest
from unittest import mock

import yaml


ROOT = Path(__file__).resolve().parents[1]
SPEC = importlib.util.spec_from_file_location("p3c_prbs9_contract", ROOT / "tools/verify_p3c_prbs9_waveform_jitter_contract.py")
assert SPEC and SPEC.loader
GATE = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(GATE)


class Prbs9WaveformJitterContractTests(unittest.TestCase):
    def setUp(self) -> None:
        self.document = yaml.safe_load((ROOT / "docs/baselines/p3c-prbs9-waveform-jitter-contract.v1.yaml").read_text(encoding="utf-8"))

    def verify(self, document: dict) -> dict:
        return GATE.verify_document(document)

    def test_current_contract_is_metric_ready_but_not_accepted(self) -> None:
        report = self.verify(self.document)
        self.assertTrue(report["metric_semantics_ready"])
        self.assertFalse(report["acceptance_ready"])
        self.assertFalse(report["runtime_invoked"])
        self.assertFalse(report["external_reference_observed"])

    def test_sequence_and_waveform_metric_drift_are_rejected(self) -> None:
        document = copy.deepcopy(self.document)
        document["stimulus"]["prbs"]["initial_state_hex"] = 1
        with self.assertRaisesRegex(GATE.ContractError, "metric_contract_drift"):
            self.verify(document)
        document = copy.deepcopy(self.document)
        document["waveform_compare"]["alignment"] = "allowed"
        with self.assertRaisesRegex(GATE.ContractError, "metric_contract_drift"):
            self.verify(document)
        document = copy.deepcopy(self.document)
        document["eye"]["cdr"] = "used"
        with self.assertRaisesRegex(GATE.ContractError, "metric_contract_drift"):
            self.verify(document)
        document = copy.deepcopy(self.document)
        document["jitter"]["tie_mean_removal"] = "allowed"
        with self.assertRaisesRegex(GATE.ContractError, "metric_contract_drift"):
            self.verify(document)

    def test_admission_and_reference_promotion_are_rejected(self) -> None:
        document = copy.deepcopy(self.document)
        document["admission"]["ami_runtime_invoked"] = True
        with self.assertRaisesRegex(GATE.ContractError, "metric_contract_drift"):
            self.verify(document)
        document = copy.deepcopy(self.document)
        document["reference"]["external_observed"] = True
        with self.assertRaisesRegex(GATE.ContractError, "metric_contract_drift"):
            self.verify(document)

    def test_period_and_external_gate_drift_are_rejected(self) -> None:
        with mock.patch.object(GATE, "generated_period", return_value="0" * 511):
            with self.assertRaisesRegex(GATE.ContractError, "prbs9_period_hash_mismatch"):
                self.verify(self.document)
        with mock.patch.object(GATE, "load_yaml", return_value={"status": "admitted"}):
            with self.assertRaisesRegex(GATE.ContractError, "historical_preflight_drift"):
                self.verify(self.document)

        original_load_yaml = GATE.load_yaml

        def p4b_only_drift(path: Path) -> dict:
            if path.name == GATE.P4B.name:
                return {"status": "admitted"}
            return original_load_yaml(path)

        with mock.patch.object(GATE, "load_yaml", side_effect=p4b_only_drift):
            with self.assertRaisesRegex(GATE.ContractError, "p4b_runtime_admission_drift"):
                self.verify(self.document)

    def test_release_compare_gate_drift_is_rejected(self) -> None:
        invalid_rows = [{"id": "compare", "acceptance_state": "accepted", "blockers": ["metric_profile_semantics_not_implemented"]}]
        with mock.patch.object(GATE.json, "loads", return_value={"rows": invalid_rows}):
            with self.assertRaisesRegex(GATE.ContractError, "release_compare_metric_gate_drift"):
                self.verify(self.document)


if __name__ == "__main__":
    unittest.main()
