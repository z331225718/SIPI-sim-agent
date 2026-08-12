from __future__ import annotations

import copy
import importlib.util
from pathlib import Path
import unittest
from unittest import mock

import yaml

ROOT = Path(__file__).resolve().parents[1]
SPEC = importlib.util.spec_from_file_location("p3c_metric_core_v2", ROOT / "tools/verify_p3c_prbs9_metric_core_v2.py")
assert SPEC and SPEC.loader
GATE = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(GATE)


class Prbs9MetricCoreV2Tests(unittest.TestCase):
    def setUp(self) -> None:
        self.document = yaml.safe_load((ROOT / "docs/baselines/p3c-prbs9-metric-core.v2.yaml").read_text(encoding="utf-8"))

    def test_current_metric_core_stays_non_acceptance(self) -> None:
        report = GATE.verify_document(self.document)
        self.assertEqual(report["historical_nrmse_core"], "source_drift_preserved")
        self.assertEqual(report["external_reference_binding"], "not_evaluated")
        self.assertFalse(report["release_promoted"])

    def test_semantic_and_admission_drift_are_rejected(self) -> None:
        document = copy.deepcopy(self.document)
        document["profile"]["eye"]["wraparound"] = "allowed"
        with self.assertRaisesRegex(GATE.CoreError, "profile_semantics_drift"):
            GATE.verify_document(document)
        document = copy.deepcopy(self.document)
        document["profile"]["tie"]["tie_mean_removal"] = "allowed"
        with self.assertRaisesRegex(GATE.CoreError, "profile_semantics_drift"):
            GATE.verify_document(document)
        document = copy.deepcopy(self.document)
        document["admission"]["acceptance_ready"] = True
        with self.assertRaisesRegex(GATE.CoreError, "admission_gate_drift"):
            GATE.verify_document(document)

    def test_contract_release_and_implementation_drift_are_rejected(self) -> None:
        with mock.patch.object(GATE, "sha256_file", return_value="0" * 64):
            with self.assertRaisesRegex(GATE.CoreError, "contract_source_drift"):
                GATE.verify_document(self.document)
        with mock.patch.object(GATE.json, "loads", return_value={"rows": [{"id": "compare", "acceptance_state": "accepted", "blockers": []}]}):
            with self.assertRaisesRegex(GATE.CoreError, "release_compare_metric_gate_drift"):
                GATE.verify_document(self.document)
        with mock.patch.object(GATE, "implementation_source", return_value=""):
            with self.assertRaisesRegex(GATE.CoreError, "implementation_binding_drift"):
                GATE.verify_document(self.document)


if __name__ == "__main__":
    unittest.main()
