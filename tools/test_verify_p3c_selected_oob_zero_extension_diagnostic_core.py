"""Mutation tests for the selected OOB zero-extension diagnostic core."""

from __future__ import annotations

import copy
from pathlib import Path
import unittest

import yaml

from verify_p3c_selected_oob_zero_extension_diagnostic_core import VerificationError, verify_document


ROOT = Path(__file__).resolve().parents[1]
BASELINE = ROOT / "docs/baselines/p3c-selected-oob-zero-extension-diagnostic-core.v1.yaml"


class OobZeroExtensionDiagnosticTests(unittest.TestCase):
    def setUp(self) -> None:
        self.document = yaml.safe_load(BASELINE.read_text(encoding="utf-8"))

    def rejects(self, mutate) -> None:
        document = copy.deepcopy(self.document)
        mutate(document)
        with self.assertRaises(VerificationError):
            verify_document(document)

    def test_baseline_is_non_promoting(self) -> None:
        result = verify_document(self.document)
        self.assertTrue(result["valid"])
        self.assertFalse(result["external_observation"])

    def test_cutoff_and_policy_mutations_reject(self) -> None:
        self.rejects(lambda value: value["profile"].__setitem__("first_zeroed_bin_index", 2000))
        self.rejects(lambda value: value["profile"].__setitem__("caller_configuration", "present"))
        self.rejects(lambda value: value["prohibitions"].remove("taper"))

    def test_acceptance_or_observation_promotion_rejects(self) -> None:
        self.rejects(lambda value: value["admission"].__setitem__("oob_extension_sensitivity_observed", True))
        self.rejects(lambda value: value["admission"].__setitem__("selected_highloss_waveform_only_profile_accepted", True))


if __name__ == "__main__":
    unittest.main()
