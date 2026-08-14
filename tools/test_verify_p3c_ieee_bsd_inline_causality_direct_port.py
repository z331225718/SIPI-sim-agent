"""Mutation tests for the IEEE BSD bounded inline-causality direct port."""

from __future__ import annotations

import copy
from pathlib import Path
import unittest

import yaml

from verify_p3c_ieee_bsd_inline_causality_direct_port import DirectPortError, verify_document


ROOT = Path(__file__).resolve().parents[1]
BASELINE = ROOT / "docs" / "baselines" / "p3c-ieee-bsd-inline-causality-direct-port.v1.yaml"


class InlineCausalityDirectPortTests(unittest.TestCase):
    def setUp(self) -> None:
        self.document = yaml.safe_load(BASELINE.read_text(encoding="utf-8"))

    def rejects(self, mutate) -> None:
        document = copy.deepcopy(self.document)
        mutate(document)
        with self.assertRaises(DirectPortError):
            verify_document(document)

    def test_baseline_is_valid(self) -> None:
        self.assertTrue(verify_document(self.document)["valid"])

    def test_policy_or_unbounded_mutation_rejects(self) -> None:
        self.rejects(lambda value: value["policy"].__setitem__("maximum_iterations", 0))
        self.rejects(lambda value: value["policy"].__setitem__("relative_tolerance", 0.01))

    def test_helper_or_causal_admission_mutation_rejects(self) -> None:
        self.rejects(lambda value: value["source"]["excluded_source_objects"].clear())
        self.rejects(lambda value: value["gates"].__setitem__("causal_impulse_admitted", True))

    def test_external_or_release_promotion_rejects(self) -> None:
        self.rejects(lambda value: value["gates"].__setitem__("external_selected_causality_admitted", True))
        self.rejects(lambda value: value["gates"].__setitem__("release_ledger_promoted", True))


if __name__ == "__main__":
    unittest.main()
