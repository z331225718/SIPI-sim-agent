from __future__ import annotations

import copy
import importlib.util
from pathlib import Path
import unittest
from unittest import mock

import yaml


ROOT = Path(__file__).resolve().parents[1]
SPEC = importlib.util.spec_from_file_location("p3c_prbs9_artifact_cli", ROOT / "tools/verify_p3c_prbs9_metric_artifact_cli.py")
assert SPEC and SPEC.loader
GATE = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(GATE)


class Prbs9ArtifactCliTests(unittest.TestCase):
    def setUp(self) -> None:
        self.document = yaml.safe_load((ROOT / "docs/baselines/p3c-prbs9-metric-artifact-cli.v1.yaml").read_text(encoding="utf-8"))

    def test_route_stays_non_acceptance(self) -> None:
        report = GATE.verify_document(self.document)
        self.assertFalse(report["release_promoted"])

    def test_boundary_and_admission_drift_are_rejected(self) -> None:
        document = copy.deepcopy(self.document)
        document["artifact_boundary"]["waveform_payload_exact_bytes"] = 392447
        with self.assertRaisesRegex(GATE.ArtifactCliError, "artifact_boundary_drift"):
            GATE.verify_document(document)
        document = copy.deepcopy(self.document)
        document["admission"]["accepted_receiver"] = True
        with self.assertRaisesRegex(GATE.ArtifactCliError, "admission_gate_drift"):
            GATE.verify_document(document)

    def test_source_and_publication_drift_are_rejected(self) -> None:
        with mock.patch.object(GATE, "source", return_value=""):
            with self.assertRaisesRegex(GATE.ArtifactCliError, "implementation_binding_drift"):
                GATE.verify_document(self.document)
        with mock.patch.object(GATE.json, "loads", return_value={"rows": []}):
            with self.assertRaisesRegex(GATE.ArtifactCliError, "publication_gate_drift"):
                GATE.verify_document(self.document)


if __name__ == "__main__":
    unittest.main()
