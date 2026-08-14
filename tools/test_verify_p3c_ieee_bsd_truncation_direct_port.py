"""Mutation tests for the fixed IEEE BSD truncation direct-port boundary."""

from __future__ import annotations

import copy
from pathlib import Path
import unittest

import yaml

from verify_p3c_ieee_bsd_truncation_direct_port import DirectPortError, verify_document


ROOT = Path(__file__).resolve().parents[1]
BASELINE = ROOT / "docs" / "baselines" / "p3c-ieee-bsd-truncation-direct-port.v1.yaml"


class TruncationDirectPortTests(unittest.TestCase):
    def setUp(self) -> None:
        self.document = yaml.safe_load(BASELINE.read_text(encoding="utf-8"))

    def rejects(self, mutate) -> None:
        document = copy.deepcopy(self.document)
        mutate(document)
        with self.assertRaises(DirectPortError):
            verify_document(document)

    def test_baseline_is_valid(self) -> None:
        self.assertTrue(verify_document(self.document)["valid"])

    def test_policy_or_delay_mutation_rejects(self) -> None:
        self.rejects(lambda value: value["policy"].__setitem__("threshold", 1.0e-2))
        self.rejects(lambda value: value["policy"].__setitem__("time_shift", "allowed"))

    def test_helper_or_causal_admission_mutation_rejects(self) -> None:
        self.rejects(lambda value: value["source"].__setitem__("excluded_source_objects", []))
        self.rejects(lambda value: value["gates"].__setitem__("causal_impulse_admitted", True))

    def test_convolution_or_release_promotion_rejects(self) -> None:
        self.rejects(lambda value: value["gates"].__setitem__("linear_convolution_implemented", True))
        self.rejects(lambda value: value["gates"].__setitem__("release_ledger_promoted", True))


if __name__ == "__main__":
    unittest.main()
