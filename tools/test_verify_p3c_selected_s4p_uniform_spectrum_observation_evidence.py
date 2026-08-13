"""Mutation tests for selected-S4P uniform-spectrum observation evidence."""

from __future__ import annotations

import copy
import importlib.util
from pathlib import Path
import unittest

import yaml


ROOT = Path(__file__).resolve().parents[1]
SPEC = importlib.util.spec_from_file_location(
    "p3c_uniform_spectrum_observation",
    ROOT / "tools" / "verify_p3c_selected_s4p_uniform_spectrum_observation_evidence.py",
)
assert SPEC and SPEC.loader
GATE = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(GATE)


class UniformSpectrumObservationEvidenceTests(unittest.TestCase):
    def setUp(self) -> None:
        self.document = yaml.safe_load(
            (ROOT / "docs" / "baselines" / "p3c-selected-s4p-uniform-spectrum-observation-evidence.v1.yaml").read_text(encoding="utf-8")
        )

    def test_exact_observation_passes_without_current_source_check(self) -> None:
        self.assertEqual(
            GATE.verify_document(self.document),
            {"valid": True, "interpolation_admitted": True, "release_admitted": False},
        )

    def test_custody_outcome_and_gate_mutations_reject(self) -> None:
        mutations = (
            lambda value: value["external_observation"].__setitem__("fresh_custody_runs", 1),
            lambda value: value["external_observation"]["manifest_sha256s"].__setitem__(1, value["external_observation"]["manifest_sha256s"][0]),
            lambda value: value["external_observation"]["outcome"].__setitem__("spectrum_sha256", "0" * 64),
            lambda value: value["admission"].__setitem__("ifft_implemented", True),
            lambda value: value["admission"].__setitem__("candidate_waveform_generated", True),
            lambda value: value["admission"].__setitem__("release_ledger_promoted", True),
            lambda value: value["blockers"].remove("raw_impulse_ifft_policy_not_implemented"),
        )
        for mutate in mutations:
            altered = copy.deepcopy(self.document)
            mutate(altered)
            with self.assertRaises(GATE.VerificationError):
                GATE.verify_document(altered)


if __name__ == "__main__":
    unittest.main()
