from __future__ import annotations

import copy
import importlib.util
import unittest
from pathlib import Path

import yaml


ROOT = Path(__file__).resolve().parents[1]
SPEC = importlib.util.spec_from_file_location(
    "residual_v2_evidence",
    ROOT / "tools/verify_p3c_selected_highloss_residual_diagnostic_v2_observation_evidence.py",
)
assert SPEC and SPEC.loader
VERIFIER = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(VERIFIER)


class ResidualDiagnosticV2EvidenceTests(unittest.TestCase):
    def setUp(self) -> None:
        self.document = yaml.safe_load(
            (ROOT / "docs/baselines/p3c-selected-highloss-residual-diagnostic-v2-observation-evidence.v1.yaml").read_text(encoding="utf-8")
        )

    def test_document_is_current_and_valid(self) -> None:
        self.assertTrue(VERIFIER.verify(self.document, check_source=True)["valid"])

    def test_mutations_fail_closed(self) -> None:
        cases = []
        changed = copy.deepcopy(self.document)
        changed["external_observation"]["periods"][2]["residual_nrmse_bits"] = "0000000000000000"
        cases.append(changed)
        changed = copy.deepcopy(self.document)
        changed["admission"]["selected_highloss_waveform_only_profile_accepted"] = True
        cases.append(changed)
        changed = copy.deepcopy(self.document)
        changed["external_observation"]["source_manifests"][1] = changed["external_observation"]["source_manifests"][0]
        cases.append(changed)
        changed = copy.deepcopy(self.document)
        changed["external_observation"]["source_inventory"]["Cargo.lock"] = "0" * 64
        with self.assertRaises(VERIFIER.VerificationError):
            VERIFIER.verify(changed, check_source=True)
        for document in cases:
            with self.assertRaises(VERIFIER.VerificationError):
                VERIFIER.verify(document, check_source=False)


if __name__ == "__main__":
    unittest.main()
