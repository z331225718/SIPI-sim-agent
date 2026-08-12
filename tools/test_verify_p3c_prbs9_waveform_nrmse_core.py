from __future__ import annotations

import copy
import importlib.util
from pathlib import Path
import unittest
from unittest import mock

import yaml

ROOT = Path(__file__).resolve().parents[1]
SPEC = importlib.util.spec_from_file_location("p3c_nrmse_core", ROOT / "tools/verify_p3c_prbs9_waveform_nrmse_core.py")
assert SPEC and SPEC.loader
GATE = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(GATE)


class Prbs9WaveformNrmseCoreTests(unittest.TestCase):
    def setUp(self) -> None:
        self.document = yaml.safe_load((ROOT / "docs/baselines/p3c-prbs9-waveform-nrmse-core.v1.yaml").read_text(encoding="utf-8"))

    def test_current_core_is_not_profile_acceptance(self) -> None:
        report = GATE.verify_document(self.document)
        self.assertEqual(report["external_reference_binding"], "not_evaluated")
        self.assertFalse(report["release_promoted"])

    def test_metric_and_admission_drift_are_rejected(self) -> None:
        document = copy.deepcopy(self.document)
        document["profile"]["alignment"] = "allowed"
        with self.assertRaisesRegex(GATE.CoreError, "profile_semantics_drift"):
            GATE.verify_document(document)
        document = copy.deepcopy(self.document)
        document["admission"]["acceptance_ready"] = True
        with self.assertRaisesRegex(GATE.CoreError, "admission_gate_drift"):
            GATE.verify_document(document)

    def test_contract_and_release_drift_are_rejected(self) -> None:
        with mock.patch.object(GATE, "sha256_file", return_value="0" * 64):
            with self.assertRaisesRegex(GATE.CoreError, "contract_source_drift"):
                GATE.verify_document(self.document)
        with mock.patch.object(GATE.json, "loads", return_value={"rows": [{"id": "compare", "acceptance_state": "accepted", "blockers": []}]}):
            with self.assertRaisesRegex(GATE.CoreError, "release_compare_metric_gate_drift"):
                GATE.verify_document(self.document)

    def test_implementation_binding_drift_is_rejected(self) -> None:
        with mock.patch.object(GATE, "implementation_source", return_value=""):
            with self.assertRaisesRegex(GATE.CoreError, "implementation_binding_drift"):
                GATE.verify_document(self.document)


if __name__ == "__main__":
    unittest.main()
